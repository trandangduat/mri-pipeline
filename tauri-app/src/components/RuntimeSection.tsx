import React from 'react';
import {
  FolderOpen,
  Cpu,
  ShieldCheck,
  ServerCog,
  Loader2,
} from 'lucide-react';
import {open} from '@tauri-apps/plugin-dialog';
import {Panel, Button, Alert, inputCls, labelCls} from './ui';
import {formatBytes} from '../lib/format';
import {runtimeWarnings, currentTargetHardware} from '../lib/runtime';
import {useEnvironment} from '../query/useEnvironment';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useRemoteStore} from '../stores/remoteStore';
import {useUiStore} from '../stores/uiStore';
import {useJobsStore} from '../stores/jobsStore';
import {buildRemotePayload} from '../api/runConfig';
import {useRemoteValidateMutation} from '../query/useRemote';
import type {RuntimeTarget, RemoteConfigSummary, RemoteHardware, RemoteJobSummary} from '../types/backend';

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

  const busy = useUiStore((s) => s.busy);
  const setBusyKey = useUiStore((s) => s.setBusyKey);
  const appendOutput = useJobsStore((s) => s.appendOutput);

  const print = (label: string, payload: unknown) => {
    appendOutput(`${label}\n${JSON.stringify(payload, null, 2)}\n\n`);
  };

  const remotePayload = () => buildRemotePayload(formValues);

  function renderRemoteResult(result: {
    ok?: boolean | undefined;
    connected?: boolean | undefined;
    config?: RemoteConfigSummary | null | undefined;
    hardware?: RemoteHardware | null | undefined;
    error?: string | undefined;
    errors?: string[] | undefined;
    jobs?: RemoteJobSummary[] | undefined;
    warnings?: string[] | undefined;
  }) {
    if (!result.ok) {
      setRemoteResult({
        ok: false,
        connected: false,
        config: null,
        hardware: null,
        error: result.error || (result.errors || []).join(' ') || 'SSH connection failed.',
        jobs: [],
        warnings: [],
      });
      return;
    }
    if (result.connected !== true) {
      setRemoteResult({
        ok: true,
        connected: false,
        config: null,
        hardware: null,
        error:
          'SSH connection was not confirmed. Restart NeuroFlow so the updated backend is used, then press Connect again.',
        jobs: [],
        warnings: [],
      });
      return;
    }
    setRemoteResult({
      ok: true,
      connected: true,
      config: result.config || null,
      hardware: result.hardware || null,
      error: '',
      jobs: result.jobs || [],
      warnings: Array.isArray(result.warnings) ? result.warnings : [],
    });
  }

  const validateRemoteMutation = useRemoteValidateMutation();

  const connectRemote = async () => {
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
  const warnings = runtimeWarnings({
    runtimeTarget: target,
    hardware,
    cpuThreads: formValues.cpuThreads,
    ramPercent: formValues.ramPercent,
  });

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
                  remoteResult.connected ? 'text-cursor-semantic-success' : 'text-cursor-muted'
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    remoteResult.connected ? 'bg-cursor-semantic-success' : 'bg-cursor-muted'
                  }`}
                />
                {remoteResult.connected ? 'Connected' : 'Disconnected'}
              </span>
            )}
          </span>
          <select
            id="runtimeTarget"
            name="runtimeTarget"
            value={formValues.runtimeTarget}
            onChange={(e) => setFormField('runtimeTarget', e.target.value)}
            className={inputCls}
          >
            <option value="Local">Local</option>
            <option value="Server">Server (SSH)</option>
          </select>
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
            onChange={(e) => setFormField('ramPercent', e.target.value)}
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
            onChange={(e) => setFormField('cpuThreads', e.target.value)}
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
            <select
              id="gpuMode"
              name="gpuMode"
              value={formValues.gpuMode}
              onChange={(e) => setFormField('gpuMode', e.target.value as 'on' | 'off')}
              className={inputCls}
            >
              <option value="off">Off</option>
              <option value="on">On</option>
            </select>
          </label>
        )}
      </div>

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
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.25 text-2xs font-semibold ${
                remoteResult.connected
                  ? 'bg-cursor-semantic-success/10 text-cursor-semantic-success'
                  : 'bg-cursor-surface-strong text-cursor-muted'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  remoteResult.connected ? 'bg-cursor-semantic-success' : 'bg-cursor-muted'
                }`}
              />
              {remoteResult.connected ? 'Connected' : 'Not Connected'}
            </span>
          </div>

          <div className="grid gap-2.5 grid-cols-2">
            <label className={labelCls}>
              Host
              <input
                name="host"
                placeholder="10.8.0.1 or server.domain"
                value={formValues.host}
                onChange={(e) => setFormField('host', e.target.value)}
                className={inputCls}
              />
            </label>
            <label className={labelCls}>
              Port
              <input
                name="port"
                type="number"
                min="1"
                max="65535"
                value={formValues.port}
                onChange={(e) => setFormField('port', e.target.value)}
                className={inputCls}
              />
            </label>
            <label className={labelCls}>
              Username
              <input
                name="username"
                placeholder="username"
                value={formValues.username}
                onChange={(e) => setFormField('username', e.target.value)}
                className={inputCls}
              />
            </label>
            <label className={labelCls}>
              Remote Python
              <input
                name="remote_python"
                placeholder="python3"
                value={formValues.remote_python}
                onChange={(e) => setFormField('remote_python', e.target.value)}
                className={inputCls}
              />
            </label>
            <label className={labelCls}>
              Workspace directory
              <input
                name="workspace"
                placeholder="~/neuroflow-workspace"
                value={formValues.workspace}
                onChange={(e) => setFormField('workspace', e.target.value)}
                className={inputCls}
              />
            </label>
            <label className={labelCls}>
              SSH key path
              <div className="flex items-center gap-1.5">
                <input
                  name="key_path"
                  placeholder="C:\\Users\\ADMIN\\.ssh\\duat"
                  value={formValues.key_path}
                  onChange={(e) => setFormField('key_path', e.target.value)}
                  className={inputCls}
                />
                <Button
                  variant="ghost"
                  icon={<FolderOpen className="h-3.5 w-3.5" />}
                  className="h-8 flex-none px-2.5 text-xs"
                  onClick={browseSshKeyPath}
                  aria-label="Browse SSH key path"
                >
                  Browse
                </Button>
              </div>
            </label>
            <label className={`${labelCls} col-span-2`}>
              Password (optional)
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

            {remoteResult.connected ? (
              <Alert severity="success" size="sm">
                Connected to {remoteResult.config?.username}@{remoteResult.config?.host}:{remoteResult.config?.port} ({remoteResult.hardware?.logical_cores || '—'} cores, {formatBytes(remoteResult.hardware?.total_ram_bytes)} RAM{remoteResult.hardware?.gpus?.length ? `, ${remoteResult.hardware.gpus.length} GPU${remoteResult.hardware.gpus.length > 1 ? 's' : ''}` : ''})
              </Alert>
            ) : remoteResult.error ? (
              <Alert severity="error" size="sm">
                {remoteResult.error}
              </Alert>
            ) : null}

            {remoteResult.connected && Array.isArray(remoteResult.warnings) && remoteResult.warnings.length > 0 && (
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
    </Panel>
  );
}
