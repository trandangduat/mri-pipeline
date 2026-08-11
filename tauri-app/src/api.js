export const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8765';

export class BackendClient {
  constructor(baseUrl = DEFAULT_BACKEND_URL, fetchImpl = defaultFetch) {
    this.baseUrl = normalizeBaseUrl(baseUrl);
    this.fetchImpl = fetchImpl;
  }

  health() {
    return this.get('/health');
  }

  async waitForHealth({attempts = 20, delayMs = 250, sleep = defaultSleep} = {}) {
    let lastError = null;
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
    throw lastError || new Error('Backend did not become healthy.');
  }

  metadata() {
    return this.get('/metadata');
  }

  localEnvironment() {
    return this.get('/environment/local');
  }

  prepareRunRequest(payload) {
    return this.post('/run-request/prepare', payload);
  }

  startLocalJob(runRequest) {
    return this.post('/jobs/local/start', {run_request: runRequest});
  }

  listLocalJobs() {
    return this.get('/jobs/local');
  }

  readLocalEvents(jobId, offset = 0, limit = 500) {
    return this.get(`/jobs/local/events?job_id=${encodeURIComponent(jobId)}&offset=${offset}&limit=${limit}`);
  }

  readLocalLog(jobId, offset = 0, maxBytes = 65536) {
    return this.get(`/jobs/local/log?job_id=${encodeURIComponent(jobId)}&offset=${offset}&max_bytes=${maxBytes}`);
  }

  localImageStatus(selectedTools, {target = 'Local', remote = null} = {}) {
    return this.post('/tools/local/images', {
      target,
      selected_tools: selectedTools,
      remote,
    });
  }

  validateRemoteConfig(payload) {
    return this.post('/remote/validate', payload);
  }

  listRemoteJobs(payload) {
    return this.post('/remote/jobs', payload);
  }

  async get(path) {
    return this.request(path, {method: 'GET'});
  }

  async post(path, body) {
    return this.request(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body ?? {}),
    });
  }

  async request(path, options) {
    if (typeof this.fetchImpl !== 'function') {
      throw new Error('Fetch is not available in this environment.');
    }
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, options);
    const payload = await response.json();
    if (!response.ok) {
      const message = payload && typeof payload.error === 'string' ? payload.error : `HTTP ${response.status}`;
      throw new Error(message);
    }
    return payload;
  }
}

export function normalizeBaseUrl(value) {
  const url = String(value || DEFAULT_BACKEND_URL).trim();
  return url.endsWith('/') ? url.slice(0, -1) : url;
}

function defaultSleep(delayMs) {
  return new Promise((resolve) => setTimeout(resolve, delayMs));
}

function defaultFetch(url, options) {
  return globalThis.fetch(url, options);
}

export function buildRunConfig(formValues, metadata) {
  const mode = formValues.pipelineMode || 'Custom';
  const preset = metadata?.presets?.[mode];
  const inputMode = formValues.inputMode || 'file';
  const inputPath = formValues.inputPath || '';
  const additionalPaths = String(formValues.additionalInputPaths || '')
    .split(',')
    .map((path) => path.trim())
    .filter(Boolean);
  return {
    input_source: formValues.inputSource || 'Local',
    input_mode: inputMode,
    input_path: inputPath,
    input_paths: inputMode === 'multi_file' ? [inputPath, ...additionalPaths].filter(Boolean) : [],
    output_dir: formValues.outputDir,
    pipeline_mode: mode,
    selected_tools: preset?.tools || {},
    export_config: {enabled: false, folder: 'exports', default_format: '.nii.gz', names: {}, formats: {}},
    stats_vector_config: {enabled_stats: {}, atlases: {}},
  };
}
