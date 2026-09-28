import {z} from 'zod';

export const healthSchema = z.object({
  ok: z.boolean(),
  service: z.string(),
  pid: z.number(),
});

export const commandStatusSchema = z.object({
  ok: z.boolean(),
  path: z.string(),
});

export const pythonStatusSchema = commandStatusSchema.extend({
  version: z.string(),
});

export const gpuInfoSchema = z.object({
  name: z.string(),
  total_memory_mib: z.number().nullable(),
  free_memory_mib: z.number().nullable(),
});

export const hardwareSchema = z.object({
  hostname: z.string(),
  logical_cores: z.number().nullable(),
  physical_cores: z.number().nullable(),
  total_ram_bytes: z.number().nullable(),
  gpus: z.array(gpuInfoSchema).optional(),
});

export const dockerStatusSchema = commandStatusSchema.extend({
  version: z.string().optional(),
  error: z.string().optional(),
});

export const environmentSchema = z.object({
  ok: z.boolean(),
  python: pythonStatusSchema,
  docker: dockerStatusSchema,
  ssh: commandStatusSchema,
  hardware: hardwareSchema,
});

export const runRequestSummarySchema = z.record(z.string(), z.unknown()).optional();

export const batchSummarySchema = z.object({
  total: z.number(),
  success: z.number(),
  failed: z.number(),
  running: z.number(),
  pending: z.number(),
});

export const localJobSummarySchema = z.object({
  job_id: z.string(),
  target: z.string().optional(),
  state: z.string().optional(),
  job_dir: z.string().optional(),
  pid: z.number().optional(),
  exit_code: z.number().nullable().optional(),
  started_at: z.number().optional(),
  updated_at: z.number().optional(),
  output_dir: z.string().optional(),
  effective_output_dir: z.string().optional(),
  download_subdir: z.string().optional(),
  input_files: z.array(z.string()).optional(),
  batch_summary: batchSummarySchema.optional(),
  run_request_summary: runRequestSummarySchema,
});

export const localJobsResponseSchema = z.object({
  ok: z.boolean(),
  jobs: z.array(localJobSummarySchema).optional(),
  error: z.string().optional(),
});

export const pipelineEventSchema = z.record(z.string(), z.unknown());

export const eventsResponseSchema = z.object({
  ok: z.boolean(),
  events: z.array(pipelineEventSchema),
  warnings: z.array(z.string()).optional(),
  next_offset: z.number(),
  error: z.string().optional(),
  events_file_found: z.boolean().optional(),
});

export const logResponseSchema = z.object({
  ok: z.boolean(),
  text: z.string(),
  next_offset: z.number(),
  truncated: z.boolean(),
  error: z.string().optional(),
});

export const toolDetailSchema = z.object({
  key: z.string(),
  name: z.string(),
});

export const toolImageSchema = z.object({
  image: z.string(),
  status: z.string(),
  tools: z.array(z.string()),
  tool_details: z.array(toolDetailSchema).optional(),
  disk_usage: z.string().nullable().optional(),
  content_size: z.string().nullable().optional(),
  download_size: z.string().nullable().optional(),
  image_id: z.string().nullable().optional(),
  pull_status: z.string().optional(),
  pull_pid: z.union([z.string(), z.number()]).optional(),
  pull_started_at: z.number().optional(),
  pull_updated_at: z.number().optional(),
  pull_error: z.string().nullable().optional(),
  pull_log_tail: z.string().optional(),
});

export const toolsImageResponseSchema = z.object({
  ok: z.boolean(),
  target: z.string(),
  images: z.array(toolImageSchema).optional(),
  warnings: z.array(z.string()).optional(),
  errors: z.array(z.string()).optional(),
  error: z.string().optional(),
});

export const pullImageResponseSchema = z.object({
  ok: z.boolean(),
  error: z.string().optional(),
  target: z.string().optional(),
  image: z.string().optional(),
  status: z.string().optional(),
  already_running: z.boolean().optional(),
  pid: z.union([z.string(), z.number()]).optional(),
});

export const removeImageResponseSchema = z.object({
  ok: z.boolean(),
  error: z.string().nullable().optional(),
  target: z.string().optional(),
});

