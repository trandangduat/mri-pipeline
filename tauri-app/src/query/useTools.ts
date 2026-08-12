import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {useMemo} from 'react';
import {useClient} from './useEnvironment';
import type {BackendClient} from '../api/client';
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
