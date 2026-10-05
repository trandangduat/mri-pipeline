import React from 'react';
import {CheckCircle2, XCircle, Circle, Loader2, Download, AlertCircle} from 'lucide-react';
import {cn} from '@/lib/utils';
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

function SolutionButton({label, onClick}: {label: string; onClick: () => void}) {
  return (
    <button
      type="button"
      className="cursor-pointer border-0 bg-transparent p-0 text-left text-xs font-medium text-cursor-primary underline-offset-2 hover:underline"
      onClick={onClick}
    >
      {label}
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
  onApplyRamPercent?: (percent: number) => void;
  onApplyPreset?: (mode: string) => void;
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
          <ul className="m-0 mt-0.5 list-disc space-y-0.5 pl-4">
            {showIncrease && (
              <li>
                <SolutionButton
                  label={`Increase RAM allocation to ${solutions.increaseRamPercent}%`}
                  onClick={() => {
                    onApplyRamPercent?.(solutions.increaseRamPercent as number);
                    onClose();
                  }}
                />
              </li>
            )}
            {showPresets && (
              <li>
                <span>Use compatible presets:</span>
                <ul className="m-0 mt-0.5 list-disc space-y-0.5 pl-4">
                  {solutions.presets.map((preset) => (
                    <li key={preset}>
                      <SolutionButton
                        label={preset}
                        onClick={() => {
                          onApplyPreset?.(preset);
                          onClose();
                        }}
                      />
                    </li>
                  ))}
                </ul>
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

export function StartPipelineDialog({
  open,
  onClose,
  steps,
  complete,
  success,
  errorMessage,
  onApplyRamPercent,
  onApplyPreset,
}: Props) {
  const atlasStream = useDownloadAtlasStream();
  if (!open) return null;

  const rawAtlasError = errorMessage || steps.find((s) => s.status === 'failed')?.detail || '';
  const atlasMatch = rawAtlasError.match(/Atlas ['"]([^'"]+)['"] content is not installed/i);
  const missingAtlasKey = atlasMatch ? atlasMatch[1] : null;
  const missingPackId = missingAtlasKey ? resolveAtlasPackId(missingAtlasKey) : null;

  const isDuplicateError =
    Boolean(errorMessage) &&
    steps.some(
      (step) =>
        step.status === 'failed' &&
        Boolean(step.detail) &&
        step.detail?.trim() === errorMessage?.trim(),
    );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/30 p-3"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && complete) onClose();
      }}
    >
      <div className="relative w-full max-w-[28rem] rounded-lg border border-cursor-hairline bg-cursor-surface-card p-4 shadow-none">
        <h3 className="m-0 mb-3 text-base font-semibold leading-[1.3] text-cursor-ink">
          {complete ? (success ? 'Pipeline Started' : 'Start Failed') : 'Starting Pipeline...'}
        </h3>
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
        {missingAtlasKey && missingPackId && (
          <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-xs font-medium text-cursor-ink">
                  Missing Atlas: <span className="font-mono text-amber-600 dark:text-amber-400">{missingAtlasKey}</span>
                </p>
                <p className="mt-0.5 text-2xs text-cursor-muted">
                  Download the required surface atlas assets to run this pipeline.
                </p>
              </div>
              {atlasStream.status === 'idle' && (
                <button
                  type="button"
                  onClick={() => atlasStream.download(missingPackId)}
                  className="shrink-0 flex items-center gap-1 rounded bg-cursor-primary px-2.5 py-1 text-2xs font-medium text-white hover:bg-cursor-primary/90 transition-colors cursor-pointer"
                >
                  <Download className="h-3 w-3" />
                  Download
                </button>
              )}
            </div>
            {atlasStream.status !== 'idle' && (
              <div className="mt-2 space-y-1">
                <div className="flex items-center justify-between text-2xs text-cursor-muted">
                  <span className="flex items-center gap-1">
                    {['connecting', 'downloading', 'extracting'].includes(atlasStream.status) && (
                      <Loader2 className="h-3 w-3 animate-spin text-cursor-primary" />
                    )}
                    {atlasStream.message}
                  </span>
                  {atlasStream.status === 'downloading' && <span>{atlasStream.percent}%</span>}
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-cursor-canvas-soft">
                  <div
                    className={cn(
                      'h-full transition-all duration-300',
                      atlasStream.status === 'failed'
                        ? 'bg-cursor-semantic-error'
                        : atlasStream.status === 'success'
                        ? 'bg-cursor-semantic-success'
                        : 'bg-cursor-primary',
                    )}
                    style={{width: `${atlasStream.percent}%`}}
                  />
                </div>
                {atlasStream.status === 'success' && (
                  <p className="text-2xs text-cursor-semantic-success font-medium">
                    Installed! Close this dialog and retry starting the pipeline.
                  </p>
                )}
                {atlasStream.status === 'failed' && (
                  <div className="flex items-center justify-between gap-1 text-2xs text-cursor-semantic-error">
                    <span className="line-clamp-1">{atlasStream.error || 'Download failed.'}</span>
                    <button
                      type="button"
                      onClick={() => atlasStream.download(missingPackId)}
                      className="underline hover:text-cursor-semantic-error/80 cursor-pointer"
                    >
                      Retry
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
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
      </div>
    </div>
  );
}
