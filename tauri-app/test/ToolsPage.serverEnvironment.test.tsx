import React from 'react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {render, screen} from '@testing-library/react';
import {LocalEnvironmentCards, ServerEnvironmentCards, ToolsPage} from '../src/pages/ToolsPage';
import {DEFAULT_FORM_VALUES} from '../src/api/runConfig';
import {usePipelineFormStore} from '../src/stores/pipelineFormStore';
import {useRemoteStore} from '../src/stores/remoteStore';

const hooks = vi.hoisted(() => ({
  useRemoteEnvironment: vi.fn(),
}));

vi.mock('../src/query/useEnvironment', () => ({
  useEnvironment: () => ({data: undefined, refetch: vi.fn()}),
  useRemoteEnvironment: hooks.useRemoteEnvironment,
}));

vi.mock('../src/query/useTools', () => ({
  useLocalImageStatusMutation: () => ({mutateAsync: vi.fn().mockResolvedValue({ok: true, images: []})}),
  useRemoveImage: () => ({mutateAsync: vi.fn().mockResolvedValue({ok: true})}),
  usePullImageStream: () => ({status: 'idle', logs: [], error: null, image: null, target: 'Local', pull: vi.fn(), reset: vi.fn()}),
}));

const completeEnvironment = {
  ok: true,
  connected: true,
  server: {
    ok: true,
    hostname: 'gpu-node-01',
    logical_cores: 32,
    total_ram_bytes: 128 * 1024 ** 3,
    gpus: [{name: 'NVIDIA A100', total_memory_mib: 40960, free_memory_mib: 39321}],
  },
  python: {ok: true, path: '/usr/bin/python3', version: 'Python 3.12.1'},
  environment: {
    ok: true,
    path: '/work/mri/.venv',
    venv_exists: true,
    python_ok: true,
    python_version: 'Python 3.12.1',
    pip_ok: true,
    pip_version: 'pip 24.0',
  },
  docker: {ok: true, version: '26.1.0', error: ''},
};

describe('ToolsPage server environment', () => {
  beforeEach(() => {
    usePipelineFormStore.setState({formValues: {...DEFAULT_FORM_VALUES, runtimeTarget: 'Server'}});
    useRemoteStore.getState().reset();
    hooks.useRemoteEnvironment.mockReturnValue({
      data: completeEnvironment,
      error: null,
      isFetching: false,
      refetch: vi.fn(),
      dataUpdatedAt: Date.now(),
    });
  });

  it('renders compact server status cards', () => {
    render(
      <ServerEnvironmentCards
        environment={completeEnvironment}
        error=""
        pending={false}
      />,
    );

    expect(screen.getByText('Resources')).toBeInTheDocument();
    expect(screen.getByText('gpu-node-01')).toBeInTheDocument();
    expect(screen.getByText('Python')).toBeInTheDocument();
    expect(screen.getByText('Docker')).toBeInTheDocument();
    expect(screen.getByText('32 cores · 128 GiB RAM')).toBeInTheDocument();
    expect(screen.getAllByText('Ready')).toHaveLength(3);
  });

  it('shows grouped loading states while inspection is pending', () => {
    render(
      <ServerEnvironmentCards
        error=""
        pending
      />,
    );

    expect(screen.getAllByText('Checking')).toHaveLength(3);
    expect(screen.getByText('Resources')).toBeInTheDocument();
    expect(screen.getByText('Python')).toBeInTheDocument();
    expect(screen.getByText('Docker')).toBeInTheDocument();
  });

  it('keeps healthy cards visible when Python and Docker are unavailable', () => {
    render(
      <ServerEnvironmentCards
        environment={{
          ...completeEnvironment,
          environment: {...completeEnvironment.environment, ok: false, python_ok: false, pip_ok: false},
          docker: {ok: false, version: '', error: 'Docker daemon is unavailable'},
        }}
        error=""
        pending={false}
      />,
    );

    expect(screen.getByText('32 cores · 128 GiB RAM')).toBeInTheDocument();
    expect(screen.getAllByText('Not Ready').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Docker daemon is unavailable')).not.toHaveLength(0);
  });

  it('keeps connect-first guidance when the server is disconnected', () => {
    useRemoteStore.setState({connected: false, config: null});

    render(<ToolsPage />);

    expect(screen.getByText(/Connect to the server in Runtime settings/)).toBeInTheDocument();
    expect(hooks.useRemoteEnvironment).toHaveBeenCalled();
  });

  it('renders compact local environment cards matching server component style', () => {
    const localEnv = {
      ok: true,
      python: {ok: true, path: '/usr/local/bin/python3', version: '3.12.10'},
      docker: {ok: true, path: '/usr/local/bin/docker'},
      ssh: {ok: true, path: '/usr/bin/ssh'},
      hardware: {
        hostname: 'neuroflow-dev-box',
        logical_cores: 16,
        physical_cores: 8,
        total_ram_bytes: 64 * 1024 ** 3,
        gpus: [{name: 'NVIDIA RTX 4080', total_memory_mib: 16384, free_memory_mib: 16000}],
      },
    };

    render(
      <LocalEnvironmentCards
        environment={localEnv}
        pending={false}
      />,
    );

    expect(screen.getByText('Resources')).toBeInTheDocument();
    expect(screen.getByText('neuroflow-dev-box')).toBeInTheDocument();
    expect(screen.getByText('16 cores · 64 GiB RAM')).toBeInTheDocument();
    expect(screen.getByText('GPU: NVIDIA RTX 4080')).toBeInTheDocument();
    expect(screen.getByText('Python')).toBeInTheDocument();
    expect(screen.getByText('Python 3.12.10')).toBeInTheDocument();
    expect(screen.getByText('Docker')).toBeInTheDocument();
    expect(screen.getAllByText('Ready')).toHaveLength(3);
  });

  it('renders local environment cards in ToolsPage when runtimeTarget is Local', () => {
    usePipelineFormStore.setState({formValues: {...DEFAULT_FORM_VALUES, runtimeTarget: 'Local'}});
    render(<ToolsPage />);
    expect(screen.getByText('Resources')).toBeInTheDocument();
  });
});
