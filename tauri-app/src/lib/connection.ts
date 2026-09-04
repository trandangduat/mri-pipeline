/**
 * Connection-health helpers for Jobs Monitor.
 *
 * Two independent channels are tracked:
 * - Backend channel: HTTP between this UI and the local NeuroFlow backend
 *   (`http://127.0.0.1:8765`). Every job action goes through it.
 * - SSH channel: SSH between the backend and the remote server. Only Server
 *   jobs need it. SSH failures surface as `{ok: false, error}` payloads from
 *   the backend (or as HTTP timeouts while local requests still succeed).
 */

/** Failures before a channel is reported as down. 1 = warn on the first failure. */
export const MAX_CONNECTION_FAILURES = 1;

/** Timeout for remote job polling. The list endpoint is light and normally
 *  answers in <5s, so 10s fails fast on a dead route without false alarms. */
export const REMOTE_JOBS_TIMEOUT_MS = 10_000;

/** Cap for remote detail (events/log/metrics) fetches. Delta reads should be
 *  quick; hanging the full 60s default hides a dead connection. */
export const REMOTE_DETAIL_TIMEOUT_MS = 20_000;

export type SshHealth = 'connected' | 'degraded' | 'disconnected';
export type BackendHealth = 'ok' | 'degraded' | 'down';

export function nextSshHealth(failures: number): SshHealth {
  if (failures >= MAX_CONNECTION_FAILURES) return 'disconnected';
  if (failures > 0) return 'degraded';
  return 'connected';
}

export function nextBackendHealth(failures: number): BackendHealth {
  if (failures >= MAX_CONNECTION_FAILURES) return 'down';
  if (failures > 0) return 'degraded';
  return 'ok';
}

export type ConnectionWarningKind = 'backend' | 'ssh';

/** Single source of truth for "should we warn?": backend outage always
 *  warns; SSH outage only warns while the Server runtime is in use (and was
 *  connected at least once). Used by the status line and the footer. */
export function getConnectionWarningKind(args: {
  backendStatus: BackendHealth;
  sshStatus: SshHealth;
  connected: boolean;
  sshLastSeenAt: number | null;
  runtimeTarget: string;
}): ConnectionWarningKind | null {
  if (args.backendStatus === 'down') return 'backend';
  if (
    args.sshStatus === 'disconnected' &&
    args.runtimeTarget === 'Server' &&
    (args.connected || args.sshLastSeenAt != null)
  ) {
    return 'ssh';
  }
  return null;
}

/**
 * True when a local-backend request never got a usable HTTP response
 * (backend process down, port closed, network error).
 * App-level `{ok: false}` payloads are NOT included: the backend answered,
 * so the channel itself is alive.
 */
export function isBackendUnreachableMessage(message: string): boolean {
  const msg = String(message || '');
  return /cannot reach neuroflow backend|failed to fetch|networkerror|load failed|econnrefused|econnreset|enotfound|eai_again|socket hang up/i.test(
    msg,
  );
}

/**
 * True when a remote (SSH-leg) request failed for connection reasons:
 * backend-reported "SSH ..." errors, timeouts, or transport failures.
 * App-level errors (bad job dir, unknown file) and user aborts are NOT
 * included: they say nothing about the health of the SSH channel.
 *
 * Note: our own request timeouts abort fetch, so their messages contain
 * both "aborted" and "timed out" — timeout wins over the abort exclusion.
 */
export function isSshConnectionMessage(message: string): boolean {
  const msg = String(message || '');
  if (/timed out|timeout/i.test(msg)) return true;
  if (/abort/i.test(msg)) return false;
  return /ssh|cannot reach|failed to fetch|network|econn|eai_again|socket hang up/i.test(msg);
}

/** True for user/abort-controller cancellations, which must never drive health. */
export function isAbortError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const name = (error as {name?: unknown}).name;
  return (
    name === 'AbortError' ||
    (error instanceof DOMException && error.name === 'AbortError')
  );
}

/**
 * User-facing one-liner for a connection error. Strips internal plumbing
 * (backend URL, abort-controller jargon) that only confuses.
 */
export function shortConnectionError(message: string): string {
  const msg = String(message || '').trim();
  if (!msg) return 'Unknown error.';
  if (/request timed out/i.test(msg)) {
    const endpoint = msg.match(/(\/remote\/[^\s:)]+|\/jobs\/[^\s:)]+)/);
    return endpoint ? `Request to ${endpoint[1]} timed out.` : 'Request timed out.';
  }
  return msg
    .replace(/\s+at https?:\/\/[^/\s:]+(?::\d+)?/, '')
    .replace(/signal is aborted without reason/gi, 'request was cancelled')
    .replace(/\s{2,}/g, ' ')
    .replace(/\s+([.,:;])/g, '$1')
    .trim() || 'Unknown error.';
}

/** Human-readable "last synced" label for stale-data banners. */
export function formatLastSyncedAgo(lastSeenAt: number | null | undefined, now: number = Date.now()): string {
  if (!lastSeenAt || lastSeenAt <= 0) return 'never synced successfully';
  const diffSec = Math.max(0, Math.floor((now - lastSeenAt) / 1000));
  if (diffSec < 5) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${Math.floor(diffHours / 24)}d ago`;
}
