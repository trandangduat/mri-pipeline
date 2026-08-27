import {create} from 'zustand';

interface JobsState {
  latestJobs: Record<string, unknown>[];
  selectedJobId: string | null;
  jobEvents: Record<string, unknown>[];
  jobLogSearch: string;
  outputText: string;
  setLatestJobs: (jobs: Record<string, unknown>[] | ((prev: Record<string, unknown>[]) => Record<string, unknown>[])) => void;
  setSelectedJobId: (id: string | null | ((prev: string | null) => string | null)) => void;
  setJobEvents: (events: Record<string, unknown>[] | ((prev: Record<string, unknown>[]) => Record<string, unknown>[])) => void;
  setJobLogSearch: (query: string) => void;
  setOutputText: (text: string | ((prev: string) => string)) => void;
  appendJobEvents: (events: Record<string, unknown>[]) => void;
  appendOutputText: (text: string) => void;
  clearJobLog: () => void;
  appendOutput: (block: string) => void;
}

export const useJobsStore = create<JobsState>((set) => ({
  latestJobs: [],
  selectedJobId: null,
  jobEvents: [],
  jobLogSearch: '',
  outputText: 'Log stream is idle.',
  setLatestJobs: (latestJobs) =>
    set((state) => ({
      latestJobs: typeof latestJobs === 'function' ? latestJobs(state.latestJobs) : latestJobs,
    })),
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
    set((state) => ({
      outputText: typeof outputText === 'function' ? outputText(state.outputText) : outputText,
    })),
  appendJobEvents: (events) =>
    set((state) => ({
      jobEvents: [...state.jobEvents, ...events],
    })),
  appendOutputText: (text) =>
    set((state) => ({
      outputText: state.outputText ? `${state.outputText}${text}` : text,
    })),
  clearJobLog: () => set({outputText: ''}),
  appendOutput: (block) => set((state) => ({outputText: `${block}${state.outputText}`})),
}));
