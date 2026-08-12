import {create} from 'zustand';

interface JobsState {
  latestJobs: Record<string, unknown>[];
  selectedJobId: string | null;
  jobEvents: Record<string, unknown>[];
  jobLogSearch: string;
  outputText: string;
  setLatestJobs: (jobs: Record<string, unknown>[]) => void;
  setSelectedJobId: (id: string | null) => void;
  setJobEvents: (events: Record<string, unknown>[]) => void;
  setJobLogSearch: (query: string) => void;
  setOutputText: (text: string) => void;
  clearJobLog: () => void;
  appendOutput: (block: string) => void;
}

export const useJobsStore = create<JobsState>((set) => ({
  latestJobs: [],
  selectedJobId: null,
  jobEvents: [],
  jobLogSearch: '',
  outputText: 'Log stream is idle.',
  setLatestJobs: (latestJobs) => set({latestJobs}),
  setSelectedJobId: (selectedJobId) => set({selectedJobId}),
  setJobEvents: (jobEvents) => set({jobEvents}),
  setJobLogSearch: (jobLogSearch) => set({jobLogSearch}),
  setOutputText: (outputText) => set({outputText}),
  clearJobLog: () => set({outputText: ''}),
  appendOutput: (block) => set((state) => ({outputText: `${block}${state.outputText}`})),
}));
