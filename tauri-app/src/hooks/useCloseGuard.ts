import {useEffect} from 'react';
import {getCurrentWindow} from '@tauri-apps/api/window';
import {ask} from '@tauri-apps/plugin-dialog';
import {BackendClient} from '../api/client';
import {buildRemotePayload} from '../api/runConfig';
import {useJobsStore} from '../stores/jobsStore';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useRemoteStore} from '../stores/remoteStore';
import {useUploadStore} from '../stores/uploadStore';

function hasTauriInternals() {
  if (typeof window === 'undefined') return false;
  const internals = (window as unknown as {__TAURI_INTERNALS__?: {invoke?: unknown}}).__TAURI_INTERNALS__;
  return typeof internals?.invoke === 'function';
}

export function useCloseGuard(enabled: boolean) {
  useEffect(() => {
    if (!enabled || !hasTauriInternals()) return;
    let unlisten: (() => void) | undefined;
    let disposed = false;

    void getCurrentWindow()
      .onCloseRequested(async (event) => {
        const remoteConnected = useRemoteStore.getState().connected;
        const uploadsByJob = useUploadStore.getState().uploadsByJob;
        const hasUploads = Object.values(uploadsByJob).some((entries) =>
          entries.some((entry) => entry.state === 'pending' || entry.state === 'uploading'),
        );
        const hasLocalRunning = useJobsStore
          .getState()
          .latestJobs.some(
            (job) =>
              String(job?.target || 'Local') === 'Local' &&
              String(job?.state || '').toLowerCase().includes('run'),
          );

        if (!remoteConnected && !hasUploads && !hasLocalRunning) return;

        event.preventDefault();
        const ok = await ask(
          'A pipeline job is currently running.\nClosing now will CANCEL the job and abort any in-progress uploads.\n\nClose anyway?',
          {title: 'Cancel running job?', kind: 'warning'},
        );
        if (!ok) return;

        const client = new BackendClient();
        const formValues = usePipelineFormStore.getState().formValues;
        try {
          const payload = buildRemotePayload(formValues);
          const jobsByDir = useUploadStore.getState().uploadsByJob;
          await Promise.all(
            Object.keys(jobsByDir).map((remoteJobDir) =>
              client.cancelUploads({...payload, job_id: remoteJobDir}).catch(() => undefined),
            ),
          );
        } catch {
          // best-effort cleanup before exit
        }
        getCurrentWindow().destroy();
      })
      .then((fn) => {
        if (disposed) fn();
        else unlisten = fn;
      });

    return () => {
      disposed = true;
      unlisten?.();
    };
  }, [enabled]);
}
