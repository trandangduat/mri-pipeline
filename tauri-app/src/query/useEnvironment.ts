import {useQuery} from '@tanstack/react-query';
import {BackendClient, DEFAULT_BACKEND_URL} from '../api/client';
import {queryKeys} from './keys';

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

export function useEnvironment() {
  const client = useClient();
  return useQuery({
    queryKey: queryKeys.environment.local(),
    queryFn: () => client.localEnvironment(),
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
