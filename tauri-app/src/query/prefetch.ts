import type {QueryClient} from '@tanstack/react-query';
import {BackendClient, DEFAULT_BACKEND_URL} from '../api/client';
import {queryKeys} from './keys';

export async function prefetchInitialData(
  queryClient: QueryClient,
  client: BackendClient = new BackendClient(DEFAULT_BACKEND_URL),
): Promise<void> {
  await Promise.allSettled([
    queryClient.prefetchQuery({queryKey: queryKeys.metadata(), queryFn: () => client.metadata()}),
    queryClient.prefetchQuery({queryKey: queryKeys.environment.local(), queryFn: () => client.localEnvironment()}),
    queryClient.prefetchQuery({queryKey: queryKeys.jobs.local(), queryFn: () => client.listLocalJobs()}),
  ]);
}
