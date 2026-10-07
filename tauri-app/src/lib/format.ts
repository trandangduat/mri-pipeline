export function formatBytes(value: number | string | null | undefined): string {
  const bytes = Number(value || 0);
  if (!bytes) {
    return 'unknown';
  }
  const gib = bytes / 1024 ** 3;
  return `${gib.toFixed(gib >= 10 ? 0 : 1)} GiB`;
}

export function formatTime(value: number | string | null | undefined): string {
  if (!value) {
    return 'Unknown';
  }
  const numeric = Number(value);
  const date = Number.isFinite(numeric) ? new Date(numeric * 1000) : new Date(String(value));
  return Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleString();
}

export function formatEta(totalSeconds: number | null | undefined): string {
  if (totalSeconds == null || !Number.isFinite(totalSeconds) || totalSeconds < 0) {
    return '—';
  }
  const s = Math.round(totalSeconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, '0')}s`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`;
}

export function formatFilesPerSec(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value) || value <= 0) {
    return '—';
  }
  return value < 10 ? value.toFixed(1) : String(Math.round(value));
}
