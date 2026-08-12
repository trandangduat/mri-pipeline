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
      className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/30 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && complete) onClose();
      }}
    >
      <div className="relative w-full max-w-[min(28rem,calc(100vw-2rem))] rounded-xl border border-cursor-hairline bg-white p-6 shadow-none">
        <h3 className="m-0 mb-4 text-[16px] font-semibold leading-[1.4] text-cursor-ink">
          {complete ? (success ? 'Pipeline Started' : 'Start Failed') : 'Starting Pipeline...'}
        </h3>
        <div className="flex flex-col gap-3">
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
        {errorMessage && (
          <p className="mt-3 text-[12px] text-cursor-semantic-error">{errorMessage}</p>
        )}
        {complete && (
          <div className="mt-4 flex justify-end">
            <button
              className="rounded-lg border border-cursor-hairline bg-white px-4 py-2 text-[13px] font-medium text-cursor-ink hover:bg-cursor-canvas"
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
