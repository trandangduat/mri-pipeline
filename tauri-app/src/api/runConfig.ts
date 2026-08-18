import type {AppMetadata, PreparedRunRequest} from '../types/backend';

export interface PipelineFormValues {
  pipelineMode: string;
  inputSource: string;
  inputMode: string;
  inputPath: string;
  additionalInputPaths: string;
  outputDir: string;
  runtimeTarget: 'Local' | 'Server';
  ramPercent: number;
  cpuThreads: number;
  gpuMode: string;
  host: string;
  port: number;
  username: string;
  remote_python: string;
  workspace: string;
  key_path: string;
  password: string;
  licensePath?: string;
  batchImageCount?: number;
  nonRecursive?: boolean;
  neuroflowEnabled?: boolean;
  neuroflowMaxConcurrentTasks?: number;
  neuroflowMachineProfileId?: string;
  [key: string]: unknown;
}

export const DEFAULT_FORM_VALUES: PipelineFormValues = {
  pipelineMode: 'Custom',
  inputSource: 'Local',
  inputMode: 'file',
  inputPath: '',
  additionalInputPaths: '',
  outputDir: '',
  runtimeTarget: 'Local',
  ramPercent: 80,
  cpuThreads: 4,
  gpuMode: 'auto',
  host: '',
  port: 22,
  username: '',
  remote_python: 'python3',
  workspace: '~/mri-remote-jobs',
  key_path: '',
  password: '',
  licensePath: '',
  neuroflowEnabled: false,
  neuroflowMaxConcurrentTasks: 1,
  neuroflowMachineProfileId: 'application_default',
};

export function buildRunConfig(
  formValues: PipelineFormValues,
  metadata: AppMetadata | null,
  selectedStatsAtlases?: Record<string, string[]>,
): Record<string, unknown> {
  const mode = formValues.pipelineMode || 'Custom';
  const preset = metadata?.presets?.[mode];
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
    pipeline_mode: mode,
    selected_tools: preset?.tools || {},
    export_config: {enabled: false, folder: 'exports', default_format: '.nii.gz', names: {}, formats: {}},
    stats_vector_config: {enabled_stats: {}, atlases: selectedStatsAtlases || {}},
    non_recursive: Boolean(formValues.nonRecursive),
    device: formValues.gpuMode === 'enabled' ? 'cuda' : 'cpu',
    threads: formValues.cpuThreads ?? 4,
    ram_percent: formValues.ramPercent ?? 100,
    license_dir: formValues.licensePath || '',
    neuroflow_enabled: Boolean(formValues.neuroflowEnabled),
    neuroflow_max_concurrent_tasks: Math.max(1, Number(formValues.neuroflowMaxConcurrentTasks || 1)),
    neuroflow_machine_profile_id: String(formValues.neuroflowMachineProfileId || 'application_default'),
  } satisfies PreparedRunRequest;

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
