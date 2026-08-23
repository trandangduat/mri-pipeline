import React from 'react';
import {UploadCloud, Loader2, CheckCircle2, XCircle} from 'lucide-react';
import {BackendClient} from '../api/client';
import {buildRemotePayload} from '../api/runConfig';
import {usePipelineFormStore} from '../stores/pipelineFormStore';

const POLL_INTERVAL_MS = 2000;

interface UploadEntry {
  staging_path: string;
  subject: string;
  pct: number;
  state: string;
  error?: string;
}

export function LazyUploadProgress({jobId, remoteJobDir}: {jobId: string; remoteJobDir: string}) {
  const formValues = usePipelineFormStore((s) => s.formValues);
  const [uploads, setUploads] = React.useState<UploadEntry[]>([]);
  const [terminal, setTerminal] = React.useState(false);
  const [sawAny, setSawAny] = React.useState(false);

  React.useEffect(() => {
    if (!jobId || !remoteJobDir) return;
    let cancelled = false;
    let timer: number | undefined;
    const client = new BackendClient();

    const poll = async () => {
      try {
        const payload = buildRemotePayload(formValues);
        const result = await client.fetchUploadState({...payload, job_id: remoteJobDir});
        if (cancelled) return;
        const list = Array.isArray(result?.uploads) ? (result.uploads as UploadEntry[]) : [];
        setUploads(list);
        if (list.length > 0) setSawAny(true);
        if (result?.terminal) {
          setTerminal(true);
          return;
        }
      } catch {
        // backend unreachable or no active upload — keep polling quietly
      }
      if (!cancelled) timer = window.setTimeout(poll, POLL_INTERVAL_MS);
    };
    void poll();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [jobId, remoteJobDir, formValues]);

  if (!sawAny || terminal) return null;

  const uploading = uploads.filter((u) => u.state === 'uploading' || u.state === 'pending');
  const done = uploads.filter((u) => u.state === 'ready').length;
  const failed = uploads.filter((u) => u.state === 'failed');

  return (
    <div className="mt-2.5 rounded-md border border-cursor-hairline bg-cursor-surface-card p-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-cursor-ink">
          <UploadCloud className="h-3.5 w-3.5 text-cursor-primary" />
          <span>
            Uploading inputs {done}/{uploads.length}
            {failed.length > 0 ? ` · ${failed.length} failed` : ''}
          </span>
        </div>
        {uploading.length > 0 && <Loader2 className="h-3 w-3 animate-spin text-cursor-muted" />}
      </div>
      <div className="mt-1.5 grid gap-1">
        {uploads.map((entry) => (
          <div key={entry.staging_path} className="flex items-center gap-2 text-2xs text-cursor-muted">
            {entry.state === 'ready' ? (
              <CheckCircle2 className="h-3 w-3 flex-none text-cursor-semantic-success" />
            ) : entry.state === 'failed' || entry.state === 'cancelled' ? (
              <span title={entry.error || ''} className="flex-none inline-flex">
                <XCircle className="h-3 w-3 text-cursor-semantic-error" />
              </span>
            ) : (
              <Loader2 className="h-3 w-3 flex-none animate-spin" />
            )}
            <span className="w-24 truncate flex-none font-medium">{entry.subject}</span>
            <div className="h-1 min-w-0 flex-1 overflow-hidden rounded-full bg-cursor-canvas-soft">
              <div
                className={`h-full rounded-full ${entry.state === 'failed' ? 'bg-cursor-semantic-error' : 'bg-cursor-primary'}`}
                style={{width: `${Math.round(entry.pct)}%`}}
              />
            </div>
            <span className="w-10 flex-none text-right tabular-nums">{Math.round(entry.pct)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
