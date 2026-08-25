import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {BackendClient, DEFAULT_BACKEND_URL} from '../api/client';
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

export interface PullStreamState {
  status: 'idle' | 'pulling' | 'success' | 'failed';
  logs: string[];
  error: string | null;
  image: string | null;
  target: string;
}

export function usePullImageStream() {
  const queryClient = useQueryClient();
  const [state, setState] = useState<PullStreamState>({status: 'idle', logs: [], error: null, image: null, target: 'Local'});
  const abortRef = useRef<AbortController | null>(null);
  const pollRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current != null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  const startPolling = useCallback(
    (image: string, remote: unknown) => {
      stopPolling();
      let offset = 0;
      pollRef.current = window.setInterval(async () => {
        try {
          const res = await fetch(`${DEFAULT_BACKEND_URL}/tools/server/pull/status`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
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
              setState((s) => ({...s, logs: [...s.logs, ...newLines]}));
            }
          }
          if (typeof data.next_offset === 'number') {
            offset = data.next_offset;
          }
          if (data.exit_code != null) {
            stopPolling();
            if (data.exit_code === 0) {
              setState((s) => ({...s, status: 'success', logs: [...s.logs, 'Server pull completed.']}));
            } else {
              setState((s) => ({
                ...s,
                status: 'failed',
                error: data.error || `Server pull failed (exit ${data.exit_code})`,
              }));
            }
            void queryClient.invalidateQueries({queryKey: queryKeys.tools.all});
          }
        } catch {
          // transient network error while polling - keep retrying until terminal state
        }
      }, 3000);
    },
    [queryClient, stopPolling],
  );

  const pull = useCallback(
    async (image: string, {target = 'Local', remote = null}: {target?: string; remote?: unknown} = {}) => {
      stopPolling();
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setState({status: 'pulling', logs: [], error: null, image, target});

      try {
        const response = await fetch(`${DEFAULT_BACKEND_URL}/tools/local/pull`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({image, target, remote}),
          signal: controller.signal,
        });

        if (!response.ok) {
          setState((s) => ({...s, status: 'failed', error: `HTTP ${response.status}`}));
          return;
        }

        const reader = response.body?.getReader();
        if (!reader) {
          setState((s) => ({...s, status: 'failed', error: 'No response body'}));
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
                  setState((s) => ({...s, logs: [...s.logs, data.detail]}));
                } else if (currentEvent === 'complete') {
                  sawComplete = true;
                  if (data.ok) {
                    if (target === 'Server' && data.status === 'pulling') {
                      setState((s) => ({...s, status: 'pulling', logs: [...s.logs, 'Server pull is running in the background.']}));
                      startPolling(image, remote);
                    } else {
                      setState((s) => ({...s, status: 'success'}));
                    }
                    void queryClient.invalidateQueries({queryKey: queryKeys.tools.all});
                  } else {
                    setState((s) => ({...s, status: 'failed', error: data.error || 'Pull failed'}));
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
          setState((s) => {
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
          setState((s) => ({...s, status: 'failed', error: (err as Error).message || 'Stream error'}));
        }
      }
    },
    [queryClient, startPolling, stopPolling],
  );

  const reset = useCallback(() => {
    stopPolling();
    abortRef.current?.abort();
    setState({status: 'idle', logs: [], error: null, image: null, target: 'Local'});
  }, [stopPolling]);

  return {...state, pull, reset};
}
