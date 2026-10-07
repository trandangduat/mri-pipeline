import React from 'react';
import {act, render, screen} from '@testing-library/react';
import {describe, expect, it, vi} from 'vitest';
import {StartPipelineDialog} from '../src/components/StartPipelineDialog';

const state = vi.hoisted(() => ({
  stream: {status: 'idle', packId: null as string | null},
}));
const mockDownload = vi.fn();
const mockReset = vi.fn();

vi.mock('../src/query/useAtlases', () => ({
  useDownloadAtlasStream: () => ({
    status: state.stream.status,
    packId: state.stream.packId,
    percent: 0,
    downloadedBytes: 0,
    totalBytes: 0,
    message: '',
    error: null,
    download: mockDownload,
    reset: mockReset,
  }),
}));

const PACK_ID = 'schaefer2018_400parcels_17networks';
const errorMsg =
  `Atlas '${PACK_ID}' content is not installed (missing: lh.Schaefer2018_400Parcels_17Networks.gcs). ` +
  'Install the required atlas assets, then retry.';

function dialogProps() {
  return {
    open: true,
    onClose: vi.fn(),
    steps: [{id: 'validate', label: 'Validating configuration', status: 'failed' as const, detail: errorMsg}],
    complete: true,
    success: false,
    errorMessage: errorMsg,
  };
}

describe('StartPipelineDialog atlas marks are scoped to a preflight run', () => {
  it('forgets in-dialog Installed marks when remounted for a new run', () => {
    // AppHeader remounts the dialog per run via key={runId}.
    const {rerender, unmount} = render(<StartPipelineDialog key={1} {...dialogProps()} />);
    // Files missing on disk: offers Download.
    expect(screen.getByRole('button', {name: /^download$/i})).toBeTruthy();

    // User installs the atlas inside the dialog.
    act(() => {
      state.stream.status = 'success';
      state.stream.packId = PACK_ID;
    });
    rerender(<StartPipelineDialog key={1} {...dialogProps()} />);
    expect(screen.getByText('Installed')).toBeTruthy();

    // Files deleted externally, user starts a new preflight (remount):
    // must offer Download again instead of the stale Installed label.
    unmount();
    // Reset the module-level stream mock to a fresh idle state for the run.
    state.stream.status = 'idle';
    state.stream.packId = null;
    render(<StartPipelineDialog key={2} {...dialogProps()} />);
    expect(screen.queryByText('Installed')).toBeNull();
    expect(screen.getByRole('button', {name: /^download$/i})).toBeTruthy();
  });
});
