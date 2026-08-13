import React from 'react';
import {CheckCircle2, XCircle, Circle, Loader2, Download, FolderOpen} from 'lucide-react';
import {cn} from '@/lib/utils';

export interface DownloadStep {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  detail?: string;
}

interface Props {
  open: boolean;
  jobId: string;
  remotePath: string;
  localDir: string;
  onLocalDirChange: (path: string) => void;
  phase: 'select' | 'running' | 'success' | 'failed';
  steps: DownloadStep[];
  logs: string[];
  copiedFiles?: number | undefined;
  totalFiles?: number | undefined;
  finalPath?: string | undefined;
  errorMessage?: string | undefined;
  onBrowse: () => void;
  onStart: () => void;
  onClose: () => void;
  canClose?: boolean | undefined;
  webBrowseHint?: boolean | undefined;
}

function StepIcon({status}: {status: DownloadStep['status']}) {
  if (status === 'done') return <CheckCircle2 className="h-4 w-4 flex-none text-cursor-semantic-success" />;
  if (status === 'failed') return <XCircle className="h-4 w-4 flex-none text-cursor-semantic-error" />;
  if (status === 'running') return <Loader2 className="h-4 w-4 flex-none animate-spin text-cursor-primary" />;
  return <Circle className="h-4 w-4 flex-none text-cursor-muted-soft" />;
}

