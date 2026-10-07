import React, {useEffect, useState} from 'react';
import {CheckCircle2, XCircle, Circle, Loader2, Download, AlertCircle, ArrowRight, Check} from 'lucide-react';
import {cn} from '@/lib/utils';
import {ModalPortal} from './ModalPortal';
import {resolveSurfaceAtlasPackId} from '../lib/atlasPacks';
import {useDownloadAtlasStream} from '../query/useAtlases';

export interface ResourceSolutions {
  summary: string;
  increaseRamPercent: number | null;
  presets: string[];
}

export interface PipelineStep {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  detail?: string;
  solutions?: ResourceSolutions;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onCancel?: () => void;
  steps: PipelineStep[];
  complete: boolean;
  success: boolean;
  errorMessage?: string;
  onApplyRamPercent?: (percent: number) => void;
  onApplyPreset?: (mode: string) => void;
}

function StepIcon({status}: {status: PipelineStep['status']}) {
  if (status === 'done') return <CheckCircle2 className="h-4 w-4 flex-none text-cursor-semantic-success" />;
  if (status === 'failed') return <XCircle className="h-4 w-4 flex-none text-cursor-semantic-error" />;
  if (status === 'running') return <Loader2 className="h-4 w-4 flex-none animate-spin text-cursor-primary" />;
  return <Circle className="h-4 w-4 flex-none text-cursor-muted-soft" />;
}

function resolveAtlasPackId(key: string): string {
  const norm = key.toLowerCase();
  const schaeferPack = resolveSurfaceAtlasPackId(key);
  if (schaeferPack) return schaeferPack;
  if (norm.includes('destrieux')) return 'destrieux';
  if (norm.includes('kong')) return 'kong2022';
  if (norm.includes('yale')) return 'yale';
  return key;
}

function SolutionApplyButton({onClick}: {onClick: () => void}) {
  return (
    <button
      type="button"
      className="flex h-full w-full cursor-pointer items-center justify-center gap-1 border-0 bg-cursor-primary/10 px-3 py-1.5 text-xs font-medium text-cursor-primary transition-colors hover:bg-cursor-primary/20"
      onClick={onClick}
    >
      <ArrowRight className="h-3 w-3" />
      Apply
    </button>
  );
}

