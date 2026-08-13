import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {useCallback, useMemo, useRef, useState} from 'react';
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

  const pull = useCallback(
    async (image: string, {target = 'Local', remote = null}: {target?: string; remote?: unknown} = {}) => {
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
                  if (data.ok) {
                    if (target === 'Server' && data.status === 'pulling') {
                      setState((s) => ({...s, status: 'pulling', logs: [...s.logs, 'Server pull is running in the background.']}));
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
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setState((s) => ({...s, status: 'failed', error: (err as Error).message || 'Stream error'}));
        }
      }
    },
    [queryClient],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState({status: 'idle', logs: [], error: null, image: null, target: 'Local'});
  }, []);

  return {...state, pull, reset};
}
