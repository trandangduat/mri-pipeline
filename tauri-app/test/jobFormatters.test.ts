import {expect, test} from 'vitest';
import {formatDuration, jobBasename, normalizeJob, normalizeJobState, shortJobName, statusClass} from '../src/jobFormatters';

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

test('jobBasename strips local and remote paths', () => {
  expect(jobBasename('/home/user/jobs/job_20260811_123')).toBe('job_20260811_123');
  expect(jobBasename('C:\\jobs\\job_abc')).toBe('job_abc');
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

test('normalizeJob uses remote job basename as route-safe id', () => {
  const job = normalizeJob(
    {
      remote_job_dir: '/home/catcd1/duat-jobs2/job_20260730_164556',
      state: 'completed',
      pid: '9988',
    },
    'Server',
  );

  expect(job.job_id).toBe('job_20260730_164556');
  expect(job.display_name).toBe('job_20260730_164556');
  expect(job.remote_job_dir).toBe('/home/catcd1/duat-jobs2/job_20260730_164556');
});

test('normalizeJob shows real remote folder name while keeping stable remote id', () => {
  const job = normalizeJob(
    {
      job_id: 'remote_job_20260814_102225',
      remote_job_dir: '/home/catcd1/mri-remote-jobs/job_20260814_102225',
      target: 'Server',
      state: 'running',
    },
    'Server',
  );

  expect(job.job_id).toBe('remote_job_20260814_102225');
  expect(job.display_name).toBe('job_20260814_102225');
});
