import {create} from 'zustand';

export type AppTab = 'pipeline' | 'tools' | 'jobs';

export interface BusyState {
  connect: boolean;
  listRemote: boolean;
  refreshTools: boolean;
  refreshJobs: boolean;
  checkEnv: boolean;
}

interface UiState {
  activeTab: AppTab;
  sidebarOpen: boolean;
  busy: BusyState;
  setActiveTab: (tab: AppTab) => void;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setBusyKey: (key: keyof BusyState, value: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  activeTab: 'pipeline',
  sidebarOpen: true,
  busy: {
    connect: false,
    listRemote: false,
    refreshTools: false,
    refreshJobs: false,
    checkEnv: false,
  },
  setActiveTab: (activeTab) => set({activeTab}),
  toggleSidebar: () => set((state) => ({sidebarOpen: !state.sidebarOpen})),
  setSidebarOpen: (sidebarOpen) => set({sidebarOpen}),
  setBusyKey: (key, value) => set((state) => ({busy: {...state.busy, [key]: value}})),
}));
