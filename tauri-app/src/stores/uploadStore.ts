import {create} from 'zustand';

export interface UploadEntryState {
  staging_path: string;
  subject: string;
  pct: number;
  state: 'pending' | 'uploading' | 'ready' | 'failed' | 'cancelled';
  error?: string;
}

interface UploadStore {
  uploadsByJob: Record<string, UploadEntryState[]>;
  setUploads: (jobId: string, uploads: UploadEntryState[]) => void;
  clearUploads: (jobId: string) => void;
}

export const useUploadStore = create<UploadStore>((set) => ({
  uploadsByJob: {},
  setUploads: (jobId, uploads) =>
    set((prev) => ({uploadsByJob: {...prev.uploadsByJob, [jobId]: uploads}})),
  clearUploads: (jobId) =>
    set((prev) => {
      const next = {...prev.uploadsByJob};
      delete next[jobId];
      return {uploadsByJob: next};
    }),
}));
