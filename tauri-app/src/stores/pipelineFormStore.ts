import {create} from 'zustand';
import {DEFAULT_FORM_VALUES} from '../api/runConfig';
import type {PipelineFormValues} from '../api/runConfig';

interface PipelineFormState {
  formValues: PipelineFormValues;
  selectedStatsAtlases: Record<string, string[]>;
  preparedRequest: Record<string, unknown> | null;
  setFormField: (name: string, value: unknown) => void;
  setFormFields: (patch: Record<string, unknown>) => void;
  setPipelineMode: (mode: string) => void;
  setSelectedStatsAtlases: (
    selectedStatsAtlases: Record<string, string[]> | ((prev: Record<string, string[]>) => Record<string, string[]>),
  ) => void;
  setPreparedRequest: (request: Record<string, unknown> | null) => void;
  resetForm: () => void;
  addAtlas: (statKey: string, atlasKey: string) => void;
  removeAtlas: (statKey: string, atlasKey: string, metadata?: Record<string, unknown>) => void;
  applyWorkspaceConfig: (workspace: Record<string, unknown>) => void;
  applyPresetConfig: (preset: Record<string, unknown>) => void;
}

export const usePipelineFormStore = create<PipelineFormState>((set) => ({
  formValues: {...DEFAULT_FORM_VALUES},
  selectedStatsAtlases: {},
  preparedRequest: null,
  setFormField: (name, value) => set((state) => ({formValues: {...state.formValues, [name]: value}})),
  setFormFields: (patch) => set((state) => ({formValues: {...state.formValues, ...patch}})),
  setPipelineMode: (pipelineMode) => set((state) => ({formValues: {...state.formValues, pipelineMode}})),
  setSelectedStatsAtlases: (selectedStatsAtlases) =>
    set((state) => ({
      selectedStatsAtlases:
        typeof selectedStatsAtlases === 'function'
          ? selectedStatsAtlases(state.selectedStatsAtlases)
          : selectedStatsAtlases,
    })),
  setPreparedRequest: (preparedRequest) => set({preparedRequest}),
  resetForm: () => set({formValues: {...DEFAULT_FORM_VALUES}, preparedRequest: null}),
  addAtlas: (statKey, atlasKey) =>
    set((state) => ({
      selectedStatsAtlases: {
        ...state.selectedStatsAtlases,
        [statKey]: [...(state.selectedStatsAtlases[statKey] || []), atlasKey],
      },
    })),
  removeAtlas: (statKey, atlasKey, metadata) => {
    const atlases = metadata?.atlases as Record<string, {label?: string}> | undefined;
    const atlas = atlases?.[atlasKey] || {label: atlasKey};
    if (typeof window !== 'undefined' && window.confirm) {
      if (!window.confirm(`Remove atlas "${atlas.label || atlasKey}" from this stats vector?`)) {
        return;
      }
    }
    set((state) => ({
      selectedStatsAtlases: {
        ...state.selectedStatsAtlases,
        [statKey]: (state.selectedStatsAtlases[statKey] || []).filter((key) => key !== atlasKey),
      },
    }));
  },
  applyWorkspaceConfig: (workspace) => {
    const remote = (workspace.remote as Record<string, unknown>) || {};
    set((state) => ({
      formValues: {
        ...state.formValues,
        inputSource: (workspace.input_source as string) || (workspace.run_target === 'Server' ? 'Server' : 'Local'),
        inputMode: (workspace.input_mode as string) || 'file',
        inputPath: (workspace.input_path as string) || '',
        additionalInputPaths: Array.isArray(workspace.selected_files) ? workspace.selected_files.join(', ') : '',
        outputDir: (workspace.output_dir as string) || '',
        runtimeTarget: workspace.run_target === 'Server' ? 'Server' : 'Local',
        ramPercent: (workspace.ram_percent as number) ?? 100,
        cpuThreads: (workspace.threads as number) ?? 4,
        gpuMode: workspace.device === 'cuda' || workspace.device === 'gpu' ? 'enabled' : 'disabled',
        host: (remote.host as string) || '',
        port: (remote.port as number) ?? 22,
        username: (remote.username as string) || '',
        remote_python: (remote.python as string) || 'python3',
        workspace: (remote.workspace as string) || '~/mri-remote-jobs',
        key_path: (remote.key_path as string) || '',
        nonRecursive: Boolean(workspace.non_recursive),
      },
      preparedRequest: null,
    }));
  },
  applyPresetConfig: (preset) => {
    set((state) => {
      const nextValues = {...state.formValues};
      if (preset.pipeline_mode) {
        nextValues.pipelineMode = preset.pipeline_mode as string;
      }
      const tools = (preset.tools as Record<string, unknown>) || {};
      for (const [stage, toolKey] of Object.entries(tools)) {
        (nextValues as Record<string, unknown>)[`stage_${stage}`] = String(toolKey);
      }
      const nextAtlases = {...state.selectedStatsAtlases};
      const statsVectors = (preset.stats_vectors as Record<string, unknown>) || {};
      for (const statKey of Object.keys(nextAtlases)) {
        const stat = statsVectors[statKey];
        const statAtlases = (stat as {atlases?: string[]})?.atlases;
        if (stat && typeof stat === 'object' && Array.isArray(statAtlases)) {
          nextAtlases[statKey] = statAtlases;
        } else if (Array.isArray(stat)) {
          nextAtlases[statKey] = stat as string[];
        }
      }
      return {
        formValues: nextValues,
        selectedStatsAtlases: nextAtlases,
        preparedRequest: null,
      };
    });
  },
}));
