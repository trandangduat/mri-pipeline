import React, {useCallback, useEffect, useRef, useState} from 'react';
import {useParams} from 'react-router';
import {
  BrainCircuit,
  Download,
  Eraser,
  Eye,
  EyeOff,
  FileCheck,
  ImageIcon,
  Layers,
  LayoutGrid,
  List,
  Loader2,
  RefreshCw,
  Search,
  Square,
  X,
} from 'lucide-react';
import {Card, CardTitle} from '@/components/ui/card';
import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Skeleton} from '@/components/ui/skeleton';
import {StatusPill} from '../components/ui';
import {normalizeJob, normalizeJobState} from '../jobFormatters';
import {
  deriveBatchImages,
  deriveBatchSummary,
  deriveImageSteps,
  deriveJobDisplayMetadata,
  deriveMetricsSeries,
  displayJobState,
  filterLogLines,
  StageStepDetail,
} from '../lib/jobs';
import {useListLocalJobsMutation, useReadLocalEventsMutation, useReadLocalLogMutation} from '../query/useJobs';
import {useListRemoteJobsMutation, useReadRemoteEventsMutation, useReadRemoteLogMutation} from '../query/useRemote';
import {useMetadata} from '../query/useEnvironment';
import {useJobsStore} from '../stores/jobsStore';
import {usePipelineFormStore} from '../stores/pipelineFormStore';
import {useRemoteStore} from '../stores/remoteStore';
import {useUiStore} from '../stores/uiStore';
import {buildRemotePayload} from '../api/runConfig';
import type {PipelineEvent} from '../types/backend';

