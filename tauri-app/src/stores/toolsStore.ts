import {create} from 'zustand';

export interface ImageDownloadState {
  status: 'idle' | 'pulling' | 'success' | 'failed';
  logs: string[];
  error: string | null;
}

interface ToolsState {
  latestImages: unknown[];
  cachedImagesByKey: Record<string, unknown[]>;
  downloadStates: Record<string, ImageDownloadState>;
  setLatestImages: (images: unknown[], cacheKey?: string) => void;
  setDownloadState: (image: string, state: Partial<ImageDownloadState>) => void;
  clearDownloadState: (image: string) => void;
}

export const useToolsStore = create<ToolsState>((set) => ({
  latestImages: [],
  cachedImagesByKey: {},
  downloadStates: {},
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
}));
