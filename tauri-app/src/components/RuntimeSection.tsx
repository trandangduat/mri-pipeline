import React from 'react';
import {Cpu, ShieldCheck, ListTree, ServerCog, Loader2} from 'lucide-react';
import {Panel, Button, inputCls, labelCls} from './ui';
import {formatBytes} from '../lib/format';
import {runtimeWarnings, currentTargetHardware} from '../lib/runtime';
import {useEnvironment} from '../query/useEnvironment';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useRemoteStore} from '../stores/remoteStore';
import {useUiStore} from '../stores/uiStore';
import {useJobsStore} from '../stores/jobsStore';
import {buildRemotePayload} from '../api/runConfig';
import {useRemoteValidateMutation, useListRemoteJobsMutation} from '../query/useRemote';
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
    if (Array.isArray(result.jobs)) {
      setRemoteResult({
        ok: true,
        connected: remoteResult.connected,
        config: result.config || remoteResult.config,
        hardware: result.hardware || remoteResult.hardware,
        error: '',
        jobs: result.jobs,
        warnings: Array.isArray(result.warnings) ? result.warnings : remoteResult.warnings,
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
      jobs: [],
      warnings: Array.isArray(result.warnings) ? result.warnings : [],
    });
  }

  const validateRemoteMutation = useRemoteValidateMutation();
  const listRemoteJobsMutation = useListRemoteJobsMutation();

  const connectRemote = async () => {
    setRemoteResult({ok: false, connected: false, error: '', jobs: [], hardware: null});
    setBusyKey('connect', true);
    setBusyKey('listRemote', true);
    try {
      const result = await validateRemoteMutation.mutateAsync(remotePayload());
      renderRemoteResult(result);
    } catch (error: unknown) {
      renderRemoteResult({ok: false, connected: false, error: (error as Error).message || 'SSH connection failed.'});
      print('Remote connect failed', {error: (error as Error).message});
    } finally {
      setBusyKey('connect', false);
      setBusyKey('listRemote', false);
    }
  };

  const listRemoteJobs = async () => {
    setBusyKey('listRemote', true);
    try {
      const result = await listRemoteJobsMutation.mutateAsync(remotePayload());
      renderRemoteResult(result);
      print('Remote jobs', result);
    } catch (error: unknown) {
      renderRemoteResult({
        ok: false,
        connected: false,
        error: (error as Error).message || 'Remote job listing failed.',
      });
      print('Remote jobs failed', {error: (error as Error).message});
    } finally {
      setBusyKey('listRemote', false);
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

  const remoteSummary = remoteResult.connected
    ? [
        `Status: Connected`,
        `SSH: ${remoteResult.config?.username || ''}@${remoteResult.config?.host || ''}:${remoteResult.config?.port || ''}`,
        `Auth: ${remoteResult.config?.auth_method || 'unknown'}`,
        `Workspace: ${remoteResult.config?.workspace || ''}`,
        `CPU threads max: ${remoteResult.hardware?.logical_cores || 'unknown'}`,
        `RAM: ${formatBytes(remoteResult.hardware?.total_ram_bytes)}`,
      ]
        .concat(remoteResult.warnings?.length ? ['', ...remoteResult.warnings.map((w) => `Note: ${w}`)] : [])
        .join('\n')
    : remoteResult.error ||
      (remoteResult.jobs?.length ? `${remoteResult.jobs.length} remote job(s) found.` : 'SSH is not connected.');

  return (
    <Panel icon={<Cpu className="h-5 w-5 text-cursor-primary" />} title="Runtime" className="min-w-0">
      <div className="grid gap-6 grid-cols-2 max-[1080px]:grid-cols-1">
        <label className={labelCls}>
          Runtime target
          <select
            id="runtimeTarget"
            name="runtimeTarget"
            value={formValues.runtimeTarget}
            onChange={(e) => setFormField('runtimeTarget', e.target.value)}
            className={inputCls}
          >
            <option value="Local">Local</option>
            <option value="Server">Server</option>
          </select>
        </label>
        <label className={labelCls}>
          RAM %
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
          CPU threads
          <input
            name="cpuThreads"
            type="number"
            min="1"
            value={formValues.cpuThreads}
            onChange={(e) => setFormField('cpuThreads', e.target.value)}
            className={inputCls}
          />
        </label>
        <label className={labelCls}>
          GPU
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

      <div className="mt-5 rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft p-3 text-cursor-body">
        {hardware.label} target: CPU threads max {hardware.logicalCores || 'unknown'} · RAM{' '}
        {formatBytes(hardware.totalRamBytes)}
      </div>
      <div className="mt-3 grid gap-2">
        {warnings.map((warning) => (
          <div
            key={warning}
            className="rounded-lg border border-cursor-timeline-thinking bg-cursor-timeline-thinking/30 px-3 py-2 text-cursor-ink"
          >
            {warning}
          </div>
        ))}
      </div>

      {formValues.runtimeTarget === 'Server' ? (
        <div id="sshBox" className="mt-5 rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft p-5">
          <div className="mb-4 m-0 flex items-center gap-2 text-[18px] font-semibold leading-[1.4] text-cursor-ink">
            <ServerCog className="h-5 w-5 text-cursor-primary" />
            SSH Server
          </div>
          <label className={labelCls}>
            Host
            <input
              name="host"
              placeholder="server.example.edu"
              value={formValues.host}
              onChange={(e) => setFormField('host', e.target.value)}
              className={inputCls}
            />
          </label>
          <div className="mt-6 grid gap-6 grid-cols-2 max-[1080px]:grid-cols-1">
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
                placeholder="netid"
                value={formValues.username}
                onChange={(e) => setFormField('username', e.target.value)}
                className={inputCls}
              />
            </label>
          </div>
          <label className={`${labelCls} mt-6`}>
            Remote Python
            <input
              name="remote_python"
              value={formValues.remote_python}
              onChange={(e) => setFormField('remote_python', e.target.value)}
              className={inputCls}
            />
          </label>
          <label className={`${labelCls} mt-6`}>
            Workspace
            <input
              name="workspace"
              value={formValues.workspace}
              onChange={(e) => setFormField('workspace', e.target.value)}
              className={inputCls}
            />
          </label>
          <label className={`${labelCls} mt-6`}>
            SSH key path
            <input
              name="key_path"
              placeholder="/home/user/.ssh/id_rsa"
              value={formValues.key_path}
              onChange={(e) => setFormField('key_path', e.target.value)}
              className={inputCls}
            />
          </label>
          <label className={`${labelCls} mt-6`}>
            Password
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              value={formValues.password}
              onChange={(e) => setFormField('password', e.target.value)}
              className={inputCls}
            />
          </label>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              icon={busy.connect ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
              onClick={connectRemote}
              disabled={busy.connect || busy.listRemote}
            >
              {busy.connect ? 'Connecting...' : 'Connect'}
            </Button>
            <Button
              variant="ghost"
              icon={busy.listRemote ? <Loader2 className="h-4 w-4 animate-spin" /> : <ListTree className="h-4 w-4" />}
              onClick={listRemoteJobs}
              disabled={busy.listRemote}
            >
              {busy.listRemote ? 'Listing...' : 'List Remote Jobs'}
            </Button>
          </div>
          <div
            className={`mt-4 whitespace-pre-wrap rounded-lg border p-4 text-cursor-body ${remoteResult.ok ? 'border-cursor-hairline bg-white' : 'border-cursor-hairline bg-white'}`}
          >
            {remoteSummary}
          </div>
        </div>
      ) : null}
    </Panel>
  );
}
