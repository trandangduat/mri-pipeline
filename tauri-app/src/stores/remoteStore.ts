import {create} from 'zustand';
import {
  MAX_CONNECTION_FAILURES,
  nextBackendHealth,
  nextSshHealth,
  type BackendHealth,
  type SshHealth,
} from '../lib/connection';
import type {RemoteConfigSummary, RemoteHardware, RemoteJobSummary} from '../types/backend';

export interface RemoteResultState {
  ok: boolean;
  connected: boolean;
  config: RemoteConfigSummary | null;
  hardware: RemoteHardware | null;
  error: string;
  jobs: RemoteJobSummary[];
  warnings: string[];
  /** Runtime SSH health. `connected` above is sticky (last explicit Connect
   *  result); this tracks live failures so mid-session drops get reported. */
  sshStatus: SshHealth;
  sshFailures: number;
  sshLastError: string;
  sshLastSeenAt: number | null;
  /** Runtime local-backend health (HTTP UI -> 127.0.0.1:8765). */
  backendStatus: BackendHealth;
  backendFailures: number;
  backendLastError: string;
  backendLastSeenAt: number | null;
}

const INITIAL_REMOTE: RemoteResultState = {
  ok: false,
  connected: false,
  config: null,
  hardware: null,
  error: '',
  jobs: [],
  warnings: [],
  sshStatus: 'connected',
  sshFailures: 0,
  sshLastError: '',
  sshLastSeenAt: null,
  backendStatus: 'ok',
  backendFailures: 0,
  backendLastError: '',
  backendLastSeenAt: null,
};

interface RemoteState extends RemoteResultState {
  setResult: (result: Partial<RemoteResultState>) => void;
  reset: () => void;
  reportSshSuccess: () => void;
  reportSshFailure: (error: string) => void;
  setSshConnected: () => void;
  setSshDisconnected: (error: string) => void;
  resetSshHealth: () => void;
  reportBackendSuccess: () => void;
  reportBackendFailure: (error: string) => void;
}

export const useRemoteStore = create<RemoteState>((set) => ({
  ...INITIAL_REMOTE,
  setResult: (result) => set(result),
  reset: () => set({...INITIAL_REMOTE}),
  reportSshSuccess: () =>
    set({sshStatus: 'connected', sshFailures: 0, sshLastError: '', sshLastSeenAt: Date.now()}),
  reportSshFailure: (error) =>
    set((state) => {
      const sshFailures = state.sshFailures + 1;
      return {
        sshFailures,
        sshStatus: nextSshHealth(sshFailures),
        sshLastError: error || 'SSH request failed.',
      };
    }),
  setSshConnected: () =>
    set({sshStatus: 'connected', sshFailures: 0, sshLastError: '', sshLastSeenAt: Date.now()}),
  setSshDisconnected: (error) =>
    set({
      sshStatus: 'disconnected',
      sshFailures: MAX_CONNECTION_FAILURES,
      sshLastError: error || 'SSH connection failed.',
    }),
  // User switched back to Local (or otherwise abandoned the server leg):
  // drop the warning state immediately instead of waiting for recovery.
  resetSshHealth: () =>
    set({sshStatus: 'connected', sshFailures: 0, sshLastError: '', sshLastSeenAt: null}),
  reportBackendSuccess: () =>
    set({backendStatus: 'ok', backendFailures: 0, backendLastError: '', backendLastSeenAt: Date.now()}),
  reportBackendFailure: (error) =>
    set((state) => {
      const backendFailures = state.backendFailures + 1;
      return {
        backendFailures,
        backendStatus: nextBackendHealth(backendFailures),
        backendLastError: error || 'Backend request failed.',
      };
    }),
}));
