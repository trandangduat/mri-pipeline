import {create} from 'zustand';

interface ToolsState {
  imageSearch: string;
  imageSelection: Set<string>;
  imageLogText: string;
  toolMessage: string;
  latestImages: unknown[];
  setImageSearch: (query: string) => void;
  setImageSelection: (selection: Set<string>) => void;
  appendImageLog: (line: string) => void;
  setToolMessage: (message: string) => void;
  setLatestImages: (images: unknown[]) => void;
}

export const useToolsStore = create<ToolsState>((set) => ({
  imageSearch: '',
  imageSelection: new Set<string>(),
  imageLogText: 'Docker image log is idle.',
  toolMessage: 'Image status is not loaded.',
  latestImages: [],
  setImageSearch: (imageSearch) => set({imageSearch}),
  setImageSelection: (imageSelection) => set({imageSelection}),
  appendImageLog: (line) => {
    const timestamp = new Date().toLocaleTimeString();
    set((state) => ({imageLogText: `[${timestamp}] ${line}\n${state.imageLogText}`.trim()}));
  },
  setToolMessage: (toolMessage) => set({toolMessage}),
  setLatestImages: (latestImages) => set({latestImages}),
}));
