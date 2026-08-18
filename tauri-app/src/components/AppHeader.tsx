import React, {useRef, useState, useMemo} from 'react';
import {useNavigate} from 'react-router';
import {
  BrainCircuit,
  SlidersHorizontal,
  Container,
  Activity,
  Save,
  FolderOpen,
  Play,
  Square,
  Loader2,
} from 'lucide-react';
import {Button} from './ui';
import {StartPipelineDialog} from './StartPipelineDialog';
import {useStartPipelineStream} from '../hooks/useStartPipelineStream';
import {useMetadata, useClient} from '../query/useEnvironment';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useJobsStore} from '../stores/jobsStore';
import {useRemoteStore} from '../stores/remoteStore';
import {buildRunConfig, buildRemotePayload} from '../api/runConfig';
import {normalizeJob, sortJobsByStartedAtDesc} from '../jobFormatters';
import type {AppTab} from '../stores/uiStore';

export interface AppHeaderProps {
  activeTab: AppTab;
  onSelectTab: (tab: AppTab) => void;
  jobsCount?: number;
}

export function AppHeader({activeTab, onSelectTab, jobsCount = 0}: AppHeaderProps) {
  const navigate = useNavigate();
  const client = useClient();
  const {data: metadata} = useMetadata();

  const formValues = usePipelineFormStore((s) => s.formValues);
  const applyWorkspaceConfig = usePipelineFormStore((s) => s.applyWorkspaceConfig);
  const setLatestJobs = useJobsStore((s) => s.setLatestJobs);
  const setSelectedJobId = useJobsStore((s) => s.setSelectedJobId);
  const appendOutput = useJobsStore((s) => s.appendOutput);

  const remoteResult = useRemoteStore();
  const [starting, setStarting] = useState(false);
  const workspaceFileInput = useRef<HTMLInputElement>(null);

  const needsLicense = useMemo(() => {
    if (!metadata?.tools) return false;
    const stageKeys = metadata.stage_order || [];
    for (const stage of stageKeys) {
      const toolKey = (formValues as Record<string, unknown>)[`stage_${stage}`] as string | undefined;
      if (toolKey && metadata.tools[toolKey]?.needs_license) return true;
    }
    return false;
  }, [metadata, formValues]);

  const {
    open: dialogOpen,
    steps: dialogSteps,
    complete: dialogComplete,
    success: dialogSuccess,
    job: dialogJob,
    errorMessage: dialogError,
    start: startStream,
    close: closeDialog,
  } = useStartPipelineStream();

  const print = (label: string, payload: unknown) => {
    appendOutput(`${label}\n${JSON.stringify(payload, null, 2)}\n\n`);
  };

  const handleStartPipeline = async () => {
    setStarting(true);
    try {
      if (needsLicense && !formValues.licensePath) {
        print('Start pipeline failed', {
          error: 'FreeSurfer license file is required. Select a license.txt in the Pipeline Steps section.',
        });
        return;
      }
      const isRemote = formValues.runtimeTarget === 'Server';
      const config = buildRunConfig(
        formValues,
        metadata ?? null,
        usePipelineFormStore.getState().selectedStatsAtlases,
      );
      if (isRemote) {
        const payload = {
          ...buildRemotePayload(formValues),
          run_request: config,
        };
        await startStream('/remote/jobs/start/stream', payload, true);
      } else {
        await startStream('/jobs/local/start/stream', config, false);
      }
    } catch (err: unknown) {
      print('Start pipeline failed', {error: (err as Error).message});
    } finally {
      setStarting(false);
    }
  };

  const handleDialogClose = () => {
    closeDialog();
    if (!dialogSuccess) return;

    if (dialogJob) {
      const target = String(dialogJob.target || formValues.runtimeTarget || 'Local');
      const normalized = normalizeJob(dialogJob, target === 'Server' ? 'Server' : 'Local');
      const newJobId = String(normalized.job_id || '');
      if (newJobId) {
        const existing = useJobsStore.getState().latestJobs || [];
        const existingJob = existing.find((j) => String(j.job_id || '') === newJobId) || {};
        const mergedStartedJob = {...existingJob, ...normalized};
        const merged = sortJobsByStartedAtDesc([
          mergedStartedJob,
          ...existing.filter((j) => String(j.job_id || '') !== newJobId),
        ] as Record<string, unknown>[]);
        setLatestJobs(merged);
        setSelectedJobId(newJobId);
        navigate(`/jobs/${encodeURIComponent(newJobId)}`);
        return;
      }
    }

    navigate('/jobs');
  };

  const handleSaveWorkspace = async () => {
    const name = window.prompt('Workspace name:');
    if (!name) return;
    try {
      const sv = usePipelineFormStore.getState().selectedStatsAtlases;
      const fv = usePipelineFormStore.getState().formValues;
      const tools: Record<string, string> = {};
      if (metadata) {
        for (const stage of metadata.stage_order || []) {
          const val = (fv as Record<string, unknown>)[`stage_${stage}`] as string | undefined;
          if (val) tools[stage] = val;
        }
      }
      const workspace: Record<string, unknown> = {
        version: 1,
        type: 'mri-pipeline-workspace',
        name,
        input_source: fv.inputSource,
        input_mode: fv.inputMode,
        input_path: fv.inputPath,
        selected_files: fv.additionalInputPaths
          .split(',')
          .map((s: string) => s.trim())
          .filter(Boolean),
        output_dir: fv.outputDir,
        pipeline_mode: fv.pipelineMode,
        device: fv.gpuMode === 'enabled' ? 'cuda' : 'cpu',
        threads: fv.cpuThreads,
        ram_percent: fv.ramPercent,
        non_recursive: Boolean(fv.nonRecursive),
        run_target: fv.runtimeTarget,
        license_dir: fv.licensePath || '',
        neuroflow_enabled: Boolean(fv.neuroflowEnabled),
        neuroflow_max_concurrent_tasks: Math.max(1, Number(fv.neuroflowMaxConcurrentTasks || 1)),
        neuroflow_machine_profile_id: String(fv.neuroflowMachineProfileId || 'application_default'),
        stats_vectors: sv,
        tools,
        ...(fv.runtimeTarget === 'Server'
          ? {
              remote: {
                host: fv.host,
                port: fv.port,
                username: fv.username,
                python: fv.remote_python,
                workspace: fv.workspace,
                key_path: fv.key_path,
              },
            }
          : {}),
      };
      const res = await client.saveWorkspace(name, workspace);
      if (res.ok) {
        print('Workspace saved', {name});
      } else {
        print('Save workspace failed', {error: res.error || 'Unknown error'});
      }
    } catch (err: unknown) {
      print('Save workspace failed', {error: (err as Error).message});
    }
  };

  const handleWorkspaceFile = async (file?: File | null) => {
    if (!file) return;
    try {
      const content = await file.text();
      const workspace = JSON.parse(content);
      if (!workspace || typeof workspace !== 'object') {
        throw new Error('Workspace JSON must be an object.');
      }
      applyWorkspaceConfig(workspace, metadata ?? undefined);
      print('Loaded workspace file', {name: file.name, type: workspace.type || 'unknown'});
    } catch (error: unknown) {
      print('Load workspace failed', {error: (error as Error).message});
    }
  };

  const startDisabled =
    starting ||
    (formValues.runtimeTarget === 'Server' && !remoteResult.connected) ||
    (needsLicense && !formValues.licensePath);

  const startButtonText = starting
    ? 'Starting...'
    : formValues.runtimeTarget === 'Server' && !remoteResult.connected
      ? 'Connect SSH first'
      : needsLicense && !formValues.licensePath
        ? 'License required'
        : 'Start Pipeline';

  return (
    <header className="sticky top-0 z-30 w-full flex-none border-b border-cursor-hairline bg-white">
      {/* Top Bar: Brand & Action Buttons */}
      <div className="flex h-16 items-center justify-between px-6">
        {/* Brand Logo & Title */}
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 flex-none items-center justify-center rounded-lg bg-cursor-primary text-white">
            <BrainCircuit className="h-5 w-5" />
          </div>
          <div className="flex flex-col">
            <strong className="text-base font-semibold leading-tight tracking-tight text-cursor-ink">
              NeuroFlow
            </strong>
            <span className="text-[11px] font-mono text-cursor-body leading-tight">MRI Pipeline</span>
          </div>
        </div>

        {/* Global Action Buttons */}
        <div className="flex flex-wrap items-center gap-2.5">
          <Button
            variant="ghost"
            icon={<Save className="h-4 w-4 text-cursor-body" />}
            onClick={handleSaveWorkspace}
          >
            Save Workspace
          </Button>

          <Button
            variant="ghost"
            icon={<FolderOpen className="h-4 w-4 text-cursor-body" />}
            onClick={() => workspaceFileInput.current?.click()}
          >
            Load Workspace
          </Button>

          <input
            ref={workspaceFileInput}
            className="hidden"
            type="file"
            accept="application/json,.json"
            onChange={(e) => handleWorkspaceFile(e.target.files?.[0])}
          />

          <Button
            id="headerStartButton"
            variant="primary"
            icon={starting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            onClick={handleStartPipeline}
            disabled={startDisabled}
          >
            {startButtonText}
          </Button>

          <Button
            variant="danger"
            icon={<Square className="h-4 w-4" />}
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
      </div>

      {/* Navigation Tabs Bar */}
      <nav
        aria-label="Main Navigation"
        className="flex items-center gap-8 px-6 border-t border-cursor-hairline"
      >
        <button
          type="button"
          onClick={() => onSelectTab('pipeline')}
          className={`flex items-center gap-2 py-3 text-sm transition-colors border-b-2 -mb-px font-medium ${
            activeTab === 'pipeline'
              ? 'border-cursor-primary text-cursor-primary font-semibold'
              : 'border-transparent text-cursor-body hover:text-cursor-ink'
          }`}
        >
          <SlidersHorizontal className="h-4 w-4" />
          <span>Pipeline Configuration</span>
        </button>

        <button
          type="button"
          onClick={() => onSelectTab('tools')}
          className={`flex items-center gap-2 py-3 text-sm transition-colors border-b-2 -mb-px font-medium ${
            activeTab === 'tools'
              ? 'border-cursor-primary text-cursor-primary font-semibold'
              : 'border-transparent text-cursor-body hover:text-cursor-ink'
          }`}
        >
          <Container className="h-4 w-4" />
          <span>Tools Configuration</span>
        </button>

        <button
          type="button"
          onClick={() => onSelectTab('jobs')}
          className={`flex items-center gap-2 py-3 text-sm transition-colors border-b-2 -mb-px font-medium ${
            activeTab === 'jobs'
              ? 'border-cursor-primary text-cursor-primary font-semibold'
              : 'border-transparent text-cursor-body hover:text-cursor-ink'
          }`}
        >
          <Activity className="h-4 w-4" />
          <span>Jobs Monitor</span>
          <span className="ml-1 inline-flex items-center rounded-full bg-cursor-surface-strong px-2 py-0.5 text-[11px] font-semibold text-cursor-ink">
            {jobsCount}
          </span>
        </button>
      </nav>

      {/* Start Pipeline Stream Dialog */}
      <StartPipelineDialog
        open={dialogOpen}
        onClose={handleDialogClose}
        steps={dialogSteps}
        complete={dialogComplete}
        success={dialogSuccess}
        errorMessage={dialogError}
      />
    </header>
  );
}
