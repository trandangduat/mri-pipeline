import React, {useRef} from 'react';
import {Workflow, FolderInput} from 'lucide-react';
import {useNavigate} from 'react-router';
import {Panel, Button, inputCls, labelCls} from '../components/ui';
import {SplitPaneForm} from '../components/SplitPaneForm';
import {RuntimeSection} from '../components/RuntimeSection';
import {useMetadata, useClient} from '../query/useEnvironment';
import {usePrepareRunRequestMutation, useStartLocalJobMutation} from '../query/useJobs';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useJobsStore} from '../stores/jobsStore';
import {useRemoteStore} from '../stores/remoteStore';
import {useUiStore} from '../stores/uiStore';
import {buildRunConfig, buildRemotePayload} from '../api/runConfig';
import {normalizeJob} from '../jobFormatters';

function browseJsonFile(inputRef: React.RefObject<HTMLInputElement | null>) {
  if (inputRef.current) inputRef.current.click();
}

async function readJsonFile(file?: File | null) {
  if (!file) return null;
  return JSON.parse(await file.text());
}

export function PipelineStepsSection() {
  const {data: metadata} = useMetadata();
  const formValues = usePipelineFormStore((s) => s.formValues);
  const setFormField = usePipelineFormStore((s) => s.setFormField);
  const setFormFields = usePipelineFormStore((s) => s.setFormFields);
  const applyPresetConfig = usePipelineFormStore((s) => s.applyPresetConfig);
  const appendOutput = useJobsStore((s) => s.appendOutput);

  const presetFileInput = useRef<HTMLInputElement>(null);

  const print = (label: string, payload: unknown) => {
    appendOutput(`${label}\n${JSON.stringify(payload, null, 2)}\n\n`);
  };

  const handlePipelineModeChange = (value: string) => {
    const presetTools = metadata?.presets?.[value]?.tools || {};
    const patch: Record<string, string> = {pipelineMode: value};
    for (const stage of metadata?.stages || []) {
      patch[`stage_${stage.id}`] = presetTools[stage.id] || '';
    }
    setFormFields(patch);
  };

  async function handlePresetFile(file?: File | null) {
    try {
      const preset = await readJsonFile(file);
      if (!preset || typeof preset !== 'object') {
        throw new Error('Preset JSON must be an object.');
      }
      if (preset.type && !['mri-pipeline-run-config', 'mri-pipeline-preset'].includes(preset.type)) {
        throw new Error('Selected file is not an MRI pipeline preset.');
      }
      applyPresetConfig(preset);
      print('Loaded preset file', {name: file?.name, pipeline_mode: preset.pipeline_mode || 'Custom'});
    } catch (error: unknown) {
      print('Load preset failed', {error: (error as Error).message});
    }
  }

  return (
    <Panel icon={<Workflow className="h-5 w-5 text-cursor-primary" />} title="Pipeline Steps" className="min-w-0">
      <div className="mb-5 grid items-end gap-3 grid-cols-[minmax(16rem,1fr)_auto_auto] max-[1080px]:grid-cols-1">
        <label className={labelCls}>
          Pipeline preset
          <select
            id="pipelineMode"
            name="pipelineMode"
            value={formValues.pipelineMode}
            onChange={(e) => handlePipelineModeChange(e.target.value)}
            className={inputCls}
          >
            {(metadata?.pipeline_modes || []).map((mode) => (
              <option key={mode.id} value={mode.id}>
                {mode.id}
              </option>
            ))}
          </select>
        </label>
        <Button variant="ghost" onClick={() => browseJsonFile(presetFileInput)}>
          Load Preset
        </Button>
        <Button
          variant="ghost"
          onClick={() => print('Save preset', {ok: false, error: 'Preset save UI is not wired in this slice.'})}
        >
          Save Preset
        </Button>
        <input
          ref={presetFileInput}
          className="hidden"
          type="file"
          accept="application/json,.json"
          onChange={(e) => handlePresetFile(e.target.files?.[0])}
        />
      </div>
      <div className="grid border border-cursor-hairline">
        {(metadata?.stages || []).map((stage) => {
          const tools = metadata?.tools_by_stage?.[stage.id] || [];
          return (
            <div
              key={stage.id}
              className="grid items-center gap-4 border-b border-cursor-hairline-soft p-4 last:border-b-0 grid-cols-[minmax(12rem,0.55fr)_minmax(14rem,1fr)] max-[1080px]:grid-cols-1"
            >
              <div className="grid gap-1">
                <strong className="font-semibold text-cursor-ink">{stage.label}</strong>
                <span className="text-[13px] text-cursor-muted">{stage.id}</span>
              </div>
              <select
                name={`stage_${stage.id}`}
                value={((formValues as Record<string, unknown>)[`stage_${stage.id}`] as string) || ''}
                onChange={(e) => setFormField(`stage_${stage.id}`, e.target.value)}
                className={inputCls}
              >
                <option value="">Disabled / Skip</option>
                {tools.map((toolKey) => {
                  const tool = metadata?.tools?.[toolKey];
                  return (
                    <option key={toolKey} value={toolKey}>
                      {tool?.display_name || toolKey}
                    </option>
                  );
                })}
              </select>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

export function StatsAtlasSection() {
  const {data: metadata} = useMetadata();
  const selectedStatsAtlases = usePipelineFormStore((s) => s.selectedStatsAtlases);
  const removeAtlasStore = usePipelineFormStore((s) => s.removeAtlas);
  const order = ['subcortical_volume', 'cortical_volume', 'cortical_thickness'];

  const removeAtlas = (statKey: string, atlasKey: string) =>
    removeAtlasStore(statKey, atlasKey, metadata as Record<string, unknown>);

  return (
    <Panel
      icon={
        <span className="flex h-5 w-5 items-center">
          <BarChartIcon />
        </span>
      }
      title="Stats & Atlas Mapping"
      className="min-w-0"
    >
      <div id="statsAtlasGroups" className="grid gap-4">
        {order.map((statKey) => {
          const stat = metadata?.stats_vectors?.[statKey];
          const selectedAtlases = selectedStatsAtlases[statKey] || [];
          const atlasKeys = Array.isArray(stat?.atlases) ? stat.atlases : [];
          return (
            <section key={statKey} className="grid gap-3 rounded-xl border border-cursor-hairline bg-white p-5">
              <label className="m-0 flex items-center gap-2 text-[13px] font-semibold leading-[1.4] text-cursor-ink">
                <input type="checkbox" name={`stat_${statKey}`} checked readOnly className="h-auto w-auto" />
                <span>{stat?.label || statKey}</span>
              </label>
              <div className="grid gap-2">
                {selectedAtlases.length ? (
                  selectedAtlases.map((atlasKey) => {
                    const atlas = metadata?.atlases?.[atlasKey] || {key: atlasKey, label: atlasKey};
                    return (
                      <div
                        key={atlasKey}
                        className="flex items-center justify-between gap-3 rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft px-3 py-2 text-cursor-ink"
                      >
                        <span>{atlas.label || atlas.key}</span>
                        <button
                          type="button"
                          onClick={() => removeAtlas(statKey, atlas.key)}
                          className="h-6 w-6 flex-none cursor-pointer rounded-md border border-cursor-hairline bg-white text-cursor-muted hover:border-cursor-semantic-error hover:text-cursor-semantic-error"
                        >
                          -
                        </button>
                      </div>
                    );
                  })
                ) : (
                  <div className="mt-4 whitespace-pre-wrap rounded-lg border border-cursor-hairline bg-white p-4 text-cursor-body">
                    No atlas selected.
                  </div>
                )}
              </div>
              <AtlasPicker statKey={statKey} atlasKeys={atlasKeys} selectedAtlases={selectedAtlases} />
            </section>
          );
        })}
      </div>
    </Panel>
  );
}

function AtlasPicker({
  statKey,
  atlasKeys,
  selectedAtlases,
}: {
  statKey: string;
  atlasKeys: string[];
  selectedAtlases: string[];
}) {
  const {data: metadata} = useMetadata();
  const addAtlas = usePipelineFormStore((s) => s.addAtlas);
  const selected = new Set(selectedAtlases);

  if (!atlasKeys.length) {
    return (
      <div className="mt-4 whitespace-pre-wrap rounded-lg border border-cursor-hairline bg-white p-4 text-cursor-body">
        No atlas available.
      </div>
    );
  }
  return (
    <div className="mt-3 grid gap-1.5 rounded-lg border border-cursor-hairline bg-cursor-canvas-soft p-3">
      {atlasKeys.map((atlasKey) => {
        const atlas = metadata?.atlases?.[atlasKey] || {key: atlasKey, label: atlasKey};
        return (
          <button
            key={atlasKey}
            type="button"
            disabled={selected.has(atlasKey)}
            onClick={() => addAtlas(statKey, atlasKey)}
            className="flex min-h-8 cursor-pointer items-center justify-center rounded-md border border-cursor-hairline bg-white px-3 text-xs text-cursor-ink hover:border-cursor-primary hover:text-cursor-primary disabled:cursor-not-allowed disabled:opacity-40"
          >
            {selected.has(atlasKey) ? `Selected: ${atlas.label || atlas.key}` : atlas.label || atlas.key}
          </button>
        );
      })}
    </div>
  );
}

function BarChartIcon() {
  return (
    <svg
      className="h-5 w-5 text-cursor-primary"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M3 3v18h18" />
      <path d="M18 17V9" />
      <path d="M13 17V5" />
      <path d="M8 17v-3" />
    </svg>
  );
}

export function InputOutputSection() {
  const formValues = usePipelineFormStore((s) => s.formValues);
  const setFormField = usePipelineFormStore((s) => s.setFormField);

  return (
    <Panel icon={<FolderInput className="h-5 w-5 text-cursor-primary" />} title="Input & Output" className="min-w-0">
      <div className="grid gap-6 grid-cols-2 max-[1080px]:grid-cols-1">
        <label className={labelCls}>
          Source
          <select
            name="inputSource"
            value={formValues.inputSource}
            onChange={(e) => setFormField('inputSource', e.target.value)}
            className={inputCls}
          >
            <option value="Local">Local</option>
            <option value="Server">Server</option>
          </select>
        </label>
        <label className={labelCls}>
          Input mode
          <select
            name="inputMode"
            value={formValues.inputMode}
            onChange={(e) => setFormField('inputMode', e.target.value)}
            className={inputCls}
          >
            <option value="file">Single file</option>
            <option value="multi_file">Multiple files</option>
            <option value="batch_folder">Batch folder</option>
            <option value="dicom_folder">DICOM folder</option>
          </select>
        </label>
      </div>
      <label className={`${labelCls} mt-6`}>
        Input path
        <input
          id="inputPath"
          name="inputPath"
          value={formValues.inputPath}
          onChange={(e) => setFormField('inputPath', e.target.value)}
          placeholder="/data/sub-001_T1w.nii.gz or /data/batch"
          required
          className={inputCls}
        />
      </label>
      <label className={`${labelCls} mt-6`}>
        Additional files
        <input
          name="additionalInputPaths"
          value={formValues.additionalInputPaths}
          onChange={(e) => setFormField('additionalInputPaths', e.target.value)}
          placeholder="Optional, comma-separated paths for multi-file runs"
          className={inputCls}
        />
      </label>
      <label className={`${labelCls} mt-6`}>
        Output directory
        <input
          id="outputDir"
          name="outputDir"
          value={formValues.outputDir}
          onChange={(e) => setFormField('outputDir', e.target.value)}
          placeholder="/outputs/project"
          required
          className={inputCls}
        />
      </label>
    </Panel>
  );
}

export function PipelinePage() {
  const client = useClient();
  const navigate = useNavigate();
  const {data: metadata} = useMetadata();
  const formValues = usePipelineFormStore((s) => s.formValues);
  const preparedRequest = usePipelineFormStore((s) => s.preparedRequest);
  const setPreparedRequest = usePipelineFormStore((s) => s.setPreparedRequest);
  const applyWorkspaceConfig = usePipelineFormStore((s) => s.applyWorkspaceConfig);

  const setLatestJobs = useJobsStore((s) => s.setLatestJobs);
  const selectedJobId = useJobsStore((s) => s.selectedJobId);
  const setSelectedJobId = useJobsStore((s) => s.setSelectedJobId);
  const setJobEvents = useJobsStore((s) => s.setJobEvents);
  const setOutputText = useJobsStore((s) => s.setOutputText);
  const appendOutput = useJobsStore((s) => s.appendOutput);

  const remoteResult = useRemoteStore();
  const setBusyKey = useUiStore((s) => s.setBusyKey);

  const workspaceFileInput = useRef<HTMLInputElement>(null);

  const print = (label: string, payload: unknown) => {
    appendOutput(`${label}\n${JSON.stringify(payload, null, 2)}\n\n`);
  };

  const loadJobDetails = async (jobId: string | null) => {
    if (!jobId) {
      setJobEvents([]);
      setOutputText('Log stream is idle.');
      return;
    }
    const [eventsResult, logResult] = await Promise.all([
      client.readLocalEvents(jobId).catch(() => ({events: []})),
      client.readLocalLog(jobId, 0, 65536).catch(() => ({text: ''})),
    ]);
    const events = Array.isArray(eventsResult.events) ? eventsResult.events : [];
    setJobEvents(events);
    setOutputText(logResult.text || '');
  };

  const refreshJobs = async () => {
    setBusyKey('refreshJobs', true);
    try {
      const localRes = await client.listLocalJobs().catch(() => ({jobs: []}));
      const remoteRes = remoteResult.connected
        ? await client.listRemoteJobs(buildRemotePayload(formValues)).catch(() => ({jobs: []}))
        : {jobs: []};
      const localJobs = (Array.isArray(localRes.jobs) ? localRes.jobs : []).map((j) => normalizeJob(j, 'Local'));
      const remoteJobs = (Array.isArray(remoteRes.jobs) ? remoteRes.jobs : []).map((j) => normalizeJob(j, 'Server'));
      const jobs = [...localJobs, ...remoteJobs];
      setLatestJobs(jobs);

      let nextSelected = selectedJobId;
      if (jobs.length && (!nextSelected || !jobs.some((j) => j.job_id === nextSelected))) {
        nextSelected = jobs[0]?.job_id || null;
        setSelectedJobId(nextSelected);
      }
      const currentJob = jobs.find((j) => j.job_id === nextSelected);
      await loadJobDetails(currentJob ? nextSelected : '');
    } catch (err: unknown) {
      print('Refresh jobs failed', {error: (err as Error).message});
    } finally {
      setBusyKey('refreshJobs', false);
    }
  };

  const prepareRunRequestMutation = usePrepareRunRequestMutation();
  const startLocalJobMutation = useStartLocalJobMutation();

  const prepareRunRequest = async () => {
    const config = buildRunConfig(formValues, metadata ?? null);
    const request = (await prepareRunRequestMutation.mutateAsync(config)) as Record<string, unknown>;
    setPreparedRequest(request);
    print('Prepared run request', request);
    return request;
  };

  const startPipeline = async () => {
    let request: Record<string, unknown> | null = preparedRequest;
    if (!request?.request) {
      request = await prepareRunRequest();
      if (!request?.ok) return;
    }
    if (!request?.request) return;
    const result = await startLocalJobMutation.mutateAsync(request.request as Record<string, unknown>);
    print('Started local job', result);
    navigate('/jobs');
    void refreshJobs();
  };

  async function handleWorkspaceFile(file?: File | null) {
    try {
      const workspace = await readJsonFile(file);
      if (!workspace || typeof workspace !== 'object') {
        throw new Error('Workspace JSON must be an object.');
      }
      applyWorkspaceConfig(workspace);
      print('Loaded workspace file', {name: file?.name, type: workspace.type || 'unknown'});
    } catch (error: unknown) {
      print('Load workspace failed', {error: (error as Error).message});
    }
  }

  return (
    <>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <Button
          variant="ghost"
          onClick={() => print('Save workspace', {ok: false, error: 'Workspace save UI is not wired in this slice.'})}
        >
          Save Workspace
        </Button>
        <Button variant="ghost" onClick={() => browseJsonFile(workspaceFileInput)}>
          Load Workspace
        </Button>
        <input
          ref={workspaceFileInput}
          className="hidden"
          type="file"
          accept="application/json,.json"
          onChange={(e) => handleWorkspaceFile(e.target.files?.[0])}
        />
        <Button id="startButton" variant="primary" onClick={startPipeline}>
          Start Pipeline
        </Button>
        <Button
          variant="danger"
          onClick={() =>
            print('Stop pipeline', {
              ok: false,
              error: 'Select a running job in Jobs Monitor to stop it in a later slice.',
            })
          }
        >
          Stop Pipeline
        </Button>
      </div>

      <SplitPaneForm
        left={
          <div className="grid min-h-0 content-start gap-6 overflow-y-auto pr-4 [scrollbar-gutter:stable] max-[1080px]:overflow-visible max-[1080px]:pr-0">
            <PipelineStepsSection />
            <StatsAtlasSection />
          </div>
        }
        right={
          <div className="grid min-h-0 content-start gap-6 overflow-y-auto pl-4 pr-0 [scrollbar-gutter:stable] max-[1080px]:overflow-visible max-[1080px]:pl-0">
            <InputOutputSection />
            <RuntimeSection />
          </div>
        }
      />
    </>
  );
}
