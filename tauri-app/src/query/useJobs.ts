import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {useMemo} from 'react';
import {useClient} from './useEnvironment';
import type {BackendClient} from '../api/client';
import {normalizeJob} from '../jobFormatters';
import {queryKeys} from './keys';

export function useLocalJobs(client: BackendClient) {
  return useQuery({
    queryKey: queryKeys.jobs.local(),
    queryFn: () => client.listLocalJobs(),
    select: (data) => (data.jobs || []).map((job) => normalizeJob(job, 'Local')),
  });
}

export function useStartLocalJob(client: BackendClient) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runRequest: unknown) => client.startLocalJob(runRequest),
    onSuccess: () => {
      void queryClient.invalidateQueries({queryKey: queryKeys.jobs.local()});
    },
  });
}

export function useJobDetails(client: BackendClient, jobId: string | null) {
  return useQuery({
    queryKey: queryKeys.jobs.events(jobId || 'none'),
    queryFn: async () => {
      const [eventsResult, logResult] = await Promise.all([
        client.readLocalEvents(jobId || '').catch(() => null),
        client.readLocalLog(jobId || '', 0, 65536).catch(() => null),
      ]);
      return {
        events: eventsResult?.events || [],
        log: logResult?.text || '',
        nextOffset: logResult?.next_offset ?? 0,
      };
    },
    enabled: Boolean(jobId),
  });
}

export function useJobLogPoll(client: BackendClient, jobId: string | null, offset: number, maxBytes: number) {
  return useQuery({
    queryKey: queryKeys.jobs.log(jobId || 'none', offset, maxBytes),
    queryFn: () => client.readLocalLog(jobId || '', offset, maxBytes),
    enabled: Boolean(jobId),
    refetchInterval: 3_000,
  });
}

export function useLatestJobs(client: BackendClient) {
  const localJobs = useLocalJobs(client);
  const jobs = useMemo(() => localJobs.data || [], [localJobs.data]);
  return {jobs, isPending: localJobs.isPending, refetch: localJobs.refetch};
}

export function useListLocalJobsMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: () => client.listLocalJobs(),
  });
}

export function useReadLocalEventsMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: (jobId: string) => client.readLocalEvents(jobId),
  });
}

export function useReadLocalLogMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: ({jobId, offset, maxBytes}: {jobId: string; offset?: number; maxBytes?: number}) =>
      client.readLocalLog(jobId, offset, maxBytes),
  });
}

export function usePrepareRunRequestMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: (config: unknown) => client.prepareRunRequest(config as Record<string, unknown>),
  });
}

export function useStartLocalJobMutation() {
  const client = useClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runRequest: unknown) => client.startLocalJob(runRequest),
    onSuccess: () => {
      void queryClient.invalidateQueries({queryKey: queryKeys.jobs.local()});
    },
  });
}
