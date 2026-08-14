import type {JobState} from './types/backend';

export function normalizeJobState(value: unknown): JobState {
  const normalized = String(value || 'unknown').toLowerCase();
  if (normalized.includes('run')) return 'running';
  if (normalized.includes('compl') || normalized.includes('done') || normalized.includes('success')) return 'completed';
  if (normalized.includes('fail') || normalized.includes('error')) return 'failed';
  if (normalized.includes('stop') || normalized.includes('cancel')) return 'stopped';
  return 'unknown';
}

export function shortJobName(jobId: unknown): string {
  const str = String(jobId || 'unknown-job');
  if (str.length <= 22) return str;
  return `${str.slice(0, 10)}...${str.slice(-8)}`;
}

export function jobBasename(value: unknown): string {
  const str = String(value || '').trim();
  if (!str) return 'unknown-job';
  const normalized = str.replace(/\\/g, '/').replace(/\/+$/, '');
  return normalized.split('/').pop() || normalized || 'unknown-job';
}

export function formatDuration(start: unknown, end?: unknown): string {
  const startNum = Number(start);
  const endNum = Number(end || Date.now() / 1000);
  if (!Number.isFinite(startNum) || !startNum || !Number.isFinite(endNum)) {
    return 'Unknown';
  }
  const seconds = Math.max(0, Math.round(endNum - startNum));
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export function statusClass(value: unknown): string {
  const normalized = normalizeJobState(value);
  if (normalized === 'running') return 'running';
  if (normalized === 'completed') return 'installed';
  if (normalized === 'failed') return 'missing';
  if (normalized === 'stopped') return 'checking';
  return 'unknown';
}

export interface NormalizedJob {
  job_id: string;
  target: string;
  state: JobState;
  display_name: string;
  started_at: number;
  updated_at: number;
  pid: number | string;
  [key: string]: unknown;
}

export function normalizeJob(job: Record<string, unknown>, fallbackTarget = 'Local'): NormalizedJob {
  const target = String(job.target || fallbackTarget);
  const rawIdentity = job.job_id || job.remote_job_dir || job.job_dir || job.pid || 'unknown-job';
  const jobId = job.job_id || jobBasename(rawIdentity);
  const displayName = target === 'Server'
    ? jobBasename(job.remote_job_dir || job.job_dir || jobId)
    : jobBasename(jobId);

  return {
    ...job,
    job_id: String(jobId),
    target,
    state: normalizeJobState(job.state || job.status),
    display_name: displayName,
    started_at: Number(job.started_at || job.created_at || 0),
    updated_at: Number(job.updated_at || 0),
    pid: typeof job.pid === 'string' || typeof job.pid === 'number' ? job.pid : '',
  };
}

export function jobStartedAtValue(job: Record<string, unknown>): number {
  const startedAt = Number(job.started_at || job.created_at || 0);
  if (Number.isFinite(startedAt) && startedAt > 0) {
    return startedAt;
  }
  const updatedAt = Number(job.updated_at || 0);
  return Number.isFinite(updatedAt) ? updatedAt : 0;
}

export function sortJobsByStartedAtDesc<T extends Record<string, unknown>>(jobs: T[]): T[] {
  return [...jobs].sort((a, b) => jobStartedAtValue(b) - jobStartedAtValue(a));
}
