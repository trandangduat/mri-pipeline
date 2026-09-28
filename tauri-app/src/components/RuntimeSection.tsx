import React, {useState} from 'react';
import {
  FolderOpen,
  Cpu,
  ShieldCheck,
  ServerCog,
  Loader2,
} from 'lucide-react';
import {open} from '@tauri-apps/plugin-dialog';
import {toast} from 'sonner';
import {Panel, Button, Alert, CustomSelect, inputCls, labelCls} from './ui';
import {ConfirmDialog} from './ConfirmDialog';
import {formatBytes} from '../lib/format';
import {runtimeWarnings, runtimeLimitErrors, currentTargetHardware, sanitizeBoundedIntText, clampBoundedIntValue, safeLimitMark, cpuThreadCapForTarget, reclampCpuThreadsForTarget, reclampRamPercentForTarget, RAM_PERCENT_MAX, RAM_PERCENT_MIN, DEFAULT_CPU_THREADS} from '../lib/runtime';
import {useEnvironment} from '../query/useEnvironment';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useRemoteStore} from '../stores/remoteStore';
import {useUiStore} from '../stores/uiStore';
import {useJobsStore} from '../stores/jobsStore';
import {buildRemotePayload} from '../api/runConfig';
import {useApproveRemoteHostKeyMutation, useRemoteValidateMutation} from '../query/useRemote';
import {shortConnectionError} from '../lib/connection';
import type {RuntimeTarget, RemoteConfigSummary, RemoteHardware, RemoteJobSummary, RemoteValidateResponse, SshHostKeyInfo} from '../types/backend';


function formatHostKeyChangedMessage(info: SshHostKeyInfo, fallback?: string): string {
  const lines = [
    fallback || 'SSH host key changed. Connection refused.',
    `Host: ${info.host}:${info.port}`,
    `Key type: ${info.key_type}`,
    `Presented fingerprint: ${info.fingerprint}`,
  ];
  if (info.expected_fingerprint) {
    lines.push(`Previously trusted fingerprint: ${info.expected_fingerprint}`);
  }
  lines.push('Do not trust this host until you verify the key change out-of-band. Automatic trust is not available.');
  return lines.join(' ');
}

function selectedDialogPath(selected: Awaited<ReturnType<typeof open>>) {
  if (Array.isArray(selected)) return selected[0] || '';
  return selected || '';
}

