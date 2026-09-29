import React from 'react';
import {describe, expect, it, vi} from 'vitest';
import {fireEvent, render, screen} from '@testing-library/react';
import {StartPipelineDialog} from '../src/components/StartPipelineDialog';

const mockDownload = vi.fn();
const mockReset = vi.fn();

vi.mock('../src/query/useAtlases', () => ({
  useDownloadAtlasStream: () => ({
    status: 'idle',
    packId: null,
    percent: 0,
    downloadedBytes: 0,
    totalBytes: 0,
    message: '',
    error: null,
    download: mockDownload,
    reset: mockReset,
  }),
}));

describe('StartPipelineDialog Atlas Error Handling', () => {
  it('detects missing atlas error and displays download card', () => {
    const errorMsg =
      "Atlas 'schaefer2018_400parcels_17networks' content is not installed (missing: lh.Schaefer2018_400Parcels_17Networks.gcs). Install the required atlas assets, then retry.";

    render(
      <StartPipelineDialog
        open={true}
        onClose={vi.fn()}
        steps={[
          {id: 'validation', label: 'Validating configuration', status: 'failed', detail: errorMsg},
        ]}
        complete={true}
        success={false}
        errorMessage={errorMsg}
      />,
    );

    expect(screen.getByText(/Missing Atlas:/i)).toBeInTheDocument();
    expect(screen.getByText('schaefer2018_400parcels_17networks')).toBeInTheDocument();

    const downloadBtn = screen.getByRole('button', {name: /download/i});
    expect(downloadBtn).toBeInTheDocument();

    fireEvent.click(downloadBtn);
    expect(mockDownload).toHaveBeenCalledWith('schaefer2018_400parcels_17networks');
  });

  it('does not display download card when error is unrelated to atlases', () => {
    render(
      <StartPipelineDialog
        open={true}
        onClose={vi.fn()}
        steps={[
          {id: 'validation', label: 'Validating configuration', status: 'failed', detail: 'Missing FreeSurfer license'},
        ]}
        complete={true}
        success={false}
        errorMessage="Missing FreeSurfer license"
      />,
    );

    expect(screen.queryByText(/Missing Atlas:/i)).not.toBeInTheDocument();
  });
});
