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

export const hardwareSchema = z.object({
  hostname: z.string(),
  logical_cores: z.number().nullable(),
  physical_cores: z.number().nullable(),
  total_ram_bytes: z.number().nullable(),
});

export const environmentSchema = z.object({
  ok: z.boolean(),
  python: pythonStatusSchema,
  docker: commandStatusSchema,
  ssh: commandStatusSchema,
  hardware: hardwareSchema,
});

export const runRequestSummarySchema = z.record(z.string(), z.unknown()).optional();

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
  warnings: z.array(z.string()),
  next_offset: z.number(),
  error: z.string().optional(),
});

export const logResponseSchema = z.object({
  ok: z.boolean(),
  text: z.string(),
  next_offset: z.number(),
  truncated: z.boolean(),
  error: z.string().optional(),
});

export const toolImageSchema = z.object({
  image: z.string(),
  status: z.string(),
  tools: z.array(z.string()),
});

export const toolsImageResponseSchema = z.object({
  ok: z.boolean(),
  target: z.string(),
  images: z.array(toolImageSchema).optional(),
  warnings: z.array(z.string()).optional(),
  errors: z.array(z.string()).optional(),
  error: z.string().optional(),
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
});

export const remoteValidateResponseSchema = z.object({
  ok: z.boolean(),
  connected: z.boolean().optional(),
  config: remoteConfigSummarySchema.optional(),
  hardware: remoteHardwareSchema.optional(),
  warnings: z.array(z.string()).optional(),
  errors: z.array(z.string()).optional(),
  error: z.string().optional(),
});

export const remoteJobSummarySchema = z.object({
  target: z.string(),
  state: z.string(),
  pid: z.string(),
  remote_job_dir: z.string(),
});

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
});

export const appMetadataSchema = z.object({
  version: z.number(),
  project_root: z.string(),
  pipeline_modes: z.array(pipelineModeMetadataSchema),
  presets: z.record(z.string(), z.object({tools: z.record(z.string(), z.string()), stats: z.array(z.string())})),
  stages: z.array(z.object({id: z.string(), label: z.string()})),
  stage_order: z.array(z.string()),
  fs7_recon_style_stage_order: z.array(z.string()),
  tools: z.record(z.string(), toolMetadataSchema),
  tools_by_stage: z.record(z.string(), z.array(z.string())),
  export_items: z.record(
    z.string(),
    z.object({id: z.string(), stage: z.string(), label: z.string(), default_name: z.string()}),
  ),
  export_defaults: z.record(z.string(), z.unknown()),
  stats_vectors: z.record(
    z.string(),
    z.object({key: z.string(), label: z.string(), value_column: z.string(), atlases: z.array(z.string())}),
  ),
  atlases: z.record(z.string(), z.object({key: z.string(), label: z.string()})),
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
});

export const preparedRunRequestSchema = z.record(z.string(), z.unknown());
