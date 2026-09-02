import React from 'react';
import {CheckCircle2, XCircle, Circle, Loader2, Download, FolderOpen, X} from 'lucide-react';
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
}: Props) {
  if (!open) return null;

  const title =
    phase === 'select'
      ? 'Download Server Outputs'
      : phase === 'running'
        ? 'Downloading Outputs...'
        : phase === 'success'
          ? 'Download Complete'
          : 'Download Failed';

  const pct = totalFiles && totalFiles > 0 ? Math.min(100, Math.round(((copiedFiles ?? 0) / totalFiles) * 100)) : 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && canClose) onClose();
      }}
    >
      <div className="relative w-full max-w-[34rem] rounded-lg border border-cursor-hairline bg-cursor-surface-card p-6 shadow-md">
        {/* Header */}
        <div className="flex items-start justify-between gap-2 mb-5">
          <div>
            <h3 className="m-0 text-base font-semibold leading-tight text-cursor-ink">{title}</h3>
            <p className="m-0 mt-1 text-xs text-cursor-muted">
              Job: <span className="font-mono text-cursor-body">{jobId}</span>
            </p>
          </div>
          {canClose && (
            <button
              type="button"
              onClick={onClose}
              className="text-cursor-muted hover:text-cursor-ink transition-colors p-1 -mr-1 -mt-1 rounded-md cursor-pointer"
              title="Close"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Phase: Select destination */}
        {phase === 'select' && (
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-cursor-ink mb-1.5">
                Save outputs to
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={localDir}
                  readOnly
                  placeholder="Select a destination folder with Browse..."
                  className="flex-1 rounded-md border border-cursor-hairline bg-cursor-canvas-soft px-3 py-2 text-sm text-cursor-muted placeholder:text-cursor-muted-soft focus:outline-none focus:ring-1 focus:ring-cursor-primary h-10 font-mono"
                  autoFocus
                />
                <button
                  type="button"
                  onClick={onBrowse}
                  className="inline-flex h-10 items-center gap-1.5 rounded-md border border-cursor-hairline bg-cursor-surface-card px-3.5 text-xs font-medium text-cursor-ink hover:bg-cursor-canvas-soft transition-colors cursor-pointer flex-none"
                >
                  <FolderOpen className="h-4 w-4 text-cursor-muted" />
                  Browse
                </button>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-cursor-hairline-soft">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-cursor-hairline bg-cursor-surface-card px-4 py-2 text-xs font-medium text-cursor-ink hover:bg-cursor-canvas transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={onStart}
                disabled={!localDir.trim()}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md border px-4 py-2 text-xs font-medium transition-colors cursor-pointer',
                  localDir.trim()
                    ? 'border-cursor-primary bg-cursor-primary text-white hover:bg-cursor-primary-active'
                    : 'border-cursor-hairline bg-cursor-canvas text-cursor-muted cursor-not-allowed',
                )}
              >
                <Download className="h-3.5 w-3.5" />
                Start Download
              </button>
            </div>
          </div>
        )}

        {/* Phase: Running download */}
        {phase === 'running' && (
          <div className="space-y-3.5">
            {totalFiles != null && totalFiles > 0 && (
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs text-cursor-body">
                    {copiedFiles ?? 0} of {totalFiles} files
                  </span>
                  <span className="text-xs font-semibold text-cursor-primary">{pct}%</span>
                </div>
                <div className="w-full h-1.5 rounded-full bg-cursor-canvas border border-cursor-hairline overflow-hidden">
                  <div
                    className="h-full bg-cursor-primary transition-all duration-300"
                    style={{width: `${pct}%`}}
                  />
                </div>
              </div>
            )}
            <div className="space-y-2">
              {steps.map((step) => (
                <div key={step.id} className="flex items-start gap-2.5">
                  <div className="pt-0.5">
                    <StepIcon status={step.status} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p
                      className={cn(
                        'm-0 text-xs leading-normal',
                        step.status === 'pending' ? 'text-cursor-muted-soft' : 'font-medium text-cursor-ink',
                      )}
                    >
                      {step.label}
                    </p>
                    {step.detail && (step.id !== 'copy' || step.status === 'failed') && (
                      <p
                        className={cn(
                          'm-0 mt-0.5 text-2xs leading-normal break-all',
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
              <div className="max-h-24 overflow-x-hidden overflow-y-auto rounded-md border border-cursor-hairline bg-cursor-canvas-soft p-2">
                {logs.slice(-10).map((line, i) => (
                  <p key={i} className="m-0 font-mono text-2xs text-cursor-body leading-relaxed break-all whitespace-pre-wrap">{line}</p>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Phase: Download Success */}
        {phase === 'success' && (
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="h-5 w-5 flex-none text-cursor-semantic-success mt-0.5" />
              <div className="space-y-1">
                <p className="m-0 text-sm font-semibold text-cursor-ink">
                  Downloaded {copiedFiles ?? 0} file{(copiedFiles ?? 0) === 1 ? '' : 's'} successfully
                </p>
                {finalPath && (
                  <div className="mt-1.5 rounded-md border border-cursor-hairline bg-cursor-canvas-soft px-2.5 py-1.5 font-mono text-xs text-cursor-body break-all">
                    {finalPath}
                  </div>
                )}
              </div>
            </div>
            <div className="flex justify-end pt-2 border-t border-cursor-hairline-soft">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-cursor-primary bg-cursor-primary px-4 py-1.5 text-xs font-medium text-white hover:bg-cursor-primary-active transition-colors cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        )}

        {/* Phase: Download Failed */}
        {phase === 'failed' && (
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <XCircle className="h-5 w-5 flex-none text-cursor-semantic-error mt-0.5" />
              <div className="space-y-1">
                <p className="m-0 text-sm font-semibold text-cursor-ink">Download failed</p>
                {errorMessage && (
                  <p className="m-0 mt-0.5 text-xs text-cursor-semantic-error break-all">{errorMessage}</p>
                )}
              </div>
            </div>
            <div className="flex justify-end pt-2 border-t border-cursor-hairline-soft">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-cursor-hairline bg-cursor-surface-card px-3.5 py-1.5 text-xs font-medium text-cursor-ink hover:bg-cursor-canvas transition-colors cursor-pointer"
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

