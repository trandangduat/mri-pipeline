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

const summary = 'Insufficient resources (8.0 GiB allocated, 14.6 GiB required)';

function renderFailure(options?: {
  increaseRamPercent?: number | null;
  presets?: string[];
  onApplyRamPercent?: (percent: number) => void;
  onApplyPreset?: (mode: string) => void;
  onClose?: () => void;
}) {
  const onClose = options?.onClose ?? vi.fn();
  const onApplyRamPercent = options?.onApplyRamPercent ?? vi.fn();
  const onApplyPreset = options?.onApplyPreset ?? vi.fn();
  render(
    <StartPipelineDialog
      open={true}
      onClose={onClose}
      complete={true}
      success={false}
      errorMessage={summary}
      onApplyRamPercent={onApplyRamPercent}
      onApplyPreset={onApplyPreset}
      steps={[
        {
          id: 'resources',
          label: 'Checking server resources',
          status: 'failed',
          detail: summary,
          solutions: {
            summary,
            increaseRamPercent: options?.increaseRamPercent === undefined ? 91 : options.increaseRamPercent,
            presets: options?.presets ?? ['FreeSurfer 7 + Volume', 'FastSurfer + Volume'],
          },
        },
        {id: 'validate', label: 'Validating configuration', status: 'pending'},
      ]}
    />,
  );
  return {onClose, onApplyRamPercent, onApplyPreset};
}

describe('StartPipelineDialog resource solutions', () => {
  it('shows a short reason, a RAM increase, and compatible presets', () => {
    renderFailure();

    expect(screen.getByText(summary)).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Increase RAM allocation to 91%'})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'FreeSurfer 7 + Volume'})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'FastSurfer + Volume'})).toBeInTheDocument();
    expect(screen.getByText('Use compatible presets:')).toBeInTheDocument();
    expect(screen.queryByText(/Compatible pipelines runnable/)).not.toBeInTheDocument();
    expect(screen.getAllByText(summary)).toHaveLength(1);
  });

  it('hides the RAM action when a higher percent still cannot cover the peak', () => {
    renderFailure({increaseRamPercent: null, presets: ['FreeSurfer 7 + Volume']});

    expect(screen.queryByRole('button', {name: /Increase RAM allocation/})).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'FreeSurfer 7 + Volume'})).toBeInTheDocument();
  });

  it('hides Solutions when neither action is available', () => {
    renderFailure({increaseRamPercent: null, presets: []});

    expect(screen.getByText(summary)).toBeInTheDocument();
    expect(screen.queryByText('Solutions:')).not.toBeInTheDocument();
  });

  it('applies the RAM percent and closes the dialog', () => {
    const onApplyRamPercent = vi.fn();
    const onApplyPreset = vi.fn();
    const onClose = vi.fn();
    renderFailure({onApplyRamPercent, onApplyPreset, onClose});

    fireEvent.click(screen.getByRole('button', {name: 'Increase RAM allocation to 91%'}));

    expect(onApplyRamPercent).toHaveBeenCalledWith(91);
    expect(onApplyPreset).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('applies the selected preset and closes the dialog', () => {
    const onApplyRamPercent = vi.fn();
    const onApplyPreset = vi.fn();
    const onClose = vi.fn();
    renderFailure({onApplyRamPercent, onApplyPreset, onClose});

    fireEvent.click(screen.getByRole('button', {name: 'FastSurfer + Volume'}));

    expect(onApplyPreset).toHaveBeenCalledWith('FastSurfer + Volume');
    expect(onApplyRamPercent).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledOnce();
  });
});
