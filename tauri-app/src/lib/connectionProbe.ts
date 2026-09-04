import {BackendClient, DEFAULT_BACKEND_URL} from '../api/client';
import {buildRemotePayload, type PipelineFormValues} from '../api/runConfig';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useRemoteStore} from '../stores/remoteStore';
import {isBackendUnreachableMessage, isSshConnectionMessage, REMOTE_JOBS_TIMEOUT_MS} from './connection';

export interface ProbeResult {
  backendOk: boolean;
  sshOk: boolean;
}

/**
 * Lightweight manual re-check of both channels (footer Retry). Mirrors the
 * classification in JobsPage.refreshJobs but fetches no job data: on success
 * the warning line disappears and normal polling resumes; on failure the
 * counters keep climbing toward the banner threshold. Never throws.
 */
export async function probeConnectionHealth(formValues?: PipelineFormValues): Promise<ProbeResult> {
  const fv = formValues ?? usePipelineFormStore.getState().formValues;
  const health = () => useRemoteStore.getState();
  const client = new BackendClient(DEFAULT_BACKEND_URL);

  let backendOk = health().backendStatus !== 'down';
  try {
    await client.listLocalJobs();
    // Any usable HTTP answer (even `{ok: false}`) proves the backend is up.
    health().reportBackendSuccess();
    backendOk = true;
  } catch (err: unknown) {
    const message = (err as Error)?.message || 'Backend request failed.';
    if (isBackendUnreachableMessage(message)) {
      health().reportBackendFailure(message);
      backendOk = false;
    } else {
      health().reportBackendSuccess();
      backendOk = true;
    }
  }

  // Re-read: the backend leg may have just changed above.
  const {connected, sshStatus} = health();
  let sshOk = sshStatus !== 'disconnected';
  if (connected && backendOk) {
    try {
      const remoteRes = await client.listRemoteJobs(buildRemotePayload(fv), REMOTE_JOBS_TIMEOUT_MS);
      if (remoteRes.ok === false) {
        const message = remoteRes.error || 'Server jobs request failed.';
        if (isSshConnectionMessage(message)) {
          health().reportSshFailure(message);
          sshOk = false;
        }
      } else {
        health().reportSshSuccess();
        sshOk = true;
      }
    } catch (err: unknown) {
      // Local already proved the backend is up, so any throw here is the SSH leg.
      const message = (err as Error)?.message || 'Server jobs request failed.';
      health().reportSshFailure(message);
      sshOk = false;
    }
  }
  return {backendOk, sshOk};
}
