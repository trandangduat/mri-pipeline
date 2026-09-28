import React from 'react';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {remoteValidateResponseSchema} from '../src/api/schemas';
import {DEFAULT_FORM_VALUES} from '../src/api/runConfig';
import {RuntimeSection} from '../src/components/RuntimeSection';
import {usePipelineFormStore} from '../src/stores/pipelineFormStore';
import {useRemoteStore} from '../src/stores/remoteStore';
import {useUiStore} from '../src/stores/uiStore';

const mocks = vi.hoisted(() => ({
  validateMutate: vi.fn(),
  approveMutate: vi.fn(),
}));

vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: vi.fn(),
}));

vi.mock('../src/query/useEnvironment', () => ({
  useEnvironment: () => ({
    data: {
      ok: true,
      python: {ok: true, path: 'python', version: '3.12'},
      docker: {ok: true, path: 'docker'},
      ssh: {ok: true, path: 'ssh'},
      hardware: {hostname: 'local', logical_cores: 8, physical_cores: 8, total_ram_bytes: 16_000_000_000, gpus: []},
    },
  }),
}));

vi.mock('../src/query/useRemote', () => ({
  useRemoteValidateMutation: () => ({mutateAsync: mocks.validateMutate}),
  useApproveRemoteHostKeyMutation: () => ({mutateAsync: mocks.approveMutate}),
}));

function renderSection() {
  const queryClient = new QueryClient({
    defaultOptions: {queries: {retry: false}, mutations: {retry: false}},
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <RuntimeSection />
    </QueryClientProvider>,
  );
}

const trustRequired = {
  host: 'gpu-node',
  port: 22,
  key_type: 'ssh-ed25519',
  fingerprint: 'SHA256:abcdefghijklmnopqrstuvwxyz0123456789ABCD',
};

const connectedResult = {
  ok: true,
  connected: true,
  config: {
    host: 'gpu-node',
    port: 22,
    username: 'alice',
    auth_method: 'password',
    workspace: '~/mri-remote-jobs',
    python: 'python3',
  },
  hardware: {
    hostname: 'gpu-node',
    logical_cores: 32,
    total_ram_bytes: 128_000_000_000,
    gpus: [],
  },
};

describe('SSH host-key approval schema', () => {
  it('keeps trust_required and host_key_changed fields from validate responses', () => {
    const withTrust = remoteValidateResponseSchema.parse({
      ok: false,
      connected: false,
      error: 'SSH host-key approval is required before connecting.',
      trust_required: trustRequired,
      config: connectedResult.config,
    });
    expect(withTrust.trust_required).toEqual(trustRequired);

    const withChanged = remoteValidateResponseSchema.parse({
      ok: false,
      connected: false,
      error: 'SSH host key changed. Connection refused.',
      host_key_changed: {
        ...trustRequired,
        fingerprint: 'SHA256:newFingerprintValue',
        expected_fingerprint: 'SHA256:oldFingerprintValue',
      },
    });
    expect(withChanged.host_key_changed?.fingerprint).toBe('SHA256:newFingerprintValue');
    expect(withChanged.host_key_changed?.expected_fingerprint).toBe('SHA256:oldFingerprintValue');
  });
});

describe('RuntimeSection SSH host-key approval', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    usePipelineFormStore.setState({
      formValues: {
        ...DEFAULT_FORM_VALUES,
        runtimeTarget: 'Server',
        host: 'gpu-node',
        port: 22,
        username: 'alice',
        password: 'secret',
      },
    });
    useRemoteStore.getState().reset();
    useUiStore.setState({
      busy: {connect: false, listRemote: false, refreshTools: false, refreshJobs: false, checkEnv: false},
    });
  });

  it('shows approval dialog and retries connect after trust succeeds', async () => {
    mocks.validateMutate
      .mockResolvedValueOnce({
        ok: false,
        connected: false,
        error: 'SSH host-key approval is required before connecting.',
        trust_required: trustRequired,
        config: connectedResult.config,
      })
      .mockResolvedValueOnce(connectedResult);
    mocks.approveMutate.mockResolvedValue({
      ok: true,
      trusted: true,
      host_key: trustRequired,
    });

    renderSection();
    fireEvent.click(screen.getByRole('button', {name: 'Connect'}));

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Trust SSH host key?'})).toBeInTheDocument();
    expect(screen.getByText('gpu-node:22')).toBeInTheDocument();
    expect(screen.getByText(trustRequired.fingerprint)).toBeInTheDocument();
    expect(screen.getByText(/verify the fingerprint out-of-band/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Trust and Connect'}));

    await waitFor(() => {
      expect(mocks.approveMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          host: 'gpu-node',
          fingerprint: trustRequired.fingerprint,
        }),
      );
    });
    await waitFor(() => {
      expect(mocks.validateMutate).toHaveBeenCalledTimes(2);
    });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
    expect(useRemoteStore.getState().connected).toBe(true);
    expect(useRemoteStore.getState().error).toBe('');
  });

  it('leaves disconnected with a clear message when approval is cancelled', async () => {
    mocks.validateMutate.mockResolvedValue({
      ok: false,
      connected: false,
      error: 'SSH host-key approval is required before connecting.',
      trust_required: trustRequired,
    });

    renderSection();
    fireEvent.click(screen.getByRole('button', {name: 'Connect'}));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
    expect(mocks.approveMutate).not.toHaveBeenCalled();
    expect(useRemoteStore.getState().connected).toBe(false);
    expect(useRemoteStore.getState().error).toMatch(/approval cancelled/i);
  });

  it('refuses host_key_changed without offering trust approval', async () => {
    mocks.validateMutate.mockResolvedValue({
      ok: false,
      connected: false,
      error: 'SSH host key changed. Connection refused.',
      host_key_changed: {
        host: 'gpu-node',
        port: 22,
        key_type: 'ssh-ed25519',
        fingerprint: 'SHA256:newFingerprintValue',
        expected_fingerprint: 'SHA256:oldFingerprintValue',
      },
    });

    renderSection();
    fireEvent.click(screen.getByRole('button', {name: 'Connect'}));

    await waitFor(() => {
      expect(useRemoteStore.getState().connected).toBe(false);
    });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByRole('button', {name: 'Trust and Connect'})).toBeNull();
    expect(mocks.approveMutate).not.toHaveBeenCalled();
    expect(useRemoteStore.getState().error).toMatch(/host key changed/i);
    expect(useRemoteStore.getState().error).toMatch(/SHA256:newFingerprintValue/);
    expect(useRemoteStore.getState().error).toMatch(/SHA256:oldFingerprintValue/);
  });
});
