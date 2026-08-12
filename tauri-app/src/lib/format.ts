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
