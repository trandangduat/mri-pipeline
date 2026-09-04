import React from 'react';
import {describe, it, expect, beforeEach, afterEach, vi} from 'vitest';
import {render, screen, fireEvent, waitFor} from '@testing-library/react';
import {ConnectionStatusLine} from '../src/components/ConnectionStatusLine';
import {probeConnectionHealth} from '../src/lib/connectionProbe';
import {useRemoteStore} from '../src/stores/remoteStore';
import {usePipelineFormStore} from '../src/stores/pipelineFormStore';

function setRuntimeTarget(target: 'Local' | 'Server') {
  usePipelineFormStore.setState({
    formValues: {...usePipelineFormStore.getState().formValues, runtimeTarget: target},
  });
}

describe('ConnectionStatusLine', () => {
  beforeEach(() => {
    useRemoteStore.getState().reset();
    setRuntimeTarget('Server');
  });

  it('renders nothing while all channels are healthy', () => {
    useRemoteStore.setState({connected: true});
    const {container} = render(<ConnectionStatusLine />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the SSH warning with Retry but no SSH settings button when SSH is down', async () => {
    useRemoteStore.setState({
      connected: true,
      sshStatus: 'disconnected',
      sshFailures: 1,
      sshLastError: 'SSH connection failed: timeout',
      sshLastSeenAt: Date.now() - 60_000,
      config: {host: '10.8.0.1', port: 19622, username: 'catcd1', auth_method: 'key', workspace: '~/w', python: 'python3'},
    });
    const onRetry = vi.fn();
    render(<ConnectionStatusLine onRetry={onRetry} />);

    expect(screen.getByText(/Lost SSH connection to catcd1@10\.8\.0\.1:19622/)).toBeInTheDocument();
    expect(screen.getByRole('button', {name: /retry/i})).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: /ssh settings/i})).toBeNull();

    fireEvent.click(screen.getByRole('button', {name: /retry/i}));
    await waitFor(() => expect(onRetry).toHaveBeenCalledTimes(1));
  });

  it('shows the backend warning when the backend is down', () => {
    useRemoteStore.setState({
      backendStatus: 'down',
      backendFailures: 1,
      backendLastError: 'Failed to fetch',
      backendLastSeenAt: Date.now() - 60_000,
    });
    render(<ConnectionStatusLine />);

    expect(screen.getByText(/Local backend unreachable/)).toBeInTheDocument();
  });

  it('hides the SSH warning when Runtime target is Local', () => {
    setRuntimeTarget('Local');
    useRemoteStore.setState({
      connected: true,
      sshStatus: 'disconnected',
      sshFailures: 1,
      sshLastSeenAt: Date.now() - 60_000,
    });
    const {container} = render(<ConnectionStatusLine />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('probeConnectionHealth', () => {
  beforeEach(() => {
    useRemoteStore.getState().reset();
    setRuntimeTarget('Server');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function stubFetch(handler: (url: string) => unknown) {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => ({
        ok: true,
        json: async () => handler(url),
      })),
    );
  }

  it('recovers both channels when the backend and server answer', async () => {
    useRemoteStore.setState({
      connected: true,
      sshStatus: 'disconnected',
      sshFailures: 1,
      backendStatus: 'degraded',
      backendFailures: 1,
    });
    stubFetch(() => ({ok: true, jobs: []}));

    const result = await probeConnectionHealth();

    expect(result).toEqual({backendOk: true, sshOk: true});
    expect(useRemoteStore.getState().sshStatus).toBe('connected');
    expect(useRemoteStore.getState().backendStatus).toBe('ok');
  });

  it('trips the backend to down on transport failure and skips the SSH leg', async () => {
    useRemoteStore.setState({
      connected: true,
      backendStatus: 'degraded',
      backendFailures: 1,
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('Failed to fetch');
      }),
    );

    const result = await probeConnectionHealth();

    expect(result).toEqual({backendOk: false, sshOk: true});
    expect(useRemoteStore.getState().backendStatus).toBe('down');
    // SSH leg untouched: no data to judge it by.
    expect(useRemoteStore.getState().sshStatus).toBe('connected');
  });

  it('counts backend-reported SSH errors without wiping on app errors', async () => {
    useRemoteStore.setState({connected: true, sshStatus: 'degraded', sshFailures: 1});
    stubFetch((url: string) =>
      url.endsWith('/remote/jobs')
        ? {ok: false, error: 'SSH connection failed: timeout'}
        : {ok: true, jobs: []},
    );

    await probeConnectionHealth();

    expect(useRemoteStore.getState().sshStatus).toBe('disconnected');
  });
});
