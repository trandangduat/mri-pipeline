import React from 'react';
import {BackendClient, DEFAULT_BACKEND_URL} from '../api/client';
import type {PipelineStep, ResourceSolutions} from '../components/StartPipelineDialog';

export function parseResourceSolutions(value: unknown): ResourceSolutions | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const record = value as Record<string, unknown>;
  const summary = typeof record.summary === 'string' ? record.summary.trim() : '';
  if (!summary) return undefined;
  const increase = record.increase_ram_percent;
  const presets = Array.isArray(record.presets)
    ? record.presets.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    : [];
  const increaseRamPercent =
    typeof increase === 'number' && Number.isInteger(increase) && increase >= 1 && increase <= 100
      ? increase
      : null;
  return {summary, increaseRamPercent, presets};
}

export const REMOTE_STEPS: PipelineStep[] = [
  {id: 'ssh', label: 'Checking SSH connection', status: 'pending'},
  {id: 'resources', label: 'Checking server resources', status: 'pending'},
  {id: 'validate', label: 'Validating configuration', status: 'pending'},
  {id: 'paths', label: 'Validating input/output paths', status: 'pending'},
  {id: 'images', label: 'Checking Docker images', status: 'pending'},
  {id: 'code', label: 'Checking code changes', status: 'pending'},
  {id: 'venv', label: 'Checking Python environment', status: 'pending'},
  {id: 'license', label: 'Checking FreeSurfer license', status: 'pending'},
  {id: 'config', label: 'Uploading job configuration', status: 'pending'},
  {id: 'start', label: 'Starting remote worker', status: 'pending'},
];

const LOCAL_STEPS: PipelineStep[] = [
  {id: 'validate', label: 'Validating configuration', status: 'pending'},
  {id: 'license', label: 'Checking FreeSurfer license', status: 'pending'},
  {id: 'config', label: 'Preparing job configuration', status: 'pending'},
  {id: 'start', label: 'Starting local worker', status: 'pending'},
];

export function useStartPipelineStream() {
  const [open, setOpen] = React.useState(false);
  const [steps, setSteps] = React.useState<PipelineStep[]>([]);
  const [complete, setComplete] = React.useState(false);
  const [success, setSuccess] = React.useState(false);
  const [job, setJob] = React.useState<Record<string, unknown> | null>(null);
  const [errorMessage, setErrorMessage] = React.useState('');
  const [runId, setRunId] = React.useState(0);
  const abortRef = React.useRef<AbortController | null>(null);

  const start = React.useCallback(async (path: string, payload: Record<string, unknown>, isRemote: boolean) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setRunId((n) => n + 1);
    const initialSteps = isRemote ? [...REMOTE_STEPS] : [...LOCAL_STEPS];
    setSteps(initialSteps);
    setComplete(false);
    setSuccess(false);
    setJob(null);
    setErrorMessage('');
    setOpen(true);

    const client = new BackendClient(DEFAULT_BACKEND_URL);
    try {
      await client.startPipelineStream(
        path,
        payload,
        (event, data) => {
          if (controller.signal.aborted) return;
        if (event === 'step') {
          const stepId = data.step as string;
          const status = data.status as PipelineStep['status'];
          const detail = (data.detail as string) || '';
          const solutions = parseResourceSolutions(data.solutions);
          setSteps((prev) =>
            prev.map((s): PipelineStep =>
              s.id === stepId
                ? solutions === undefined
                  ? {...s, status, detail}
                  : {...s, status, detail, solutions}
                : s,
            ),
          );
        } else if (event === 'complete') {
          const ok = data.ok as boolean;
          setComplete(true);
          setSuccess(ok);
          if (ok) {
            setJob(data.job as Record<string, unknown>);
          } else {
            const errors = Array.isArray(data.errors)
              ? data.errors.filter((error): error is string => typeof error === 'string').join('; ')
              : '';
            setErrorMessage((data.error as string) || errors || 'Start failed');
          }
        }
      },
      (error) => {
          if (controller.signal.aborted) return;
          setComplete(true);
          setSuccess(false);
          setErrorMessage(error);
        },
        controller.signal,
      );
    } catch (err) {
      if (controller.signal.aborted) return;
      setComplete(true);
      setSuccess(false);
      setErrorMessage((err as Error).message || 'Start failed');
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, []);

  const cancel = React.useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    // Mark cancelled so the dialog can close immediately; late SSE events
    // are ignored via the aborted-signal guard above.
    setComplete(true);
    setSuccess(false);
    setErrorMessage('Preflight cancelled by user.');
  }, []);

  const close = React.useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setOpen(false);
  }, []);

  React.useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

  return {open, steps, complete, success, job, errorMessage, runId, start, cancel, close};
}
