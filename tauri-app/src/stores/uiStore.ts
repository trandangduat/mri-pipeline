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
  sidebarWidth: number;
  busy: BusyState;
  setActiveTab: (tab: AppTab) => void;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setSidebarWidth: (width: number) => void;
  setBusyKey: (key: keyof BusyState, value: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  activeTab: 'pipeline',
  sidebarOpen: true,
  sidebarWidth: 360,
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
  setSidebarWidth: (sidebarWidth) => set({sidebarWidth: Math.max(280, Math.min(520, sidebarWidth))}),
  setBusyKey: (key, value) => set((state) => ({busy: {...state.busy, [key]: value}})),
}));
