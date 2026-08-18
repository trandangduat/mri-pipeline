import {expect, test} from 'vitest';
import {BackendClient, normalizeBaseUrl} from '../src/api/client';
import {buildRunConfig} from '../src/api/runConfig';
import type {PipelineMetadata} from '../src/types/backend';

const validHealth = {ok: true, service: 'mri-pipeline-backend', pid: 1234};
const validEnv = {
  ok: true,
  python: {ok: true, path: '/usr/bin/python3', version: '3.12'},
  docker: {ok: true, path: '/usr/bin/docker'},
  ssh: {ok: true, path: '/usr/bin/ssh'},
  hardware: {hostname: 'host', logical_cores: 8, physical_cores: 8, total_ram_bytes: 17179869184},
};

test('normalizeBaseUrl removes trailing slash', () => {
  expect(normalizeBaseUrl('http://127.0.0.1:8765/')).toBe('http://127.0.0.1:8765');
});

test('BackendClient sends JSON POST requests', async () => {
  const calls: Array<{url: string; options: RequestInit}> = [];
  const client = new BackendClient('http://backend/', async (url: RequestInfo | URL, options?: RequestInit) => {
    calls.push({url: String(url), options: options || {}});
    return {ok: true, json: async () => ({})} as Response;
  });

  const result = await client.prepareRunRequest({input_path: '/tmp/image.nii.gz'});

  expect(result).toEqual({});
  expect(calls[0]?.url).toBe('http://backend/run-request/prepare');
  expect(calls[0]?.options.method).toBe('POST');
  expect((calls[0]?.options.headers as Record<string, string>)?.['Content-Type']).toBe('application/json');
  expect(calls[0]?.options.body).toBe(JSON.stringify({input_path: '/tmp/image.nii.gz'}));
});

test('BackendClient uses expected endpoint paths', async () => {
  const calls: Array<{url: string; options: RequestInit}> = [];
  const client = new BackendClient('http://backend', async (url: RequestInfo | URL, options?: RequestInit) => {
    calls.push({url: String(url), options: options || {}});
    const payload = {
      health: validHealth,
      metadata: {
        version: 1,
        project_root: '/p',
        pipeline_modes: [],
        presets: {},
        stages: [],
        stage_order: [],
        fs7_recon_style_stage_order: [],
        tools: {},
        tools_by_stage: {},
        export_items: {},
        export_defaults: {},
        stats_vectors: {},
        atlases: {},
        vector_specs: {},
      },
      environment: validEnv,
      jobs: {ok: true, jobs: []},
      events: {ok: true, events: [], warnings: [], next_offset: 0},
      log: {ok: true, text: '', next_offset: 0, truncated: false},
      tools: {ok: true, target: 'Local', images: []},
      remote: {ok: true, connected: true},
      start: {ok: true},
    };
    const pick = () => {
      const u = String(url);
      if (u.includes('/health')) return payload.health;
      if (u.includes('/metadata')) return payload.metadata;
      if (u.includes('/environment/local')) return payload.environment;
      if (u.includes('/jobs/local/events')) return payload.events;
      if (u.includes('/jobs/local/log')) return payload.log;
      if (u.includes('/jobs/local')) return payload.jobs;
      if (u.includes('/tools/local/images')) return payload.tools;
      if (u.includes('/remote/validate')) return payload.remote;
      if (u.includes('/remote/jobs')) return {ok: true, jobs: []};
      if (u.includes('/jobs/local/start')) return payload.start;
      return {};
    };
    return {ok: true, json: async () => pick()} as Response;
  });

  await client.metadata();
  await client.localEnvironment();
  await client.startLocalJob({mode: 'file'});
  await client.listLocalJobs();
  await client.readLocalEvents('job 1', 7, 9);
  await client.readLocalLog('job 1', 11, 13);
  await client.localImageStatus({segmentation: 'tool'});
  await client.validateRemoteConfig({
    host: 'server',
    port: 22,
    username: 'u',
    password: '',
    remote_python: 'python3',
    workspace: '~/mri-remote-jobs',
    key_path: '',
  });
  await client.listRemoteJobs({
    host: 'server',
    port: 22,
    username: 'u',
    password: '',
    remote_python: 'python3',
    workspace: '~/mri-remote-jobs',
    key_path: '',
  });

  expect(calls[0]?.url).toBe('http://backend/metadata');
  expect(calls[0]?.options.method).toBe('GET');
  expect(calls[1]?.url).toBe('http://backend/environment/local');
  expect(calls[1]?.options.method).toBe('GET');
  expect(calls[2]?.url).toBe('http://backend/jobs/local/start');
  expect(calls[2]?.options.body).toBe(JSON.stringify({run_request: {mode: 'file'}}));
  expect(calls[3]?.url).toBe('http://backend/jobs/local');
  expect(calls[4]?.url).toBe('http://backend/jobs/local/events?job_id=job%201&offset=7&limit=9');
  expect(calls[5]?.url).toBe('http://backend/jobs/local/log?job_id=job%201&offset=11&max_bytes=13');
  expect(calls[6]?.url).toBe('http://backend/tools/local/images');
  expect(calls[6]?.options.body).toBe(
    JSON.stringify({target: 'Local', selected_tools: {segmentation: 'tool'}, remote: null}),
  );
  expect(calls[7]?.url).toBe('http://backend/remote/validate');
  expect(calls[8]?.url).toBe('http://backend/remote/jobs');
});

