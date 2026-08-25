import React from 'react';
import {BackendClient, DEFAULT_BACKEND_URL} from '../api/client';
import type {PipelineStep} from '../components/StartPipelineDialog';

export const REMOTE_STEPS: PipelineStep[] = [
  {id: 'ssh', label: 'Checking SSH connection', status: 'pending'},
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

  const start = React.useCallback(async (path: string, payload: Record<string, unknown>, isRemote: boolean) => {
    const initialSteps = isRemote ? [...REMOTE_STEPS] : [...LOCAL_STEPS];
    setSteps(initialSteps);
    setComplete(false);
    setSuccess(false);
    setJob(null);
    setErrorMessage('');
    setOpen(true);

    const client = new BackendClient(DEFAULT_BACKEND_URL);
    await client.startPipelineStream(
      path,
      payload,
      (event, data) => {
        if (event === 'step') {
          const stepId = data.step as string;
          const status = data.status as PipelineStep['status'];
          const detail = (data.detail as string) || '';
          setSteps((prev) => prev.map((s) => (s.id === stepId ? {...s, status, detail} : s)));
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
        setComplete(true);
        setSuccess(false);
        setErrorMessage(error);
      },
    );
  }, []);

  const close = React.useCallback(() => {
    setOpen(false);
  }, []);

  return {open, steps, complete, success, job, errorMessage, start, close};
}
