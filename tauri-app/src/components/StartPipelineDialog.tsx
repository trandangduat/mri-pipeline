import React from 'react';
import {CheckCircle2, XCircle, Circle, Loader2} from 'lucide-react';
import {cn} from '@/lib/utils';

export interface PipelineStep {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'done' | 'failed';
  detail?: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  steps: PipelineStep[];
  complete: boolean;
  success: boolean;
  errorMessage?: string;
}

function StepIcon({status}: {status: PipelineStep['status']}) {
  if (status === 'done') return <CheckCircle2 className="h-4 w-4 flex-none text-cursor-semantic-success" />;
  if (status === 'failed') return <XCircle className="h-4 w-4 flex-none text-cursor-semantic-error" />;
  if (status === 'running') return <Loader2 className="h-4 w-4 flex-none animate-spin text-cursor-primary" />;
  return <Circle className="h-4 w-4 flex-none text-cursor-muted-soft" />;
}

export function StartPipelineDialog({open, onClose, steps, complete, success, errorMessage}: Props) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/30 p-3"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && complete) onClose();
      }}
    >
      <div className="relative w-full max-w-[26rem] rounded-lg border border-cursor-hairline bg-white p-4 shadow-none">
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
                {step.detail && (
                  <p
                    className={cn(
                      'm-0 mt-0.5 text-xs leading-[1.3]',
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
        {errorMessage && (
          <p className="mt-2.5 text-xs text-cursor-semantic-error">{errorMessage}</p>
        )}
        {complete && (
          <div className="mt-3.5 flex justify-end">
            <button
              className="rounded-md border border-cursor-hairline bg-white px-3 py-1.5 text-xs font-medium text-cursor-ink hover:bg-cursor-canvas transition-colors cursor-pointer"
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
