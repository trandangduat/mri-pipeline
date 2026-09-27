import {useQuery} from '@tanstack/react-query';
import {BackendClient, DEFAULT_BACKEND_URL} from '../api/client';
import {queryKeys} from './keys';

import type {RemotePayload} from '../types/backend';

export function useClient(): BackendClient {
  return new BackendClient(DEFAULT_BACKEND_URL);
}

export function useHealth() {
  const client = useClient();
  return useQuery({
    queryKey: queryKeys.health(),
    queryFn: () => client.health(),
    staleTime: 30_000,
  });
}

export function useEnvironment(enabled: boolean = true) {
  const client = useClient();
  return useQuery({
    queryKey: queryKeys.environment.local(),
    queryFn: () => client.localEnvironment(),
    enabled,
  });
}

export function useRemoteEnvironment(payload: RemotePayload, enabled: boolean = true) {
  const client = useClient();
  const fingerprint = JSON.stringify(payload);
  return useQuery({
    queryKey: queryKeys.remote.environment(fingerprint),
    queryFn: () => client.inspectRemoteEnvironment(payload),
    enabled: enabled && Boolean(payload?.host),
    staleTime: 10_000,
  });
}

export function useMetadata() {
  const client = useClient();
  return useQuery({
    queryKey: queryKeys.metadata(),
    queryFn: () => client.metadata(),
    staleTime: 60_000,
  });
}
