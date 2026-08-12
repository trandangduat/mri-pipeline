import React, {useCallback, useEffect, useRef, useState} from 'react';
import {useParams} from 'react-router';
import {
  Activity,
  Download,
  Eraser,
  Eye,
  EyeOff,
  FileCheck,
  Filter,
  ImageIcon,
  Layers,
  LineChart,
  ListOrdered,
  RefreshCw,
  Search,
  Square,
  Terminal,
  X,
} from 'lucide-react';
import {Card, CardContent, CardHeader, CardTitle} from '@/components/ui/card';
import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Skeleton} from '@/components/ui/skeleton';
import {StatusPill, inputCls} from '../components/ui';
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
    async (jobId: string | null, targetJob?: Record<string, unknown> | null) => {
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

      setIsLoadingDetails(true);
      setJobEvents([]);
      setOutputText('');
      setActiveModalSubjectFile(null);
      setDownloadNotice(null);

      const isRemote = String(targetJob?.target || 'Local') === 'Server';

      let events: PipelineEvent[] = [];
      let logText = '';

      try {
        if (isRemote) {
          const remotePayload = buildRemotePayload(formValues);
          const remoteJobDir = String(targetJob?.remote_job_dir || targetJob?.job_dir || jobId);
          const [eventsResult, logResult] = await Promise.all([
            readRemoteEventsMutation
              .mutateAsync({...remotePayload, remote_job_dir: remoteJobDir, job_id: jobId})
              .catch(() => ({events: []})),
            readRemoteLogMutation
              .mutateAsync({...remotePayload, remote_job_dir: remoteJobDir, job_id: jobId, offset: 0})
              .catch(() => ({text: ''})),
          ]);
          events = Array.isArray(eventsResult?.events) ? (eventsResult.events as PipelineEvent[]) : [];
          logText = logResult?.text || '';
        } else {
          const [eventsResult, logResult] = await Promise.all([
            readEventsMutation.mutateAsync(jobId).catch(() => ({events: []})),
            readLogMutation.mutateAsync({jobId, offset: 0, maxBytes: 65536}).catch(() => ({text: ''})),
          ]);
          events = Array.isArray(eventsResult?.events) ? (eventsResult.events as PipelineEvent[]) : [];
          logText = logResult?.text || '';
        }
      } finally {
        if (seq === reqSeqRef.current) {
          setJobEvents(events);
          setOutputText(logText || '');
          setIsLoadingDetails(false);
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
      await loadJobDetails(currentJob ? nextSelected : '', currentJob as Record<string, unknown>);
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
      void loadJobDetails(selectedJobId);
    }, 2000);
    return () => clearInterval(interval);
  }, [selectedJobId, normState, loadJobDetails]);

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

  // Modal active subject
  const modalSubject = batchImages.find((img) => img.input_file === activeModalSubjectFile) || null;
  const modalImageSteps = modalSubject
    ? deriveImageSteps(safeEvents, modalSubject, selectedTools, stageOrder, stageLabels)
    : [];
  const modalMetricsSeries = modalSubject ? deriveMetricsSeries(safeEvents, modalSubject) : {cpuSeries: [], ramSeries: [], latestContainer: ''};

  const getSubjectCurrentStepLabel = (img: typeof batchImages[0]) => {
    if (img.status === 'success') return 'Completed';
    if (img.status === 'failed') return 'Failed';
    if (img.status === 'pending') return 'Waiting in queue';
    const steps = deriveImageSteps(safeEvents, img, selectedTools, stageOrder, stageLabels);
    const runningStep = steps.find((s) => s.status === 'running');
    return runningStep ? runningStep.label || runningStep.stage : 'Processing...';
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
                <RefreshCw className="h-4 w-4 mr-1.5" /> Refresh Jobs
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
        <Card className="p-8 text-center text-[#5a5852]">
          <div className="space-y-3 max-w-md mx-auto">
            <Skeleton className="h-4 w-3/4 mx-auto" />
            <Skeleton className="h-4 w-1/2 mx-auto" />
            <Skeleton className="h-20 w-full" />
          </div>
        </Card>
      ) : job ? (
        <Card className="p-4 bg-white border-[#e6e5e0] flex-1 flex flex-col overflow-hidden">
          {/* Panel Controls: Header Row 1 (Title + Count), Row 2 (Search + Status Filter) */}
          <div className="flex flex-col gap-3 pb-3.5 border-b border-[#f2f2ee] mb-4">
            {/* Row 1: Title & Count Badge */}
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#f7f7f4] border border-[#e6e5e0] text-[#0077b6]">
                  <ImageIcon className="h-4 w-4" />
                </div>
                <CardTitle className="text-base font-semibold text-[#26251e]">Batch Subjects Workspace</CardTitle>
              </div>
              <Badge variant="outline" className="font-mono text-xs">
                {filteredBatchImages.length} / {batchImages.length} subjects
              </Badge>
            </div>

            {/* Row 2: Search Bar + Status Filter */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
              {/* Search Bar */}
              <label className="relative m-0 block w-full max-w-[18rem]">
                <input
                  type="search"
                  placeholder="Search subject ID or #..."
                  value={subjectSearchQuery}
                  onChange={(e) => setSubjectSearchQuery(e.target.value)}
                  className={`${inputCls} pr-8 text-xs h-8.5`}
                />
                <Search className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#807d72]" />
              </label>

              {/* Status Filter Tabs */}
              <div className="flex flex-wrap items-center gap-1 bg-[#f7f7f4] border border-[#e6e5e0] p-1 rounded-lg text-xs">
                <Filter className="h-3.5 w-3.5 text-[#807d72] ml-1 mr-0.5" />
                {(['all', 'success', 'running', 'failed', 'pending'] as const).map((st) => (
                  <button
                    key={st}
                    type="button"
                    onClick={() => setSubjectStatusFilter(st)}
                    className={`px-3 py-1 rounded-md text-[11px] font-medium transition-colors cursor-pointer capitalize ${
                      subjectStatusFilter === st
                        ? 'bg-white text-[#0077b6] shadow-xs font-semibold'
                        : 'text-[#807d72] hover:text-[#26251e]'
                    }`}
                  >
                    {st === 'success' ? 'OK' : st}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Subjects List (Micro Compact 3 Column Card Grid Layout on Desktop) */}
          <div className="grid grid-cols-3 gap-2 max-[1280px]:grid-cols-2 max-[768px]:grid-cols-1 overflow-y-auto flex-1 min-h-0 p-1">
            {filteredBatchImages.length === 0 ? (
              <div className="col-span-full p-12 text-center text-xs text-[#807d72] italic bg-[#f7f7f4] rounded-lg border border-dashed border-[#e6e5e0]">
                No batch subjects matching the current search or status filter.
              </div>
            ) : (
              filteredBatchImages.map((img) => {
                const currentStepText = getSubjectCurrentStepLabel(img);
                return (
                  <div
                    key={img.input_file}
                    onClick={() => setActiveModalSubjectFile(img.input_file)}
                    className="flex items-center justify-between gap-2 rounded-md border border-[#e6e5e0] bg-[#f7f7f4] px-2.5 py-1.5 cursor-pointer hover:border-[#0077b6] hover:bg-white transition-all group text-xs"
                  >
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <span className="flex h-5 w-5 items-center justify-center rounded bg-white border border-[#e6e5e0] text-[10px] font-bold text-[#0077b6] flex-none">
                        #{img.idx}
                      </span>
                      <div className="flex flex-col min-w-0 flex-1">
                        <span className="truncate font-bold text-xs text-[#26251e] group-hover:text-[#0077b6] transition-colors">
                          {img.subject_id}
                        </span>
                        <span className="truncate text-[10px] text-[#807d72]">
                          {img.input_file.split('/').pop()} · <strong className="font-semibold text-[#26251e]">{currentStepText}</strong>
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-none">
                      {img.duration_sec && (
                        <span className="text-[10px] text-[#807d72]">{img.duration_sec.toFixed(1)}s</span>
                      )}
                      <StatusPill state={img.status}>{img.status.toUpperCase()}</StatusPill>
                    </div>
                  </div>
                );
              })
            )}
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
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4"
          onClick={() => setActiveModalSubjectFile(null)}
        >
          <div
            className="relative bg-white border border-[#e6e5e0] rounded-xl max-w-4xl w-full max-h-[90vh] flex flex-col shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-[#e6e5e0] px-5 py-4 bg-[#f7f7f4]">
              <div className="flex items-center gap-3 min-w-0">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white border border-[#e6e5e0] font-mono text-xs font-bold text-[#0077b6]">
                  #{modalSubject.idx}
                </span>
                <div className="flex flex-col min-w-0">
                  <h3 className="m-0 text-base font-bold font-mono text-[#26251e] truncate">
                    {modalSubject.subject_id}
                  </h3>
                  <span className="text-xs text-[#807d72] truncate">{modalSubject.input_file}</span>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <StatusPill state={modalSubject.status}>{modalSubject.status.toUpperCase()}</StatusPill>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setActiveModalSubjectFile(null)}
                  className="h-8 w-8 p-0 rounded-full text-[#807d72] hover:text-[#26251e] hover:bg-[#e6e5e0]"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Modal Content Body */}
            <div className="flex-1 overflow-auto p-5 space-y-5">
              {/* Vertical Pipeline Stage Flow */}
              <Card className="p-4 bg-white border-[#e6e5e0]">
                <CardHeader className="p-0 pb-3 flex flex-row items-center justify-between border-b border-[#f2f2ee] mb-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <ListOrdered className="h-4 w-4 text-[#0077b6] flex-none" />
                    <CardTitle className="text-sm font-medium">Pipeline Stage Execution Flow</CardTitle>
                  </div>
                  <Badge variant="outline" className="font-mono text-xs">
                    {modalImageSteps.length} stages
                  </Badge>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="relative pl-6 space-y-2.5 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-[#e6e5e0]">
                    {modalImageSteps.map((step) => (
                      <VerticalTimelineStepRow key={step.stage} step={step} />
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* Run Telemetry */}
              <Card className="p-4 bg-white border-[#e6e5e0]">
                <CardHeader className="p-0 pb-2.5 flex flex-row items-center justify-between">
                  <div className="flex items-center gap-2">
                    <LineChart className="h-4 w-4 text-[#0077b6]" />
                    <CardTitle className="text-sm font-medium">Run Telemetry</CardTitle>
                  </div>
                  <span className="text-[11px] font-mono text-[#807d72]">events.jsonl metrics</span>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="grid grid-cols-2 gap-3 max-[1080px]:grid-cols-1">
                    <MetricSparkline label="CPU Usage" points={modalMetricsSeries.cpuSeries} unit="%" />
                    <MetricSparkline label="RAM Usage" points={modalMetricsSeries.ramSeries} unit="MB" />
                  </div>
                  <div className="mt-2 text-[11px] font-mono text-[#807d72] bg-[#f7f7f4] border border-[#e6e5e0] px-3 py-1.5 rounded-md flex items-center justify-between">
                    <span>GPU Usage: Not reported (CPU Mode)</span>
                    <Badge variant="secondary" className="text-[9px]">CPU Mode</Badge>
                  </div>
                </CardContent>
              </Card>

              {/* Operator Console Terminal Log */}
              <Card className="p-4 bg-white border-[#e6e5e0]">
                <CardHeader className="p-0 pb-2.5 flex flex-row items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Terminal className="h-4 w-4 text-[#0077b6]" />
                    <CardTitle className="text-sm font-medium">Operator Console Log</CardTitle>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setShowRawLog(!showRawLog)}
                      className="h-7 px-2 text-xs border-[#e6e5e0]"
                    >
                      {showRawLog ? (
                        <>
                          <EyeOff className="h-3.5 w-3.5 mr-1" /> Sanitized View
                        </>
                      ) : (
                        <>
                          <Eye className="h-3.5 w-3.5 mr-1" /> View Raw Logs
                        </>
                      )}
                    </Button>
                    <label className="relative m-0 block w-full max-w-[12rem]">
                      <input
                        type="search"
                        placeholder="Filter console..."
                        value={jobLogSearch}
                        onChange={(e) => setJobLogSearch(e.target.value)}
                        className={`${inputCls} pr-8 text-xs h-7`}
                      />
                      <Search className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#807d72]" />
                    </label>
                    <Button variant="ghost" size="sm" onClick={clearJobLog} className="h-7 px-2 text-xs">
                      <Eraser className="h-3.5 w-3.5 mr-1" /> Clear
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="p-0">
                  <pre
                    className="mt-1 min-h-48 max-h-[18rem] w-full overflow-auto whitespace-pre-wrap rounded-lg border border-[#e6e5e0] bg-[#f7f7f4] p-3 font-mono text-[12px] leading-[1.45] text-[#26251e]"
                    aria-live="polite"
                  >
                    {filteredLog || 'Log stream is empty.'}
                  </pre>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function VerticalTimelineStepRow({step}: {step: StageStepDetail}) {
  const statusBadge =
    step?.status === 'success' ? (
      <Badge variant="success">OK</Badge>
    ) : step?.status === 'running' ? (
      <Badge variant="running">RUNNING</Badge>
    ) : step?.status === 'failed' ? (
      <Badge variant="destructive">FAIL</Badge>
    ) : step?.status === 'not_scheduled' ? (
      <Badge variant="not_scheduled">Not Scheduled</Badge>
    ) : (
      <Badge variant="secondary">Pending</Badge>
    );

  const statusBg =
    step?.status === 'success'
      ? 'bg-emerald-50/40 border-emerald-200'
      : step?.status === 'running'
        ? 'bg-blue-50/60 border-blue-200'
        : step?.status === 'failed'
          ? 'bg-rose-50/40 border-rose-200'
          : step?.status === 'not_scheduled'
            ? 'bg-[#f7f7f4]/60 border-[#e6e5e0] opacity-50'
            : 'bg-white border-[#e6e5e0]';

  const dotClass =
    step?.status === 'success'
      ? 'bg-emerald-500 ring-2 ring-emerald-100'
      : step?.status === 'running'
        ? 'bg-[#0077b6] animate-pulse ring-4 ring-blue-100'
        : step?.status === 'failed'
          ? 'bg-rose-500 ring-2 ring-rose-100'
          : step?.status === 'not_scheduled'
            ? 'bg-[#cfcdc4]'
            : 'bg-white border-2 border-[#807d72]';

  return (
    <div className="relative flex items-center gap-3">
      {/* Node Dot on vertical connector line */}
      <span className={`absolute -left-[1.375rem] h-3 w-3 rounded-full flex-none transition-all ${dotClass}`} />

      <div className={`flex-1 flex items-center justify-between gap-3 rounded-lg border p-2.5 text-xs transition-colors ${statusBg}`}>
        <div className="flex items-center gap-2.5 min-w-0">
          {statusBadge}
          <div className="flex flex-col min-w-0">
            <strong className="truncate font-medium text-[#26251e]">{step?.label || step?.stage}</strong>
            <span className="truncate text-[10px] font-mono text-[#807d72]">
              {step?.status === 'not_scheduled'
                ? 'Not scheduled for run'
                : step?.tool
                  ? step.tool
                  : 'Default pipeline tool'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-none text-[10px] font-mono text-[#807d72]">
          {step?.elapsed_sec !== undefined && <span>{step.elapsed_sec.toFixed(1)}s</span>}
          {step?.cpu_pct !== undefined && step.cpu_pct > 0 && <span>CPU: {step.cpu_pct}%</span>}
          {step?.ram_bytes !== undefined && step.ram_bytes > 0 && (
            <span>RAM: {Math.round(step.ram_bytes / (1024 * 1024))}MB</span>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricSparkline({label, points, unit = '%'}: {label: string; points: number[]; unit?: string}) {
  const safePoints = (Array.isArray(points) ? points : []).map((v) =>
    typeof v === 'number' && Number.isFinite(v) ? v : 0,
  );
  const maxVal = Math.max(...safePoints, 100);
  const minVal = 0;
  const range = maxVal - minVal || 1;
  const width = 200;
  const height = 32;

  const polylinePoints = safePoints.length
    ? safePoints
        .map((val, idx) => {
          const x = (idx / Math.max(safePoints.length - 1, 1)) * width;
          const y = height - ((val - minVal) / range) * (height - 6) - 3;
          return `${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join(' ')
    : `0,${height} ${width},${height}`;

  const currentVal = safePoints.length ? safePoints[safePoints.length - 1] : 0;
  const peakVal = safePoints.length ? Math.max(...safePoints) : 0;

  return (
    <div className="flex flex-col justify-between gap-1 rounded-lg border border-[#e6e5e0] bg-[#f7f7f4] p-2.5 text-[#5a5852]">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-[#26251e]">{label}</span>
        <span className="font-mono text-[#0077b6] font-semibold text-xs">
          {currentVal}
          {unit} <span className="text-[10px] text-[#807d72] font-normal">(peak: {peakVal}{unit})</span>
        </span>
      </div>
      <div className="relative">
        <svg className="h-7 w-full overflow-visible" viewBox={`0 0 ${width} ${height}`}>
          <polyline className="fill-none stroke-[#0077b6] stroke-[1.5]" points={polylinePoints} />
        </svg>
        <div className="flex justify-between text-[9px] font-mono text-[#807d72] mt-0.5">
          <span>0{unit}</span>
          <span>Peak: {peakVal}{unit}</span>
        </div>
      </div>
    </div>
  );
}
