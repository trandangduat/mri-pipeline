import {create} from 'zustand';
import type {RemoteConfigSummary, RemoteHardware, RemoteJobSummary} from '../types/backend';

export interface RemoteResultState {
  ok: boolean;
  connected: boolean;
  config: RemoteConfigSummary | null;
  hardware: RemoteHardware | null;
  error: string;
  jobs: RemoteJobSummary[];
  warnings: string[];
}

const INITIAL_REMOTE: RemoteResultState = {
  ok: false,
  connected: false,
  config: null,
  hardware: null,
  error: '',
  jobs: [],
  warnings: [],
};

interface RemoteState extends RemoteResultState {
  setResult: (result: Partial<RemoteResultState>) => void;
  reset: () => void;
}

export const useRemoteStore = create<RemoteState>((set) => ({
  ...INITIAL_REMOTE,
  setResult: (result) => set(result),
  reset: () => set({...INITIAL_REMOTE}),
}));
