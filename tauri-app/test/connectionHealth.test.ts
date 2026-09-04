import {describe, it, expect, beforeEach} from 'vitest';
import {useRemoteStore} from '../src/stores/remoteStore';
import {
  MAX_CONNECTION_FAILURES,
  REMOTE_DETAIL_TIMEOUT_MS,
  REMOTE_JOBS_TIMEOUT_MS,
  formatLastSyncedAgo,
  isAbortError,
  isBackendUnreachableMessage,
  isSshConnectionMessage,
  nextBackendHealth,
  nextSshHealth,
  shortConnectionError,
} from '../src/lib/connection';

describe('connection health thresholds', () => {
  it('reports down from the very first failure', () => {
    expect(nextSshHealth(0)).toBe('connected');
    expect(nextSshHealth(1)).toBe('disconnected');
    expect(nextBackendHealth(0)).toBe('ok');
    expect(nextBackendHealth(1)).toBe('down');
    expect(MAX_CONNECTION_FAILURES).toBe(1);
  });

  it('classifies transport-level backend errors only (not app-level ok:false payloads)', () => {
    expect(isBackendUnreachableMessage('Cannot reach NeuroFlow backend at http://127.0.0.1:8765/jobs/local: Failed to fetch')).toBe(true);
    expect(isBackendUnreachableMessage('Cannot reach NeuroFlow backend at http://127.0.0.1:8765/remote/jobs: xxx (request timed out)')).toBe(true);
    expect(isBackendUnreachableMessage('SSH connection failed: timeout')).toBe(false);
    expect(isBackendUnreachableMessage('')).toBe(false);
  });

  it('classifies SSH-leg connection errors without matching app errors or aborts', () => {
    expect(isSshConnectionMessage('SSH connection failed: timeout')).toBe(true);
    expect(isSshConnectionMessage('Cannot reach NeuroFlow backend at http://127.0.0.1:8765/remote/jobs/events: x (request timed out)')).toBe(true);
    expect(isSshConnectionMessage('Failed to fetch')).toBe(true);
    // App-level errors say nothing about channel health.
    expect(isSshConnectionMessage('events.jsonl not found')).toBe(false);
    expect(isSshConnectionMessage('unknown job')).toBe(false);
    expect(isSshConnectionMessage('')).toBe(false);
    // User aborts must never drive health — but our own timeout aborts do.
    expect(isSshConnectionMessage('The operation was aborted')).toBe(false);
    expect(isSshConnectionMessage('signal is aborted without reason')).toBe(false);
    expect(isSshConnectionMessage('signal is aborted without reason (request timed out)')).toBe(true);
  });

  it('detects abort errors so cancellations never count as failures', () => {
    const abort = new DOMException('The operation was aborted', 'AbortError');
    expect(isAbortError(abort)).toBe(true);
    expect(isAbortError(new Error('boom'))).toBe(false);
    expect(isAbortError(null)).toBe(false);
    expect(isAbortError('AbortError')).toBe(false);
  });

  it('shortens internal connection errors for display', () => {
    expect(
      shortConnectionError(
        'Cannot reach NeuroFlow backend at http://127.0.0.1:8765/remote/jobs: signal is aborted without reason (request timed out)',
      ),
    ).toBe('Request to /remote/jobs timed out.');
    expect(shortConnectionError('Cannot reach NeuroFlow backend at http://127.0.0.1:8765: Failed to fetch')).toBe(
      'Cannot reach NeuroFlow backend: Failed to fetch',
    );
    expect(shortConnectionError('')).toBe('Unknown error.');
  });

  it('keeps detection budgets tight so a dead route warns fast', () => {
    // Worst case to banner ≈ confirm poll + 2 request timeouts.
    // Guard against regressions back to 60s hangs.
    expect(REMOTE_JOBS_TIMEOUT_MS).toBeLessThanOrEqual(10_000);
    expect(REMOTE_DETAIL_TIMEOUT_MS).toBeLessThanOrEqual(20_000);
    expect(MAX_CONNECTION_FAILURES).toBe(1);
  });

  it('formats last-synced labels without crashing on null', () => {
    expect(formatLastSyncedAgo(null)).toBe('never synced successfully');
    expect(formatLastSyncedAgo(Date.now())).toBe('just now');
    expect(formatLastSyncedAgo(Date.now() - 5 * 60_000)).toContain('m ago');
  });
});

describe('remoteStore connection health', () => {
  beforeEach(() => {
    useRemoteStore.getState().reset();
  });

  it('moves SSH to disconnected on the first failure and recovers on success', () => {
    const store = useRemoteStore.getState();
    store.reportSshFailure('boom 1');
    const down = useRemoteStore.getState();
    expect(down.sshStatus).toBe('disconnected');
    expect(down.sshLastError).toBe('boom 1');

    useRemoteStore.getState().reportSshSuccess();
    const recovered = useRemoteStore.getState();
    expect(recovered.sshStatus).toBe('connected');
    expect(recovered.sshFailures).toBe(0);
    expect(recovered.sshLastSeenAt).toBeTypeOf('number');
  });

  it('moves backend to down on the first failure and recovers on success', () => {
    const store = useRemoteStore.getState();
    store.reportBackendFailure('down 1');
    expect(useRemoteStore.getState().backendStatus).toBe('down');

    useRemoteStore.getState().reportBackendSuccess();
    expect(useRemoteStore.getState().backendStatus).toBe('ok');
    expect(useRemoteStore.getState().backendFailures).toBe(0);
  });

  it('explicit connect result drives SSH health directly', () => {
    useRemoteStore.getState().setSshDisconnected('auth failed');
    expect(useRemoteStore.getState().sshStatus).toBe('disconnected');
    useRemoteStore.getState().setSshConnected();
    expect(useRemoteStore.getState().sshStatus).toBe('connected');
    expect(useRemoteStore.getState().sshFailures).toBe(0);
  });
});
