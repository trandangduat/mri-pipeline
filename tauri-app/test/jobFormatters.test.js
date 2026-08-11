import assert from 'node:assert/strict';
import {test} from 'node:test';
import {formatDuration, normalizeJob, normalizeJobState, shortJobName, statusClass} from '../src/jobFormatters.js';

test('normalizeJobState maps common backend states correctly', () => {
  assert.equal(normalizeJobState('running'), 'running');
  assert.equal(normalizeJobState('completed'), 'completed');
  assert.equal(normalizeJobState('DONE'), 'completed');
  assert.equal(normalizeJobState('FAILED'), 'failed');
  assert.equal(normalizeJobState('error'), 'failed');
  assert.equal(normalizeJobState('stopped'), 'stopped');
  assert.equal(normalizeJobState('unknown_state'), 'unknown');
});

test('shortJobName truncates long job IDs', () => {
  assert.equal(shortJobName('job-123'), 'job-123');
  assert.equal(shortJobName('very-long-job-id-for-testing-purpose-123456789'), 'very-long-...23456789');
});

test('formatDuration calculates formatted minutes and seconds', () => {
  assert.equal(formatDuration(100, 165), '1m 5s');
  assert.equal(formatDuration(null, 100), 'Unknown');
});

test('statusClass maps normalized state to CSS class', () => {
  assert.equal(statusClass('running'), 'running');
  assert.equal(statusClass('completed'), 'installed');
  assert.equal(statusClass('failed'), 'missing');
  assert.equal(statusClass('stopped'), 'checking');
});

test('normalizeJob builds standardized job object', () => {
  const job = normalizeJob({
    job_id: 'job_20260811_123',
    state: 'RUNNING',
    started_at: 1700000000,
    pid: 12345,
  }, 'Local');

  assert.equal(job.job_id, 'job_20260811_123');
  assert.equal(job.target, 'Local');
  assert.equal(job.state, 'running');
  assert.equal(job.pid, 12345);
});
