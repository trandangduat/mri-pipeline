import React from 'react';
import {
  Cpu,
  ShieldCheck,
  ServerCog,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
} from 'lucide-react';
import {Panel, Button, inputCls, labelCls} from './ui';
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

  const target = (formValues.runtimeTarget === 'Server' ? 'Server' : 'Local') as RuntimeTarget;
  const hardware = currentTargetHardware({runtimeTarget: target, environment, remoteResult});
  const warnings = runtimeWarnings({
    runtimeTarget: target,
    hardware,
    cpuThreads: formValues.cpuThreads,
    ramPercent: formValues.ramPercent,
  });

  return (
    <Panel icon={<Cpu className="h-5 w-5 text-cursor-primary" />} title="Runtime" className="min-w-0">
      {/* 1. Core Compute Grid */}
      <div className="grid gap-3.5 grid-cols-2">
        <label className={labelCls}>
          <span className="flex items-center justify-between">
            <span>Runtime target</span>
            {formValues.runtimeTarget === 'Server' && (
              <span
                className={`inline-flex items-center gap-1 text-[11px] font-medium ${
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
            <span className="text-[11px] font-normal text-cursor-muted">
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
            <span className="text-[11px] font-normal text-cursor-muted">
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
        <label className={labelCls}>
          <span>GPU acceleration</span>
          <select
            name="gpuMode"
            value={formValues.gpuMode}
            onChange={(e) => setFormField('gpuMode', e.target.value)}
            className={inputCls}
          >
            <option value="auto">Auto</option>
            <option value="enabled">Enabled</option>
            <option value="disabled">Disabled</option>
          </select>
        </label>
      </div>

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="mt-3 grid gap-2">
          {warnings.map((warning) => (
            <div
              key={warning}
              className="flex items-center gap-2 rounded-lg border border-cursor-timeline-thinking bg-cursor-timeline-thinking/30 px-3 py-2 text-xs text-cursor-ink"
            >
              <AlertTriangle className="h-4 w-4 text-cursor-semantic-warn flex-none" />
              <span>{warning}</span>
            </div>
          ))}
        </div>
      )}

      {/* 2. SSH Server Section (when Runtime Target is Server) */}
      {formValues.runtimeTarget === 'Server' && (
        <div id="sshBox" className="mt-4 rounded-xl border border-cursor-hairline bg-white p-4">
          <div className="mb-3.5 flex items-center justify-between border-b border-cursor-hairline-soft pb-2.5">
            <div className="flex items-center gap-2 text-sm font-semibold text-cursor-ink">
              <ServerCog className="h-4.5 w-4.5 text-cursor-primary" />
              <span>SSH Server Settings</span>
            </div>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                remoteResult.connected
                  ? 'bg-cursor-semantic-success/10 text-cursor-semantic-success'
                  : 'bg-cursor-surface-strong text-cursor-muted'
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  remoteResult.connected ? 'bg-cursor-semantic-success' : 'bg-cursor-muted'
                }`}
              />
              {remoteResult.connected ? 'Connected' : 'Not Connected'}
            </span>
          </div>

          <div className="grid gap-3 grid-cols-2">
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
              <input
                name="key_path"
                placeholder="/path/to/id_rsa"
                value={formValues.key_path}
                onChange={(e) => setFormField('key_path', e.target.value)}
                className={inputCls}
              />
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

          <div className="mt-3.5 flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              icon={busy.connect ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              onClick={connectRemote}
              disabled={busy.connect}
            >
              {busy.connect ? 'Connecting...' : remoteResult.connected ? 'Reconnect' : 'Connect'}
            </Button>

            {remoteResult.connected ? (
              <span className="flex items-center gap-1.5 text-xs font-medium text-cursor-semantic-success">
                <CheckCircle2 className="h-4 w-4 flex-none" />
                <span>
                  Connected to {remoteResult.config?.username}@{remoteResult.config?.host}:{remoteResult.config?.port} ({remoteResult.hardware?.logical_cores || '—'} cores, {formatBytes(remoteResult.hardware?.total_ram_bytes)} RAM)
                </span>
              </span>
            ) : remoteResult.error ? (
              <span className="flex items-center gap-1.5 text-xs text-cursor-semantic-error">
                <XCircle className="h-4 w-4 flex-none" />
                <span>{remoteResult.error}</span>
              </span>
            ) : (
              <span className="text-xs text-cursor-muted">
                Click Connect to test SSH connection
              </span>
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}
