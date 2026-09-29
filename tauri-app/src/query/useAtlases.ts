import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {useCallback, useState} from 'react';
import {useClient} from './useEnvironment';
import {queryKeys} from './keys';
import type {AtlasPack} from '../types/backend';

export function useAtlasStatus() {
  const client = useClient();
  const query = useQuery({
    queryKey: queryKeys.atlases.status(),
    queryFn: () => client.getAtlasStatus(),
    staleTime: 10000,
  });

  return {
    packs: (query.data?.packs || []) as AtlasPack[],
    isPending: query.isPending,
    isFetching: query.isFetching,
    error: query.data && !query.data.ok ? 'Failed to fetch atlas status' : query.error?.message || null,
    refetch: query.refetch,
  };
}

export function useImportAtlas() {
  const client = useClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (path: string) => client.importAtlas(path),
    onSuccess: () => {
      void queryClient.invalidateQueries({queryKey: queryKeys.atlases.status()});
    },
  });
}

export interface AtlasDownloadStreamState {
  status: 'idle' | 'connecting' | 'downloading' | 'extracting' | 'success' | 'failed';
  packId: string | null;
  percent: number;
  downloadedBytes: number;
  totalBytes: number;
  message: string;
  error: string | null;
}

const INITIAL_DOWNLOAD_STATE: AtlasDownloadStreamState = {
  status: 'idle',
  packId: null,
  percent: 0,
  downloadedBytes: 0,
  totalBytes: 0,
  message: '',
  error: null,
};

export function useDownloadAtlasStream() {
  const client = useClient();
  const queryClient = useQueryClient();
  const [state, setState] = useState<AtlasDownloadStreamState>(INITIAL_DOWNLOAD_STATE);

  const download = useCallback(
    async (packId: string) => {
      setState({
        status: 'connecting',
        packId,
        percent: 0,
        downloadedBytes: 0,
        totalBytes: 0,
        message: 'Connecting to download server...',
        error: null,
      });

      await client.startAtlasDownloadStream(
        packId,
        (event, data) => {
          if (event === 'connecting') {
            setState((prev) => ({
              ...prev,
              status: 'connecting',
              message: String(data.message || 'Connecting...'),
            }));
          } else if (event === 'downloading') {
            const downloaded = typeof data.downloaded_bytes === 'number' ? data.downloaded_bytes : 0;
            const total = typeof data.total_bytes === 'number' ? data.total_bytes : 0;
            const pct = typeof data.percent === 'number' ? data.percent : 0;
            setState((prev) => ({
              ...prev,
              status: 'downloading',
              downloadedBytes: downloaded,
              totalBytes: total,
              percent: pct,
              message: `Downloading: ${pct}%`,
            }));
          } else if (event === 'extracting') {
            setState((prev) => ({
              ...prev,
              status: 'extracting',
              percent: 100,
              message: String(data.message || 'Extracting atlas assets...'),
            }));
          } else if (event === 'complete') {
            setState((prev) => ({
              ...prev,
              status: 'success',
              percent: 100,
              message: String(data.message || 'Installed successfully!'),
            }));
            void queryClient.invalidateQueries({queryKey: queryKeys.atlases.status()});
          } else if (event === 'error') {
            setState((prev) => ({
              ...prev,
              status: 'failed',
              error: String(data.error || 'Download failed'),
              message: 'Download failed',
            }));
          }
        },
        (errMsg) => {
          setState((prev) => ({
            ...prev,
            status: 'failed',
            error: errMsg,
            message: 'Download failed',
          }));
        },
      );
    },
    [client, queryClient],
  );

  const reset = useCallback(() => {
    setState(INITIAL_DOWNLOAD_STATE);
  }, []);

  return {
    ...state,
    download,
    reset,
  };
}
