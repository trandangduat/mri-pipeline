import type {AppMetadata, PreparedRunRequest} from '../types/backend';

export interface PipelineFormValues {
  pipelineMode: string;
  inputSource: string;
  inputMode: string;
  inputPath: string;
  additionalInputPaths: string;
  outputDir: string;
  serverOutputDir?: string;
  inputServerDir: string;
  runtimeTarget: 'Local' | 'Server';
  ramPercent: number;
  cpuThreads: number;
  gpuMode: 'on' | 'off';
  host: string;
  port: number;
  username: string;
  remote_python: string;
  workspace: string;
  key_path: string;
  password: string;
  licensePath?: string;
  batchImageCount?: number;
  batchScanMode?: string;
  nonRecursive?: boolean;
  neuroflowEnabled?: boolean;
  neuroflowMaxConcurrentTasks?: number;
  neuroflowMaxRetries?: number;
  neuroflowWarmupEnabled?: boolean;
  neuroflowWarmupInitialConcurrency?: number;
  neuroflowWarmupSafeSuccesses?: number;
  neuroflowPreserveOomBounds?: boolean;
  neuroflowEstimationMode?: 'balanced' | 'conservative' | 'aggressive';
  neuroflowMaxIoHeavyTasks?: number;
  neuroflowMachineProfileId?: string;
  neuroflowPresetFile?: string;
  neuroflowProfileFile?: string;
  [key: string]: unknown;
}

export const NEUROFLOW_PIPELINE_CONFIGS: Record<string, string> = {
  'FreeSurfer 8 + Volume': 'freesurfer8_volumetrics',
  'FreeSurfer 8 + Cortical Thickness': 'freesurfer8_cortical_thickness',
  'FreeSurfer 8 + Volume + Cortical Thickness': 'freesurfer8_all',
  'FreeSurfer 7 + Volume': 'freesurfer7_volumetrics',
  'FreeSurfer 7 + Cortical Thickness': 'freesurfer7_cortical_thickness',
  'FreeSurfer 7 + Volume + Cortical Thickness': 'freesurfer7_all',
  'FastSurfer + Volume': 'fastsurfer_volumetrics',
  'FastSurfer + Cortical Thickness': 'fastsurfer_cortical_thickness',
  'FastSurfer + Volume + Cortical Thickness': 'fastsurfer_all',
};

export function neuroflowConfigFilesForMode(mode: string): {preset: string; profile: string} {
  const presetId = NEUROFLOW_PIPELINE_CONFIGS[mode];
  if (!presetId) return {preset: '', profile: ''};
  return {
    preset: `configs/neuroflow/presets/${presetId}.yaml`,
    profile: `configs/neuroflow/profiles/${presetId}_default.yaml`,
  };
}

export const DEFAULT_FORM_VALUES: PipelineFormValues = {
  pipelineMode: 'FreeSurfer 8 + Volume + Cortical Thickness',
  inputSource: 'Local',
  inputMode: 'file',
  inputPath: '',
  additionalInputPaths: '',
  outputDir: '',
  inputServerDir: '',
  runtimeTarget: 'Local',
  ramPercent: 80,
  cpuThreads: 4,
  gpuMode: 'off',
  host: '',
  port: 22,
  username: '',
  remote_python: 'python3',
  workspace: '~/mri-remote-jobs',
  key_path: '',
  password: '',
  licensePath: '',
  neuroflowEnabled: true,
  neuroflowMaxConcurrentTasks: 2,
  neuroflowMaxRetries: 3,
  neuroflowWarmupEnabled: true,
  neuroflowWarmupInitialConcurrency: 2,
  neuroflowWarmupSafeSuccesses: 3,
  neuroflowPreserveOomBounds: true,
  neuroflowEstimationMode: 'balanced',
  neuroflowMaxIoHeavyTasks: 2,
  neuroflowMachineProfileId: 'application_default',
  neuroflowPresetFile: 'configs/neuroflow/presets/freesurfer8_all.yaml',
  neuroflowProfileFile: 'configs/neuroflow/profiles/freesurfer8_all_default.yaml',
};

