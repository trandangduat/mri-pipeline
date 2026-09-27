import assert from 'node:assert/strict';
import test from 'node:test';
import {waitForBackendReadiness} from './backend-readiness.mjs';

test('waits for health and capabilities before reporting the backend ready', async () => {
  let calls = 0;
  const fetchImpl = async (url) => {
    calls += 1;
    if (calls === 1) throw new Error('connection refused');
    if (url.endsWith('/health')) return {ok: true, json: async () => ({ok: true})};
    return {ok: true, json: async () => ({ok: true, components: []})};
  };

  const result = await waitForBackendReadiness({fetchImpl, attempts: 3, delayMs: 0, sleep: async () => {}});

  assert.deepEqual(result, {ok: true, missing: []});
  assert.equal(calls, 3);
});

test('reports failed backend components without starting the UI', async () => {
  const fetchImpl = async (url) => url.endsWith('/health')
    ? {ok: true, json: async () => ({ok: true})}
    : {ok: true, json: async () => ({ok: false, components: [{id: 'paramiko', label: 'Paramiko', ok: false}]})};

  const result = await waitForBackendReadiness({fetchImpl, attempts: 1});

  assert.deepEqual(result, {ok: false, missing: ['Paramiko'], error: 'Required application backend components are unavailable.'});
});
