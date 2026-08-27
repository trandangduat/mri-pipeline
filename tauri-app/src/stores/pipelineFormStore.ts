import {create} from 'zustand';
import {DEFAULT_FORM_VALUES, neuroflowConfigFilesForMode} from '../api/runConfig';
import type {PipelineFormValues} from '../api/runConfig';
import {clampBoundedIntValue, RAM_PERCENT_MAX} from '../lib/runtime';

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
  toggleAtlas: (statKey: string, atlasKey: string) => void;
  applyWorkspaceConfig: (workspace: Record<string, unknown>, metadata?: {presets?: Record<string, {tools?: Record<string, string>}>; stage_order?: string[]}) => void;
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
    set((state) => {
      const current = state.selectedStatsAtlases[statKey] || [];
      if (current.includes(atlasKey)) return state;
      return {
        selectedStatsAtlases: {
          ...state.selectedStatsAtlases,
          [statKey]: [...current, atlasKey],
        },
      };
    }),
  removeAtlas: (statKey, atlasKey) =>
    set((state) => ({
      selectedStatsAtlases: {
        ...state.selectedStatsAtlases,
        [statKey]: (state.selectedStatsAtlases[statKey] || []).filter((key) => key !== atlasKey),
      },
    })),
  toggleAtlas: (statKey, atlasKey) =>
    set((state) => {
      const current = state.selectedStatsAtlases[statKey] || [];
      const exists = current.includes(atlasKey);
      return {
        selectedStatsAtlases: {
          ...state.selectedStatsAtlases,
          [statKey]: exists
            ? current.filter((key) => key !== atlasKey)
            : [...current, atlasKey],
        },
      };
    }),
  applyWorkspaceConfig: (workspace, metadata) => {
    const remote = (workspace.remote as Record<string, unknown>) || {};
    const pipelineMode = (workspace.pipeline_mode as string) || 'Custom';
    const workspaceTools = (workspace.tools as Record<string, unknown>) || {};
    set((state) => {
      const nextFormValues = {...state.formValues};
      nextFormValues.pipelineMode = pipelineMode;
      nextFormValues.inputSource = (workspace.input_source as string) || (workspace.run_target === 'Server' ? 'Server' : 'Local');
      const rawInputMode = (workspace.input_mode as string) || 'file';
      nextFormValues.inputMode = rawInputMode === 'dir' || rawInputMode === 'batch_folder' ? 'batch_folder' : rawInputMode;
      nextFormValues.inputPath = String(workspace.input_path || '');
      nextFormValues.outputDir = String(workspace.output_dir || '');
      nextFormValues.serverOutputDir = String(workspace.server_output_dir || '');
      nextFormValues.inputServerDir = String(workspace.input_server_dir || '');
      nextFormValues.additionalInputPaths = Array.isArray(workspace.selected_files)
        ? workspace.selected_files.join(', ')
        : (workspace.selected_files as string) || '';
      nextFormValues.batchImageCount =
        (workspace.batch_image_count as number) ??
        (Array.isArray(workspace.selected_files) ? workspace.selected_files.length : undefined);
      if (workspace.batch_scan_mode) {
        nextFormValues.batchScanMode = String(workspace.batch_scan_mode);
      }
      nextFormValues.runtimeTarget = workspace.run_target === 'Server' ? 'Server' : 'Local';
      nextFormValues.ramPercent = clampBoundedIntValue(workspace.ram_percent as number | undefined, 100, RAM_PERCENT_MAX);
      nextFormValues.cpuThreads = clampBoundedIntValue(workspace.threads as number | undefined, 4, null);
      nextFormValues.gpuMode = workspace.device === 'cuda' || workspace.device === 'gpu' ? 'on' : 'off';
      nextFormValues.host = (remote.host as string) || '';
      nextFormValues.port = (remote.port as number) ?? 22;
      nextFormValues.username = (remote.username as string) || '';
      nextFormValues.remote_python = (remote.python as string) || 'python3';
      nextFormValues.workspace = (remote.workspace as string) || '~/mri-remote-jobs';
      nextFormValues.key_path = (remote.key_path as string) || '';
      nextFormValues.nonRecursive = Boolean(workspace.non_recursive);
      nextFormValues.licensePath = (workspace.license_dir as string) || '';
      nextFormValues.neuroflowEnabled = workspace.neuroflow_enabled !== undefined ? Boolean(workspace.neuroflow_enabled) : true;
      nextFormValues.neuroflowMaxConcurrentTasks = Math.max(1, (workspace.neuroflow_max_concurrent_tasks as number) ?? 2);
      nextFormValues.neuroflowPolicy = String(workspace.neuroflow_policy || 'B6');
      nextFormValues.neuroflowMaxRetries = Math.max(0, (workspace.neuroflow_max_retries as number) ?? 3);
      nextFormValues.neuroflowWarmupEnabled = workspace.neuroflow_warmup_enabled !== undefined ? Boolean(workspace.neuroflow_warmup_enabled) : true;
      nextFormValues.neuroflowWarmupInitialConcurrency = Math.min(
        Math.max(1, (workspace.neuroflow_warmup_initial_concurrency as number) ?? 2),
        nextFormValues.neuroflowMaxConcurrentTasks,
      );
      nextFormValues.neuroflowWarmupSafeSuccesses = Math.max(1, (workspace.neuroflow_warmup_safe_successes as number) ?? 3);
      nextFormValues.neuroflowPreserveOomBounds = workspace.neuroflow_preserve_oom_bounds !== undefined ? Boolean(workspace.neuroflow_preserve_oom_bounds) : true;
      nextFormValues.neuroflowEstimationMode = (workspace.neuroflow_estimation_mode as 'balanced' | 'conservative' | 'aggressive') || 'balanced';
      nextFormValues.neuroflowMaxIoHeavyTasks = Math.max(1, (workspace.neuroflow_max_io_heavy_tasks as number) ?? 2);
      nextFormValues.neuroflowMachineProfileId = 'application_default';
      const neuroflowFiles = neuroflowConfigFilesForMode(pipelineMode);
      nextFormValues.neuroflowPresetFile = pipelineMode === 'Custom'
        ? String(workspace.neuroflow_preset_file || '')
        : neuroflowFiles.preset;
      nextFormValues.neuroflowProfileFile = pipelineMode === 'Custom'
        ? String(workspace.neuroflow_profile_file || '')
        : neuroflowFiles.profile;
      if (Object.keys(workspaceTools).length > 0) {
        for (const [stage, toolKey] of Object.entries(workspaceTools)) {
          (nextFormValues as Record<string, unknown>)[`stage_${stage}`] = String(toolKey);
        }
      } else if (metadata?.presets?.[pipelineMode]?.tools) {
        const presetTools = metadata.presets[pipelineMode].tools;
        for (const [stage, toolKey] of Object.entries(presetTools)) {
          (nextFormValues as Record<string, unknown>)[`stage_${stage}`] = toolKey;
        }
      }
      const nextAtlases = {...state.selectedStatsAtlases};
      const sv = workspace.stats_vectors as Record<string, unknown> | undefined;
      if (sv && typeof sv === 'object') {
        for (const [statKey, val] of Object.entries(sv)) {
          if (Array.isArray(val)) {
            nextAtlases[statKey] = val as string[];
          } else if (val && typeof val === 'object' && Array.isArray((val as {atlases?: string[]}).atlases)) {
            nextAtlases[statKey] = (val as {atlases: string[]}).atlases;
          }
        }
      }
      return {
        formValues: nextFormValues,
        selectedStatsAtlases: nextAtlases,
        preparedRequest: null,
      };
    });
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
      const defaultAtlases = (preset.default_atlases as Record<string, unknown>) || {};
      for (const [statKey, atlases] of Object.entries(defaultAtlases)) {
        if (Array.isArray(atlases)) {
          nextAtlases[statKey] = atlases as string[];
        }
      }
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
