import React from 'react';
import {render, screen} from '@testing-library/react';
import {expect, test, vi} from 'vitest';
import {BackendClient} from '../src/api/client';
import {REMOTE_STEPS, parseResourceSolutions, useStartPipelineStream} from '../src/hooks/useStartPipelineStream';

function Harness() {
  const {start, steps, complete, success, errorMessage} = useStartPipelineStream();

  return (
    <>
      <button onClick={() => void start('/remote/jobs/start/stream', {}, true)}>Start</button>
      <output data-testid="steps">{JSON.stringify(steps)}</output>
      <output data-testid="complete">{String(complete)}</output>
      <output data-testid="success">{String(success)}</output>
      <output data-testid="error">{errorMessage}</output>
    </>
  );
}

test('remote preflight lists license before config and keeps later steps pending on failure', async () => {
  expect(REMOTE_STEPS.map((step) => step.id)).toEqual([
    'ssh',
    'resources',
    'validate',
    'paths',
    'images',
    'code',
    'venv',
    'license',
    'config',
    'start',
  ]);

  const stream = vi
    .spyOn(BackendClient.prototype, 'startPipelineStream')
    .mockImplementation(async (_path, _payload, onEvent) => {
      onEvent('step', {step: 'license', status: 'running'});
      onEvent('step', {step: 'license', status: 'failed', detail: 'License not found locally: /tmp/license.txt'});
      onEvent('complete', {ok: false, error: 'License not found locally: /tmp/license.txt'});
    });

  render(<Harness />);
  screen.getByRole('button', {name: 'Start'}).click();

  expect(await screen.findByTestId('complete')).toHaveTextContent('true');
  expect(screen.getByTestId('success')).toHaveTextContent('false');
  expect(screen.getByTestId('error')).toHaveTextContent('License not found locally');
  const steps = JSON.parse(screen.getByTestId('steps').textContent || '[]') as Array<{
    id: string;
    status: string;
  }>;
  expect(steps.find((step) => step.id === 'license')?.status).toBe('failed');
  expect(steps.find((step) => step.id === 'config')?.status).toBe('pending');
  expect(steps.find((step) => step.id === 'start')?.status).toBe('pending');
  expect(stream).toHaveBeenCalledOnce();
  stream.mockRestore();
});

test('remote preflight fails at resources step and keeps later steps pending', async () => {
  const stream = vi
    .spyOn(BackendClient.prototype, 'startPipelineStream')
    .mockImplementation(async (_path, _payload, onEvent) => {
      onEvent('step', {step: 'resources', status: 'running'});
      onEvent('step', {step: 'resources', status: 'failed', detail: 'Insufficient RAM allocated'});
      onEvent('complete', {ok: false, error: 'Insufficient RAM allocated'});
    });

  render(<Harness />);
  screen.getByRole('button', {name: 'Start'}).click();

  expect(await screen.findByTestId('complete')).toHaveTextContent('true');
  expect(screen.getByTestId('success')).toHaveTextContent('false');
  expect(screen.getByTestId('error')).toHaveTextContent('Insufficient RAM allocated');
  const steps = JSON.parse(screen.getByTestId('steps').textContent || '[]') as Array<{
    id: string;
    status: string;
  }>;
  expect(steps.find((step) => step.id === 'resources')?.status).toBe('failed');
  expect(steps.find((step) => step.id === 'validate')?.status).toBe('pending');
  expect(steps.find((step) => step.id === 'config')?.status).toBe('pending');
  stream.mockRestore();
});

test('resource failure keeps the short solutions payload on the resources step', async () => {
  const stream = vi
    .spyOn(BackendClient.prototype, 'startPipelineStream')
    .mockImplementation(async (_path, _payload, onEvent) => {
      onEvent('step', {
        step: 'resources',
        status: 'failed',
        detail: 'Insufficient resources (8.0 GiB allocated, 14.6 GiB required)',
        solutions: {
          summary: 'Insufficient resources (8.0 GiB allocated, 14.6 GiB required)',
          increase_ram_percent: 91,
          presets: ['FreeSurfer 7 + Volume', 'FastSurfer + Volume'],
        },
      });
      onEvent('complete', {ok: false, error: 'Insufficient resources (8.0 GiB allocated, 14.6 GiB required)'});
    });

  render(<Harness />);
  screen.getByRole('button', {name: 'Start'}).click();

  expect(await screen.findByTestId('complete')).toHaveTextContent('true');
  const steps = JSON.parse(screen.getByTestId('steps').textContent || '[]') as Array<{
    id: string;
    solutions?: {increaseRamPercent: number | null; presets: string[]};
  }>;
  expect(steps.find((step) => step.id === 'resources')?.solutions).toEqual({
    summary: 'Insufficient resources (8.0 GiB allocated, 14.6 GiB required)',
    increaseRamPercent: 91,
    presets: ['FreeSurfer 7 + Volume', 'FastSurfer + Volume'],
  });
  expect(stream).toHaveBeenCalledOnce();
  stream.mockRestore();
});

test('parseResourceSolutions drops an increase that is not a RAM percent', () => {
  expect(
    parseResourceSolutions({
      summary: 'Insufficient resources (1.0 GiB allocated, 14.6 GiB required)',
      increase_ram_percent: null,
      presets: ['FreeSurfer 7 + Volume', 3],
    }),
  ).toEqual({
    summary: 'Insufficient resources (1.0 GiB allocated, 14.6 GiB required)',
    increaseRamPercent: null,
    presets: ['FreeSurfer 7 + Volume'],
  });
  expect(parseResourceSolutions(null)).toBeUndefined();
});
