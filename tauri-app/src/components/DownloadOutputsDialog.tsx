import React, {useEffect, useState} from 'react';
import {
  Check,
  CheckCircle2,
  Clock,
  Copy,
  Download,
  FileText,
  FolderOpen,
  Gauge,
  Loader2,
  Square,
  X,
  XCircle,
} from 'lucide-react';
import {cn} from '@/lib/utils';
import {formatEta, formatFilesPerSec} from '../lib/format';

export interface DownloadStep {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  detail?: string;
}

interface Props {
  open: boolean;
  jobId: string;
  localDir: string;
  phase: 'select' | 'running' | 'success' | 'failed';
  steps: DownloadStep[];
  copiedFiles?: number | undefined;
  totalFiles?: number | undefined;
  speedFilesPerSec?: number | null | undefined;
  etaSeconds?: number | null | undefined;
  finalPath?: string | undefined;
  errorMessage?: string | undefined;
  cancelled?: boolean | undefined;
  onBrowse: () => void;
  onStart: () => void;
  onResume: () => void;
  onClose: () => void;
  onStop?: () => void;
  canClose?: boolean | undefined;
}

function safeJobFolder(jobId: string): string {
  const raw = jobId.trim() || 'server_job_outputs';
  const sanitized = raw.replace(/[/\\:*?"<>|]/g, '_').replace(/^_+|_+$/g, '');
  return sanitized || 'server_job_outputs';
}

function splitCopyDetail(detail: string | undefined): {name: string; dest?: string | undefined} | undefined {
  if (!detail) return undefined;
  const clean = detail.replace(/^(Downloading file:|Skipping existing file:)\s*/i, '');
  const parts = clean.split('→').map((p) => p.trim());
  const name = parts[0] || clean;
  const dest = parts.length > 1 ? parts[parts.length - 1] : undefined;
  return {name, dest};
}

export function DownloadOutputsDialog({
  open,
  jobId,
  localDir,
  phase,
  steps,
  copiedFiles,
  totalFiles,
  speedFilesPerSec,
  etaSeconds,
  finalPath,
  errorMessage,
  cancelled = false,
  onBrowse,
  onStart,
  onResume,
  onClose,
  onStop,
  canClose = true,
}: Props) {
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const running = phase === 'running';
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (running) onStop?.();
      else if (canClose) onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, phase, canClose, onClose, onStop]);

  if (!open) return null;
  const running = phase === 'running';
  const headerCanClose = canClose || (running && onStop != null);

  const title =
    phase === 'select'
      ? 'Download Server Outputs'
      : phase === 'running'
        ? 'Downloading Outputs'
        : phase === 'success'
          ? 'Download Complete'
          : cancelled
            ? 'Download Stopped'
            : 'Download Failed';

  const pct =
    totalFiles && totalFiles > 0 ? Math.min(100, Math.round(((copiedFiles ?? 0) / totalFiles) * 100)) : 0;
  const activeStep = steps.find((s) => s.status === 'running');
  const currentFile =
    running && activeStep?.id === 'copy' ? splitCopyDetail(activeStep.detail) : undefined;
  const trimmedDir = localDir.trim();
  // Single destination box: the job folder is always appended by the backend,
  // so show the final path up front. Join with "\" to match the base style.
  const fullDest = trimmedDir ? `${trimmedDir.replace(/[/\\]+$/g, '')}\\${safeJobFolder(jobId)}` : '';
  const hasRate = typeof speedFilesPerSec === 'number' && speedFilesPerSec > 0;
  const hasEta = typeof etaSeconds === 'number' && Number.isFinite(etaSeconds) && etaSeconds >= 0;

  const handleCopyPath = () => {
    if (!finalPath) return;
    navigator.clipboard.writeText(finalPath).catch(() => {});
    setCopiedPath(finalPath);
    window.setTimeout(() => setCopiedPath(null), 2000);
  };
  const pathCopied = copiedPath != null && copiedPath === finalPath;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/30 p-3"
      onMouseDown={(e) => {
        if (e.target !== e.currentTarget) return;
        if (running) onStop?.();
        else if (canClose) onClose();
      }}
    >
      <div className="relative w-full max-w-[34rem] rounded-lg border border-cursor-hairline bg-cursor-surface-card p-6 shadow-none">
        {/* Header */}
        <div className="mb-5 flex items-start gap-3.5">
          {running && (
            <span className="flex h-12 w-12 flex-none items-center justify-center rounded-full bg-cursor-primary/10 text-cursor-primary">
              <Download className="h-5 w-5" />
            </span>
          )}
          <div className="min-w-0 flex-1">
            <h3 className="m-0 text-base font-semibold leading-tight text-cursor-ink">{title}</h3>
            <p className="m-0 mt-1.5 truncate font-mono text-sm text-cursor-muted" title={jobId}>
              {jobId}
            </p>
          </div>
          {headerCanClose && (
            <button
              type="button"
              onClick={() => {
                if (running) onStop?.();
                else onClose();
              }}
              className="-mr-1 -mt-1 flex-none cursor-pointer rounded-md p-1 text-cursor-muted transition-colors hover:text-cursor-ink"
              title={running ? 'Stop download' : 'Close'}
              aria-label={running ? 'Stop download' : 'Close'}
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Phase: Select destination */}
        {phase === 'select' && (
          <div className="space-y-4">
            <div>
              <p className="m-0 mb-1.5 text-xs font-semibold uppercase tracking-[0.06em] text-cursor-muted">
                Destination
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={fullDest}
                  readOnly
                  placeholder="Choose a folder…"
                  title={fullDest || undefined}
                  className="h-10 min-w-0 flex-1 rounded-md border border-cursor-hairline bg-cursor-canvas-soft px-3 font-mono text-sm text-cursor-muted outline-none placeholder:text-cursor-muted-soft focus:border-cursor-primary"
                  autoFocus
                />
                <button
                  type="button"
                  onClick={onBrowse}
                  className="inline-flex h-10 flex-none cursor-pointer items-center gap-1.5 rounded-md border border-cursor-hairline bg-cursor-surface-card px-3.5 text-sm font-medium text-cursor-ink transition-colors hover:bg-cursor-canvas-soft"
                >
                  <FolderOpen className="h-4 w-4 text-cursor-muted" />
                  Browse
                </button>
              </div>
            </div>

            <div className="flex justify-end gap-2 border-t border-cursor-hairline-soft pt-4">
              <button
                type="button"
                onClick={onClose}
                className="cursor-pointer rounded-md border border-cursor-hairline bg-cursor-surface-card px-4 py-2 text-sm font-medium text-cursor-ink transition-colors hover:bg-cursor-canvas"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={onStart}
                disabled={!trimmedDir}
                className={cn(
                  'inline-flex cursor-pointer items-center gap-1.5 rounded-md border px-4 py-2 text-sm font-medium transition-colors',
                  trimmedDir
                    ? 'border-cursor-primary bg-cursor-primary text-white hover:bg-cursor-primary-active'
                    : 'cursor-not-allowed border-cursor-hairline bg-cursor-canvas text-cursor-muted',
                )}
              >
                <Download className="h-4 w-4" />
                Start Download
              </button>
            </div>
          </div>
        )}

        {/* Phase: Running download */}
        {phase === 'running' && (
          <div className="space-y-3.5">
            <div className="rounded-xl bg-cursor-canvas-soft p-5">
              <div className="flex items-end justify-between gap-3">
                <span className="text-[28px] font-semibold leading-none tabular-nums text-cursor-ink">
                  {pct}%
                </span>
                <span className="text-sm tabular-nums text-cursor-body">
                  {copiedFiles ?? 0} of {totalFiles ?? 0} files
                </span>
              </div>
              <div className="mt-3 h-3 w-full overflow-hidden rounded-full bg-cursor-primary/15">
                <div
                  className="h-full rounded-full bg-cursor-primary transition-all duration-300"
                  style={{width: `${pct}%`}}
                />
              </div>
              {(hasRate || hasEta) && (
                <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-cursor-body">
                  {hasRate && (
                    <span className="inline-flex items-center gap-2 tabular-nums">
                      <Gauge className="h-4 w-4 flex-none text-cursor-muted" />
                      {formatFilesPerSec(speedFilesPerSec)} files/s
                    </span>
                  )}
                  {hasRate && hasEta && (
                    <span className="h-4 w-px flex-none bg-cursor-hairline" aria-hidden="true" />
                  )}
                  {hasEta && (
                    <span className="inline-flex items-center gap-2 tabular-nums">
                      <Clock className="h-4 w-4 flex-none text-cursor-muted" />
                      ETA {formatEta(etaSeconds)}
                    </span>
                  )}
                </div>
              )}
            </div>
            {currentFile && (
              <div className="flex items-center gap-3 rounded-xl bg-cursor-canvas-soft p-4">
                <span className="flex h-10 w-10 flex-none items-center justify-center rounded-lg bg-cursor-primary/10 text-cursor-primary">
                  <FileText className="h-5 w-5" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="m-0 truncate text-sm font-semibold text-cursor-ink" title={currentFile.name}>
                    {currentFile.name}
                  </p>
                  {currentFile.dest && (
                    <p className="m-0 mt-0.5 truncate font-mono text-sm text-cursor-muted" title={currentFile.dest}>
                      {currentFile.dest}
                    </p>
                  )}
                </div>
                <Loader2 className="h-5 w-5 flex-none animate-spin text-cursor-primary" />
              </div>
            )}
            {onStop && (
              <div className="flex justify-end border-t border-cursor-hairline-soft pt-4">
                <button
                  type="button"
                  onClick={onStop}
                  title="Stop now. Files already copied are kept — resume continues where it stopped."
                  className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-cursor-semantic-error/40 bg-cursor-surface-card px-4 py-2 text-sm font-medium text-cursor-semantic-error transition-colors hover:bg-cursor-semantic-error/10"
                >
                  <Square className="h-4 w-4" />
                  Stop Download
                </button>
              </div>
            )}
          </div>
        )}

        {/* Phase: Download Success */}
        {phase === 'success' && (
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="mt-0.5 h-5 w-5 flex-none text-cursor-semantic-success" />
              <div className="min-w-0">
                <p className="m-0 text-sm font-semibold text-cursor-ink">
                  Downloaded {copiedFiles ?? 0} file{(copiedFiles ?? 0) === 1 ? '' : 's'}
                </p>
                {finalPath && (
                  <p className="m-0 mt-1 break-all font-mono text-sm text-cursor-body">{finalPath}</p>
                )}
              </div>
            </div>
            <div className="flex justify-end gap-2 border-t border-cursor-hairline-soft pt-4">
              {finalPath && (
                <button
                  type="button"
                  onClick={handleCopyPath}
                  className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-cursor-hairline bg-cursor-surface-card px-4 py-2 text-sm font-medium text-cursor-ink transition-colors hover:bg-cursor-canvas"
                >
                  {pathCopied ? (
                    <>
                      <Check className="h-4 w-4 text-cursor-semantic-success" />
                      Copied
                    </>
                  ) : (
                    <>
                      <Copy className="h-4 w-4" />
                      Copy Path
                    </>
                  )}
                </button>
              )}
              <button
                type="button"
                onClick={onClose}
                className="cursor-pointer rounded-md border border-cursor-primary bg-cursor-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-cursor-primary-active"
              >
                Close
              </button>
            </div>
          </div>
        )}

        {/* Phase: Download Failed / Stopped */}
        {phase === 'failed' && (
          <div className="space-y-4">
            <div className="flex items-start gap-3">
              <XCircle className="mt-0.5 h-5 w-5 flex-none text-cursor-semantic-error" />
              <p className="m-0 min-w-0 flex-1 break-words text-sm text-cursor-body">
                {errorMessage || (cancelled ? 'Download stopped.' : 'Download failed.')}
              </p>
            </div>
            <div className="flex justify-end gap-2 border-t border-cursor-hairline-soft pt-4">
              <button
                type="button"
                onClick={onClose}
                className="cursor-pointer rounded-md border border-cursor-hairline bg-cursor-surface-card px-4 py-2 text-sm font-medium text-cursor-ink transition-colors hover:bg-cursor-canvas"
              >
                Close
              </button>
              <button
                type="button"
                onClick={onResume}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-cursor-primary bg-cursor-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-cursor-primary-active"
              >
                <Download className="h-4 w-4" />
                {cancelled ? 'Resume Download' : 'Retry'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
