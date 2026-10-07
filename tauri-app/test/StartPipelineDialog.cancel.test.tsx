import React from 'react';
import {describe, expect, it, vi} from 'vitest';
import {fireEvent, render, screen} from '@testing-library/react';
import {StartPipelineDialog} from '../src/components/StartPipelineDialog';

vi.mock('../src/query/useAtlases', () => ({
  useDownloadAtlasStream: () => ({
    status: 'idle',
    packId: null,
    percent: 0,
    downloadedBytes: 0,
    totalBytes: 0,
    message: '',
    error: null,
    download: vi.fn(),
    reset: vi.fn(),
  }),
}));

const runningSteps = [
  {id: 'ssh', label: 'Checking SSH connection', status: 'done' as const},
  {id: 'code', label: 'Checking code changes', status: 'running' as const},
  {id: 'venv', label: 'Checking Python environment', status: 'pending' as const},
];

describe('StartPipelineDialog preflight cancel', () => {
  it('shows Cancel preflight while running and calls onCancel', () => {
    const onClose = vi.fn();
    const onCancel = vi.fn();
    render(
      <StartPipelineDialog
        open={true}
        onClose={onClose}
        onCancel={onCancel}
        complete={false}
        success={false}
        steps={runningSteps}
      />,
    );
    fireEvent.click(screen.getByText('Cancel preflight'));
    expect(onCancel).toHaveBeenCalledOnce();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('header X also cancels while running', () => {
    const onCancel = vi.fn();
    render(
      <StartPipelineDialog
        open={true}
        onClose={vi.fn()}
        onCancel={onCancel}
        complete={false}
        success={false}
        steps={runningSteps}
      />,
    );
    fireEvent.click(screen.getByTitle('Cancel preflight (Esc)'));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('hides Cancel preflight once complete', () => {
    render(
      <StartPipelineDialog
        open={true}
        onClose={vi.fn()}
        onCancel={vi.fn()}
        complete={true}
        success={true}
        steps={runningSteps}
      />,
    );
    expect(screen.queryByText('Cancel preflight')).toBeNull();
    expect(screen.getByRole('button', {name: 'View Jobs' })).toBeTruthy();
  });

  it('stays backward compatible without onCancel', () => {
    render(
      <StartPipelineDialog open={true} onClose={vi.fn()} complete={false} success={false} steps={runningSteps} />,
    );
    expect(screen.getByText('Starting Pipeline...')).toBeTruthy();
    expect(screen.queryByText('Cancel preflight')).toBeNull();
  });
});
