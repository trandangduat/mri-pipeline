import type {
  AppMetadata,
  EnvironmentResponse,
  EventsResponse,
  GenericResponse,
  HealthResponse,
  LicenseUploadResponse,
  LocalJobsResponse,
  LogResponse,
  PreparedRunRequest,
  PullImageResponse,
  RemoteBrowseResponse,
  RemoteJobsResponse,
  RemoteValidateResponse,
  RemoveImageResponse,
  StartJobResponse,
  ToolsImageResponse,
} from '../types/backend';
import {
  appMetadataSchema,
  environmentSchema,
  eventsResponseSchema,
  genericResponseSchema,
  healthSchema,
  licenseUploadResponseSchema,
  localJobsResponseSchema,
  logResponseSchema,
  preparedRunRequestSchema,
  pullImageResponseSchema,
  remoteBrowseResponseSchema,
  remoteJobsResponseSchema,
  remoteValidateResponseSchema,
  removeImageResponseSchema,
  startJobResponseSchema,
  toolsImageResponseSchema,
} from './schemas';
import type {RemotePayload} from './runConfig';

export const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8765';

const REQUEST_TIMEOUT_MS = 30000;

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

  async uploadLicense(file: File): Promise<LicenseUploadResponse> {
    const content = await file.arrayBuffer();
    return licenseUploadResponseSchema.parse(
      await this.post('/licenses/upload', {
        filename: file.name,
        content_base64: arrayBufferToBase64(content),
      }),
    );
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

  async readRemoteEvents(
    payload: RemotePayload & {job_id?: string; remote_job_dir?: string; offset?: number; limit?: number},
  ): Promise<EventsResponse> {
    return eventsResponseSchema.parse(await this.post('/remote/jobs/events', {...payload}));
  }

  async readRemoteLog(
    payload: RemotePayload & {job_id?: string; remote_job_dir?: string; offset?: number; max_bytes?: number},
  ): Promise<LogResponse> {
    return logResponseSchema.parse(await this.post('/remote/jobs/log', {...payload}));
  }

  async fetchUploadState(
    payload: RemotePayload & {job_id: string},
  ): Promise<{ok: boolean; uploads?: Array<{staging_path: string; subject: string; pct: number; state: string; error?: string}>; terminal?: boolean; error?: string}> {
    return (await this.post('/remote/jobs/upload/state', {...payload})) as {
      ok: boolean;
      uploads?: Array<{staging_path: string; subject: string; pct: number; state: string; error?: string}>;
      terminal?: boolean;
      error?: string;
    };
  }

  async cancelUploads(
    payload: RemotePayload & {job_id: string},
  ): Promise<GenericResponse> {
    return genericResponseSchema.parse(await this.post('/remote/jobs/upload/cancel', {...payload}));
  }

  async uploadStage(
    payload: RemotePayload & {local_path?: string; local_paths?: string[]; remote_path: string},
  ): Promise<GenericResponse & {local_path?: string; local_paths?: string[]; remote_path?: string; uploaded_count?: number}> {
    return genericResponseSchema.passthrough().parse(await this.post('/remote/jobs/upload/stage', {...payload})) as GenericResponse & {local_path?: string; local_paths?: string[]; remote_path?: string; uploaded_count?: number};
  }

  async remoteMkdir(
    payload: RemotePayload & {path: string},
  ): Promise<GenericResponse & {path?: string}> {
    return genericResponseSchema.passthrough().parse(await this.post('/remote/mkdir', {...payload})) as GenericResponse & {path?: string};
  }

  async stopRemoteJob(
    payload: RemotePayload & {job_id?: string; remote_job_dir?: string},
  ): Promise<GenericResponse> {
    return genericResponseSchema.parse(await this.post('/remote/jobs/stop', {...payload}, 20_000));
  }

  async stopLocalJob(jobId: string): Promise<GenericResponse> {
    return genericResponseSchema.parse(await this.post('/jobs/local/stop', {job_id: jobId}, 10_000));
  }

  async deleteLocalJob(jobId: string): Promise<GenericResponse> {
    return genericResponseSchema.parse(await this.post('/jobs/local/delete', {job_id: jobId}));
  }

  async deleteRemoteJob(payload: RemotePayload & {job_id?: string; remote_job_dir?: string}): Promise<GenericResponse> {
    return genericResponseSchema.parse(await this.post('/remote/jobs/delete', {...payload}));
  }

  async browseRemotePath(
    payload: RemotePayload & {path?: string; purpose?: string; recursive?: boolean; max_depth?: number},
  ): Promise<RemoteBrowseResponse> {
    return remoteBrowseResponseSchema.parse(await this.post('/remote/browse', {...payload}));
  }

  async browseLocalPath(payload: {
    path: string;
    purpose?: string;
    recursive?: boolean;
    max_depth?: number;
  }): Promise<RemoteBrowseResponse> {
    return remoteBrowseResponseSchema.parse(await this.post('/local/browse', {...payload}));
  }

  async pullImage(image: string, {target = 'Local', remote = null}: {target?: string; remote?: unknown} = {}): Promise<PullImageResponse> {
    return pullImageResponseSchema.parse(await this.post('/tools/local/pull', {image, target, remote}));
  }

  async removeImage(image: string, {target = 'Local', remote = null}: {target?: string; remote?: unknown} = {}): Promise<RemoveImageResponse> {
    return removeImageResponseSchema.parse(await this.post('/tools/local/remove', {image, target, remote}));
  }

  async saveWorkspace(name: string, data: Record<string, unknown>): Promise<GenericResponse> {
    return genericResponseSchema.parse(await this.post('/config/workspaces/save', {name, data}));
  }

  async exportConfig(path: string, data: Record<string, unknown>): Promise<GenericResponse> {
    return genericResponseSchema.parse(await this.post('/config/export', {path, data}));
  }

  async startPipelineStream(
    path: string,
    payload: Record<string, unknown>,
    onEvent: (event: string, data: Record<string, unknown>) => void,
    onError: (error: string) => void,
  ): Promise<void> {
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      onError(`HTTP ${response.status}`);
      return;
    }
    const reader = response.body?.getReader();
    if (!reader) {
      onError('No response body');
      return;
    }
    const decoder = new TextDecoder();
    let buffer = '';
    try {
      let isComplete = false;
      while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {stream: true});
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        let currentEvent = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ') && currentEvent) {
            try {
              const data = JSON.parse(line.slice(6));
              const ev = currentEvent;
              currentEvent = '';
              onEvent(ev, data);
              if (ev === 'complete') {
                isComplete = true;
                break;
              }
            } catch {
              // skip malformed JSON
            }
          }
        }
        if (isComplete) break;
      }
    } catch (err) {
      onError((err as Error).message || 'Stream error');
    } finally {
      try {
        await reader.cancel();
      } catch {
        // ignore reader cancellation errors
      }
      reader.releaseLock();
    }
  }

  async startRemoteDownloadStream(
    payload: Record<string, unknown>,
    onEvent: (event: string, data: Record<string, unknown>) => void,
    onError: (error: string) => void,
  ): Promise<void> {
    return this.startPipelineStream('/remote/jobs/download/stream', payload, onEvent, onError);
  }

  async get(path: string): Promise<unknown> {
    return this.request(path, {method: 'GET'});
  }

  async post(path: string, body: Record<string, unknown>, timeoutMs?: number): Promise<unknown> {
    const controller = timeoutMs ? new AbortController() : null;
    const timeout = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
    try {
      return await this.request(path, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body ?? {}),
        signal: controller?.signal ?? null,
      });
    } finally {
      if (timeout !== null) clearTimeout(timeout);
    }
  }

  async request(path: string, options: RequestInit): Promise<unknown> {
    if (typeof this.fetchImpl !== 'function') {
      throw new Error('Fetch is not available in this environment.');
    }
    const url = `${this.baseUrl}${path}`;
    const signal = options.signal ?? null;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    if (!signal) {
      const controller = new AbortController();
      options = {...options, signal: controller.signal};
      timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    }
    try {
      return await this.performRequest(url, options);
    } finally {
      if (timeoutId !== null) clearTimeout(timeoutId);
    }
  }

  private async performRequest(url: string, options: RequestInit): Promise<unknown> {
    let response: Response;
    try {
      response = await this.fetchImpl(url, options);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      const timedOut = error instanceof DOMException && error.name === 'AbortError';
      throw new Error(`Cannot reach NeuroFlow backend at ${url}: ${message}${timedOut ? ' (request timed out)' : ''}`);
    }
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

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}
