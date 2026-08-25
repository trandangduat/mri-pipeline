import React from 'react';
import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {PipelinePage} from '../src/pages/PipelinePage';
import {usePipelineFormStore} from '../src/stores/pipelineFormStore';
import {useRemoteStore} from '../src/stores/remoteStore';

const mockMetadata = {
  version: 1,
  stages: [],
  stage_order: [],
  tools: {},
  tools_by_stage: {},
  pipeline_modes: [{id: 'CAT12 + Volume'}, {id: 'Custom'}],
  presets: {},
  stats_vectors: {},
  atlases: {},
  tool_contracts: {},
};

vi.mock('../src/query/useEnvironment', () => ({
  useMetadata: () => ({
    data: mockMetadata,
    isLoading: false,
    isError: false,
  }),
  useEnvironment: () => ({
    data: {docker_available: true, local_hardware: {}},
    isLoading: false,
    isError: false,
  }),
  useClient: () => ({
    uploadLicense: vi.fn(),
    browseLocalPath: vi.fn().mockResolvedValue({ok: true, path: '/local', parent: '/', dirs: [], files: [], entries: []}),
    browseRemotePath: vi.fn().mockResolvedValue({ok: true, path: '/remote', parent: '/', dirs: [], files: [], entries: []}),
  }),
}));

vi.mock('../src/hooks/useStartPipelineStream', () => ({
  useStartPipelineStream: () => ({
    start: vi.fn(),
    abort: vi.fn(),
    isStarting: false,
    steps: [],
    completed: false,
    error: null,
  }),
}));

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {queries: {retry: false}},
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

describe('PipelinePage - TC-01 & TC-02 Input & Output Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    usePipelineFormStore.setState({
      formValues: {
        runtimeTarget: 'Server',
        inputSource: 'Server',
        inputMode: 'file',
        inputPath: '',
        outputDir: '',
        inputServerDir: '',
        pipelineMode: 'CAT12 + Volume',
        selectedTools: {},
        selectedStatsAtlases: {},
        threads: 4,
        ramPercent: 100,
      },
    });
    useRemoteStore.setState({
      connected: false,
      host: 'server.example.com',
      port: 22,
      username: 'catcd1',
    });
  });

  it('TC-01: Disables server location inputs and browse buttons when Server runtime is disconnected', () => {
    renderWithClient(<PipelinePage />);

    // When disconnected with Runtime=Server, Source=Local: Local input enabled, Server input & output disabled
    const inputLocalField = screen.getByLabelText(/Input location \(local\)/i);
    expect(inputLocalField).not.toBeDisabled();

    const inputServerField = screen.getByLabelText(/Input location \(server\)/i);
    const outputDirField = screen.getByLabelText(/Output location \(server\)/i);

    expect(inputServerField).toBeDisabled();
    expect(inputServerField).toHaveAttribute('placeholder', 'Connect to server first');

    expect(outputDirField).toBeDisabled();
    expect(outputDirField).toHaveAttribute('placeholder', 'Connect to server first');

    // Browse buttons for those fields have title "Connect to server first" and are disabled
    const browseButtons = screen.getAllByTitle('Connect to server first');
    expect(browseButtons.length).toBeGreaterThanOrEqual(2);
    browseButtons.forEach((btn) => {
      expect(btn).toBeDisabled();
    });

    // Upload data to server button under Source Input is also disabled
    const uploadBtn = screen.getByRole('button', {name: 'Upload data to server'});
    expect(uploadBtn).toBeDisabled();
  });

  it('TC-01: Enables server path fields when connected and Source is Server', async () => {
    useRemoteStore.setState({
      connected: true,
      host: 'server.example.com',
      port: 22,
      username: 'catcd1',
    });
    usePipelineFormStore.setState({
      formValues: {
        ...usePipelineFormStore.getState().formValues,
        inputSource: 'Server',
      },
    });

    renderWithClient(<PipelinePage />);

    const inputPathField = screen.getByLabelText(/Input location \(server path\)/i);
    const outputDirField = screen.getByLabelText(/Output location \(server path\)/i);

    expect(inputPathField).not.toBeDisabled();
    expect(outputDirField).not.toBeDisabled();
  });

  it('TC-02: Upload data to server button is positioned under Source Input and opens DualPane modal when connected', async () => {
    const user = userEvent.setup();
    useRemoteStore.setState({
      connected: true,
      host: 'server.example.com',
      port: 22,
      username: 'catcd1',
    });

    renderWithClient(<PipelinePage />);

    const uploadBtn = screen.getByRole('button', {name: 'Upload data to server'});
    expect(uploadBtn).not.toBeDisabled();

    await user.click(uploadBtn);

    // Should open Dual-Pane SFTP modal
    expect(screen.getByText('Upload Data to Server')).toBeInTheDocument();
    expect(screen.getByText('Local Computer')).toBeInTheDocument();
    expect(screen.getByText('Remote Server (SSH)')).toBeInTheDocument();
  });
});
