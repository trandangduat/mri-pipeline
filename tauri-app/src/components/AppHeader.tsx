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
  Loader2,
} from 'lucide-react';
import {Button} from './ui';
import {ThemeToggle} from './ThemeToggle';
import {FontScaleToggle} from './FontScaleToggle';
import {StartPipelineDialog} from './StartPipelineDialog';
import {useStartPipelineStream} from '../hooks/useStartPipelineStream';
import {useMetadata, useEnvironment} from '../query/useEnvironment';
import {EMPTY_STAGE_VIOLATIONS, validateStageTools} from '../lib/stageValidation';
import {currentTargetHardware, runtimeLimitErrors} from '../lib/runtime';
import {defaultConfigName, saveJsonAsDialog} from '../lib/configExport';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useJobsStore} from '../stores/jobsStore';
import {useRemoteStore} from '../stores/remoteStore';
import {buildRunConfig, buildRemotePayload} from '../api/runConfig';
import {normalizeJob, normalizeJobState, normalizeJobTarget, sortJobsByStartedAtDesc} from '../jobFormatters';
import type {AppTab} from '../stores/uiStore';

export interface AppHeaderProps {
  activeTab: AppTab;
  onSelectTab: (tab: AppTab) => void;
  jobsCount?: number;
}

export function AppHeader({activeTab, onSelectTab}: AppHeaderProps) {
  const navigate = useNavigate();
  const {data: metadata} = useMetadata();
  const {data: environment} = useEnvironment();

  const formValues = usePipelineFormStore((s) => s.formValues);
  const applyWorkspaceConfig = usePipelineFormStore((s) => s.applyWorkspaceConfig);
  const setLatestJobs = useJobsStore((s) => s.setLatestJobs);
  const setSelectedJobId = useJobsStore((s) => s.setSelectedJobId);
  const appendOutput = useJobsStore((s) => s.appendOutput);

  const remoteResult = useRemoteStore();
  const [starting, setStarting] = useState(false);
  const [runningJobsWarning, setRunningJobsWarning] = useState<Record<string, unknown>[] | null>(null);
  const [workspaceInvalid, setWorkspaceInvalid] = useState(false);
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

  const executeStartPipeline = async () => {
    setStarting(true);
    try {
      if (needsLicense && !formValues.licensePath) {
        print('Start pipeline failed', {
          error: 'FreeSurfer license file is required. Select a license.txt in the Pipeline Steps section.',
        });
        return;
      }
      const isRemote = formValues.runtimeTarget === 'Server';
      const limitErrors = runtimeLimitErrors({
        runtimeTarget: isRemote ? 'Server' : 'Local',
        hardware: currentTargetHardware({runtimeTarget: isRemote ? 'Server' : 'Local', environment, remoteResult}),
        cpuThreads: formValues.cpuThreads,
        ramPercent: formValues.ramPercent,
      });
      if (limitErrors.length > 0) {
        print('Start pipeline failed', {error: limitErrors.join(' ')});
        return;
      }
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

  const handleStartPipeline = async () => {
    const latestJobs = useJobsStore.getState().latestJobs || [];
    const currentTarget = formValues.runtimeTarget === 'Server' ? 'Server' : 'Local';
    const activeJobs = latestJobs.filter((j) => {
      const target = normalizeJobTarget(j.target);
      const isTargetMatch = target === currentTarget;
      const state = normalizeJobState(j.state || j.status);
      return isTargetMatch && state === 'running';
    });

    if (activeJobs.length > 0) {
      setRunningJobsWarning(activeJobs);
      return;
    }

    await executeStartPipeline();
  };

  const handleDialogClose = () => {
    setStarting(false);
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
        input_source: fv.inputSource,
        input_mode: fv.inputMode === 'batch_folder' ? 'batch_folder' : (fv.inputMode || 'file'),
        input_path: fv.inputPath,
        selected_files: fv.additionalInputPaths
          ? fv.additionalInputPaths
              .split(',')
              .map((s: string) => s.trim())
              .filter(Boolean)
          : [],
        batch_image_count: fv.batchImageCount,
        batch_scan_mode: fv.batchScanMode || (fv.nonRecursive ? 'one-level' : 'recursive'),
        output_dir: fv.outputDir,
        server_output_dir: fv.serverOutputDir || '',
        input_server_dir: fv.inputServerDir || '',
        pipeline_mode: fv.pipelineMode,
        device: fv.gpuMode === 'on' ? 'cuda' : 'cpu',
        threads: fv.cpuThreads,
        ram_percent: fv.ramPercent,
        non_recursive: Boolean(fv.nonRecursive),
        run_target: fv.runtimeTarget,
        license_dir: fv.licensePath || '',
        neuroflow_enabled: Boolean(fv.neuroflowEnabled),
        neuroflow_max_concurrent_tasks: Math.max(1, Number(fv.neuroflowMaxConcurrentTasks || 2)),
        neuroflow_policy: String(fv.neuroflowPolicy || 'B6'),
        neuroflow_max_retries: Math.max(0, Number(fv.neuroflowMaxRetries ?? 3)),
        neuroflow_warmup_enabled: Boolean(fv.neuroflowWarmupEnabled),
        neuroflow_warmup_initial_concurrency: Math.max(1, Number(fv.neuroflowWarmupInitialConcurrency || 2)),
        neuroflow_warmup_safe_successes: Math.max(1, Number(fv.neuroflowWarmupSafeSuccesses || 3)),
        neuroflow_preserve_oom_bounds:
          fv.neuroflowPreserveOomBounds !== undefined ? Boolean(fv.neuroflowPreserveOomBounds) : true,
        neuroflow_estimation_mode: String(fv.neuroflowEstimationMode || 'balanced'),
        neuroflow_max_io_heavy_tasks: Math.max(1, Number(fv.neuroflowMaxIoHeavyTasks || 2)),
        neuroflow_machine_profile_id: 'application_default',
        neuroflow_preset_file: String(fv.neuroflowPresetFile || ''),
        neuroflow_profile_file: String(fv.neuroflowProfileFile || ''),
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
      const result = await saveJsonAsDialog(defaultConfigName('neuroflow-workspace'), workspace);
      if (result.ok) {
        print('Workspace saved', {ok: true, path: result.path});
      } else if (!result.cancelled) {
        print('Save workspace failed', {error: result.error || 'Unknown error'});
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
      if (!workspace || typeof workspace !== 'object' || Array.isArray(workspace)) {
        throw new Error('Workspace file must contain a JSON object.');
      }
      if (workspace.type !== 'mri-pipeline-workspace') {
        throw new Error(
          `"${file.name}" is not a valid NeuroFlow workspace file (missing type "mri-pipeline-workspace").`,
        );
      }
      applyWorkspaceConfig(workspace, metadata ?? undefined);
      print('Loaded workspace file', {name: file.name, type: workspace.type || 'unknown'});
    } catch {
      setWorkspaceInvalid(true);
    }
  };

  const stageViolations = useMemo(
    () => (metadata ? validateStageTools(metadata, formValues) : EMPTY_STAGE_VIOLATIONS),
    [metadata, formValues],
  );

  const startDisabled =
    starting ||
    (formValues.runtimeTarget === 'Server' && !remoteResult.connected) ||
    (needsLicense && !formValues.licensePath) ||
    stageViolations.length > 0;

  const startButtonText = starting
    ? 'Starting...'
    : formValues.runtimeTarget === 'Server' && !remoteResult.connected
      ? 'Connect SSH first'
      : needsLicense && !formValues.licensePath
        ? 'License required'
        : stageViolations.length > 0
          ? 'Fix tool combination'
          : 'Start Pipeline';

  return (
    <header className="sticky top-0 z-30 w-full flex-none border-b border-cursor-hairline bg-cursor-surface-card [--font-scale:1]">
      {/* Top Bar: Brand & Action Buttons */}
      <div className="flex h-12 items-center justify-between px-4">
        {/* Brand Logo, Title & Theme Toggle */}
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 flex-none items-center justify-center rounded-md bg-cursor-primary text-white">
            <BrainCircuit className="h-4 w-4" />
          </div>
          <strong className="text-base font-semibold leading-tight tracking-tight text-cursor-ink">
            NeuroFlow
          </strong>
          <div className="ml-1 flex items-center gap-1.5">
            <FontScaleToggle />
            <ThemeToggle />
          </div>
        </div>

        {/* Global Action Buttons */}
        <div className="flex flex-wrap items-center gap-1.5">
          <Button
            variant="ghost"
            icon={<Save className="h-3.5 w-3.5 text-cursor-body" />}
            onClick={handleSaveWorkspace}
          >
            Save Workspace
          </Button>

          <Button
            variant="ghost"
            icon={<FolderOpen className="h-3.5 w-3.5 text-cursor-body" />}
            onClick={() => workspaceFileInput.current?.click()}
          >
            Load Workspace
          </Button>

          <input
            ref={workspaceFileInput}
            className="hidden"
            type="file"
            accept="application/json,.json"
            onChange={(e) => {
              handleWorkspaceFile(e.target.files?.[0]);
              e.target.value = '';
            }}
          />

          <Button
            id="headerStartButton"
            variant="primary"
            icon={starting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            onClick={handleStartPipeline}
            disabled={startDisabled}
          >
            {startButtonText}
          </Button>
        </div>
      </div>

      {/* Navigation Tabs Bar */}
      <nav
        aria-label="Main Navigation"
        className="flex items-center gap-5 px-4 border-t border-cursor-hairline"
      >
        <button
          type="button"
          onClick={() => onSelectTab('pipeline')}
          className={`flex items-center gap-1.5 py-2 text-sm transition-colors border-b-2 -mb-px font-medium ${
            activeTab === 'pipeline'
              ? 'border-cursor-primary text-cursor-primary font-semibold'
              : 'border-transparent text-cursor-body hover:text-cursor-ink'
          }`}
        >
          <SlidersHorizontal className="h-3.5 w-3.5" />
          <span>Pipeline Configuration</span>
        </button>

        <button
          type="button"
          onClick={() => onSelectTab('tools')}
          className={`flex items-center gap-1.5 py-2 text-sm transition-colors border-b-2 -mb-px font-medium ${
            activeTab === 'tools'
              ? 'border-cursor-primary text-cursor-primary font-semibold'
              : 'border-transparent text-cursor-body hover:text-cursor-ink'
          }`}
        >
          <Container className="h-3.5 w-3.5" />
          <span>Tools Configuration</span>
        </button>

        <button
          type="button"
          onClick={() => onSelectTab('jobs')}
          className={`flex items-center gap-1.5 py-2 text-sm transition-colors border-b-2 -mb-px font-medium ${
            activeTab === 'jobs'
              ? 'border-cursor-primary text-cursor-primary font-semibold'
              : 'border-transparent text-cursor-body hover:text-cursor-ink'
          }`}
        >
          <Activity className="h-3.5 w-3.5" />
          <span>Jobs Monitor</span>
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

      {/* Invalid Workspace File Popup */}
      {workspaceInvalid && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/35 p-3"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setWorkspaceInvalid(false);
          }}
        >
          <div className="relative w-full max-w-[24rem] rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 shadow-none">
            <h3 className="m-0 mb-1.5 text-sm font-semibold leading-[1.3] text-cursor-semantic-error">
              Invalid workspace file
            </h3>
            <p className="m-0 break-words text-xs leading-relaxed text-cursor-body">
              The selected file is not a valid NeuroFlow workspace file.
            </p>
            <div className="mt-3 flex items-center justify-end">
              <Button variant="primary" onClick={() => setWorkspaceInvalid(false)}>
                OK
              </Button>
            </div>
          </div>
        </div>
      )}
      {/* Active Running Job Warning Modal */}
      {runningJobsWarning && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/35 p-3"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setRunningJobsWarning(null);
          }}
        >
          <div className="relative w-full max-w-[28rem] rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 shadow-none">
            <h3 className="m-0 mb-1.5 text-sm font-semibold leading-[1.3] text-cursor-ink">
              Job Already Running
            </h3>
            <p className="m-0 break-words text-xs leading-relaxed text-cursor-body">
              There {runningJobsWarning.length > 1 ? 'are active jobs' : 'is an active job'} currently running on target <span className="font-semibold text-cursor-ink">{formValues.runtimeTarget || 'Local'}</span> ({runningJobsWarning.map((j) => String(j.job_id || j.display_name || 'job')).join(', ')}). Starting another job may cause resource contention or conflicts.
            </p>
            <div className="mt-4 flex items-center justify-end gap-2">
              <Button
                variant="ghost"
                onClick={() => setRunningJobsWarning(null)}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={() => {
                  setRunningJobsWarning(null);
                  executeStartPipeline();
                }}
              >
                Run Anyway
              </Button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