test('BackendClient raises backend JSON errors', async () => {
  const client = new BackendClient(
    'http://backend',
    async () =>
      ({
        ok: false,
        status: 404,
        json: async () => ({error: 'Not found'}),
      }) as Response,
  );

  await expect(() => client.health()).rejects.toThrow(/Not found/);
});

test('BackendClient uploads license file contents as base64 JSON', async () => {
  const calls: Array<{url: string; options: RequestInit}> = [];
  const client = new BackendClient('http://backend', async (url: RequestInfo | URL, options?: RequestInit) => {
    calls.push({url: String(url), options: options || {}});
    return {ok: true, json: async () => ({ok: true, path: '/managed/license.txt'})} as Response;
  });

  const result = await client.uploadLicense(new File(['license-body'], 'license.txt', {type: 'text/plain'}));
  const body = JSON.parse(String(calls[0]?.options.body || '{}')) as {filename: string; content_base64: string};

  expect(result).toEqual({ok: true, path: '/managed/license.txt'});
  expect(calls[0]?.url).toBe('http://backend/licenses/upload');
  expect(body.filename).toBe('license.txt');
  expect(atob(body.content_base64)).toBe('license-body');
});

test('BackendClient default fetch keeps global fetch binding', async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = function fetchWithRequiredBinding(
      this: typeof globalThis,
      url: RequestInfo | URL,
      options?: RequestInit,
    ) {
      expect(this).toBe(globalThis);
      expect(url).toBe('http://backend/health');
      expect(options?.method).toBe('GET');
      return Promise.resolve({ok: true, json: async () => validHealth} as Response);
    };

    const client = new BackendClient('http://backend');

    expect(await client.health()).toEqual(validHealth);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('BackendClient waits for health across transient failures', async () => {
  let calls = 0;
  const client = new BackendClient('http://backend', async () => {
    calls += 1;
    if (calls < 3) {
      throw new Error('connection refused');
    }
    return {ok: true, json: async () => validHealth} as Response;
  });

  const result = await client.waitForHealth({attempts: 3, delayMs: 0, sleep: async () => {}});

  expect(result).toEqual(validHealth);
  expect(calls).toBe(3);
});

test('BackendClient waitForHealth raises the last failure', async () => {
  const client = new BackendClient('http://backend', async () => {
    throw new Error('connection refused');
  });

  await expect(() => client.waitForHealth({attempts: 2, delayMs: 0, sleep: async () => {}})).rejects.toThrow(
    /connection refused/,
  );
});

test('buildRunConfig uses preset tools from metadata', () => {
  const config = buildRunConfig(
    {
      inputPath: '/data/a.nii.gz',
      outputDir: '/out',
      pipelineMode: 'FreeSurfer 7 + Volume',
      inputSource: 'Local',
      inputMode: 'file',
      additionalInputPaths: '',
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
    },
    {presets: {'FreeSurfer 7 + Volume': {tools: {segmentation: 'fs7'}, stats: []}}} as unknown as PipelineMetadata,
  );

  expect(config.input_path).toBe('/data/a.nii.gz');
  expect(config.output_dir).toBe('/out');
  expect(config.pipeline_mode).toBe('FreeSurfer 7 + Volume');
  expect(config.selected_tools).toEqual({segmentation: 'fs7'});
});

test('buildRunConfig sends selected FreeSurfer license path', () => {
  const config = buildRunConfig(
    {
      inputPath: '/data/a.nii.gz',
      outputDir: '/out',
      pipelineMode: 'FreeSurfer 7 + Volume',
      inputSource: 'Local',
      inputMode: 'file',
      additionalInputPaths: '',
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
      licensePath: '/licenses/license.txt',
    },
    null,
  );

  expect(config.license_dir).toBe('/licenses/license.txt');
});

test('buildRunConfig sends selected stats atlases', () => {
  const config = buildRunConfig(
    {
      inputPath: '/data/a.nii.gz',
      outputDir: '/out',
      pipelineMode: 'FreeSurfer 8 + Volume',
      inputSource: 'Local',
      inputMode: 'file',
      additionalInputPaths: '',
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
    },
    null,
    {
      subcortical_volume: ['freesurfer_aseg', 'harvard_oxford_subcortical', 'pauli_2017'],
      cortical_volume: ['freesurfer_aparc', 'brainnetome246'],
      cortical_thickness: [],
    },
  );

  expect(config.stats_vector_config).toEqual({
    enabled_stats: {},
    atlases: {
      subcortical_volume: ['freesurfer_aseg', 'harvard_oxford_subcortical', 'pauli_2017'],
      cortical_volume: ['freesurfer_aparc', 'brainnetome246'],
      cortical_thickness: [],
    },
  });
});

test('buildRunConfig maps pipeline input source and multi-file paths', () => {
  const config = buildRunConfig(
    {
      inputSource: 'Server',
      inputMode: 'multi_file',
      inputPath: '/data/a.nii.gz',
      additionalInputPaths: '/data/b.nii.gz, /data/c.nii.gz',
      outputDir: '/out',
      pipelineMode: 'Custom',
      runtimeTarget: 'Server',
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
    },
    null,
  );

  expect(config.input_source).toBe('Server');
  expect(config.input_mode).toBe('multi_file');
  expect(config.input_path).toBe('/data/a.nii.gz');
  expect(config.input_paths).toEqual(['/data/a.nii.gz', '/data/b.nii.gz', '/data/c.nii.gz']);
});
