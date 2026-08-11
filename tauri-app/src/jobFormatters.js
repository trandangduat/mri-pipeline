export function normalizeJobState(value) {
  const normalized = String(value || 'unknown').toLowerCase();
  if (normalized.includes('run')) return 'running';
  if (normalized.includes('compl') || normalized.includes('done') || normalized.includes('success')) return 'completed';
  if (normalized.includes('fail') || normalized.includes('error')) return 'failed';
  if (normalized.includes('stop') || normalized.includes('cancel')) return 'stopped';
  return 'unknown';
}

export function shortJobName(jobId) {
  const str = String(jobId || 'unknown-job');
  if (str.length <= 22) return str;
  return `${str.slice(0, 10)}...${str.slice(-8)}`;
}

export function formatDuration(start, end) {
  const startNum = Number(start);
  const endNum = Number(end || Date.now() / 1000);
  if (!Number.isFinite(startNum) || !startNum || !Number.isFinite(endNum)) {
    return 'Unknown';
  }
  const seconds = Math.max(0, Math.round(endNum - startNum));
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export function statusClass(value) {
  const normalized = normalizeJobState(value);
  if (normalized === 'running') return 'running';
  if (normalized === 'completed') return 'installed';
  if (normalized === 'failed') return 'missing';
  if (normalized === 'stopped') return 'checking';
  return 'unknown';
}

export function normalizeJob(job, fallbackTarget = 'Local') {
  const target = job.target || fallbackTarget;
  const jobId = job.job_id || job.remote_job_dir || job.pid || 'unknown-job';

  return {
    ...job,
    job_id: String(jobId),
    target,
    state: normalizeJobState(job.state || job.status),
    display_name: shortJobName(jobId),
    started_at: job.started_at || job.created_at || 0,
    updated_at: job.updated_at || 0,
    pid: job.pid || '',
  };
}
