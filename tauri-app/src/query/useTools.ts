import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {BackendClient, DEFAULT_BACKEND_URL} from '../api/client';
import {authenticatedBackendHeaders} from '../api/backendToken';
import {useClient} from './useEnvironment';
import type {RuntimeTarget, ToolImage} from '../types/backend';
import {queryKeys} from './keys';

export function useTools(client: BackendClient, target: RuntimeTarget, selectedTools: Record<string, unknown>) {
  const selectedHash = useMemo(() => JSON.stringify(selectedTools), [selectedTools]);
  return useQuery({
    queryKey: queryKeys.tools.images(target, selectedHash),
    queryFn: () =>
      client.localImageStatus(selectedTools, {
        target,
        remote: target === 'Server' ? undefined : null,
      }),
    enabled: false,
  });
}

export function useRefreshTools(client: BackendClient, target: RuntimeTarget, selectedTools: Record<string, unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      client.localImageStatus(selectedTools, {
        target,
        remote: target === 'Server' ? undefined : null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({queryKey: queryKeys.tools.images(target, JSON.stringify(selectedTools))});
    },
  });
}

export function useLocalImageStatusMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: ({
      selectedTools,
      options,
    }: {
      selectedTools: Record<string, unknown>;
      options: {target?: string; remote?: unknown};
    }) => client.localImageStatus(selectedTools, options),
  });
}

export function useToolImages(client: BackendClient, target: RuntimeTarget, selectedTools: Record<string, unknown>) {
  const toolsQuery = useTools(client, target, selectedTools);
  const refreshTools = useRefreshTools(client, target, selectedTools);
  const images: ToolImage[] = toolsQuery.data?.images || [];
  return {
    images,
    isPending: toolsQuery.isPending,
    error: toolsQuery.data?.error || toolsQuery.error?.message || '',
    refresh: refreshTools.mutateAsync,
    isRefreshing: refreshTools.isPending,
  };
}

export function usePullImage() {
  const client = useClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({image, target = 'Local', remote = null}: {image: string; target?: string; remote?: unknown}) =>
      client.pullImage(image, {target, remote}),
    onSuccess: () => {
      void queryClient.invalidateQueries({queryKey: queryKeys.tools.all});
    },
  });
}

export function useRemoveImage() {
  const client = useClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({image, target = 'Local', remote = null}: {image: string; target?: string; remote?: unknown}) =>
      client.removeImage(image, {target, remote}),
    onSuccess: () => {
      void queryClient.invalidateQueries({queryKey: queryKeys.tools.all});
    },
  });
}

import {useToolsStore, type PullStreamState} from '../stores/toolsStore';
export type {PullStreamState};

let activePullAbortController: AbortController | null = null;
let activePullPollTimer: number | null = null;

function stopPullPolling() {
  if (activePullPollTimer != null) {
    window.clearInterval(activePullPollTimer);
    activePullPollTimer = null;
  }
}

export function usePullImageStream() {
  const queryClient = useQueryClient();
  const pullStreamState = useToolsStore((s) => s.pullStreamState);

  const startPolling = useCallback(
    (image: string, remote: unknown) => {
      stopPullPolling();
      let offset = 0;
      activePullPollTimer = window.setInterval(async () => {
        try {
          const res = await fetch(`${DEFAULT_BACKEND_URL}/tools/server/pull/status`, {
            method: 'POST',
            headers: await authenticatedBackendHeaders({'Content-Type': 'application/json'}),
            body: JSON.stringify({image, remote, log_offset: offset}),
          });
          if (!res.ok) return;
          const data = (await res.json()) as {
            ok?: boolean;
            status?: string;
            exit_code?: number | null;
            error?: string | null;
            log_text?: string;
            next_offset?: number;
          };
          if (!data?.ok) return;
          if (data.log_text) {
            const newLines = data.log_text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
            if (newLines.length > 0) {
              useToolsStore.getState().appendPullLogs(newLines);
            }
          }
          if (typeof data.next_offset === 'number') {
            offset = data.next_offset;
          }
          if (data.exit_code != null) {
            stopPullPolling();
            if (data.exit_code === 0) {
              useToolsStore.getState().setPullStreamState((s) => ({
                status: 'success',
                logs: [...s.logs, 'Server pull completed.'],
              }));
            } else {
              useToolsStore.getState().setPullStreamState({
                status: 'failed',
                error: data.error || `Server pull failed (exit ${data.exit_code})`,
              });
            }
            void queryClient.invalidateQueries({queryKey: queryKeys.tools.all});
          }
        } catch {
          // transient network error while polling - keep retrying until terminal state
        }
      }, 3000);
    },
    [queryClient],
  );

  const pull = useCallback(
    async (image: string, {target = 'Local', remote = null}: {target?: string; remote?: unknown} = {}) => {
      stopPullPolling();
      activePullAbortController?.abort();
      const controller = new AbortController();
      activePullAbortController = controller;
      useToolsStore.getState().setPullStreamState({status: 'pulling', logs: [], error: null, image, target});

      try {
        const response = await fetch(`${DEFAULT_BACKEND_URL}/tools/local/pull`, {
          method: 'POST',
          headers: await authenticatedBackendHeaders({'Content-Type': 'application/json'}),
          body: JSON.stringify({image, target, remote}),
          signal: controller.signal,
        });

        if (!response.ok) {
          useToolsStore.getState().setPullStreamState({status: 'failed', error: `HTTP ${response.status}`});
          return;
        }

        const reader = response.body?.getReader();
        if (!reader) {
          useToolsStore.getState().setPullStreamState({status: 'failed', error: 'No response body'});
          return;
        }

        const decoder = new TextDecoder();
        let buffer = '';
        let currentEvent = '';
        let sawComplete = false;

        while (true) {
          const {done, value} = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, {stream: true});
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (line.startsWith('event: ')) {
              currentEvent = line.slice(7);
            } else if (line.startsWith('data: ') && currentEvent) {
              try {
                const data = JSON.parse(line.slice(6));
                if (currentEvent === 'step' && data.detail) {
                  useToolsStore.getState().appendPullLogs([data.detail]);
                } else if (currentEvent === 'complete') {
                  sawComplete = true;
                  if (data.ok) {
                    if (target === 'Server' && data.status === 'pulling') {
                      useToolsStore.getState().setPullStreamState((s) => ({
                        status: 'pulling',
                        logs: [...s.logs, 'Server pull is running in the background.'],
                      }));
                      startPolling(image, remote);
                    } else {
                      useToolsStore.getState().setPullStreamState({status: 'success'});
                    }
                    void queryClient.invalidateQueries({queryKey: queryKeys.tools.all});
                  } else {
                    useToolsStore.getState().setPullStreamState({status: 'failed', error: data.error || 'Pull failed'});
                  }
                }
                currentEvent = '';
              } catch {
                // skip malformed JSON
              }
            }
          }
        }

        if (!sawComplete) {
          useToolsStore.getState().setPullStreamState((s) => {
            if (s.status !== 'pulling') {
              return s;
            }
            return {
              ...s,
              status: 'failed',
              error: 'Connection to the server was lost during pull. Check your network and try again.',
            };
          });
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          useToolsStore.getState().setPullStreamState({status: 'failed', error: (err as Error).message || 'Stream error'});
        }
      }
    },
    [queryClient, startPolling],
  );

  const reset = useCallback(() => {
    stopPullPolling();
    activePullAbortController?.abort();
    useToolsStore.getState().resetPullStream();
  }, []);

  return {...pullStreamState, pull, reset};
}