export const remoteConfigSummarySchema = z.object({
  host: z.string(),
  port: z.number(),
  username: z.string(),
  auth_method: z.string(),
  workspace: z.string(),
  python: z.string(),
});

export const remoteHardwareSchema = z.object({
  hostname: z.string(),
  logical_cores: z.number().nullable(),
  total_ram_bytes: z.number().nullable(),
  gpus: z.array(gpuInfoSchema).optional(),
});

export const sshHostKeyInfoSchema = z.object({
  host: z.string(),
  port: z.number(),
  key_type: z.string(),
  fingerprint: z.string(),
  expected_fingerprint: z.string().optional(),
});

export const remoteValidateResponseSchema = z.object({
  ok: z.boolean(),
  connected: z.boolean().optional(),
  config: remoteConfigSummarySchema.optional(),
  hardware: remoteHardwareSchema.optional(),
  warnings: z.array(z.string()).optional(),
  errors: z.array(z.string()).optional(),
  error: z.string().optional(),
  trust_required: sshHostKeyInfoSchema.optional(),
  host_key_changed: sshHostKeyInfoSchema.optional(),
});

export const remoteTrustHostResponseSchema = z.object({
  ok: z.boolean(),
  trusted: z.boolean().optional(),
  host_key: sshHostKeyInfoSchema.optional(),
  error: z.string().optional(),
  errors: z.array(z.string()).optional(),
  host_key_changed: sshHostKeyInfoSchema.optional(),
  config: remoteConfigSummarySchema.optional(),
});

export const remoteEnvironmentServerSchema = remoteHardwareSchema.extend({
  ok: z.boolean(),
});

export const remoteEnvironmentPythonSchema = z.object({
  ok: z.boolean(),
  path: z.string(),
  version: z.string(),
});

export const remoteEnvironmentVenvSchema = z.object({
  ok: z.boolean(),
  path: z.string(),
  venv_exists: z.boolean(),
  python_ok: z.boolean(),
  python_version: z.string(),
  pip_ok: z.boolean(),
  pip_version: z.string(),
});

export const remoteEnvironmentDockerSchema = z.object({
  ok: z.boolean(),
  version: z.string(),
  error: z.string(),
});

export const remoteEnvironmentResponseSchema = z.object({
  ok: z.boolean(),
  connected: z.boolean().optional(),
  config: remoteConfigSummarySchema.optional(),
  server: remoteEnvironmentServerSchema.optional(),
  python: remoteEnvironmentPythonSchema.optional(),
  environment: remoteEnvironmentVenvSchema.optional(),
  docker: remoteEnvironmentDockerSchema.optional(),
  warnings: z.array(z.string()).optional(),
  errors: z.array(z.string()).optional(),
  error: z.string().optional(),
});

export const remoteJobSummarySchema = z.object({
  job_id: z.string().optional(),
  target: z.string(),
  state: z.string(),
  pid: z.union([z.string(), z.number()]),
  exit_code: z.number().nullable().optional(),
  remote_job_dir: z.string(),
  job_dir: z.string().optional(),
  started_at: z.number().optional(),
  updated_at: z.number().optional(),
  finished_at: z.number().nullable().optional(),
  output_dir: z.string().optional(),
  effective_output_dir: z.string().optional(),
  download_subdir: z.string().optional(),
  input_files: z.array(z.string()).optional(),
  batch_summary: batchSummarySchema.optional(),
  run_request_summary: runRequestSummarySchema,
}).passthrough();

export const remoteJobsResponseSchema = z.object({
  ok: z.boolean(),
  jobs: z.array(remoteJobSummarySchema).optional(),
  error: z.string().optional(),
});

export const toolMetadataSchema = z.object({
  key: z.string(),
  display_name: z.string(),
  stage: z.string(),
  image: z.string(),
  dockerfile: z.string(),
  needs_license: z.boolean(),
  enabled: z.boolean(),
  visible: z.boolean(),
  timeout_sec: z.number(),
  output_files: z.array(z.string()),
  output_globs: z.array(z.string()),
});

