import React from 'react';
import {parseGpuSolutions, type GpuRepairState} from '../lib/gpuReadiness';
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
  {id: 'images', label: 'Checking Docker images', status: 'pending'},
  {id: 'code', label: 'Checking code changes', status: 'pending'},
  {id: 'venv', label: 'Checking Python environment', status: 'pending'},
  {id: 'paths', label: 'Validating input/output paths', status: 'pending'},
  {id: 'license', label: 'Checking FreeSurfer license', status: 'pending'},
  {id: 'config', label: 'Uploading job configuration', status: 'pending'},
  {id: 'start', label: 'Starting remote worker', status: 'pending'},
];

const LOCAL_STEPS: PipelineStep[] = [
  {id: 'validate', label: 'Validating configuration', status: 'pending'},
  {id: 'runtime', label: 'Checking Docker and scheduler', status: 'pending'},
  {id: 'resources', label: 'Checking local resources', status: 'pending'},
  {id: 'images', label: 'Checking Docker images', status: 'pending'},
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
  const repairAbortRef = React.useRef<AbortController | null>(null);
  const repairTicketRef = React.useRef('');
  const [gpuRepair, setGpuRepair] = React.useState<GpuRepairState | null>(null);

  const repairGpu = React.useCallback(async (ticket: string, actionId: string) => {
    if (repairAbortRef.current) return;
    const controller = new AbortController();
    repairAbortRef.current = controller;
    repairTicketRef.current = ticket;
    setGpuRepair({ticket, busy: true, state: 'running', detail: 'Checking GPU setup...'});
    const client = new BackendClient(DEFAULT_BACKEND_URL);
    const fail = (message: string) => {
      if (!controller.signal.aborted) setGpuRepair({ticket, busy: false, state: 'failed', detail: message});
    };
    try {
      await client.gpuRepairStream(ticket, actionId, (event, data) => {
        if (controller.signal.aborted) return;
        const complete = event === 'complete';
        const ready = complete && data.ok === true;
        setGpuRepair({
          ticket, busy: !complete,
          state: typeof data.state === 'string' ? data.state : 'running',
          detail: typeof data.detail === 'string' ? data.detail : typeof data.error === 'string' ? data.error : '',
        });
        if (complete && !ready && data.result && typeof data.result === 'object') {
          const updated = parseGpuSolutions({...data.result as Record<string, unknown>, ticket});
          if (updated) setSteps((previous) => previous.map((step) => step.id === 'gpu'
            ? {...step, detail: updated.summary, gpuSolutions: updated} : step));
        }
        if (ready) {
          setSteps((previous) => previous.map((step) => step.id === 'gpu'
            ? {...step, status: 'done', detail: 'GPU check passed. Close this dialog and start the pipeline again.'} : step));
          setErrorMessage('');
        }
      }, fail, controller.signal);
    } catch (error) {
      fail((error as Error).message || 'GPU setup failed.');
    } finally {
      if (repairAbortRef.current === controller) repairAbortRef.current = null;
    }
  }, []);


  const start = React.useCallback(async (path: string, payload: Record<string, unknown>, isRemote: boolean) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setRunId((n) => n + 1);
    const initialSteps = isRemote ? [...REMOTE_STEPS] : [...LOCAL_STEPS];
    const request = (payload.run_request || payload) as Record<string, unknown>;
    if (request.device === 'cuda' || request.device === 'gpu') {
      const after = initialSteps.findIndex((step) => step.id === (isRemote ? 'venv' : 'images'));
      initialSteps.splice(after + 1, 0, {id: 'gpu', label: 'Checking GPU', status: 'pending'});
    }
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
          const gpuSolutions = parseGpuSolutions(data.gpu_solutions);
          setSteps((prev) =>
            prev.map((s): PipelineStep =>
              s.id === stepId
                ? {...s, status, detail, ...(solutions === undefined ? {} : {solutions}),
                   ...(gpuSolutions === undefined ? {} : {gpuSolutions})}
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
    repairAbortRef.current?.abort();
    repairAbortRef.current = null;
    abortRef.current?.abort();
    abortRef.current = null;
    setOpen(false);
  }, []);

  React.useEffect(
    () => () => {
      abortRef.current?.abort();
      repairAbortRef.current?.abort();
    },
    [],
  );

  React.useEffect(() => {
    if (!open || !repairTicketRef.current || repairAbortRef.current) return;
    const ticket = repairTicketRef.current;
    let stopped = false;
    const client = new BackendClient(DEFAULT_BACKEND_URL);
    const poll = async () => {
      try {
        const data = await client.gpuRepairStatus(ticket);
        if (stopped) return;
        const busy = data.state === 'running';
        setGpuRepair({ticket, busy, state: String(data.state || 'failed'), detail: String(data.detail || data.error || '')});
      } catch {
        // A restarted backend can expire the ticket. Fresh preflight remains authoritative.
      }
    };
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 1500);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [open, runId]);

  return {open, steps, complete, success, job, errorMessage, runId, start, cancel, close, gpuRepair, repairGpu};
}