export function buildRunConfig(
  formValues: PipelineFormValues,
  metadata: AppMetadata | null,
  selectedStatsAtlases?: Record<string, string[]>,
): Record<string, unknown> {
  const mode = formValues.pipelineMode || 'Custom';
  const preset = metadata?.presets?.[mode];
  const selectedTools = preset?.tools || selectedToolsFromForm(formValues);
  const inputMode = formValues.inputMode || 'file';
  const normalizedInputMode = inputMode === 'batch_folder' ? 'dir' : inputMode;
  const inputPath = formValues.inputPath || '';
  const additionalPaths = String(formValues.additionalInputPaths || '')
    .split(',')
    .map((path) => path.trim())
    .filter(Boolean);
  return {
    input_source: formValues.inputSource || 'Local',
    run_target: formValues.runtimeTarget || 'Local',
    input_mode: normalizedInputMode,
    input_path: inputPath,
    input_paths:
      normalizedInputMode === 'multi_file'
        ? [inputPath, ...additionalPaths].filter(Boolean)
        : normalizedInputMode === 'dir' && additionalPaths.length > 0
          ? additionalPaths
          : [],
    selected_files: additionalPaths.length > 0 ? additionalPaths : [],
    output_dir: formValues.outputDir,
    server_output_dir: formValues.runtimeTarget === 'Server'
      ? (formValues.serverOutputDir || formValues.outputDir || '')
      : '',
    input_server_dir: formValues.inputServerDir || '',
    pipeline_mode: mode,
    selected_tools: selectedTools,
    export_config: {enabled: false, folder: 'exports', default_format: '.nii.gz', names: {}, formats: {}},
    stats_vector_config: {enabled_stats: {}, atlases: selectedStatsAtlases || {}},
    non_recursive: Boolean(formValues.nonRecursive),
    device: formValues.gpuMode === 'on' ? 'cuda' : 'cpu',
    threads: formValues.cpuThreads ?? 4,
    ram_percent: formValues.ramPercent ?? 100,
    license_dir: formValues.licensePath || '',
    neuroflow_enabled: Boolean(formValues.neuroflowEnabled),
    neuroflow_max_concurrent_tasks: Math.max(1, Number(formValues.neuroflowMaxConcurrentTasks || 2)),
    neuroflow_max_retries: Math.max(0, Number(formValues.neuroflowMaxRetries ?? 3)),
    neuroflow_warmup_enabled: Boolean(formValues.neuroflowWarmupEnabled),
    neuroflow_warmup_initial_concurrency: Math.max(1, Number(formValues.neuroflowWarmupInitialConcurrency || 2)),
    neuroflow_warmup_safe_successes: Math.max(1, Number(formValues.neuroflowWarmupSafeSuccesses || 3)),
    neuroflow_preserve_oom_bounds: formValues.neuroflowPreserveOomBounds !== undefined ? Boolean(formValues.neuroflowPreserveOomBounds) : true,
    neuroflow_estimation_mode: String(formValues.neuroflowEstimationMode || 'balanced'),
    neuroflow_max_io_heavy_tasks: Math.max(1, Number(formValues.neuroflowMaxIoHeavyTasks || 2)),
    neuroflow_machine_profile_id: 'application_default',
    neuroflow_preset_file: String(formValues.neuroflowPresetFile || '').trim(),
    neuroflow_profile_file: String(formValues.neuroflowProfileFile || '').trim(),
  } satisfies PreparedRunRequest;
}

export function selectedToolsFromForm(formValues: PipelineFormValues): Record<string, string> {
  const selectedTools: Record<string, string> = {};
  for (const [key, value] of Object.entries(formValues)) {
    if (!key.startsWith('stage_')) continue;
    if (typeof value !== 'string' || !value.trim()) continue;
    selectedTools[key.slice('stage_'.length)] = value.trim();
  }
  return selectedTools;
}

export interface RemotePayload {
  host: string;
  port: number;
  username: string;
  password: string;
  remote_python: string;
  workspace: string;
  key_path: string;
}

export function buildRemotePayload(formValues: PipelineFormValues): RemotePayload {
  return {
    host: formValues.host,
    port: formValues.port,
    username: formValues.username,
    password: formValues.password,
    remote_python: formValues.remote_python,
    workspace: formValues.workspace,
    key_path: formValues.key_path,
  };
}