export function RuntimeSection() {
  const {data: environment} = useEnvironment();
  const formValues = usePipelineFormStore((s) => s.formValues);
  const setFormField = usePipelineFormStore((s) => s.setFormField);

  const remoteResult = useRemoteStore();
  const setRemoteResult = useRemoteStore((s) => s.setResult);
  const setSshConnected = useRemoteStore((s) => s.setSshConnected);
  const resetSshHealth = useRemoteStore((s) => s.resetSshHealth);
  const sshStatus = useRemoteStore((s) => s.sshStatus);
  const sshLastError = useRemoteStore((s) => s.sshLastError);
  const sshLastSeenAt = useRemoteStore((s) => s.sshLastSeenAt);
  // `connected` is sticky (last explicit Connect result); the live health
  // can report a mid-session drop while it stays true. `hadSsh` distinguishes
  // a real drop from a first-time Connect that never succeeded.
  const sshDown = sshStatus === 'disconnected';
  const hadSsh = remoteResult.connected || sshLastSeenAt != null;

  const busy = useUiStore((s) => s.busy);
  const setBusyKey = useUiStore((s) => s.setBusyKey);
  const appendOutput = useJobsStore((s) => s.appendOutput);

  const print = (label: string, payload: unknown) => {
    appendOutput(`${label}\n${JSON.stringify(payload, null, 2)}\n\n`);
  };

  const remotePayload = () => buildRemotePayload(formValues);

  const [hostKeyApproval, setHostKeyApproval] = useState<SshHostKeyInfo | null>(null);
  const [trustingHostKey, setTrustingHostKey] = useState(false);

  function renderRemoteResult(result: {
    ok?: boolean | undefined;
    connected?: boolean | undefined;
    config?: RemoteConfigSummary | null | undefined;
    hardware?: RemoteHardware | null | undefined;
    error?: string | undefined;
    errors?: string[] | undefined;
    jobs?: RemoteJobSummary[] | undefined;
    warnings?: string[] | undefined;
    trust_required?: SshHostKeyInfo | undefined;
    host_key_changed?: SshHostKeyInfo | undefined;
  }) {
    if (result.host_key_changed) {
      setHostKeyApproval(null);
      setRemoteResult({
        ok: false,
        connected: false,
        config: null,
        hardware: null,
        error: formatHostKeyChangedMessage(result.host_key_changed, result.error),
        jobs: [],
        warnings: [],
      });
      return;
    }
    if (result.trust_required) {
      setHostKeyApproval(result.trust_required);
      setRemoteResult({
        ok: false,
        connected: false,
        config: null,
        hardware: null,
        error: result.error || 'SSH host-key approval is required before connecting.',
        jobs: [],
        warnings: [],
      });
      return;
    }
    if (!result.ok) {
      setHostKeyApproval(null);
      const error = result.error || (result.errors || []).join(' ') || 'SSH connection failed.';
      setRemoteResult({
        ok: false,
        connected: false,
        config: null,
        hardware: null,
        error,
        jobs: [],
        warnings: [],
      });
      // Intentionally NOT touching SSH health here: a failed explicit Connect
      // means "never connected", not "connection lost". The monitored health
      // (disconnected) is only ever set by mid-session drops.
      return;
    }
    if (result.connected !== true) {
      setHostKeyApproval(null);
      const error =
        'SSH connection was not confirmed. Restart NeuroFlow so the updated backend is used, then press Connect again.';
      setRemoteResult({
        ok: true,
        connected: false,
        config: null,
        hardware: null,
        error,
        jobs: [],
        warnings: [],
      });
      return;
    }
    setHostKeyApproval(null);
    setRemoteResult({
      ok: true,
      connected: true,
      config: result.config || null,
      hardware: result.hardware || null,
      error: '',
      jobs: result.jobs || [],
      warnings: Array.isArray(result.warnings) ? result.warnings : [],
    });
    setSshConnected();
  }

  const validateRemoteMutation = useRemoteValidateMutation();
  const approveHostKeyMutation = useApproveRemoteHostKeyMutation();

  const connectRemote = async () => {
    setHostKeyApproval(null);
    setRemoteResult({ok: false, connected: false, error: '', jobs: [], hardware: null});
    setBusyKey('connect', true);
    try {
      const result = await validateRemoteMutation.mutateAsync(remotePayload());
      renderRemoteResult(result);
    } catch (error: unknown) {
      renderRemoteResult({ok: false, connected: false, error: (error as Error).message || 'SSH connection failed.'});
      print('Remote connect failed', {error: (error as Error).message});
    } finally {
      setBusyKey('connect', false);
    }
  };

  const cancelHostKeyApproval = () => {
    setHostKeyApproval(null);
    setRemoteResult({
      ok: false,
      connected: false,
      config: null,
      hardware: null,
      error: 'SSH host-key approval cancelled. Connection was not established.',
      jobs: [],
      warnings: [],
    });
  };

  const approveHostKeyAndReconnect = async () => {
    if (!hostKeyApproval) return;
    setTrustingHostKey(true);
    setBusyKey('connect', true);
    try {
      const trustResult = await approveHostKeyMutation.mutateAsync({
        ...remotePayload(),
        fingerprint: hostKeyApproval.fingerprint,
      });
      if (!trustResult.ok) {
        if (trustResult.host_key_changed) {
          renderRemoteResult({
            ok: false,
            connected: false,
            error: trustResult.error,
            host_key_changed: trustResult.host_key_changed,
          });
        } else {
          setHostKeyApproval(null);
          setRemoteResult({
            ok: false,
            connected: false,
            config: null,
            hardware: null,
            error: trustResult.error || (trustResult.errors || []).join(' ') || 'Failed to trust SSH host key.',
            jobs: [],
            warnings: [],
          });
        }
        return;
      }
      setHostKeyApproval(null);
      const result: RemoteValidateResponse = await validateRemoteMutation.mutateAsync(remotePayload());
      renderRemoteResult(result);
    } catch (error: unknown) {
      setHostKeyApproval(null);
      renderRemoteResult({ok: false, connected: false, error: (error as Error).message || 'Failed to trust SSH host key.'});
      print('Remote host-key trust failed', {error: (error as Error).message});
    } finally {
      setTrustingHostKey(false);
      setBusyKey('connect', false);
    }
  };

  const browseSshKeyPath = async () => {
    try {
      const selected = await open({
        multiple: false,
        directory: false,
        title: 'Select SSH key',
      });
      const path = selectedDialogPath(selected);
      if (path) {
        setFormField('key_path', path);
      }
    } catch (error: unknown) {
      print('SSH key browse failed', {error: (error as Error).message});
    }
  };

  const target = (formValues.runtimeTarget === 'Server' ? 'Server' : 'Local') as RuntimeTarget;
  const hardware = currentTargetHardware({runtimeTarget: target, environment, remoteResult});
  const limitErrors = runtimeLimitErrors({
    runtimeTarget: target,
    hardware,
    cpuThreads: formValues.cpuThreads,
    ramPercent: formValues.ramPercent,
  });
  const warnings = runtimeWarnings({
    runtimeTarget: target,
    hardware,
    cpuThreads: formValues.cpuThreads,
    ramPercent: formValues.ramPercent,
  });
  const threadMax = hardware.logicalCores ?? null;

  const handleRuntimeTargetChange = (value: string) => {
    setFormField('runtimeTarget', value);
    const nextTarget = (value === 'Server' ? 'Server' : 'Local') as RuntimeTarget;
    if (nextTarget === 'Local') {
      // Server leg abandoned: drop the SSH warning immediately instead of
      // waiting for recovery. The global status line hides with it.
      resetSshHealth();
    }
    const nextThreadCap = cpuThreadCapForTarget({runtimeTarget: nextTarget, environment, remoteResult});
    setFormField('cpuThreads', reclampCpuThreadsForTarget({cpuThreads: formValues.cpuThreads, threadCap: nextThreadCap}));
    setFormField('ramPercent', reclampRamPercentForTarget({ramPercent: formValues.ramPercent}));
  };

  return (
    <Panel icon={<Cpu className="h-4 w-4 text-cursor-primary" />} title="Runtime" className="min-w-0">
      {/* 1. Core Compute Grid */}
      <div className="grid gap-2.5 grid-cols-2">
        <label className={`${labelCls} col-span-2`}>
          <span className="flex items-center justify-between">
            <span>Runtime target</span>
            {formValues.runtimeTarget === 'Server' && (
              <span
                className={`inline-flex items-center gap-1 text-2xs font-medium ${
                  sshDown && hadSsh
                    ? 'text-cursor-semantic-error'
                    : remoteResult.connected
                      ? 'text-cursor-semantic-success'
                      : 'text-cursor-muted'
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    sshDown && hadSsh
                      ? 'bg-cursor-semantic-error'
                      : remoteResult.connected
                        ? 'bg-cursor-semantic-success'
                        : 'bg-cursor-muted'
                  }`}
                />
                {sshDown && hadSsh ? 'Connection lost' : remoteResult.connected ? 'Connected' : 'Disconnected'}
              </span>
            )}
          </span>
          <CustomSelect
            id="runtimeTarget"
            name="runtimeTarget"
            value={formValues.runtimeTarget}
            onChange={(val) => handleRuntimeTargetChange(val)}
            options={[
              {value: 'Local', label: 'Local'},
              {value: 'Server', label: 'Server (SSH)'},
            ]}
          />
        </label>
        <label className={labelCls}>
          <span className="flex items-center justify-between">
            <span>RAM allocation (%)</span>
            <span className="text-2xs font-normal text-cursor-muted">
              {hardware.totalRamBytes ? `Total: ${formatBytes(hardware.totalRamBytes)}` : '—'}
            </span>
          </span>
          <input
            name="ramPercent"
            type="number"
            min="1"
            max="100"
            value={formValues.ramPercent}
            onChange={(e) => setFormField('ramPercent', sanitizeBoundedIntText(e.target.value, RAM_PERCENT_MAX))}
            onBlur={() => {
              const clamped = clampBoundedIntValue(formValues.ramPercent, safeLimitMark(RAM_PERCENT_MAX) ?? RAM_PERCENT_MIN, RAM_PERCENT_MAX);
              if (Number(formValues.ramPercent) !== clamped) {
                toast.warning(`RAM reset to ${clamped}% (valid range: ${RAM_PERCENT_MIN}–${RAM_PERCENT_MAX}%)`);
              }
              setFormField('ramPercent', clamped);
            }}
            className={inputCls}
          />
        </label>
        <label className={labelCls}>
          <span className="flex items-center justify-between">
            <span>CPU threads</span>
            <span className="text-2xs font-normal text-cursor-muted">
              {hardware.logicalCores ? `Max: ${hardware.logicalCores} cores` : '—'}
            </span>
          </span>
          <input
            name="cpuThreads"
            type="number"
            min="1"
            max={hardware.logicalCores || undefined}
            value={formValues.cpuThreads}
            onChange={(e) => setFormField('cpuThreads', sanitizeBoundedIntText(e.target.value, threadMax))}
            onBlur={() => {
              const clamped = clampBoundedIntValue(formValues.cpuThreads, safeLimitMark(threadMax) ?? DEFAULT_CPU_THREADS, threadMax);
              if (Number(formValues.cpuThreads) !== clamped) {
                toast.warning(`CPU threads reset to ${clamped} (valid range: 1–${threadMax ?? '∞'})`);
              }
              setFormField('cpuThreads', clamped);
            }}
            className={inputCls}
          />
        </label>
        {hardware.gpus.length > 0 && (
          <label className={`${labelCls} col-span-2`}>
            <span className="flex items-center justify-between">
              <span>GPU acceleration</span>
              <span className="text-2xs font-normal text-cursor-muted">
                {hardware.gpus.map((gpu, index) => (
                  <span key={index}>
                    {gpu.name || `GPU ${index + 1}`}
                    {' — '}
                    {formatBytes((gpu.total_memory_mib || 0) * 1024 * 1024)} VRAM
                    {gpu.free_memory_mib ? ` (${formatBytes(gpu.free_memory_mib * 1024 * 1024)} free)` : ''}
                  </span>
                ))}
              </span>
            </span>
            <CustomSelect
              id="gpuMode"
              name="gpuMode"
              value={formValues.gpuMode}
              onChange={(val) => setFormField('gpuMode', val as 'on' | 'off')}
              options={[
                {value: 'off', label: 'Off'},
                {value: 'on', label: 'On'},
              ]}
            />
          </label>
        )}
      </div>

      {/* Hard limit errors */}
      {limitErrors.length > 0 && (
        <div className="mt-2.5">
          <Alert severity="error" size="sm">
            {limitErrors.length > 1 ? (
              <ul className="m-0 list-disc space-y-1 pl-4 text-sm">
                {limitErrors.map((error, index) => (
                  <li key={index}>{error}</li>
                ))}
              </ul>
            ) : (
              <div className="text-sm">{limitErrors[0]}</div>
            )}
          </Alert>
        </div>
      )}

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="mt-2.5">
          <Alert severity="warning" size="sm">
            {warnings.length > 1 ? (
              <ul className="m-0 list-disc space-y-1 pl-4 text-sm">
                {warnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            ) : (
              <div className="text-sm">{warnings[0]}</div>
            )}
          </Alert>
        </div>
      )}

      {/* 2. SSH Server Section (when Runtime Target is Server) */}
      {formValues.runtimeTarget === 'Server' && (
        <div id="sshBox" className="mt-3 rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3">
          <div className="mb-2.5 flex items-center justify-between border-b border-cursor-hairline-soft pb-2">
            <div className="flex items-center gap-1.5 text-sm font-semibold text-cursor-ink">
              <ServerCog className="h-4 w-4 text-cursor-primary" />
              <span>SSH Server Settings</span>
            </div>
          </div>

          <div className="grid gap-2.5 grid-cols-2">
            <label className={labelCls}>
              <span className="flex h-4 items-center gap-1">
                <span>Host</span>
                <span className="text-cursor-semantic-error font-medium" title="Required">*</span>
              </span>
              <input
                name="host"
                placeholder="10.8.0.1 or server.domain"
                value={formValues.host || ''}
                onChange={(e) => setFormField('host', e.target.value)}
                className={`${inputCls} ${!formValues.host?.trim() ? 'border-cursor-semantic-error focus:border-cursor-semantic-error' : ''}`}
              />
            </label>
            <label className={labelCls}>
              <span className="flex h-4 items-center gap-1">
                <span>Port</span>
                <span className="text-cursor-semantic-error font-medium" title="Required">*</span>
              </span>
              <input
                name="port"
                type="number"
                min="1"
                max="65535"
                value={formValues.port ?? ''}
                onChange={(e) => setFormField('port', e.target.value)}
                className={`${inputCls} ${!formValues.port ? 'border-cursor-semantic-error focus:border-cursor-semantic-error' : ''}`}
              />
            </label>
            <label className={labelCls}>
              <span className="flex h-4 items-center gap-1">
                <span>Username</span>
                <span className="text-cursor-semantic-error font-medium" title="Required">*</span>
              </span>
              <input
                name="username"
                placeholder="username"
                value={formValues.username || ''}
                onChange={(e) => setFormField('username', e.target.value)}
                className={`${inputCls} ${!formValues.username?.trim() ? 'border-cursor-semantic-error focus:border-cursor-semantic-error' : ''}`}
              />
            </label>
            <label className={labelCls}>
              <span className="flex h-4 items-center gap-1">
                <span>Remote Python</span>
                <span className="text-cursor-semantic-error font-medium" title="Required">*</span>
              </span>
              <input
                name="remote_python"
                placeholder="python3"
                value={formValues.remote_python || ''}
                onChange={(e) => setFormField('remote_python', e.target.value)}
                className={`${inputCls} ${!formValues.remote_python?.trim() ? 'border-cursor-semantic-error focus:border-cursor-semantic-error' : ''}`}
              />
            </label>
            <label className={labelCls}>
              <span className="flex h-4 items-center gap-1">
                <span>Workspace directory</span>
                <span className="text-cursor-semantic-error font-medium" title="Required">*</span>
              </span>
              <input
                name="workspace"
                placeholder="~/neuroflow-workspace"
                value={formValues.workspace || ''}
                onChange={(e) => setFormField('workspace', e.target.value)}
                className={`${inputCls} ${!formValues.workspace?.trim() ? 'border-cursor-semantic-error focus:border-cursor-semantic-error' : ''}`}
              />
            </label>
            <label className={labelCls}>
              <span className="flex h-4 items-center gap-1">
                <span>SSH key path</span>
              </span>
              <div className="flex items-center gap-1.5">
                <input
                  name="key_path"
                  placeholder="Select SSH key via Browse"
                  value={formValues.key_path}
                  readOnly
                  className={`${inputCls} bg-cursor-canvas-soft text-cursor-muted`}
                />
                <Button
                  variant="ghost"
                  icon={<FolderOpen className="h-3.5 w-3.5" />}
                  onClick={browseSshKeyPath}
                  aria-label="Browse SSH key path"
                >
                  Browse
                </Button>
              </div>
            </label>
            <label className={`${labelCls} col-span-2`}>
              <span className="flex h-4 items-center gap-1">
                <span>Password (optional)</span>
              </span>
              <input
                name="password"
                type="password"
                autoComplete="current-password"
                placeholder="Enter password if key is not used"
                value={formValues.password}
                onChange={(e) => setFormField('password', e.target.value)}
                className={inputCls}
              />
            </label>
          </div>

          <div className="mt-3 flex flex-col gap-2.5">
            <div>
              <Button
                variant="primary"
                icon={busy.connect ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
                onClick={connectRemote}
                disabled={busy.connect}
              >
                {busy.connect ? 'Connecting...' : remoteResult.connected ? 'Reconnect' : 'Connect'}
              </Button>
            </div>

            {sshDown && hadSsh ? (
              <Alert severity="error" size="sm" badgeLabel="Connection lost">
                <span title={sshLastError || remoteResult.error}>
                  The SSH connection dropped
                  {sshLastError ? ` (${shortConnectionError(sshLastError)})` : ''}. Press Reconnect to
                  restore it.
                </span>
              </Alert>
            ) : remoteResult.connected ? (
              <Alert severity="success" size="sm">
                Connected to {remoteResult.config?.username}@{remoteResult.config?.host}:{remoteResult.config?.port} ({remoteResult.hardware?.logical_cores || '—'} cores, {formatBytes(remoteResult.hardware?.total_ram_bytes)} RAM{remoteResult.hardware?.gpus?.length ? `, ${remoteResult.hardware.gpus.length} GPU${remoteResult.hardware.gpus.length > 1 ? 's' : ''}` : ''})
              </Alert>
            ) : remoteResult.error ? (
              <Alert severity="error" size="sm">
                <span title={remoteResult.error}>{shortConnectionError(remoteResult.error)}</span>
              </Alert>
            ) : null}

            {!sshDown && remoteResult.connected && Array.isArray(remoteResult.warnings) && remoteResult.warnings.length > 0 && (
              <Alert severity="warning" size="sm">
                {remoteResult.warnings.length > 1 ? (
                  <ul className="m-0 list-disc space-y-1 pl-4 text-sm">
                    {remoteResult.warnings.map((warning, index) => (
                      <li key={index}>{warning}</li>
                    ))}
                  </ul>
                ) : (
                  <div className="text-sm">{remoteResult.warnings[0]}</div>
                )}
              </Alert>
            )}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={hostKeyApproval != null}
        title="Trust SSH host key?"
        entityName={hostKeyApproval ? `${hostKeyApproval.host}:${hostKeyApproval.port}` : undefined}
        description={
          hostKeyApproval ? (
            <div className="space-y-2">
              <p className="m-0">
                This server has not been trusted before. Verify the fingerprint out-of-band (for example with your
                administrator or a known-good source) before continuing. NeuroFlow will not connect until you approve.
              </p>
              <p className="m-0">
                Key type: <span className="font-mono text-cursor-ink">{hostKeyApproval.key_type}</span>
              </p>
              <p className="m-0">Fingerprint (SHA-256):</p>
              <pre className="m-0 max-h-28 overflow-auto whitespace-pre-wrap break-all rounded border border-cursor-hairline-soft bg-cursor-canvas-soft px-2 py-1.5 font-mono text-2xs text-cursor-ink select-all">
                {hostKeyApproval.fingerprint}
              </pre>
            </div>
          ) : null
        }
        confirmLabel="Trust and Connect"
        confirmLoadingLabel="Trusting..."
        cancelLabel="Cancel"
        isLoading={trustingHostKey}
        onConfirm={approveHostKeyAndReconnect}
        onClose={cancelHostKeyApproval}
      />
    </Panel>
  );
}
