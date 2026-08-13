import React, {useCallback, useEffect, useRef, useState} from 'react';
import {useParams} from 'react-router';
import {
  Activity,
  Download,
  Eraser,
  Eye,
  EyeOff,
  FileCheck,
  ImageIcon,
  Layers,
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
  const runningModalStage = modalImageSteps.find((step) => step.status === 'running');
  const failedModalStages = modalImageSteps.filter((step) => step.status === 'failed').length;
  const scheduledModalStages = modalImageSteps.filter((step) => step.status !== 'not_scheduled');

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

  // Stacked bar ratios for Batch Summary
  const totalCount = batchSummary.total || 1;
  const successPct = Math.round((batchSummary.success / totalCount) * 100);
  const failedPct = Math.round((batchSummary.failed / totalCount) * 100);
  const activeCount = batchSummary.running + batchSummary.pending;
  const activePct = Math.max(0, 100 - successPct - failedPct);

  return (
    <div className="flex flex-col gap-3 text-[#26251e] max-w-full h-full overflow-hidden flex-1">
      {/* 1. Header Row: Job Overview (Left 8 cols) + Batch Summary Card (Right 4 cols) */}
      <div className="grid grid-cols-12 gap-4 max-[1080px]:grid-cols-1 flex-none">
        {/* Left Column (8 cols): Basic Job Info Header Card */}
        <Card className="col-span-8 max-[1080px]:col-span-1 p-4 bg-white border-[#e6e5e0]">
          {/* Line 1: Job Title + Status Pill */}
          <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b border-[#f2f2ee]">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#f7f7f4] border border-[#e6e5e0] text-[#0077b6]">
                <Activity className="h-5 w-5" />
              </div>
              <div className="flex flex-col min-w-0">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-[#807d72]">
                  Job Overview
                </span>
                <h2 className="m-0 text-xl font-semibold tracking-tight text-[#26251e] truncate">
                  {(job?.display_name as string) || (job?.job_id as string) || 'No Job Selected'}
                </h2>
              </div>
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

          {/* Line 2 & 3: Metadata Table */}
          <div className="my-3 overflow-hidden rounded-lg border border-[#e6e5e0]">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-[#f7f7f4] border-b border-[#e6e5e0] text-[10px] uppercase font-semibold text-[#807d72] tracking-wider">
                  <th className="py-1.5 px-3 w-1/3">Field</th>
                  <th className="py-1.5 px-3">Value</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#e6e5e0] text-[#26251e]">
                <tr>
                  <td className="py-1.5 px-3 font-bold">Started</td>
                  <td className="py-1.5 px-3">{displayMeta.started_at_str}</td>
                </tr>
                <tr>
                  <td className="py-1.5 px-3 font-bold">Process PID</td>
                  <td className="py-1.5 px-3">{String(job?.pid || 'None')}</td>
                </tr>
                <tr>
                  <td className="py-1.5 px-3 font-bold">Mode / Device</td>
                  <td className="py-1.5 px-3">{`${String(reqSummary.mode || 'N/A')} / ${String(reqSummary.device || 'cpu')}`}</td>
                </tr>
                <tr>
                  <td className="py-1.5 px-3 font-bold">Threads</td>
                  <td className="py-1.5 px-3">{String(reqSummary.threads || 4)}</td>
                </tr>
                <tr>
                  <td className="py-1.5 px-3 font-bold">RAM Alloc</td>
                  <td className="py-1.5 px-3">{`${String(reqSummary.ram_percent || 100)}%`}</td>
                </tr>
                <tr>
                  <td className="py-1.5 px-3 font-bold">Container</td>
                  <td className="py-1.5 px-3">{modalMetricsSeries.latestContainer || 'None'}</td>
                </tr>
                <tr>
                  <td className="py-1.5 px-3 font-bold">Input Path</td>
                  <td className="py-1.5 px-3 truncate max-w-[20rem]">{displayMeta.input_path_str}</td>
                </tr>
                <tr>
                  <td className="py-1.5 px-3 font-bold">Output Path</td>
                  <td className="py-1.5 px-3 truncate max-w-[20rem]">{displayMeta.output_dir_str}</td>
                </tr>
                <tr>
                  <td className="py-1.5 px-3 font-bold">NeuroFlow</td>
                  <td className="py-1.5 px-3">{reqSummary.neuroflow_enabled ? 'Enabled' : 'Disabled'}</td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Line 4: Action Controls Row (Default Button Padding) */}
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-[#f2f2ee] pt-3">
            <div className="flex flex-wrap items-center gap-2.5">
              <Button
                id="refreshJobsButton"
                variant="default"
                size="default"
                onClick={refreshJobs}
                disabled={busy.refreshJobs}
                className="bg-[#0077b6] hover:bg-[#005f92] text-white font-medium"
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
                variant="destructive"
                size="default"
                onClick={() => print('Stop job', {ok: false, error: 'Stop job requested.'})}
                disabled={!job || normState !== 'running'}
                className="font-medium"
              >
                <Square className="h-4 w-4 mr-1.5" /> Stop Job
              </Button>
              <Button
                variant="outline"
                size="default"
                onClick={handleDownloadClick}
                disabled={!job || !isTerminal}
                className="font-medium"
              >
                <Download className="h-4 w-4 mr-1.5" /> Download Outputs
              </Button>
            </div>
            {downloadNotice && (
              <div className="flex items-center gap-2 rounded-md border border-[#e6e5e0] bg-[#f7f7f4] px-3 py-1.5 text-xs text-[#26251e]">
                <FileCheck className="h-4 w-4 text-emerald-600 flex-none" />
                <span>{downloadNotice}</span>
              </div>
            )}
          </div>
        </Card>

        {/* Right Column (4 cols): Separate Batch Summary Card with Stacked Bar Chart */}
        {job ? (
          <Card className="col-span-4 max-[1080px]:col-span-1 p-4 bg-white border-[#e6e5e0] flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-[#f2f2ee] pb-2.5 mb-3">
                <div className="flex items-center gap-2">
                  <Layers className="h-4 w-4 text-[#0077b6]" />
                  <CardTitle className="text-sm font-semibold text-[#26251e]">Batch Summary</CardTitle>
                </div>
              </div>

              {/* Stacked Progress Bar */}
              <div className="flex w-full h-7 rounded-full overflow-hidden bg-[#f7f7f4] border border-[#e6e5e0] my-3">
                {successPct > 0 && (
                  <div
                    style={{width: `${successPct}%`}}
                    className="bg-emerald-500 flex items-center justify-center text-[10px] font-bold text-white transition-all"
                    title={`Success: ${successPct}%`}
                  >
                    {successPct > 8 ? `${successPct}%` : ''}
                  </div>
                )}
                {failedPct > 0 && (
                  <div
                    style={{width: `${failedPct}%`}}
                    className="bg-rose-500 flex items-center justify-center text-[10px] font-bold text-white transition-all"
                    title={`Failed: ${failedPct}%`}
                  >
                    {failedPct > 8 ? `${failedPct}%` : ''}
                  </div>
                )}
                {activePct > 0 && (
                  <div
                    style={{width: `${activePct}%`}}
                    className="bg-[#0077b6] flex items-center justify-center text-[10px] font-bold text-white transition-all"
                    title={`Running / Pending: ${activePct}%`}
                  >
                    {activePct > 8 ? `${activePct}%` : ''}
                  </div>
                )}
              </div>

              {/* Legend List */}
              <div className="flex flex-col gap-2 pt-2 border-t border-[#f2f2ee] text-xs">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 flex-none" />
                    <span className="text-[#5a5852]">Success</span>
                  </span>
                  <span className="font-semibold text-[#26251e]">{batchSummary.success}</span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full bg-rose-500 flex-none" />
                    <span className="text-[#5a5852]">Failed</span>
                  </span>
                  <span className="font-semibold text-[#26251e]">{batchSummary.failed}</span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full bg-[#0077b6] flex-none" />
                    <span className="text-[#5a5852]">Running / Pending</span>
                  </span>
                  <span className="font-semibold text-[#26251e]">{activeCount}</span>
                </div>
              </div>
            </div>
          </Card>
        ) : (
          <Card className="col-span-4 max-[1080px]:col-span-1 p-4 bg-white border-[#e6e5e0] flex items-center justify-center text-[#807d72] text-xs italic">
            No active batch job
          </Card>
        )}
      </div>

      {/* 2. Unified Batch Subjects Panel */}
      {isLoadingDetails ? (
        <Card className="p-8 text-center text-cursor-body">
          <div className="space-y-3 max-w-md mx-auto">
            <Skeleton className="h-4 w-3/4 mx-auto" />
            <Skeleton className="h-4 w-1/2 mx-auto" />
            <Skeleton className="h-20 w-full" />
          </div>
        </Card>
      ) : job ? (
        <Card className="flex-1 overflow-hidden border-cursor-hairline bg-white p-0 shadow-none flex flex-col">
          {/* Header */}
          <div className="border-b border-cursor-hairline bg-white px-5 py-4 flex-none">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-muted">Batch monitor</span>
                <h3 className="m-0 mt-1 text-[18px] font-semibold leading-[1.4] text-cursor-ink">Batch Subjects</h3>
                <span className="text-[13px] text-cursor-body mt-0.5 block">{batchImages.length} subjects tracked from events.jsonl</span>
              </div>
              <div className="flex items-center gap-2 flex-none mt-1">
                <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-white px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-muted">
                  {filteredBatchImages.length}/{batchImages.length} shown
                </span>
                {batchSummary.running + batchSummary.pending > 0 && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-cursor-primary/20 bg-cursor-primary/5 px-2.5 py-0.5 text-[11px] font-semibold text-cursor-primary">
                    <span className="h-1.5 w-1.5 rounded-full bg-cursor-primary animate-pulse" />
                    {batchSummary.running + batchSummary.pending} active
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Cream Interior */}
          <div className="flex min-h-0 flex-1 flex-col bg-cursor-canvas p-4 overflow-hidden">
            {/* Search & Filter Toolbar */}
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-cursor-hairline bg-white p-3 flex-none">
              <label className="relative m-0 block w-[min(24rem,100%)]">
                <input
                  type="search"
                  placeholder="Search subject ID or #..."
                  value={subjectSearchQuery}
                  onChange={(e) => setSubjectSearchQuery(e.target.value)}
                  className="w-full rounded-md border border-cursor-hairline bg-cursor-canvas-soft px-3 py-2 pr-9 text-sm text-cursor-ink placeholder:text-cursor-muted-soft focus:outline-none focus:ring-1 focus:ring-cursor-primary h-10"
                />
                <Search className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-cursor-muted" />
              </label>

              <div className="flex flex-wrap items-center gap-1.5">
                {(['all', 'success', 'running', 'failed', 'pending'] as const).map((st) => {
                  const label = st === 'success' ? 'OK' : st;
                  const count = subjectFilterCounts[st];
                  return (
                    <button
                      key={st}
                      type="button"
                      onClick={() => setSubjectStatusFilter(st)}
                      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors cursor-pointer capitalize border ${
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

            {/* Summary Strip */}
            <div className="mb-4 grid grid-cols-4 gap-3 max-[900px]:grid-cols-2 max-[520px]:grid-cols-1 flex-none">
              <div className="rounded-xl border border-cursor-hairline bg-white p-3">
                <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-muted block">Total</span>
                <span className="text-[18px] font-semibold text-cursor-ink mt-0.5 block">{batchImages.length}</span>
              </div>
              <div className="rounded-xl border border-cursor-hairline bg-white p-3">
                <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-muted block">Active</span>
                <span className="text-[18px] font-semibold text-cursor-primary mt-0.5 block">{batchSummary.running + batchSummary.pending}</span>
              </div>
              <div className="rounded-xl border border-cursor-hairline bg-white p-3">
                <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-muted block">Success</span>
                <span className="text-[18px] font-semibold text-cursor-semantic-success mt-0.5 block">{batchSummary.success}</span>
              </div>
              <div className="rounded-xl border border-cursor-hairline bg-white p-3">
                <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-muted block">Failed</span>
                <span className="text-[18px] font-semibold text-cursor-semantic-error mt-0.5 block">{batchSummary.failed}</span>
              </div>
            </div>

            {/* Subject Grid */}
            <div className="grid grid-cols-3 gap-4 max-[1400px]:grid-cols-2 max-[900px]:grid-cols-1 overflow-y-auto flex-1 min-h-0 p-1">
              {filteredBatchImages.length === 0 ? (
                <div className="col-span-full flex min-h-[14rem] flex-col items-center justify-center rounded-xl border border-dashed border-cursor-hairline bg-white p-8 text-center">
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
                  const steps = deriveImageSteps(safeEvents, img, selectedTools, stageOrder, stageLabels);
                  const totalStages = steps.length;
                  const completedStages = steps.filter((s) => s.status === 'success').length;
                  const runningStep = steps.find((s) => s.status === 'running');
                  const failedSteps = steps.filter((s) => s.status === 'failed').length;
                  const progressPercent = totalStages ? Math.round((completedStages / totalStages) * 100) : 0;
                  const currentStepText = getSubjectCurrentStepLabel(img);
                  const runningToolLabel = runningStep?.tool ? (toolDisplayNames[runningStep.tool] || runningStep.tool) : '';

                  return (
                    <button
                      key={img.input_file}
                      type="button"
                      onClick={() => setActiveModalSubjectFile(img.input_file)}
                      className="group flex min-h-[11rem] cursor-pointer flex-col rounded-xl border border-cursor-hairline bg-white p-4 text-left transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft focus:outline-none focus:ring-2 focus:ring-cursor-primary/30"
                    >
                      {/* Top Row: Index + Subject ID + Status */}
                      <div className="flex items-start gap-2.5 min-w-0 mb-2">
                        <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-cursor-canvas-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-cursor-muted flex-none mt-0.5">
                          #{img.idx}
                        </span>
                        <div className="flex flex-col min-w-0 flex-1">
                          <span className="truncate text-[15px] font-semibold leading-[1.4] text-cursor-ink group-hover:text-cursor-primary transition-colors">
                            {img.subject_id}
                          </span>
                          <span className="truncate text-[12px] text-cursor-muted font-mono mt-0.5" title={img.input_file}>
                            {img.input_file.split('/').pop()}
                          </span>
                        </div>
                        <div className="flex-none mt-0.5">
                          <StatusPill state={img.status}>{img.status.toUpperCase()}</StatusPill>
                        </div>
                      </div>

                      {/* Progress Section */}
                      <div className="mt-auto pt-3 border-t border-cursor-hairline-soft space-y-2.5">
                        <div>
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-cursor-muted">Stage progress</span>
                            <span className="text-[12px] font-medium text-cursor-ink">{completedStages}/{totalStages}</span>
                          </div>
                          <div className="h-1.5 w-full rounded-full bg-cursor-canvas-soft overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all ${subjectProgressClass(img.status)}`}
                              style={{width: `${progressPercent}%`}}
                            />
                          </div>
                        </div>

                        <div>
                          <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-cursor-muted block mb-0.5">Current stage</span>
                          <span className="text-[13px] font-medium text-cursor-ink block">{currentStepText}</span>
                          {runningToolLabel && (
                            <span className="text-[12px] text-cursor-body block mt-0.5 truncate">{runningToolLabel}</span>
                          )}
                        </div>

                        <div className="flex items-center justify-between">
                          {img.duration_sec ? (
                            <span className="text-[12px] text-cursor-muted font-mono">{formatElapsed(img.duration_sec)}</span>
                          ) : <span />}
                          <span className="text-[11px] text-cursor-muted-soft opacity-0 group-hover:opacity-100 transition-opacity">Open details</span>
                        </div>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </Card>
      ) : (
        <Card className="p-10 text-center text-[#5a5852] bg-white border-[#e6e5e0]">
          <Activity className="mx-auto mb-3 h-8 w-8 text-[#807d72]" />
          <h3 className="m-0 text-base font-medium text-[#26251e] mb-1">No Job Selected</h3>
          <p className="m-0 text-xs text-[#807d72] max-w-sm mx-auto mb-4">
            {jobsList.length === 0
              ? 'There are no active or recent pipeline jobs. Run a pipeline from the Configuration tab or refresh jobs.'
              : 'Select a job from the sidebar list to view its execution progress and details.'}
          </p>
          <Button
            variant="default"
            size="sm"
            onClick={refreshJobs}
            disabled={busy.refreshJobs}
            className="bg-[#0077b6] hover:bg-[#005f92] text-white"
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
            {/* Modal Header — Editorial Title Band */}
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

function subjectProgressClass(status: string) {
  if (status === 'success') return 'bg-cursor-semantic-success';
  if (status === 'failed') return 'bg-cursor-semantic-error';
  if (status === 'running') return 'bg-cursor-primary';
  return 'bg-cursor-hairline-strong';
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
