import {create} from 'zustand';

export interface ImageDownloadState {
  status: 'idle' | 'pulling' | 'success' | 'failed';
  logs: string[];
  error: string | null;
}

export interface PullStreamState {
  status: 'idle' | 'pulling' | 'success' | 'failed';
  logs: string[];
  error: string | null;
  image: string | null;
  target: string;
}

const INITIAL_PULL_STREAM_STATE: PullStreamState = {
  status: 'idle',
  logs: [],
  error: null,
  image: null,
  target: 'Local',
};

interface ToolsState {
  latestImages: unknown[];
  cachedImagesByKey: Record<string, unknown[]>;
  downloadStates: Record<string, ImageDownloadState>;
  pullStreamState: PullStreamState;
  setLatestImages: (images: unknown[], cacheKey?: string) => void;
  setDownloadState: (image: string, state: Partial<ImageDownloadState>) => void;
  clearDownloadState: (image: string) => void;
  setPullStreamState: (state: Partial<PullStreamState> | ((prev: PullStreamState) => Partial<PullStreamState>)) => void;
  appendPullLogs: (newLogs: string[]) => void;
  resetPullStream: () => void;
}

export const useToolsStore = create<ToolsState>((set) => ({
  latestImages: [],
  cachedImagesByKey: {},
  downloadStates: {},
  pullStreamState: INITIAL_PULL_STREAM_STATE,
  setLatestImages: (latestImages, cacheKey) =>
    set((prev) => ({
      latestImages,
      cachedImagesByKey: cacheKey
        ? {...prev.cachedImagesByKey, [cacheKey]: latestImages}
        : prev.cachedImagesByKey,
    })),
  setDownloadState: (image, state) =>
    set((prev) => ({
      downloadStates: {
        ...prev.downloadStates,
        [image]: {...(prev.downloadStates[image] || {status: 'idle', logs: [], error: null}), ...state},
      },
    })),
  clearDownloadState: (image) =>
    set((prev) => {
      const next = {...prev.downloadStates};
      delete next[image];
      return {downloadStates: next};
    }),
  setPullStreamState: (stateUpdate) =>
    set((prev) => {
      const resolved = typeof stateUpdate === 'function' ? stateUpdate(prev.pullStreamState) : stateUpdate;
      return {
        pullStreamState: {...prev.pullStreamState, ...resolved},
      };
    }),
  appendPullLogs: (newLogs) =>
    set((prev) => ({
      pullStreamState: {
        ...prev.pullStreamState,
        logs: [...prev.pullStreamState.logs, ...newLogs],
      },
    })),
  resetPullStream: () =>
    set(() => ({
      pullStreamState: INITIAL_PULL_STREAM_STATE,
    })),
}));
