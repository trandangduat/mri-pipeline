import {useMutation, useQueryClient} from '@tanstack/react-query';
import {useClient} from './useEnvironment';
import type {BackendClient} from '../api/client';
import type {RemotePayload} from '../api/runConfig';
import type {RemoteValidateResponse} from '../types/backend';
import {queryKeys} from './keys';

export function useRemoteValidate(client: BackendClient) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RemotePayload) => client.validateRemoteConfig(payload),
    onSuccess: (result: RemoteValidateResponse) => {
      if (result.connected === true) {
        void queryClient.invalidateQueries({queryKey: queryKeys.remote.validate()});
      }
    },
  });
}

export function useRemoteJobs(client: BackendClient) {
  return useMutation({
    mutationFn: (payload: RemotePayload) => client.listRemoteJobs(payload),
  });
}

export function useRemoteValidateMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: (payload: RemotePayload) => client.validateRemoteConfig(payload),
  });
}

export function useListRemoteJobsMutation() {
  const client = useClient();
  return useMutation({
    mutationFn: (payload: RemotePayload) => client.listRemoteJobs(payload),
  });
}