export function DownloadOutputsDialog({
  open,
  jobId,
  remotePath,
  localDir,
  onLocalDirChange,
  phase,
  steps,
  logs,
  copiedFiles,
  totalFiles,
  finalPath,
  errorMessage,
  onBrowse,
  onStart,
  onClose,
  canClose = true,
  webBrowseHint = false,
}: Props) {
  if (!open) return null;

  const title =
    phase === 'select'
      ? 'Download Server Outputs'
      : phase === 'running'
        ? 'Copying Outputs...'
        : phase === 'success'
          ? 'Download Complete'
          : 'Download Failed';

  const pct = totalFiles && totalFiles > 0 ? Math.min(100, Math.round(((copiedFiles ?? 0) / totalFiles) * 100)) : 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/30 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && canClose) onClose();
      }}
    >
      <div className="relative w-full max-w-[min(32rem,calc(100vw-2rem))] rounded-xl border border-cursor-hairline bg-white p-6 shadow-none">
        <h3 className="m-0 mb-1 text-[16px] font-semibold leading-[1.4] text-cursor-ink">{title}</h3>
        <p className="m-0 mb-4 text-[12px] text-cursor-muted">Remote job: <span className="font-mono">{jobId}</span></p>

        {phase === 'select' && (
          <div className="space-y-4">
            <div>
              <label className="block text-[12px] font-semibold text-cursor-muted uppercase tracking-[0.06em] mb-1.5">Remote output path</label>
              <div className="rounded-md border border-cursor-hairline bg-cursor-canvas-soft px-3 py-2 font-mono text-[12px] text-cursor-body break-all">
                {remotePath || '(will use default remote output path)'}
              </div>
            </div>
            <div>
              <label className="block text-[12px] font-semibold text-cursor-muted uppercase tracking-[0.06em] mb-1.5">Local destination folder</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={localDir}
                  onChange={(e) => onLocalDirChange(e.target.value)}
                  placeholder="Select or type a local folder..."
                  className="flex-1 rounded-md border border-cursor-hairline bg-white px-3 py-2 text-[13px] text-cursor-ink placeholder:text-cursor-muted-soft focus:outline-none focus:ring-1 focus:ring-cursor-primary h-10 font-mono"
                />
                <button
                  type="button"
                  onClick={onBrowse}
                  className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-cursor-hairline bg-white px-3 text-[13px] font-medium text-cursor-ink hover:bg-cursor-canvas-soft transition-colors cursor-pointer"
                >
                  <FolderOpen className="h-4 w-4" />
                  Browse
                </button>
              </div>
              {webBrowseHint && (
                <p className="m-0 mt-1.5 text-[11px] text-cursor-primary">Type or paste a local folder path in this web preview.</p>
              )}
              <p className="m-0 mt-1.5 text-[11px] text-cursor-muted">A job folder will be created inside this destination.</p>
              {localDir.trim() && jobId && (
                <p className="m-0 mt-1 text-[11px] text-cursor-body font-mono">Final folder: {localDir.trim()}/{jobId}</p>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-cursor-hairline bg-white px-4 py-2 text-[13px] font-medium text-cursor-ink hover:bg-cursor-canvas transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={onStart}
                disabled={!localDir.trim()}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg border px-4 py-2 text-[13px] font-medium transition-colors cursor-pointer',
                  localDir.trim()
                    ? 'border-cursor-primary bg-cursor-primary text-white hover:bg-cursor-primary-active'
                    : 'border-cursor-hairline bg-cursor-canvas text-cursor-muted cursor-not-allowed',
                )}
              >
                <Download className="h-4 w-4" />
                Start Download
              </button>
            </div>
          </div>
        )}

        {phase === 'running' && (
          <div className="space-y-4">
            {totalFiles != null && totalFiles > 0 && (
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[12px] text-cursor-body">{copiedFiles ?? 0} of {totalFiles} files</span>
                  <span className="text-[12px] font-semibold text-cursor-primary">{pct}%</span>
                </div>
                <div className="w-full h-2 rounded-full bg-cursor-canvas border border-cursor-hairline overflow-hidden">
                  <div
                    className="h-full bg-cursor-primary transition-all duration-300"
                    style={{width: `${pct}%`}}
                  />
                </div>
              </div>
            )}
            <div className="space-y-2">
              {steps.map((step) => (
                <div key={step.id} className="flex items-start gap-3">
                  <div className="pt-0.5">
                    <StepIcon status={step.status} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p
                      className={cn(
                        'm-0 text-[13px] leading-[1.4]',
                        step.status === 'pending' ? 'text-cursor-muted-soft' : 'font-medium text-cursor-ink',
                      )}
                    >
                      {step.label}
                    </p>
                    {step.detail && (
                      <p
                        className={cn(
                          'm-0 mt-0.5 text-[12px] leading-[1.4]',
                          step.status === 'failed' ? 'text-cursor-semantic-error' : 'text-cursor-muted',
                        )}
                      >
                        {step.detail}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
            {logs.length > 0 && (
              <div className="max-h-32 overflow-auto rounded-md border border-cursor-hairline bg-cursor-canvas-soft p-2">
                {logs.slice(-10).map((line, i) => (
                  <p key={i} className="m-0 font-mono text-[11px] text-cursor-body leading-relaxed">{line}</p>
                ))}
              </div>
            )}
          </div>
        )}

        {phase === 'success' && (
          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="h-5 w-5 flex-none text-cursor-semantic-success mt-0.5" />
              <div>
                <p className="m-0 text-[14px] font-medium text-cursor-ink">
                  Copied {copiedFiles ?? 0} file{(copiedFiles ?? 0) === 1 ? '' : 's'} successfully.
                </p>
                <p className="m-0 mt-1 text-[12px] text-cursor-muted">Local path:</p>
                <div className="mt-1 rounded-md border border-cursor-hairline bg-cursor-canvas-soft px-3 py-2 font-mono text-[12px] text-cursor-body break-all">
                  {finalPath}
                </div>
              </div>
            </div>
            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-cursor-primary bg-cursor-primary px-4 py-2 text-[13px] font-medium text-white hover:bg-cursor-primary-active transition-colors cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        )}

        {phase === 'failed' && (
          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <XCircle className="h-5 w-5 flex-none text-cursor-semantic-error mt-0.5" />
              <div>
                <p className="m-0 text-[14px] font-medium text-cursor-ink">Download failed.</p>
                {errorMessage && (
                  <p className="m-0 mt-1 text-[12px] text-cursor-semantic-error">{errorMessage}</p>
                )}
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-cursor-hairline bg-white px-4 py-2 text-[13px] font-medium text-cursor-ink hover:bg-cursor-canvas transition-colors cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
