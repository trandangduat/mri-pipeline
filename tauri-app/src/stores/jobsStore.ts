import {create} from 'zustand';

interface JobsState {
  latestJobs: Record<string, unknown>[];
  selectedJobId: string | null;
  jobEvents: Record<string, unknown>[];
  jobLogSearch: string;
  outputText: string;
  hasLoadedInitialJobs: boolean;
  lastListRefreshAt: number | null;
  lastDetailRefreshAt: number | null;
  setLatestJobs: (jobs: Record<string, unknown>[] | ((prev: Record<string, unknown>[]) => Record<string, unknown>[])) => void;
  setHasLoadedInitialJobs: (loaded: boolean) => void;
  setLastListRefreshAt: (at: number | null) => void;
  setLastDetailRefreshAt: (at: number | null) => void;
  setSelectedJobId: (id: string | null | ((prev: string | null) => string | null)) => void;
  setJobEvents: (events: Record<string, unknown>[] | ((prev: Record<string, unknown>[]) => Record<string, unknown>[])) => void;
  setJobLogSearch: (query: string) => void;
  setOutputText: (text: string | ((prev: string) => string)) => void;
  appendJobEvents: (events: Record<string, unknown>[]) => void;
  appendOutputText: (text: string) => void;
  clearJobLog: () => void;
  appendOutput: (block: string) => void;
}

const MAX_LOG_LINES = 5000;

export function capLogLines(text: string, maxLines: number = MAX_LOG_LINES): string {
  if (!text) return '';
  const lines = text.split('\n');
  if (lines.length <= maxLines) return text;
  return lines.slice(-maxLines).join('\n');
}

export const useJobsStore = create<JobsState>((set) => ({
  latestJobs: [],
  selectedJobId: null,
  jobEvents: [],
  jobLogSearch: '',
  outputText: 'Log stream is idle.',
  hasLoadedInitialJobs: false,
  lastListRefreshAt: null,
  lastDetailRefreshAt: null,
  setLatestJobs: (latestJobs) =>
    set((state) => ({
      latestJobs: typeof latestJobs === 'function' ? latestJobs(state.latestJobs) : latestJobs,
      hasLoadedInitialJobs: true,
    })),
  setHasLoadedInitialJobs: (hasLoadedInitialJobs) => set({hasLoadedInitialJobs}),
  setLastListRefreshAt: (lastListRefreshAt) => set({lastListRefreshAt}),
  setLastDetailRefreshAt: (lastDetailRefreshAt) => set({lastDetailRefreshAt}),
  setSelectedJobId: (selectedJobId) =>
    set((state) => ({
      selectedJobId: typeof selectedJobId === 'function' ? selectedJobId(state.selectedJobId) : selectedJobId,
    })),
  setJobEvents: (jobEvents) =>
    set((state) => ({
      jobEvents: typeof jobEvents === 'function' ? jobEvents(state.jobEvents) : jobEvents,
    })),
  setJobLogSearch: (jobLogSearch) => set({jobLogSearch}),
  setOutputText: (outputText) =>
    set((state) => {
      const val = typeof outputText === 'function' ? outputText(state.outputText) : outputText;
      return {outputText: capLogLines(val)};
    }),
  appendJobEvents: (events) =>
    set((state) => ({
      jobEvents: [...state.jobEvents, ...events],
    })),
  appendOutputText: (text) =>
    set((state) => {
      const combined = state.outputText ? `${state.outputText}${text}` : text;
      return {outputText: capLogLines(combined)};
    }),
  clearJobLog: () => set({outputText: ''}),
  appendOutput: (block) =>
    set((state) => {
      const combined = `${block}${state.outputText}`;
      return {outputText: capLogLines(combined)};
    }),
}));