export const pipelineModeMetadataSchema = z.object({
  id: z.string(),
  aliases: z.array(z.string()),
  tools: z.record(z.string(), z.string()),
  stats: z.array(z.string()),
  default_atlases: z.record(z.string(), z.array(z.string())).optional(),
});

export const appMetadataSchema = z.object({
  version: z.number(),
  project_root: z.string(),
  pipeline_modes: z.array(pipelineModeMetadataSchema),
  presets: z.record(z.string(), z.object({tools: z.record(z.string(), z.string()), stats: z.array(z.string()), default_atlases: z.record(z.string(), z.array(z.string())).optional()})),
  stages: z.array(z.object({id: z.string(), label: z.string()})),
  stage_order: z.array(z.string()),
  fs7_recon_style_stage_order: z.array(z.string()),
  tools: z.record(z.string(), toolMetadataSchema),
  tools_by_stage: z.record(z.string(), z.array(z.string())),
  tool_contracts: z
    .record(
      z.string(),
      z.object({requires: z.array(z.string()), produces: z.array(z.string())}),
    )
    .optional(),
  export_items: z.record(
    z.string(),
    z.object({id: z.string(), stage: z.string(), label: z.string(), default_name: z.string()}),
  ),
  export_defaults: z.record(z.string(), z.unknown()),
  stats_vectors: z.record(
    z.string(),
    z.object({key: z.string(), label: z.string(), value_column: z.string(), atlases: z.array(z.string())}),
  ),
  atlases: z.record(
    z.string(),
    z.object({
      key: z.string(),
      label: z.string(),
      available: z.boolean().optional(),
      unavailable_reason: z.string().optional(),
    }),
  ),
  vector_specs: z.record(z.string(), z.record(z.string(), z.string())),
});

export const startJobResponseSchema = z.object({
  ok: z.boolean(),
  job: localJobSummarySchema.optional(),
  error: z.string().optional(),
});

export const genericResponseSchema = z.object({
  ok: z.boolean(),
  error: z.string().optional(),
  path: z.string().optional(),
});

export const licenseUploadResponseSchema = z.object({
  ok: z.boolean(),
  path: z.string().optional(),
  error: z.string().optional(),
});

export const preparedRunRequestSchema = z.record(z.string(), z.unknown());

export const progressStepSchema = z.object({
  step: z.string(),
  status: z.enum(['running', 'done', 'failed']),
  detail: z.string().optional(),
});

export const progressCompleteSchema = z.object({
  ok: z.boolean(),
  job: localJobSummarySchema.optional(),
  error: z.string().optional(),
  errors: z.array(z.string()).optional(),
});

export const remoteBrowseEntrySchema = z.object({
  name: z.string(),
  path: z.string(),
  kind: z.enum(['directory', 'file']),
  size: z.number().nullable().optional(),
  modified_at: z.number().nullable().optional(),
  selectable: z.boolean(),
  // recursive batch scan extras
  subject_label: z.string().nullable().optional(),
  relative_path: z.string().nullable().optional(),
  depth: z.number().nullable().optional(),
  parent: z.string().nullable().optional(),
  is_dicom_series: z.boolean().nullable().optional(),
  slice_count: z.number().nullable().optional(),
});

export const remoteBrowseResponseSchema = z.object({
  ok: z.boolean(),
  path: z.string().optional(),
  parent: z.string().optional(),
  dirs: z.array(remoteBrowseEntrySchema).optional(),
  files: z.array(remoteBrowseEntrySchema).optional(),
  entries: z.array(remoteBrowseEntrySchema).optional(),
  image_count: z.number().optional(),
  error: z.string().optional(),
  errors: z.array(z.string()).optional(),
  // recursive batch scan extras
  is_batch_scan: z.boolean().optional(),
  has_multi_subject_conflict: z.boolean().optional(),
});

export const neuroflowValidationResponseSchema = z.object({
  ok: z.boolean(),
  kind: z.enum(['preset', 'profile']).optional(),
  id: z.string().optional(),
  display_name: z.string().optional(),
  stage_count: z.number().optional(),
  profile_count: z.number().optional(),
  path: z.string().nullable().optional(),
  error: z.string().optional(),
});

export type NeuroflowValidationResponse = z.infer<typeof neuroflowValidationResponseSchema>;