function ResourceSolutionsList({
  solutions,
  onApplyRamPercent,
  onApplyPreset,
  onClose,
}: {
  solutions: ResourceSolutions;
  onApplyRamPercent?: ((percent: number) => void) | undefined;
  onApplyPreset?: ((mode: string) => void) | undefined;
  onClose: () => void;
}) {
  const showIncrease = typeof solutions.increaseRamPercent === 'number';
  const showPresets = solutions.presets.length > 0;

  return (
    <div className="mt-0.5">
      <p className="m-0 text-xs leading-[1.35] text-cursor-semantic-error">{solutions.summary}</p>
      {(showIncrease || showPresets) && (
        <div className="mt-1.5 text-xs leading-[1.35] text-cursor-ink">
          <p className="m-0 font-medium">Solutions:</p>
          <div className="mt-1 overflow-hidden rounded-lg border border-cursor-hairline">
          <table className="w-full border-separate border-spacing-0 [&>tbody>tr:not(:last-child)>td]:border-b [&_td]:border-cursor-hairline">
            <tbody>
              {showIncrease && (
                <tr>
                  <td className="border-r border-cursor-hairline px-2 py-1 align-middle">Increase RAM allocation to {solutions.increaseRamPercent}%</td>
                  <td className="w-[1%] p-0 text-center align-middle whitespace-nowrap">
                    <SolutionApplyButton
                      onClick={() => {
                        onApplyRamPercent?.(solutions.increaseRamPercent as number);
                        onClose();
                      }}
                    />
                  </td>
                </tr>
              )}
              {solutions.presets.map((preset) => (
                <tr key={preset}>
                  <td className="border-r border-cursor-hairline px-2 py-1 align-middle">Use preset: {preset}</td>
                  <td className="w-[1%] p-0 text-center align-middle whitespace-nowrap">
                    <SolutionApplyButton
                      onClick={() => {
                        onApplyPreset?.(preset);
                        onClose();
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </div>
  );
}

export function StartPipelineDialog({
  open,
  onClose,
  onCancel,
  steps,
  complete,
  success,
  errorMessage,
  onApplyRamPercent,
  onApplyPreset,
}: Props) {
  const atlasStream = useDownloadAtlasStream();
  const [donePacks, setDonePacks] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (atlasStream.status === 'success' && atlasStream.packId) {
      setDonePacks((prev) => new Set(prev).add(atlasStream.packId as string));
    }
  }, [atlasStream.status, atlasStream.packId]);
  // Allow Esc to cancel an in-flight preflight, or close when finished.
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (complete) onClose();
      else onCancel?.();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [open, complete, onClose, onCancel]);
  if (!open) return null;

  const rawAtlasError = errorMessage || steps.find((s) => s.status === 'failed')?.detail || '';
   const missingAtlasKeys = Array.from(
     rawAtlasError.matchAll(/Atlas ['"]([^'"]+)['"] content is not installed/gi),
     (m) => m[1] as string,
   );


  const missingPackIds = new Set(missingAtlasKeys.map((key) => resolveAtlasPackId(key)));
  const allInstalled = missingPackIds.size > 0 && Array.from(missingPackIds).every((id) => donePacks.has(id));

  const isDuplicateError =
    Boolean(errorMessage) &&
    steps.some(
      (step) =>
        step.status === 'failed' &&
        Boolean(step.detail) &&
        step.detail?.trim() === errorMessage?.trim(),
    );

  return (
    <ModalPortal>
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/30 p-3"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && complete) onClose();
      }}
    >
      <div className="relative w-full max-w-[36rem] rounded-lg border border-cursor-hairline bg-cursor-surface-card p-4 shadow-none">
        <div className="mb-3 flex items-start justify-between gap-2">
          <h3 className="m-0 text-base font-semibold leading-[1.3] text-cursor-ink">
            {complete ? (success ? 'Pipeline Started' : 'Start Failed') : 'Starting Pipeline...'}
          </h3>
          {onCancel && !complete && (
            <button
              type="button"
              onClick={onCancel}
              title="Cancel preflight (Esc)"
              className="flex h-6 w-6 flex-none items-center justify-center rounded-md text-cursor-muted hover:bg-cursor-canvas hover:text-cursor-ink transition-colors cursor-pointer"
              aria-label="Cancel preflight"
            >
              ✕
            </button>
          )}
        </div>
        <div className="flex flex-col gap-2">
          {steps.map((step) => (
            <div key={step.id} className="flex items-start gap-2.5">
              <div className="pt-0.5">
                <StepIcon status={step.status} />
              </div>
              <div className="flex-1 min-w-0">
                <p
                  className={cn(
                    'm-0 text-sm leading-[1.3]',
                    step.status === 'pending' ? 'text-cursor-muted-soft' : 'font-medium text-cursor-ink',
                  )}
                >
                  {step.label}
                </p>
                {step.solutions ? (
                  <ResourceSolutionsList
                    solutions={step.solutions}
                    onApplyRamPercent={onApplyRamPercent}
                    onApplyPreset={onApplyPreset}
                    onClose={onClose}
                  />
                ) : step.status === 'failed' && missingAtlasKeys.length > 0 ? (
                  <div className="mt-1.5">
                    <p className="m-0 text-xs font-medium text-cursor-ink">Missing atlases ({missingAtlasKeys.length}):</p>
                    <div className="mt-1 overflow-hidden rounded-lg border border-cursor-hairline">
                      <table className="w-full border-separate border-spacing-0 [&>tbody>tr:not(:last-child)>td]:border-b [&_td]:border-cursor-hairline">
                        <tbody>
                          {missingAtlasKeys.map((atlasKey) => {
                            const packId = resolveAtlasPackId(atlasKey);
                            const isActive = atlasStream.packId === packId;
                            const isDownloading = isActive && ['connecting', 'downloading', 'extracting'].includes(atlasStream.status);
                            return (
                              <tr key={atlasKey}>
                                <td className="border-r border-cursor-hairline px-2 py-1 align-middle text-xs text-cursor-ink">{atlasKey}</td>
                                <td className="w-28 p-0 align-middle whitespace-nowrap">
                                  {isDownloading ? (
                                    <div className="relative w-28 overflow-hidden bg-cursor-primary/10 px-3 py-1.5 text-center text-xs font-medium text-cursor-primary">
                                      <div
                                        className="absolute inset-y-0 left-0 bg-cursor-primary/25 transition-all duration-300"
                                        style={{width: `${atlasStream.percent}%`}}
                                      />
                                      <span className="relative">{atlasStream.percent}%</span>
                                    </div>
                                  ) : donePacks.has(packId) ? (
                                    <span className="flex items-center justify-center gap-1 px-3 py-1.5 text-xs font-medium text-cursor-semantic-success">
                                      <Check className="h-3 w-3" />
                                      Installed
                                    </span>
                                  ) : isActive && atlasStream.status === 'failed' ? (
                                    <button
                                      type="button"
                                      onClick={() => atlasStream.download(packId)}
                                      className="flex w-28 cursor-pointer items-center justify-center gap-1 border-0 bg-cursor-semantic-error/10 px-3 py-1.5 text-xs font-medium text-cursor-semantic-error transition-colors hover:bg-cursor-semantic-error/20"
                                    >
                                      Retry
                                    </button>
                                  ) : (
                                    <button
                                      type="button"
                                      onClick={() => atlasStream.download(packId)}
                                      className="flex w-28 cursor-pointer items-center justify-center gap-1 border-0 bg-cursor-primary/10 px-3 py-1.5 text-xs font-medium text-cursor-primary transition-colors hover:bg-cursor-primary/20"
                                    >
                                      <Download className="h-3 w-3" />
                                      Download
                                    </button>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    {allInstalled && (
                      <p className="mt-1.5 text-2xs font-medium text-cursor-semantic-success">
                        Installed! Close this dialog and retry starting the pipeline.
                      </p>
                    )}
                    {atlasStream.status === 'failed' && atlasStream.error && (
                      <p className="mt-1.5 text-2xs text-cursor-semantic-error">{atlasStream.error}</p>
                    )}
                  </div>
                ) : (
                  step.detail && (
                    <p
                      className={cn(
                        'm-0 mt-0.5 text-xs leading-[1.3] whitespace-pre-line',
                        step.status === 'failed' ? 'text-cursor-semantic-error' : 'text-cursor-muted',
                      )}
                    >
                      {step.detail}
                    </p>
                  )
                )}
              </div>
            </div>
          ))}
        </div>
        {errorMessage && !isDuplicateError && (
          <p className="mt-2.5 text-xs text-cursor-semantic-error whitespace-pre-line">{errorMessage}</p>
        )}
        {complete && (
          <div className="mt-3.5 flex justify-end">
            <button
              className="rounded-md border border-cursor-hairline bg-cursor-surface-card px-3 py-1.5 text-xs font-medium text-cursor-ink hover:bg-cursor-canvas transition-colors cursor-pointer"
              onClick={onClose}
            >
              {success ? 'View Jobs' : 'Close'}
            </button>
          </div>
        )}
        {!complete && onCancel && (
          <div className="mt-3.5 flex items-center justify-between gap-2 border-t border-cursor-hairline-soft pt-3">
            <p className="m-0 text-xs text-cursor-muted">You can cancel now to change inputs — nothing has started yet.</p>
            <button
              type="button"
              className="rounded-md border border-cursor-semantic-error/40 bg-cursor-surface-card px-3 py-1.5 text-xs font-medium text-cursor-semantic-error hover:bg-cursor-semantic-error/10 transition-colors cursor-pointer flex-none"
              onClick={onCancel}
            >
              Cancel preflight
            </button>
          </div>
        )}
      </div>
    </div>
    </ModalPortal>
  );
}