export function JobsPage() {
  const storeLatestJobs = useJobsStore((s) => s.latestJobs);
  const latestJobs = React.useMemo(() => storeLatestJobs || [], [storeLatestJobs]);

  const setLatestJobs = useJobsStore((s) => s.setLatestJobs);
  const selectedJobId = useJobsStore((s) => s.selectedJobId);
  const setSelectedJobId = useJobsStore((s) => s.setSelectedJobId);
  const jobEvents = useJobsStore((s) => s.jobEvents) || [];
  const setJobEvents = useJobsStore((s) => s.setJobEvents);
  const jobLogSearch = useJobsStore((s) => s.jobLogSearch) || '';
  const setJobLogSearch = useJobsStore((s) => s.setJobLogSearch);
  const outputText = useJobsStore((s) => s.outputText) || '';
  const setOutputText = useJobsStore((s) => s.setOutputText);
  const clearJobLog = useJobsStore((s) => s.clearJobLog);
  const appendOutput = useJobsStore((s) => s.appendOutput);

  const [downloadNotice, setDownloadNotice] = useState<string | null>(null);
  const [isLoadingDetails, setIsLoadingDetails] = useState<boolean>(false);
  const [showRawLog, setShowRawLog] = useState<boolean>(false);
  const [subjectViewMode, setSubjectViewMode] = useState<'grid' | 'list'>('grid');

  // Subject panel search, filter & modal state
  const [subjectSearchQuery, setSubjectSearchQuery] = useState<string>('');
  const [subjectStatusFilter, setSubjectStatusFilter] = useState<'all' | 'success' | 'running' | 'failed' | 'pending'>('all');
  const [activeModalSubjectFile, setActiveModalSubjectFile] = useState<string | null>(null);

  const reqSeqRef = useRef<number>(0);
  const hasInitialRefreshed = useRef<boolean>(false);
  const prevSelectedJobIdRef = useRef<string | null | undefined>(undefined);

  const formValues = usePipelineFormStore((s) => s.formValues);
  const remoteResult = useRemoteStore();

  const busy = useUiStore((s) => s.busy);
  const setBusyKey = useUiStore((s) => s.setBusyKey);

  const {data: metadata} = useMetadata();

  const print = (label: string, payload: unknown) => {
    appendOutput(`${label}\n${JSON.stringify(payload, null, 2)}\n\n`);
  };

  const listLocalJobsMutation = useListLocalJobsMutation();
  const readEventsMutation = useReadLocalEventsMutation();
  const readLogMutation = useReadLocalLogMutation();
  const listRemoteJobsMutation = useListRemoteJobsMutation();
  const readRemoteEventsMutation = useReadRemoteEventsMutation();
  const readRemoteLogMutation = useReadRemoteLogMutation();

  const {jobId: urlJobId} = useParams<{jobId?: string}>();

  const loadJobDetails = useCallback(
    async (jobId: string | null, targetJob?: Record<string, unknown> | null, options: {resetUi?: boolean} = {}) => {
      const resetUi = options.resetUi ?? true;
      const seq = ++reqSeqRef.current;
      if (!jobId) {
        if (seq === reqSeqRef.current) {
          setJobEvents([]);
          setOutputText('Log stream is idle.');
          setActiveModalSubjectFile(null);
          setDownloadNotice(null);
          setIsLoadingDetails(false);
        }
        return;
      }

      if (resetUi) {
        setIsLoadingDetails(true);
        setJobEvents([]);
        setOutputText('');
        setActiveModalSubjectFile(null);
        setDownloadNotice(null);
      }

      const isRemote = String(targetJob?.target || 'Local') === 'Server';

      let events: PipelineEvent[] = [];
      let logText = '';

      try {
        if (isRemote) {
          const remotePayload = buildRemotePayload(formValues);
          const remoteJobDir = String(targetJob?.remote_job_dir || targetJob?.job_dir || jobId);
          const [eventsResult, logResult] = await Promise.all([
            readRemoteEventsMutation
              .mutateAsync({...remotePayload, remote_job_dir: remoteJobDir, job_id: jobId, offset: 0, limit: 5000})
              .catch(() => ({events: []})),
            readRemoteLogMutation
              .mutateAsync({...remotePayload, remote_job_dir: remoteJobDir, job_id: jobId, offset: 0})
              .catch(() => ({text: ''})),
          ]);
          events = Array.isArray(eventsResult?.events) ? (eventsResult.events as PipelineEvent[]) : [];
          logText = logResult?.text || '';
        } else {
          const [eventsResult, logResult] = await Promise.all([
            readEventsMutation.mutateAsync({jobId, offset: 0, limit: 5000}).catch(() => ({events: []})),
            readLogMutation.mutateAsync({jobId, offset: 0, maxBytes: 65536}).catch(() => ({text: ''})),
          ]);
          events = Array.isArray(eventsResult?.events) ? (eventsResult.events as PipelineEvent[]) : [];
          logText = logResult?.text || '';
        }
      } finally {
        if (seq === reqSeqRef.current) {
          setJobEvents(events);
          setOutputText(logText || '');
          if (resetUi) {
            setIsLoadingDetails(false);
          }
        }
      }
    },
    [
      formValues,
      readEventsMutation,
      readLogMutation,
      readRemoteEventsMutation,
      readRemoteLogMutation,
      setJobEvents,
      setOutputText,
    ],
  );

  const refreshJobs = async () => {
    setBusyKey('refreshJobs', true);
    try {
      const localRes = await listLocalJobsMutation.mutateAsync().catch(() => ({jobs: []}));
      const remoteRes = remoteResult.connected
        ? await listRemoteJobsMutation.mutateAsync(buildRemotePayload(formValues)).catch(() => ({jobs: []}))
        : {jobs: []};
      const localJobs = (Array.isArray(localRes?.jobs) ? localRes.jobs : []).map((j) =>
        normalizeJob(j as Record<string, unknown>, 'Local'),
      );
      const remoteJobs = (Array.isArray(remoteRes?.jobs) ? remoteRes.jobs : []).map((j) =>
        normalizeJob(j as Record<string, unknown>, 'Server'),
      );
      const jobs = [...localJobs, ...remoteJobs];
      setLatestJobs(jobs as Record<string, unknown>[]);

      let nextSelected = selectedJobId;
      if (jobs.length && (!nextSelected || !jobs.some((j) => (j as {job_id?: string}).job_id === nextSelected))) {
        nextSelected = (jobs[0] as {job_id?: string})?.job_id || null;
        setSelectedJobId(nextSelected);
      }
      const currentJob = jobs.find((j) => (j as {job_id?: string}).job_id === nextSelected);
      const selectedChanged = nextSelected !== selectedJobId;
      await loadJobDetails(currentJob ? nextSelected : '', currentJob as Record<string, unknown>, {
        resetUi: selectedChanged || !currentJob,
      });
    } catch (err: unknown) {
      print('Refresh jobs failed', {error: (err as Error).message});
    } finally {
      setBusyKey('refreshJobs', false);
    }
  };

  // Sync URL jobId with selectedJobId
  useEffect(() => {
    if (urlJobId && urlJobId !== selectedJobId) {
      setSelectedJobId(urlJobId);
    }
  }, [urlJobId, selectedJobId, setSelectedJobId]);

  // Load details ONLY when selectedJobId actually changes
  useEffect(() => {
    if (prevSelectedJobIdRef.current === selectedJobId) {
      return;
    }
    prevSelectedJobIdRef.current = selectedJobId;

    if (selectedJobId) {
      const jobs = Array.isArray(latestJobs) ? latestJobs : [];
      const jobObj = jobs.find((j) => j && (j as {job_id?: string}).job_id === selectedJobId) as
        | Record<string, unknown>
        | undefined;
      queueMicrotask(() => {
        void loadJobDetails(selectedJobId, jobObj);
      });
    } else {
      queueMicrotask(() => {
        setJobEvents([]);
        setOutputText('Log stream is idle.');
        setActiveModalSubjectFile(null);
        setIsLoadingDetails(false);
      });
    }
  }, [selectedJobId, latestJobs, loadJobDetails, setJobEvents, setOutputText]);

  // Initial mount auto-refresh / auto-select
  useEffect(() => {
    if (hasInitialRefreshed.current) return;
    hasInitialRefreshed.current = true;
    const jobs = Array.isArray(latestJobs) ? latestJobs : [];
    if (jobs.length > 0) {
      if (!selectedJobId) {
        const firstId = String((jobs[0] as {job_id?: string})?.job_id || '');
        if (firstId) {
          setSelectedJobId(firstId);
        }
      }
    } else {
      queueMicrotask(() => {
        void refreshJobs();
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keyboard Escape listener to close subject modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setActiveModalSubjectFile(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const jobsList = Array.isArray(latestJobs) ? latestJobs : [];
  const rawJob = jobsList.find((j) => j && (j as {job_id?: string}).job_id === selectedJobId) || null;
  const job = rawJob as Record<string, unknown> | null;
  const stateStr = (job?.state as string) || 'unknown';
  const normState = normalizeJobState(stateStr);
  const isServerJob = String(job?.target || 'Local') === 'Server';

  // Polling every 2s for running job
  useEffect(() => {
    if (!selectedJobId || normState !== 'running') {
      return;
    }
    const interval = setInterval(() => {
      const jobs = Array.isArray(latestJobs) ? latestJobs : [];
      const targetJob = jobs.find((j) => j && (j as { job_id?: string }).job_id === selectedJobId) as
        | Record<string, unknown>
        | undefined;
      void loadJobDetails(selectedJobId, targetJob, {resetUi: false});
    }, 2000);
    return () => clearInterval(interval);
  }, [selectedJobId, normState, loadJobDetails, latestJobs]);

  const reqSummary = (job?.run_request_summary as Record<string, unknown>) || {};
  const selectedTools = (reqSummary.selected_tools as Record<string, string>) || {};
  const stageOrder = metadata?.stage_order || [
    'format_conversion',
    'brain_extraction',
    'tissue_segmentation',
    'cortical_reconstruction',
    'subcortical_segmentation',
    'parcellation',
    'stat_calculation',
    'export_conversion',
    'aggregate_reporting',
  ];
  const stageLabels: Record<string, string> = {};
  if (metadata?.stages && Array.isArray(metadata.stages)) {
    metadata.stages.forEach((s) => {
      if (s?.id && s?.label) {
        stageLabels[s.id] = s.label;
      }
    });
  }

  const toolDisplayNames = React.useMemo(() => {
    const tools = (metadata?.tools || {}) as Record<string, {display_name?: string}>;
    return Object.fromEntries(Object.entries(tools).map(([key, tool]) => [key, tool.display_name || key]));
  }, [metadata?.tools]);

  const safeEvents = Array.isArray(jobEvents) ? jobEvents : [];
  const batchImages = deriveBatchImages(safeEvents, job || {});
  const batchSummary = deriveBatchSummary(batchImages);
  const displayMeta = deriveJobDisplayMetadata(job, safeEvents);

  const filteredLog = filterLogLines(outputText, jobLogSearch, showRawLog);

  const isTerminal = ['completed', 'failed', 'stopped'].includes(displayMeta.status_reconciled);

  const handleDownloadClick = () => {
    const effDir = String(displayMeta.output_dir_str);
    const subDir = String(job?.download_subdir || '');
    const fullPath = subDir && subDir !== 'N/A' ? `${effDir}/${subDir}` : effDir;
    setDownloadNotice(isServerJob ? `Remote output path: ${fullPath}` : `Local output directory: ${fullPath}`);
    print('Download Outputs', {ok: true, output_path: fullPath, target: isServerJob ? 'Server' : 'Local'});
  };

  // Filter batch images by search query & status filter
  const filteredBatchImages = batchImages.filter((img) => {
    const matchesStatus =
      subjectStatusFilter === 'all'
        ? true
        : subjectStatusFilter === 'pending'
          ? img.status === 'pending'
          : img.status === subjectStatusFilter;

    const q = subjectSearchQuery.trim().toLowerCase();
    if (!q) return matchesStatus;

    const matchesText =
      img.subject_id.toLowerCase().includes(q) ||
      img.input_file.toLowerCase().includes(q) ||
      `#${img.idx}`.includes(q) ||
      String(img.idx) === q;

    return matchesStatus && matchesText;
  });

  const subjectFilterCounts = {
    all: batchImages.length,
    success: batchSummary.success,
    running: batchSummary.running,
    failed: batchSummary.failed,
    pending: batchSummary.pending,
  };

  // Modal active subject
  const modalSubject = batchImages.find((img) => img.input_file === activeModalSubjectFile) || null;
  const modalImageSteps = modalSubject
    ? deriveImageSteps(safeEvents, modalSubject, selectedTools, stageOrder, stageLabels)
    : [];
  const modalMetricsSeries = modalSubject ? deriveMetricsSeries(safeEvents, modalSubject) : {cpuSeries: [], ramSeries: [], latestContainer: ''};

  const totalModalStages = modalImageSteps.length;
  const completedModalStages = modalImageSteps.filter((step) => step.status === 'success').length;

  const getSubjectCurrentStepLabel = (img: typeof batchImages[0]) => {
    if (img.status === 'success') return 'Completed';
    if (img.status === 'failed') return 'Failed';
    if (img.status === 'pending') return 'Waiting in queue';
    const steps = deriveImageSteps(safeEvents, img, selectedTools, stageOrder, stageLabels);
    const runningStep = steps.find((s) => s.status === 'running');
    if (runningStep) return runningStep.label || runningStep.stage;
    const lastSuccess = [...steps].reverse().find((s) => s.status === 'success');
    if (lastSuccess) return `After ${lastSuccess.label || lastSuccess.stage}`;
    return 'Processing...';
  };

  // Stacked bar ratios for Batch Summary (four-segment)
  const totalCount = batchSummary.total || 1;
  const successPct = (batchSummary.success / totalCount) * 100;
  const failedPct = (batchSummary.failed / totalCount) * 100;
  const runningPct = (batchSummary.running / totalCount) * 100;
  const pendingPct = (batchSummary.pending / totalCount) * 100;

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col gap-4 overflow-hidden text-cursor-ink">
      {/* 1. Top Grid: Job Detail (Left) + Batch Summary (Right) */}
      <div className="grid flex-none grid-cols-[minmax(0,1fr)_minmax(20rem,28rem)] gap-4 max-[1180px]:grid-cols-1">
        {/* Left: Job Detail Card */}
        <Card className="rounded-xl border-cursor-hairline bg-white shadow-none p-5">
          {/* Header: Icon + Title + Status Pills */}
          <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-cursor-hairline-soft">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cursor-canvas border border-cursor-hairline text-cursor-primary">
                <BrainCircuit className="h-5 w-5" />
              </div>
              <h2 className="m-0 text-xl font-semibold tracking-tight text-cursor-ink truncate">
                {(job?.display_name as string) || (job?.job_id as string) || 'No Job Selected'}
              </h2>
            </div>
            <div className="flex items-center gap-2">
              <StatusPill state={displayMeta.status_reconciled}>
                {displayJobState(displayMeta.status_reconciled).toUpperCase()}
              </StatusPill>
              <Badge variant="default">{(job?.target as string) || 'Local'}</Badge>
              <Badge variant="secondary">
                {(reqSummary.pipeline_mode as string) || (job?.pipeline_mode as string) || 'Custom'}
              </Badge>
            </div>
          </div>

          {/* Metadata Table */}
          <div className="mt-4 overflow-hidden rounded-lg border border-cursor-hairline">
            <div className="divide-y divide-cursor-hairline-soft text-[14px]">
              {[
                ['Started', displayMeta.started_at_str],
                ['Process PID', String(job?.pid || 'None')],
                ['Mode / Device', `${String(reqSummary.mode || 'N/A')} / ${String(reqSummary.device || 'cpu')}`],
                ['Threads', String(reqSummary.threads || 4)],
                ['RAM Alloc', `${String(reqSummary.ram_percent || 100)}%`],
                ['Container', modalMetricsSeries.latestContainer || 'None'],
                ['Input Path', displayMeta.input_path_str],
                ['Output Path', displayMeta.output_dir_str],
              ].map(([label, value]) => (
                <div key={label} className="grid grid-cols-[10rem_minmax(0,1fr)]">
                  <span className="py-2 px-3 font-semibold text-cursor-ink border-r border-cursor-hairline-soft bg-cursor-canvas-soft">{label}</span>
                  <span className={`py-2 px-3 text-cursor-body ${label === 'Input Path' || label === 'Output Path' ? 'font-mono truncate' : ''}`} title={String(value)}>
                    {String(value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </Card>

        {/* Right: Batch Summary / Actions Card */}
        {job ? (
          <Card className="rounded-xl border-cursor-hairline bg-white shadow-none p-5 flex flex-col justify-between">
            <div>
              <div className="flex items-center gap-2 pb-3 border-b border-cursor-hairline-soft mb-4">
                <Layers className="h-4 w-4 text-cursor-primary" />
                <CardTitle className="text-sm font-semibold text-cursor-ink">Batch Summary</CardTitle>
              </div>

              {/* Four-Segment Stacked Bar */}
              {batchSummary.total > 0 ? (
                <div className="flex w-full h-6 rounded-full overflow-hidden bg-cursor-canvas border border-cursor-hairline mb-3">
                  {successPct > 0 && (
                    <div
                      style={{width: `${successPct}%`}}
                      className="bg-cursor-semantic-success transition-all"
                      title={`Success: ${batchSummary.success}`}
                    />
                  )}
                  {failedPct > 0 && (
                    <div
                      style={{width: `${failedPct}%`}}
                      className="bg-cursor-semantic-error transition-all"
                      title={`Failed: ${batchSummary.failed}`}
                    />
                  )}
                  {runningPct > 0 && (
                    <div
                      style={{width: `${runningPct}%`}}
                      className="bg-cursor-primary transition-all"
                      title={`Running: ${batchSummary.running}`}
                    />
                  )}
                  {pendingPct > 0 && (
                    <div
                      style={{width: `${pendingPct}%`}}
                      className="bg-cursor-hairline-strong transition-all"
                      title={`Pending: ${batchSummary.pending}`}
                    />
                  )}
                </div>
              ) : (
                <div className="flex w-full h-6 rounded-full overflow-hidden bg-cursor-canvas border border-cursor-hairline mb-3 items-center justify-center">
                  <span className="text-[11px] text-cursor-muted">No subjects yet</span>
                </div>
              )}

              {/* Legend */}
              <div className="grid grid-cols-2 gap-2 text-xs mb-4">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-cursor-semantic-success flex-none" />
                  <span className="text-cursor-body">Success</span>
                  <span className="font-semibold text-cursor-ink ml-auto">{batchSummary.success}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-cursor-semantic-error flex-none" />
                  <span className="text-cursor-body">Failed</span>
                  <span className="font-semibold text-cursor-ink ml-auto">{batchSummary.failed}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-cursor-primary flex-none" />
                  <span className="text-cursor-body">Running</span>
                  <span className="font-semibold text-cursor-ink ml-auto">{batchSummary.running}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-cursor-hairline-strong flex-none" />
                  <span className="text-cursor-body">Pending</span>
                  <span className="font-semibold text-cursor-ink ml-auto">{batchSummary.pending}</span>
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex flex-col gap-2">
              <Button
                id="refreshJobsButton"
                variant="default"
                onClick={refreshJobs}
                disabled={busy.refreshJobs}
                className="w-full h-11 bg-cursor-primary hover:bg-cursor-primary-active text-white font-medium"
              >
                {busy.refreshJobs ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Refreshing...
                  </>
                ) : (
                  <>
                    <RefreshCw className="h-4 w-4 mr-1.5" /> Refresh Jobs
                  </>
                )}
              </Button>
              <Button
                onClick={() => print('Stop job', {ok: false, error: 'Stop job requested.'})}
                disabled={!job || normState !== 'running'}
                className="w-full h-11 border-cursor-semantic-error text-cursor-semantic-error bg-white hover:bg-cursor-semantic-error/5 font-medium"
              >
                <Square className="h-4 w-4 mr-1.5" /> Stop Job
              </Button>
              <Button
                variant="ghost"
                onClick={handleDownloadClick}
                disabled={!job || !isTerminal}
                className="w-full h-11 border-cursor-hairline text-cursor-body bg-white hover:bg-cursor-canvas-soft font-medium"
              >
                <Download className="h-4 w-4 mr-1.5" /> Download Outputs
              </Button>
              {downloadNotice && (
                <div className="flex items-center gap-2 rounded-md border border-cursor-hairline bg-cursor-canvas px-3 py-2 text-xs text-cursor-body mt-1">
                  <FileCheck className="h-4 w-4 text-cursor-semantic-success flex-none" />
                  <span>{downloadNotice}</span>
                </div>
              )}
            </div>
          </Card>
        ) : (
          <Card className="rounded-xl border-cursor-hairline bg-white shadow-none p-5 flex items-center justify-center text-cursor-muted text-xs italic">
            No active batch job
          </Card>
        )}
      </div>

      {/* 2. Batch Subjects Card */}
      {isLoadingDetails ? (
        <Card className="flex-1 rounded-xl border-cursor-hairline bg-white shadow-none p-8 text-center text-cursor-body">
          <div className="space-y-3 max-w-md mx-auto">
            <Skeleton className="h-4 w-3/4 mx-auto" />
            <Skeleton className="h-4 w-1/2 mx-auto" />
            <Skeleton className="h-20 w-full" />
          </div>
        </Card>
      ) : job ? (
        <Card className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border-cursor-hairline bg-white p-0 shadow-none">
          {/* Header */}
          <div className="border-b border-cursor-hairline bg-white px-5 py-3 flex-none">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3 min-w-0">
                <Layers className="h-4 w-4 text-cursor-primary flex-none" />
                <h3 className="m-0 text-[16px] font-semibold leading-[1.4] text-cursor-ink">Batch Subjects</h3>
                <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-cursor-canvas-soft px-2 py-0.5 text-[11px] font-semibold text-cursor-muted">
                  {batchImages.length} subjects
                </span>
                {batchSummary.running + batchSummary.pending > 0 && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-cursor-primary/20 bg-cursor-primary/5 px-2 py-0.5 text-[11px] font-semibold text-cursor-primary">
                    <span className="h-1.5 w-1.5 rounded-full bg-cursor-primary animate-pulse" />
                    {batchSummary.running + batchSummary.pending} active
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1.5 flex-none">
                <button
                  type="button"
                  onClick={() => setSubjectViewMode('grid')}
                  className={`inline-flex items-center justify-center h-8 w-8 rounded-md border transition-colors ${
                    subjectViewMode === 'grid'
                      ? 'border-cursor-hairline-strong bg-white text-cursor-ink'
                      : 'border-transparent text-cursor-muted hover:text-cursor-ink'
                  }`}
                  aria-label="Grid view"
                >
                  <LayoutGrid className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setSubjectViewMode('list')}
                  className={`inline-flex items-center justify-center h-8 w-8 rounded-md border transition-colors ${
                    subjectViewMode === 'list'
                      ? 'border-cursor-hairline-strong bg-white text-cursor-ink'
                      : 'border-transparent text-cursor-muted hover:text-cursor-ink'
                  }`}
                  aria-label="List view"
                >
                  <List className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>

          {/* Interior: Search + Filter + Grid */}
          <div className="flex min-h-0 flex-1 flex-col bg-cursor-canvas p-4 overflow-hidden">
            {/* Search & Filter Toolbar */}
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-cursor-hairline bg-white p-2.5 flex-none">
              <label className="relative m-0 block w-[min(20rem,100%)]">
                <input
                  type="search"
                  placeholder="Search subject ID or #..."
                  value={subjectSearchQuery}
                  onChange={(e) => setSubjectSearchQuery(e.target.value)}
                  className="w-full rounded-md border border-cursor-hairline bg-cursor-canvas-soft px-3 py-2 pr-9 text-sm text-cursor-ink placeholder:text-cursor-muted-soft focus:outline-none focus:ring-1 focus:ring-cursor-primary h-10"
                />
                <Search className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cursor-muted" />
              </label>
              <div className="flex flex-wrap items-center gap-1">
                {(['all', 'success', 'running', 'failed', 'pending'] as const).map((st) => {
                  const label = st === 'success' ? 'OK' : st;
                  const count = subjectFilterCounts[st];
                  return (
                    <button
                      key={st}
                      type="button"
                      onClick={() => setSubjectStatusFilter(st)}
                      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-medium transition-colors cursor-pointer capitalize border ${
                        subjectStatusFilter === st
                          ? 'border-cursor-hairline-strong bg-white text-cursor-ink font-semibold'
                          : 'border-transparent text-cursor-body hover:text-cursor-ink'
                      }`}
                    >
                      <span>{label}</span>
                      <span className={`rounded-full px-1.5 text-[11px] ${subjectStatusFilter === st ? 'bg-cursor-canvas-soft text-cursor-muted' : 'text-cursor-muted-soft'}`}>{count}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Subject Grid or List */}
            {subjectViewMode === 'grid' ? (
              <div className="grid grid-cols-3 gap-4 max-[1400px]:grid-cols-2 max-[900px]:grid-cols-1 overflow-y-auto flex-1 min-h-0 p-1">
                {filteredBatchImages.length === 0 ? (
                  <div className="col-span-full flex min-h-[12rem] flex-col items-center justify-center rounded-xl border border-dashed border-cursor-hairline bg-white p-8 text-center">
                    <ImageIcon className="h-8 w-8 text-cursor-muted-soft mb-3" />
                    <h4 className="m-0 text-[15px] font-semibold text-cursor-ink mb-1">
                      {batchImages.length === 0 ? 'No subject events yet' : 'No subjects match these filters'}
                    </h4>
                    <p className="m-0 text-[13px] text-cursor-body">
                      {batchImages.length === 0 ? 'Subjects will appear as the pipeline processes images.' : 'Try a different status filter or search term.'}
                    </p>
                  </div>
                ) : (
                  filteredBatchImages.map((img) => {
                    const currentStepText = getSubjectCurrentStepLabel(img);
                    return (
                      <button
                        key={img.input_file}
                        type="button"
                        onClick={() => setActiveModalSubjectFile(img.input_file)}
                        className="group flex cursor-pointer flex-col rounded-xl border border-cursor-hairline bg-white p-4 text-left transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft focus:outline-none focus:ring-2 focus:ring-cursor-primary/30"
                      >
                        <div className="flex items-start gap-3 min-w-0">
                          <div className={`flex h-9 w-9 items-center justify-center rounded-lg border flex-none ${subjectAccentClasses(img.status)}`}>
                            <BrainCircuit className="h-4 w-4" />
                          </div>
                          <div className="flex flex-col min-w-0 flex-1">
                            <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-cursor-muted">
                              Subject #{String(img.idx).padStart(3, '0')}
                            </span>
                            <span className="truncate text-[14px] font-semibold leading-[1.4] text-cursor-ink group-hover:text-cursor-primary transition-colors">
                              {img.subject_id}
                            </span>
                          </div>
                        </div>
                        <div className="mt-3 pt-3 border-t border-cursor-hairline-soft space-y-1.5">
                          <div className="flex items-center gap-2">
                            <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-cursor-muted w-12 flex-none">Stage</span>
                            <span className="text-[13px] text-cursor-ink truncate">{currentStepText}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-cursor-muted w-12 flex-none">Status</span>
                            <span className={`text-[12px] font-semibold uppercase tracking-[0.06em] ${
                              img.status === 'success' ? 'text-cursor-semantic-success' :
                              img.status === 'failed' ? 'text-cursor-semantic-error' :
                              img.status === 'running' ? 'text-cursor-primary' :
                              'text-cursor-muted'
                            }`}>
                              {img.status.toUpperCase()}
                            </span>
                          </div>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            ) : (
              <div className="flex flex-col gap-2 overflow-y-auto flex-1 min-h-0 p-1">
                {filteredBatchImages.length === 0 ? (
                  <div className="flex min-h-[12rem] flex-col items-center justify-center rounded-xl border border-dashed border-cursor-hairline bg-white p-8 text-center">
                    <ImageIcon className="h-8 w-8 text-cursor-muted-soft mb-3" />
                    <h4 className="m-0 text-[15px] font-semibold text-cursor-ink mb-1">
                      {batchImages.length === 0 ? 'No subject events yet' : 'No subjects match these filters'}
                    </h4>
                    <p className="m-0 text-[13px] text-cursor-body">
                      {batchImages.length === 0 ? 'Subjects will appear as the pipeline processes images.' : 'Try a different status filter or search term.'}
                    </p>
                  </div>
                ) : (
                  filteredBatchImages.map((img) => {
                    const currentStepText = getSubjectCurrentStepLabel(img);
                    return (
                      <button
                        key={img.input_file}
                        type="button"
                        onClick={() => setActiveModalSubjectFile(img.input_file)}
                        className="group flex items-center gap-4 cursor-pointer rounded-lg border border-cursor-hairline bg-white px-4 py-3 text-left transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft focus:outline-none focus:ring-2 focus:ring-cursor-primary/30"
                      >
                        <div className={`flex h-8 w-8 items-center justify-center rounded-md border flex-none ${subjectAccentClasses(img.status)}`}>
                          <BrainCircuit className="h-3.5 w-3.5" />
                        </div>
                        <div className="flex flex-col min-w-0 flex-1">
                          <span className="text-[11px] text-cursor-muted">
                            #{String(img.idx).padStart(3, '0')}
                          </span>
                          <span className="truncate text-[14px] font-semibold text-cursor-ink group-hover:text-cursor-primary transition-colors">
                            {img.subject_id}
                          </span>
                        </div>
                        <div className="flex items-center gap-6 flex-none">
                          <div className="flex flex-col items-end">
                            <span className="text-[10px] uppercase tracking-[0.06em] text-cursor-muted">Stage</span>
                            <span className="text-[13px] text-cursor-ink">{currentStepText}</span>
                          </div>
                          <span className={`text-[12px] font-semibold uppercase tracking-[0.06em] min-w-[4.5rem] text-right ${
                            img.status === 'success' ? 'text-cursor-semantic-success' :
                            img.status === 'failed' ? 'text-cursor-semantic-error' :
                            img.status === 'running' ? 'text-cursor-primary' :
                            'text-cursor-muted'
                          }`}>
                            {img.status.toUpperCase()}
                          </span>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            )}
          </div>
        </Card>
      ) : (
        <Card className="p-10 text-center text-cursor-body bg-white border-cursor-hairline rounded-xl shadow-none">
          <BrainCircuit className="mx-auto mb-3 h-8 w-8 text-cursor-muted" />
          <h3 className="m-0 text-base font-semibold text-cursor-ink mb-1">No Job Selected</h3>
          <p className="m-0 text-xs text-cursor-muted max-w-sm mx-auto mb-4">
            {jobsList.length === 0
              ? 'There are no active or recent pipeline jobs. Run a pipeline from the Configuration tab or refresh jobs.'
              : 'Select a job from the sidebar list to view its execution progress and details.'}
          </p>
          <Button
            variant="default"
            onClick={refreshJobs}
            disabled={busy.refreshJobs}
            className="bg-cursor-primary hover:bg-cursor-primary-active text-white h-10"
          >
            <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh Jobs List
          </Button>
        </Card>
      )}

      {/* 3. Subject Detail Modal Overlay */}
      {modalSubject && (
        <div
          className="fixed inset-0 z-50 bg-cursor-ink/35 backdrop-blur-[2px] flex items-center justify-center p-4"
          onClick={() => setActiveModalSubjectFile(null)}
        >
          <div
            className="relative bg-cursor-canvas border border-cursor-hairline rounded-xl w-[min(1540px,calc(100vw-1.5rem))] max-h-[94vh] flex flex-col shadow-none overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-cursor-hairline px-6 py-5 bg-cursor-canvas flex-none">
              <div className="flex items-center gap-4 min-w-0">
                <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-white px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-muted">
                  #{modalSubject.idx}
                </span>
                <div className="flex flex-col min-w-0 gap-0.5">
                  <h3 className="m-0 text-[22px] font-medium leading-tight tracking-[-0.01em] text-cursor-ink truncate">
                    {modalSubject.subject_id}
                  </h3>
                  <span className="inline-block max-w-md truncate rounded bg-white border border-cursor-hairline-soft px-2 py-1 font-mono text-[11px] text-cursor-body" title={modalSubject.input_file}>
                    {modalSubject.input_file}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-white px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-muted">
                  {completedModalStages}/{totalModalStages} stages
                </span>
                <StatusPill state={modalSubject.status}>{modalSubject.status.toUpperCase()}</StatusPill>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setActiveModalSubjectFile(null)}
                  className="h-8 w-8 p-0 rounded-full text-cursor-muted hover:text-cursor-ink hover:bg-cursor-canvas-soft"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Modal Body: Two-Column Grid */}
            <div className="grid flex-1 min-h-0 gap-5 overflow-hidden p-5 bg-cursor-canvas lg:grid-cols-[minmax(0,1.65fr)_minmax(420px,0.85fr)] max-[1024px]:overflow-auto max-[1024px]:grid-cols-1">
              {/* Left Column: Pipeline Stages */}
              <div className="bg-white border border-cursor-hairline rounded-xl p-5 shadow-none min-h-0 flex flex-col overflow-hidden max-[1024px]:overflow-visible">
                <div className="p-0 pb-3 flex flex-row items-start justify-between border-b border-cursor-hairline-soft mb-4 flex-none">
                  <div className="flex flex-col min-w-0">
                    <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-muted mb-1">Pipeline</span>
                    <h3 className="m-0 text-[18px] font-semibold leading-[1.4] text-cursor-ink">Stage Timeline</h3>
                    <span className="text-[13px] text-cursor-body mt-0.5">Live execution, tools, and resource usage for this subject</span>
                  </div>
                  <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-white px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-muted flex-none mt-0.5">
                    {completedModalStages}/{totalModalStages} complete
                  </span>
                </div>
                <div className="p-0 flex-1 overflow-auto min-h-0">
                  <div className="space-y-2">
                    {modalImageSteps.map((step, idx) => (
                      <VerticalTimelineStepRow key={step.stage} step={step} isLast={idx === modalImageSteps.length - 1} toolDisplayNames={toolDisplayNames} />
                    ))}
                  </div>
                </div>
              </div>

              {/* Right Column: Stacked Cards */}
              <div className="flex min-h-0 flex-col gap-4 overflow-hidden max-[1024px]:min-h-fit">
                {/* Run Telemetry */}
                <div className="bg-white border border-cursor-hairline rounded-xl p-5 shadow-none flex-none">
                  <div className="p-0 pb-3 flex flex-row items-center justify-between">
                    <h3 className="m-0 text-[15px] font-semibold leading-[1.4] text-cursor-ink">Run Telemetry</h3>
                    <span className="text-[12px] text-cursor-muted">events.jsonl metrics</span>
                  </div>
                  <div className="p-0">
                    <div className="grid grid-cols-1 gap-3">
                      <MetricSparkline label="CPU Usage" points={modalMetricsSeries.cpuSeries} unit="%" />
                      <MetricSparkline label="RAM Usage" points={modalMetricsSeries.ramSeries} unit="MB" />
                    </div>
                    <div className="mt-3 text-[12px] text-cursor-muted rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft px-3 py-2 flex items-center justify-between">
                      <span>GPU Usage: Not reported (CPU Mode)</span>
                      <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-white px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-cursor-muted">CPU Mode</span>
                    </div>
                  </div>
                </div>

                {/* Operator Console Log */}
                <div className="bg-white border border-cursor-hairline rounded-xl p-5 shadow-none flex-1 min-h-0 flex flex-col max-[1024px]:flex-none">
                  <div className="p-0 pb-3 flex-none">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="m-0 text-[15px] font-semibold leading-[1.4] text-cursor-ink">Operator Console Log</h3>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowRawLog(!showRawLog)}
                        className="h-8 px-2.5 text-[12px] border-cursor-hairline text-cursor-body"
                      >
                        {showRawLog ? (
                          <>
                            <EyeOff className="h-3.5 w-3.5 mr-1" /> Sanitized
                          </>
                        ) : (
                          <>
                            <Eye className="h-3.5 w-3.5 mr-1" /> Raw
                          </>
                        )}
                      </Button>
                      <label className="relative m-0 block w-full max-w-[10rem]">
                        <input
                          type="search"
                          placeholder="Filter..."
                          value={jobLogSearch}
                          onChange={(e) => setJobLogSearch(e.target.value)}
                          className="w-full rounded-md border border-cursor-hairline bg-white px-3 py-1.5 pr-8 text-[12px] text-cursor-ink placeholder:text-cursor-muted-soft focus:outline-none focus:ring-1 focus:ring-cursor-primary h-8"
                        />
                        <Search className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-cursor-muted" />
                      </label>
                      <Button variant="ghost" size="sm" onClick={clearJobLog} className="h-8 px-2.5 text-[12px] text-cursor-body">
                        <Eraser className="h-3.5 w-3.5 mr-1" /> Clear
                      </Button>
                    </div>
                  </div>
                  <div className="p-0 flex-1 min-h-0 max-[1024px]:flex-none overflow-hidden">
                    <pre
                      className="h-full min-h-[18rem] w-full overflow-auto whitespace-pre-wrap break-words rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft p-3 font-mono text-[12px] leading-relaxed text-cursor-ink"
                      aria-live="polite"
                    >
                      {filteredLog || 'Log stream is empty.'}
                    </pre>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function formatMetricValue(value: number | undefined, suffix: string, fractionDigits = 0) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return 'Not reported';
  return `${value.toFixed(fractionDigits)}${suffix}`;
}

function formatMemory(bytes: number | undefined) {
  if (typeof bytes !== 'number' || !Number.isFinite(bytes) || bytes <= 0) return 'Not reported';
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${Math.round(mb)} MB`;
}

function formatElapsed(seconds: number | undefined) {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) return 'Waiting';
  if (seconds >= 60) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  return `${seconds.toFixed(1)}s`;
}

function StageStatusPill({status}: {status: string}) {
  const cls =
    status === 'success'
      ? 'border-cursor-semantic-success/20 bg-cursor-semantic-success/5 text-cursor-semantic-success'
      : status === 'running'
        ? 'border-cursor-primary/20 bg-cursor-primary/5 text-cursor-primary'
        : status === 'failed'
          ? 'border-cursor-semantic-error/20 bg-cursor-semantic-error/5 text-cursor-semantic-error'
          : 'border-cursor-hairline bg-cursor-canvas-soft text-cursor-muted';
  const label =
    status === 'success' ? 'OK' : status === 'running' ? 'RUNNING' : status === 'failed' ? 'FAIL' : status === 'not_scheduled' ? 'NOT SCHED.' : 'PENDING';
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.08em] ${cls}`}>
      {label}
    </span>
  );
}

function subjectAccentClasses(status: string) {
  if (status === 'success') return 'text-cursor-semantic-success border-cursor-semantic-success/25 bg-cursor-semantic-success/5';
  if (status === 'failed') return 'text-cursor-semantic-error border-cursor-semantic-error/25 bg-cursor-semantic-error/5';
  if (status === 'running') return 'text-cursor-primary border-cursor-primary/25 bg-cursor-primary/5';
  return 'text-cursor-muted border-cursor-hairline bg-cursor-canvas-soft';
}

function StageMetric({label, value}: {label: string; value: string}) {
  return (
    <span className="inline-flex items-baseline gap-1.5 whitespace-nowrap">
      <span className="text-cursor-muted text-[12px]">{label}</span>
      <span className="font-medium text-cursor-ink text-[12px]">{value}</span>
    </span>
  );
}

function VerticalTimelineStepRow({step, isLast, toolDisplayNames}: {step: StageStepDetail; isLast: boolean; toolDisplayNames: Record<string, string>}) {
  const rowClass =
    step?.status === 'running'
      ? 'border-cursor-primary/40 bg-cursor-canvas-soft'
      : step?.status === 'failed'
        ? 'border-cursor-semantic-error/20 bg-cursor-canvas-soft'
        : step?.status === 'not_scheduled'
          ? 'border-cursor-hairline-soft bg-cursor-canvas-soft'
          : 'border-cursor-hairline bg-white';

  const dotClass =
    step?.status === 'success'
      ? 'bg-cursor-semantic-success ring-2 ring-cursor-semantic-success/15'
      : step?.status === 'running'
        ? 'bg-cursor-primary animate-pulse ring-4 ring-cursor-primary/15'
        : step?.status === 'failed'
          ? 'bg-cursor-semantic-error ring-2 ring-cursor-semantic-error/15'
          : step?.status === 'not_scheduled'
            ? 'bg-cursor-hairline-strong'
            : 'bg-white border-2 border-cursor-muted-soft';

  const displayTool = step?.tool ? (toolDisplayNames[step.tool] || step.tool) : '';
  const toolLabel =
    step?.status === 'not_scheduled'
      ? 'No tool selected for this stage'
      : displayTool || 'Tool not reported yet';

  return (
    <div className="relative grid grid-cols-[1.25rem_minmax(0,1fr)] gap-3">
      <div className="relative flex justify-center pt-4">
        {!isLast && <span className="absolute top-7 bottom-[-1rem] w-px bg-cursor-hairline" />}
        <span className={`h-3 w-3 rounded-full flex-none transition-all ${dotClass}`} />
      </div>
      <div className={`rounded-lg border p-3 transition-colors ${rowClass}`}>
        <div className="flex min-w-0 items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="m-0 text-[15px] font-semibold leading-[1.4] text-cursor-ink">{step?.label || step?.stage}</h4>
              <StageStatusPill status={step?.status || 'pending'} />
            </div>
            <p className="m-0 mt-1 text-[13px] leading-[1.4] text-cursor-body">{toolLabel}</p>
          </div>
          {step?.status !== 'not_scheduled' && (
            <div className="flex flex-wrap justify-end overflow-hidden rounded-md border border-cursor-hairline-soft bg-cursor-canvas-soft px-2 py-1 text-[12px]">
              <StageMetric label="Elapsed" value={formatElapsed(step?.elapsed_sec)} />
              <span className="h-4 w-px bg-cursor-hairline mx-1.5" />
              <StageMetric label="CPU" value={formatMetricValue(step?.cpu_pct, '%', 1)} />
              <span className="h-4 w-px bg-cursor-hairline mx-1.5" />
              <StageMetric label="RAM" value={formatMemory(step?.ram_bytes)} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricSparkline({label, points, unit = '%'}: {label: string; points: number[]; unit?: string}) {
  const safePoints = (Array.isArray(points) ? points : []).filter((v) =>
    typeof v === 'number' && Number.isFinite(v),
  );

  const formatValue = (v: number) => {
    if (unit === 'MB' && v >= 1024) return `${(v / 1024).toFixed(1)} GB`;
    return `${v.toFixed(1)}${unit}`;
  };

  const width = 320;
  const height = 104;

  if (safePoints.length === 0) {
    return (
      <div className="flex flex-col justify-between gap-1.5 rounded-xl border border-cursor-hairline-soft bg-cursor-canvas-soft p-4">
        <div className="flex items-center justify-between text-[13px]">
          <span className="font-medium text-cursor-ink">{label}</span>
          <span className="text-[12px] text-cursor-muted">No samples yet</span>
        </div>
        <div className="flex items-center justify-center h-24 text-[12px] text-cursor-muted italic">
          Waiting for data...
        </div>
      </div>
    );
  }

  const minPoint = Math.min(...safePoints);
  const maxPoint = Math.max(...safePoints);
  const padding = Math.max((maxPoint - minPoint) * 0.12, maxPoint === minPoint ? Math.max(maxPoint * 0.1, 1) : 1);
  const yMin = Math.max(0, minPoint - padding);
  const yMax = maxPoint + padding;
  const range = yMax - yMin || 1;

  const pointsStr = safePoints
    .map((val, idx) => {
      const x = (idx / Math.max(safePoints.length - 1, 1)) * width;
      const y = height - 8 - ((val - yMin) / range) * (height - 16);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  const firstX = 0;
  const lastX = safePoints.length > 1 ? width : 0;
  const baselineY = height - 8;
  const areaPoints = `${firstX},${baselineY} ${pointsStr} ${lastX},${baselineY}`;

  const lastPoint = safePoints[safePoints.length - 1] ?? 0;
  const lastXPos = safePoints.length > 1 ? width : 0;
  const lastYPos = height - 8 - ((lastPoint - yMin) / range) * (height - 16);

  const currentVal = safePoints[safePoints.length - 1] ?? 0;
  const peakVal = Math.max(...safePoints);

  const gridLines = [0, 0.5, 1].map((pct) => {
    const y = height - 8 - pct * (height - 16);
    const val = yMin + pct * range;
    return {y, val};
  });

  return (
    <div className="flex flex-col justify-between gap-1.5 rounded-xl border border-cursor-hairline-soft bg-cursor-canvas-soft p-4">
      <div className="flex items-center justify-between text-[13px]">
        <span className="font-medium text-cursor-ink">{label}</span>
        <span className="font-mono text-cursor-primary font-semibold text-[13px]">
          {formatValue(currentVal)} <span className="text-[11px] text-cursor-muted font-normal">(peak: {formatValue(peakVal)})</span>
        </span>
      </div>
      <div className="relative">
        <svg className="h-28 w-full overflow-visible" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
          {gridLines.map((g) => (
            <line key={g.y} x1="0" y1={g.y} x2={width} y2={g.y} className="stroke-cursor-hairline-soft" strokeWidth="1" />
          ))}
          <polygon className="fill-cursor-primary/10" points={areaPoints} />
          <polyline className="fill-none stroke-cursor-primary stroke-2" points={pointsStr} />
          {safePoints.length > 1 && (
            <circle cx={lastXPos} cy={lastYPos} r="3.5" className="fill-white stroke-cursor-primary stroke-2" />
          )}
        </svg>
      </div>
    </div>
  );
}
