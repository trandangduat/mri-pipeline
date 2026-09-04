import {useMutation, useQueryClient} from '@tanstack/react-query';
import {useClient} from './useEnvironment';
import type {BackendClient} from '../api/client';
import type {RemotePayload} from '../api/runConfig';
import type {RemoteValidateResponse} from '../types/backend';
import {queryKeys} from './keys';

export function useRemoteValidate(client: BackendClient) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RemotePayload & {timeoutMs?: number}) => {
      const {timeoutMs, ...requestPayload} = payload;
      return client.validateRemoteConfig(requestPayload, timeoutMs);
    },
    onSuccess: (result: RemoteValidateResponse) => {
      if (result.connected === true) {
        void queryClient.invalidateQueries({queryKey: queryKeys.remote.validate()});
      }
    },
  });
}

export function useRemoteJobs(client: BackendClient) {
  return useMutation({
    mutationFn: (payload: RemotePayload & {timeoutMs?: number}) => {
      const {timeoutMs, ...requestPayload} = payload;
      return client.listRemoteJobs(requestPayload, timeoutMs);
    },
  });
}

export function useRemoteValidateMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: (payload: RemotePayload & {timeoutMs?: number}) => {
      const {timeoutMs, ...requestPayload} = payload;
      return client.validateRemoteConfig(requestPayload, timeoutMs);
    },
  });
}

export function useListRemoteJobsMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: (payload: RemotePayload & {timeoutMs?: number}) => {
      const {timeoutMs, ...requestPayload} = payload;
      return client.listRemoteJobs(requestPayload, timeoutMs);
    },
  });
}

export function useReadRemoteEventsMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: (
      payload: RemotePayload & {
        job_id?: string;
        remote_job_dir?: string;
        offset?: number;
        limit?: number;
        signal?: AbortSignal;
        timeoutMs?: number;
      },
    ) => {
      const {signal, timeoutMs, ...requestPayload} = payload;
      return client.readRemoteEvents(requestPayload, signal, timeoutMs);
    },
  });
}

export function useReadRemoteMetricsMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: (
      payload: RemotePayload & {
        job_id?: string;
        remote_job_dir?: string;
        offset?: number;
        limit?: number;
        subject_id?: string;
        input_file?: string;
        signal?: AbortSignal;
        timeoutMs?: number;
      },
    ) => {
      const {signal, timeoutMs, ...requestPayload} = payload;
      return client.readRemoteMetrics(requestPayload, signal, timeoutMs);
    },
  });
}

export function useReadRemoteLogMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: (
      payload: RemotePayload & {
        job_id?: string;
        remote_job_dir?: string;
        offset?: number;
        max_bytes?: number;
        signal?: AbortSignal;
        timeoutMs?: number;
      },
    ) => {
      const {signal, timeoutMs, ...requestPayload} = payload;
      return client.readRemoteLog(requestPayload, signal, timeoutMs);
    },
  });
}

export function useRemoteBrowseMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: (payload: RemotePayload & {path?: string; purpose?: string; recursive?: boolean; max_depth?: number}) =>
      client.browseRemotePath(payload),
  });
}

export function useLocalBrowseMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: (payload: {path: string; purpose?: string; recursive?: boolean; max_depth?: number}) =>
      client.browseLocalPath(payload),
  });
}

export function useUploadStageMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: (payload: RemotePayload & {local_path?: string; local_paths?: string[]; remote_path: string}) =>
      client.uploadStage(payload),
  });
}

export function useRemoteMkdirMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: (payload: RemotePayload & {path: string}) => client.remoteMkdir(payload),
  });
}


