import React from 'react';
import {render, screen} from '@testing-library/react';
import {expect, test, vi} from 'vitest';
import {BackendClient} from '../src/api/client';
import {REMOTE_STEPS, useStartPipelineStream} from '../src/hooks/useStartPipelineStream';

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
