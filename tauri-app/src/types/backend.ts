import type {z} from 'zod';
import type {
  appMetadataSchema,
  commandStatusSchema,
  environmentSchema,
  eventsResponseSchema,
  genericResponseSchema,
  hardwareSchema,
  healthSchema,
  localJobSummarySchema,
  localJobsResponseSchema,
  logResponseSchema,
  pipelineEventSchema,
  preparedRunRequestSchema,
  remoteConfigSummarySchema,
  remoteBrowseEntrySchema,
  remoteBrowseResponseSchema,
  remoteHardwareSchema,
  remoteJobSummarySchema,
  remoteJobsResponseSchema,
  remoteValidateResponseSchema,
  startJobResponseSchema,
  toolImageSchema,
  toolMetadataSchema,
  toolsImageResponseSchema,
} from '../api/schemas';

export type HealthResponse = z.infer<typeof healthSchema>;
export type CommandStatus = z.infer<typeof commandStatusSchema>;
export type HardwareStatus = z.infer<typeof hardwareSchema>;
export type EnvironmentResponse = z.infer<typeof environmentSchema>;
export type LocalJobSummary = z.infer<typeof localJobSummarySchema>;
export type LocalJobsResponse = z.infer<typeof localJobsResponseSchema>;
export type PipelineEvent = z.infer<typeof pipelineEventSchema>;
export type EventsResponse = z.infer<typeof eventsResponseSchema>;
export type LogResponse = z.infer<typeof logResponseSchema>;
export type ToolImage = z.infer<typeof toolImageSchema>;
export type ToolsImageResponse = z.infer<typeof toolsImageResponseSchema>;
export type RemoteConfigSummary = z.infer<typeof remoteConfigSummarySchema>;
export type RemoteHardware = z.infer<typeof remoteHardwareSchema>;
export type RemoteValidateResponse = z.infer<typeof remoteValidateResponseSchema>;
export type RemoteJobSummary = z.infer<typeof remoteJobSummarySchema>;
export type RemoteJobsResponse = z.infer<typeof remoteJobsResponseSchema>;
export type ToolMetadata = z.infer<typeof toolMetadataSchema>;
export type AppMetadata = z.infer<typeof appMetadataSchema>;
export type StartJobResponse = z.infer<typeof startJobResponseSchema>;
export type GenericResponse = z.infer<typeof genericResponseSchema>;
export type PreparedRunRequest = z.infer<typeof preparedRunRequestSchema>;
export type RemoteBrowseEntry = z.infer<typeof remoteBrowseEntrySchema>;
export type RemoteBrowseResponse = z.infer<typeof remoteBrowseResponseSchema>;

export type JobState = 'running' | 'completed' | 'failed' | 'stopped' | 'missing' | 'unknown';
export type RuntimeTarget = 'Local' | 'Server';

export interface RemoteResultState {
  ok: boolean;
  connected: boolean;
  config: RemoteConfigSummary | null;
  hardware: RemoteHardware | null;
  error: string;
  jobs: RemoteJobSummary[];
  warnings: string[];
}

export interface BusyState {
  connect: boolean;
  listRemote: boolean;
  refreshTools: boolean;
  refreshJobs: boolean;
  checkEnv: boolean;
}
