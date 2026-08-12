import {expect, test} from 'vitest';
import {formatDuration, normalizeJob, normalizeJobState, shortJobName, statusClass} from '../src/jobFormatters';

test('normalizeJobState maps common backend states correctly', () => {
  expect(normalizeJobState('running')).toBe('running');
  expect(normalizeJobState('completed')).toBe('completed');
  expect(normalizeJobState('DONE')).toBe('completed');
  expect(normalizeJobState('FAILED')).toBe('failed');
  expect(normalizeJobState('error')).toBe('failed');
  expect(normalizeJobState('stopped')).toBe('stopped');
  expect(normalizeJobState('unknown_state')).toBe('unknown');
});

test('shortJobName truncates long job IDs', () => {
  expect(shortJobName('job-123')).toBe('job-123');
  expect(shortJobName('very-long-job-id-for-testing-purpose-123456789')).toBe('very-long-...23456789');
});

test('formatDuration calculates formatted minutes and seconds', () => {
  expect(formatDuration(100, 165)).toBe('1m 5s');
  expect(formatDuration(null, 100)).toBe('Unknown');
});

test('statusClass maps normalized state to CSS class', () => {
  expect(statusClass('running')).toBe('running');
  expect(statusClass('completed')).toBe('installed');
  expect(statusClass('failed')).toBe('missing');
  expect(statusClass('stopped')).toBe('checking');
});

test('normalizeJob builds standardized job object', () => {
  const job = normalizeJob(
    {
      job_id: 'job_20260811_123',
      state: 'RUNNING',
      started_at: 1700000000,
      pid: 12345,
    },
    'Local',
  );

  expect(job.job_id).toBe('job_20260811_123');
  expect(job.target).toBe('Local');
  expect(job.state).toBe('running');
  expect(job.pid).toBe(12345);
});
