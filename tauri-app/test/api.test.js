import assert from 'node:assert/strict';
import {test} from 'node:test';
import {BackendClient, buildRunConfig, normalizeBaseUrl} from '../src/api.js';

test('normalizeBaseUrl removes trailing slash', () => {
  assert.equal(normalizeBaseUrl('http://127.0.0.1:8765/'), 'http://127.0.0.1:8765');
});

test('BackendClient sends JSON POST requests', async () => {
  const calls = [];
  const client = new BackendClient('http://backend/', async (url, options) => {
    calls.push({url, options});
    return {ok: true, json: async () => ({ok: true})};
  });

  const result = await client.prepareRunRequest({input_path: '/tmp/image.nii.gz'});

  assert.deepEqual(result, {ok: true});
  assert.equal(calls[0].url, 'http://backend/run-request/prepare');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(calls[0].options.headers['Content-Type'], 'application/json');
  assert.equal(calls[0].options.body, JSON.stringify({input_path: '/tmp/image.nii.gz'}));
});

test('BackendClient uses expected endpoint paths', async () => {
  const calls = [];
  const client = new BackendClient('http://backend', async (url, options) => {
    calls.push({url, options});
    return {ok: true, json: async () => ({ok: true, jobs: [], events: [], text: ''})};
  });

  await client.metadata();
  await client.localEnvironment();
  await client.startLocalJob({mode: 'file'});
  await client.listLocalJobs();
  await client.readLocalEvents('job 1', 7, 9);
  await client.readLocalLog('job 1', 11, 13);
  await client.localImageStatus({segmentation: 'tool'});
  await client.validateRemoteConfig({host: 'server'});
  await client.listRemoteJobs({host: 'server'});

  assert.equal(calls[0].url, 'http://backend/metadata');
  assert.equal(calls[0].options.method, 'GET');
  assert.equal(calls[1].url, 'http://backend/environment/local');
  assert.equal(calls[1].options.method, 'GET');
  assert.equal(calls[2].url, 'http://backend/jobs/local/start');
  assert.equal(calls[2].options.body, JSON.stringify({run_request: {mode: 'file'}}));
  assert.equal(calls[3].url, 'http://backend/jobs/local');
  assert.equal(calls[4].url, 'http://backend/jobs/local/events?job_id=job%201&offset=7&limit=9');
  assert.equal(calls[5].url, 'http://backend/jobs/local/log?job_id=job%201&offset=11&max_bytes=13');
  assert.equal(calls[6].url, 'http://backend/tools/local/images');
  assert.equal(calls[6].options.body, JSON.stringify({target: 'Local', selected_tools: {segmentation: 'tool'}, remote: null}));
  assert.equal(calls[7].url, 'http://backend/remote/validate');
  assert.equal(calls[7].options.body, JSON.stringify({host: 'server'}));
  assert.equal(calls[8].url, 'http://backend/remote/jobs');
  assert.equal(calls[8].options.body, JSON.stringify({host: 'server'}));
});

test('BackendClient raises backend JSON errors', async () => {
  const client = new BackendClient('http://backend', async () => ({ok: false, status: 404, json: async () => ({error: 'Not found'})}));

  await assert.rejects(() => client.health(), /Not found/);
});

test('BackendClient default fetch keeps global fetch binding', async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = function fetchWithRequiredBinding(url, options) {
      assert.equal(this, globalThis);
      assert.equal(url, 'http://backend/health');
      assert.equal(options.method, 'GET');
      return Promise.resolve({ok: true, json: async () => ({ok: true})});
    };

    const client = new BackendClient('http://backend');

    assert.deepEqual(await client.health(), {ok: true});
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
    return {ok: true, json: async () => ({ok: true})};
  });

  const result = await client.waitForHealth({attempts: 3, delayMs: 0, sleep: async () => {}});

  assert.deepEqual(result, {ok: true});
  assert.equal(calls, 3);
});

test('BackendClient waitForHealth raises the last failure', async () => {
  const client = new BackendClient('http://backend', async () => {
    throw new Error('connection refused');
  });

  await assert.rejects(() => client.waitForHealth({attempts: 2, delayMs: 0, sleep: async () => {}}), /connection refused/);
});

test('buildRunConfig uses preset tools from metadata', () => {
  const config = buildRunConfig(
    {inputPath: '/data/a.nii.gz', outputDir: '/out', pipelineMode: 'FreeSurfer 7 + Volume'},
    {presets: {'FreeSurfer 7 + Volume': {tools: {segmentation: 'fs7'}}}},
  );

  assert.equal(config.input_path, '/data/a.nii.gz');
  assert.equal(config.output_dir, '/out');
  assert.equal(config.pipeline_mode, 'FreeSurfer 7 + Volume');
  assert.deepEqual(config.selected_tools, {segmentation: 'fs7'});
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
    },
    {presets: {}},
  );

  assert.equal(config.input_source, 'Server');
  assert.equal(config.input_mode, 'multi_file');
  assert.equal(config.input_path, '/data/a.nii.gz');
  assert.deepEqual(config.input_paths, ['/data/a.nii.gz', '/data/b.nii.gz', '/data/c.nii.gz']);
});
