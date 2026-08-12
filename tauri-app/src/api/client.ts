import type {
  AppMetadata,
  EnvironmentResponse,
  EventsResponse,
  GenericResponse,
  HealthResponse,
  LocalJobsResponse,
  LogResponse,
  PreparedRunRequest,
  RemoteJobsResponse,
  RemoteValidateResponse,
  StartJobResponse,
  ToolsImageResponse,
} from '../types/backend';
import {
  appMetadataSchema,
  environmentSchema,
  eventsResponseSchema,
  genericResponseSchema,
  healthSchema,
  localJobsResponseSchema,
  logResponseSchema,
  preparedRunRequestSchema,
  remoteJobsResponseSchema,
  remoteValidateResponseSchema,
  startJobResponseSchema,
  toolsImageResponseSchema,
} from './schemas';
import type {RemotePayload} from './runConfig';

export const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8765';

export type FetchLike = (url: string, options?: RequestInit) => Promise<Response>;

export interface WaitForHealthOptions {
  attempts?: number;
  delayMs?: number;
  sleep?: (delayMs: number) => Promise<void>;
}

function defaultSleep(delayMs: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, delayMs));
}

function defaultFetch(url: string, options?: RequestInit): Promise<Response> {
  return globalThis.fetch(url, options);
}

export class BackendClient {
  readonly baseUrl: string;
  private readonly fetchImpl: FetchLike;

  constructor(baseUrl: string = DEFAULT_BACKEND_URL, fetchImpl: FetchLike = defaultFetch) {
    this.baseUrl = normalizeBaseUrl(baseUrl);
    this.fetchImpl = fetchImpl;
  }

  async health(): Promise<HealthResponse> {
    return healthSchema.parse(await this.get('/health'));
  }

  async waitForHealth({
    attempts = 20,
    delayMs = 250,
    sleep = defaultSleep,
  }: WaitForHealthOptions = {}): Promise<HealthResponse> {
    let lastError: unknown = null;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        return await this.health();
      } catch (error) {
        lastError = error;
        if (attempt + 1 < attempts) {
          await sleep(delayMs);
        }
      }
    }
    throw lastError instanceof Error ? lastError : new Error('Backend did not become healthy.');
  }

  async metadata(): Promise<AppMetadata> {
    return appMetadataSchema.parse(await this.get('/metadata'));
  }

  async localEnvironment(): Promise<EnvironmentResponse> {
    return environmentSchema.parse(await this.get('/environment/local'));
  }

  async prepareRunRequest(payload: Record<string, unknown>): Promise<PreparedRunRequest> {
    return preparedRunRequestSchema.parse(await this.post('/run-request/prepare', payload));
  }

  async startLocalJob(runRequest: unknown): Promise<StartJobResponse> {
    return startJobResponseSchema.parse(await this.post('/jobs/local/start', {run_request: runRequest}));
  }

  async listLocalJobs(): Promise<LocalJobsResponse> {
    return localJobsResponseSchema.parse(await this.get('/jobs/local'));
  }

  async readLocalEvents(jobId: string, offset = 0, limit = 500): Promise<EventsResponse> {
    return eventsResponseSchema.parse(
      await this.get(`/jobs/local/events?job_id=${encodeURIComponent(jobId)}&offset=${offset}&limit=${limit}`),
    );
  }

  async readLocalLog(jobId: string, offset = 0, maxBytes = 65536): Promise<LogResponse> {
    return logResponseSchema.parse(
      await this.get(`/jobs/local/log?job_id=${encodeURIComponent(jobId)}&offset=${offset}&max_bytes=${maxBytes}`),
    );
  }

  async localImageStatus(
    selectedTools: Record<string, unknown>,
    {target = 'Local', remote = null}: {target?: string; remote?: unknown} = {},
  ): Promise<ToolsImageResponse> {
    return toolsImageResponseSchema.parse(
      await this.post('/tools/local/images', {
        target,
        selected_tools: selectedTools,
        remote,
      }),
    );
  }

  async validateRemoteConfig(payload: RemotePayload): Promise<RemoteValidateResponse> {
    return remoteValidateResponseSchema.parse(await this.post('/remote/validate', {...payload}));
  }

  async listRemoteJobs(payload: RemotePayload): Promise<RemoteJobsResponse> {
    return remoteJobsResponseSchema.parse(await this.post('/remote/jobs', {...payload}));
  }

  async stopLocalJob(jobId: string): Promise<GenericResponse> {
    return genericResponseSchema.parse(await this.post('/jobs/local/stop', {job_id: jobId}));
  }

  async get(path: string): Promise<unknown> {
    return this.request(path, {method: 'GET'});
  }

  async post(path: string, body: Record<string, unknown>): Promise<unknown> {
    return this.request(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body ?? {}),
    });
  }

  async request(path: string, options: RequestInit): Promise<unknown> {
    if (typeof this.fetchImpl !== 'function') {
      throw new Error('Fetch is not available in this environment.');
    }
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, options);
    const payload: unknown = await response.json();
    if (!response.ok) {
      const errorPayload = (payload ?? {}) as {error?: unknown};
      const message = typeof errorPayload.error === 'string' ? errorPayload.error : `HTTP ${response.status}`;
      throw new Error(message);
    }
    return payload;
  }
}

export function normalizeBaseUrl(value: string): string {
  const url = String(value || DEFAULT_BACKEND_URL).trim();
  return url.endsWith('/') ? url.slice(0, -1) : url;
}
