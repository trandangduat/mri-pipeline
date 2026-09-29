import React from 'react';
import {describe, expect, it, vi} from 'vitest';
import {fireEvent, render, screen} from '@testing-library/react';
import {AtlasCard} from '../src/components/AtlasCard';
import type {AtlasPack} from '../src/types/backend';

const mockPack: AtlasPack = {
  id: 'schaefer2018_400parcels_17networks',
  label: 'Schaefer 2018 (400 Parcels, 17 Networks)',
  description: 'Default cortical thickness atlas for FreeSurfer pipelines.',
  category: 'schaefer',
  is_default: true,
  asset_filename: 'atlas-schaefer2018-400-17.zip',
  compressed_size_bytes: 8150000,
  uncompressed_size_bytes: 27232092,
  files: [
    'schaefer/lh.Schaefer2018_400Parcels_17Networks.gcs',
    'schaefer/rh.Schaefer2018_400Parcels_17Networks.gcs',
  ],
  installed: false,
  missing_files: [
    'schaefer/lh.Schaefer2018_400Parcels_17Networks.gcs',
    'schaefer/rh.Schaefer2018_400Parcels_17Networks.gcs',
  ],
  installed_files_count: 0,
  total_files_count: 2,
  download_url: 'https://example.com/atlas-schaefer.zip',
};

describe('AtlasCard', () => {
  it('renders uninstalled pack correctly with download button', () => {
    const onDownload = vi.fn();
    render(<AtlasCard pack={mockPack} onDownload={onDownload} />);

    expect(screen.getByText('Schaefer 2018 (400 Parcels, 17 Networks)')).toBeInTheDocument();
    expect(screen.getByText('Default')).toBeInTheDocument();
    expect(screen.getByText('Not installed')).toBeInTheDocument();
    expect(screen.getByText('2 files')).toBeInTheDocument();
    expect(screen.getByText(/7.8 MB download/)).toBeInTheDocument();

    const downloadBtn = screen.getByRole('button', {name: /download/i});
    fireEvent.click(downloadBtn);
    expect(onDownload).toHaveBeenCalledWith('schaefer2018_400parcels_17networks');
  });

  it('renders installed pack with re-download button', () => {
    const onDownload = vi.fn();
    const installedPack: AtlasPack = {...mockPack, installed: true, missing_files: [], installed_files_count: 2};
    render(<AtlasCard pack={installedPack} onDownload={onDownload} />);

    expect(screen.getByText('Installed')).toBeInTheDocument();
    const redownloadBtn = screen.getByRole('button', {name: /re-download/i});
    fireEvent.click(redownloadBtn);
    expect(onDownload).toHaveBeenCalledWith('schaefer2018_400parcels_17networks');
  });

  it('renders downloading state and progress bar', () => {
    render(
      <AtlasCard
        pack={mockPack}
        onDownload={vi.fn()}
        isDownloading={true}
        downloadState={{
          status: 'downloading',
          percent: 45,
          message: 'Downloading: 45%',
          error: null,
        }}
      />,
    );

    expect(screen.getByText('Downloading: 45%')).toBeInTheDocument();
    expect(screen.getByText('45%')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: /downloading/i})).toBeDisabled();
  });

  it('renders failure error state', () => {
    render(
      <AtlasCard
        pack={mockPack}
        onDownload={vi.fn()}
        downloadState={{
          status: 'failed',
          percent: 0,
          message: 'Download failed',
          error: 'Connection timed out',
        }}
      />,
    );

    expect(screen.getByText('Connection timed out')).toBeInTheDocument();
  });
});
