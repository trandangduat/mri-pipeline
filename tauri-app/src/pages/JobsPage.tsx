import React, {useCallback, useEffect, useRef, useState} from 'react';
import {useParams, useNavigate} from 'react-router';
import {
  ArrowLeft,
  BrainCircuit,
  Check,
  ChevronRight,
  Clock,
  Copy,
  Download,
  Eraser,
  Eye,
  EyeOff,
  FileCheck,
  HardDrive,
  ImageIcon,
  Layers,
  LayoutGrid,
  List,
  Loader2,
  RefreshCw,
  Search,
  Server,
  Square,
  Trash2,
  X,
  Zap,
} from 'lucide-react';
import {Card, CardTitle} from '@/components/ui/card';
import {Badge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Skeleton} from '@/components/ui/skeleton';
import {StatusPill, StatusDotLarge, statusDotClasses} from '../components/ui';
import {normalizeJob, normalizeJobState, sortJobsByStartedAtDesc, jobBasename} from '../jobFormatters';
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
import {DownloadOutputsDialog} from '../components/DownloadOutputsDialog';
import {LazyUploadProgress} from '../components/LazyUploadProgress';
import type {DownloadStep} from '../components/DownloadOutputsDialog';
import {BackendClient, DEFAULT_BACKEND_URL} from '../api/client';

function hasTauriInternals() {
  if (typeof window === 'undefined') return false;
  const internals = (window as unknown as {__TAURI_INTERNALS__?: {invoke?: unknown}}).__TAURI_INTERNALS__;
  return typeof internals?.invoke === 'function';
}

function selectedDialogPath(selected: unknown) {
  if (Array.isArray(selected)) return selected[0] || '';
  return (selected as string) || '';
}

export function BatchPieChart({
  success,
  failed,
  running,
  pending,
  total,
  size = 80,
}: {
  success: number;
  failed: number;
  running: number;
  pending: number;
  total: number;
  size?: number;
}) {
  const radius = 44;
  const center = 50;
  const chartStyle = {width: `${size}px`, height: `${size}px`, minWidth: `${size}px`, minHeight: `${size}px`};

  if (total <= 0) {
    return (
      <div
        className="relative flex items-center justify-center flex-none w-20 h-20 min-w-20 min-h-20"
        style={chartStyle}
      >
        <svg viewBox="0 0 100 100" className="w-20 h-20 min-w-20 min-h-20 block flex-none" style={chartStyle}>
          <circle cx={center} cy={center} r={radius} fill="#e6e5e0" />
        </svg>
      </div>
    );
  }

  const segments = [
    {count: success, color: '#1f8a65', key: 'success'}, // Semantic Success
    {count: failed, color: '#cf2d56', key: 'failed'}, // Semantic Error
    {count: running, color: '#0077b6', key: 'running'}, // Primary
    {count: pending, color: '#cfcdc4', key: 'pending'}, // Muted / Pending
  ].filter((s) => s.count > 0);

  // If only 1 category exists, render a full solid circle
  const singleSeg = segments.length === 1 ? segments[0] : undefined;
  if (singleSeg) {
    return (
      <div
        className="relative flex items-center justify-center flex-none w-20 h-20 min-w-20 min-h-20"
        style={chartStyle}
      >
        <svg viewBox="0 0 100 100" className="w-20 h-20 min-w-20 min-h-20 block flex-none" style={chartStyle}>
          <circle cx={center} cy={center} r={radius} fill={singleSeg.color} stroke="#ffffff" strokeWidth="1.5" />
        </svg>
      </div>
    );
  }

  // Multiple segments: generate SVG pie slice paths
  let currentAngle = -Math.PI / 2; // Start from top (12 o'clock)
  const paths = segments.map((seg) => {
    const sliceAngle = (seg.count / total) * 2 * Math.PI;
    const startAngle = currentAngle;
    const endAngle = currentAngle + sliceAngle;
    currentAngle = endAngle;

    const x1 = center + radius * Math.cos(startAngle);
    const y1 = center + radius * Math.sin(startAngle);
    const x2 = center + radius * Math.cos(endAngle);
    const y2 = center + radius * Math.sin(endAngle);
    const largeArcFlag = sliceAngle > Math.PI ? 1 : 0;

    const d = `M ${center} ${center} L ${x1} ${y1} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${x2} ${y2} Z`;

    return (
      <path
        key={seg.key}
        d={d}
        fill={seg.color}
        stroke="#ffffff"
        strokeWidth="1.5"
        className="transition-all duration-300"
      />
    );
  });

  return (
    <div className="relative flex items-center justify-center flex-none w-20 h-20 min-w-20 min-h-20" style={chartStyle}>
      <svg viewBox="0 0 100 100" className="w-20 h-20 min-w-20 min-h-20 block flex-none" style={chartStyle}>
        {paths}
      </svg>
    </div>
  );
}

function jobStatusLabel(state: unknown): string {
  const normalized = normalizeJobState(state);
  if (normalized === 'completed') return 'Finished';
  if (normalized === 'failed' || normalized === 'stopped') return 'Failed';
  if (normalized === 'running') return 'Running';
  return 'Unknown';
}

function jobStatusBadgeClasses(state: unknown): string {
  const normalized = normalizeJobState(state);
  if (normalized === 'completed')
    return 'text-cursor-semantic-success bg-cursor-semantic-success/10 border-cursor-semantic-success/20';
  if (normalized === 'failed' || normalized === 'stopped')
    return 'text-cursor-semantic-error bg-cursor-semantic-error/10 border-cursor-semantic-error/20';
  if (normalized === 'running') return 'text-cursor-primary bg-cursor-primary/10 border-cursor-primary/20';
  return 'text-cursor-muted bg-cursor-canvas-soft border-cursor-hairline';
}

function JobCard({
  job,
  onClick,
  onDelete,
  deleting,
  lagging = false,
}: {
  job: Record<string, unknown>;
  onClick: () => void;
  onDelete: () => void;
  deleting: boolean;
  lagging?: boolean;
}) {
  const normState = normalizeJobState(job.state);
  const batchSummary = deriveBatchSummary(deriveBatchImages([], job));
  const title = jobBasename(job.display_name || job.job_id);
  const startedAt = Number(job.started_at || job.created_at || 0);
  const startedStr =
    startedAt > 0
      ? new Date(startedAt * 1000).toLocaleString(undefined, {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })
      : 'Not started';

  const req = (job.run_request_summary as Record<string, unknown>) || {};
  const mode = String(req.pipeline_mode || job.pipeline_mode || 'Default');

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
      className="group flex flex-col justify-between gap-2 rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3 text-left transition-all hover:border-cursor-primary hover:bg-cursor-canvas-soft hover:shadow-xs cursor-pointer"
    >
      <div className="flex items-start gap-2.5 min-w-0">
        <div
          className="flex items-center justify-center rounded-md border border-cursor-hairline-soft bg-cursor-canvas-soft p-1"
          title="Batch summary"
        >
          <BatchPieChart {...batchSummary} size={34} />
        </div>
        <strong className="truncate text-sm font-semibold text-cursor-ink group-hover:text-cursor-primary transition-colors flex-1">
          {title}
        </strong>
        <div className="flex flex-wrap justify-end gap-1">
          {lagging && (
            <span className="inline-flex rounded-full border border-cursor-semantic-warn/30 bg-cursor-semantic-warn/10 px-2 py-0.5 text-2xs font-semibold uppercase tracking-[0.05em] text-cursor-semantic-warn">
              Lagging
            </span>
          )}
          <span
            className={`inline-flex rounded-full border px-2 py-0.5 text-2xs font-semibold uppercase tracking-[0.05em] ${jobStatusBadgeClasses(normState)}`}
          >
            {jobStatusLabel(normState)}
          </span>
        </div>
      </div>

      <div className="flex items-center">
        <span className="inline-flex max-w-full truncate rounded border border-cursor-hairline bg-cursor-canvas px-2 py-0.25 text-2xs font-medium text-cursor-body">
          {mode}
        </span>
      </div>

      <div className="flex items-center justify-between pt-1.5 border-t border-cursor-hairline-soft text-xs text-cursor-muted">
        <span className="flex items-center gap-1 font-mono text-2xs">
          <Clock className="h-3 w-3" />
          {startedStr}
        </span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label={`Delete ${title}`}
            title={normState === 'running' ? 'Stop the job before deleting it' : 'Delete job'}
            disabled={normState === 'running' || deleting}
            onClick={(event) => {
              event.stopPropagation();
              onDelete();
            }}
            className="inline-flex h-6 w-6 items-center justify-center rounded text-cursor-muted transition-colors hover:bg-cursor-semantic-error/10 hover:text-cursor-semantic-error disabled:cursor-not-allowed disabled:opacity-40"
          >
            {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
          </button>
          <span className="flex items-center gap-0.5 text-xs font-medium text-cursor-primary opacity-0 group-hover:opacity-100 transition-opacity">
            <ChevronRight className="h-3.5 w-3.5" />
          </span>
        </div>
      </div>
    </div>
  );
}

function JobsListView({
  jobs,
  onSelectJob,
  onRefresh,
  isRefreshing,
  onDeleteJob,
  deletingJobId,
  remoteLagging,
}: {
  jobs: Record<string, unknown>[];
  onSelectJob: (jobId: string) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
  onDeleteJob: (job: Record<string, unknown>) => void;
  deletingJobId: string | null;
  remoteLagging: boolean;
}) {
  const sortedJobs = sortJobsByStartedAtDesc(jobs);
  const localJobs = sortedJobs.filter((job) => String(job.target || 'Local') !== 'Server');
  const serverJobs = sortedJobs.filter((job) => String(job.target || 'Local') === 'Server');

  return (
    <div className="h-full w-full overflow-y-auto p-4 flex flex-col gap-4 text-cursor-ink">
      {/* Local Jobs Section */}
      <section>
        <div className="flex items-center justify-between gap-3 mb-2">
          <div className="flex items-center gap-1.5">
            <HardDrive className="h-4 w-4 text-cursor-primary" />
            <h2 className="text-base font-semibold text-cursor-ink">Local Jobs</h2>
            <span className="ml-0.5 inline-flex items-center rounded-full bg-cursor-surface-strong px-2 py-0.25 text-2xs font-semibold text-cursor-ink">
              {localJobs.length}
            </span>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={isRefreshing}
            className="h-7 px-2 text-xs font-medium border-cursor-hairline bg-cursor-surface-card hover:bg-cursor-canvas-soft"
          >
            {isRefreshing ? (
              <>
                <Loader2 className="h-3 w-3 mr-1 animate-spin" /> Refreshing...
              </>
            ) : (
              <>
                <RefreshCw className="h-3 w-3 mr-1" /> Refresh
              </>
            )}
          </Button>
        </div>

        {localJobs.length === 0 ? (
          <div className="rounded-lg border border-dashed border-cursor-hairline-strong bg-cursor-canvas-soft p-4 text-center text-xs text-cursor-muted">
            No local jobs found. Run a local pipeline to start.
          </div>
        ) : (
          <div className="grid gap-2.5 [grid-template-columns:repeat(auto-fill,minmax(16rem,1fr))]">
            {localJobs.map((j) => (
              <JobCard
                key={String(j.job_id || j.display_name)}
                job={j}
                onClick={() => onSelectJob(String(j.job_id))}
                onDelete={() => onDeleteJob(j)}
                deleting={deletingJobId === String(j.job_id)}
              />
            ))}
          </div>
        )}
      </section>

      {/* Server Jobs Section */}
      <section>
        <div className="flex items-center gap-1.5 mb-2">
          <Server className="h-4 w-4 text-cursor-primary" />
          <h2 className="text-base font-semibold text-cursor-ink">Server Jobs</h2>
          <span className="ml-0.5 inline-flex items-center rounded-full bg-cursor-surface-strong px-2 py-0.25 text-2xs font-semibold text-cursor-ink">
            {serverJobs.length}
          </span>
        </div>

        {serverJobs.length === 0 ? (
          <div className="rounded-lg border border-dashed border-cursor-hairline-strong bg-cursor-canvas-soft p-4 text-center text-xs text-cursor-muted">
            No server jobs found. Connect SSH and start a remote pipeline.
          </div>
        ) : (
          <div className="grid gap-2.5 [grid-template-columns:repeat(auto-fill,minmax(16rem,1fr))]">
            {serverJobs.map((j) => (
              <JobCard
                key={String(j.job_id || j.display_name)}
                job={j}
                onClick={() => onSelectJob(String(j.job_id))}
                onDelete={() => onDeleteJob(j)}
                deleting={deletingJobId === String(j.job_id)}
                lagging={remoteLagging}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

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
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const handleCopy = (key: string, text: string) => {
    if (!text) return;
    navigator.clipboard.writeText(text).catch(() => {});
    setCopiedField(key);
    setTimeout(() => setCopiedField(null), 2000);
  };

  // Subject panel search, filter & modal state
  const [subjectSearchQuery, setSubjectSearchQuery] = useState<string>('');
  const [subjectStatusFilter, setSubjectStatusFilter] = useState<'all' | 'success' | 'running' | 'failed' | 'pending'>(
    'all',
  );
  const [activeModalSubjectFile, setActiveModalSubjectFile] = useState<string | null>(null);

  // Download dialog state
  const [downloadDialogOpen, setDownloadDialogOpen] = useState(false);
  const [downloadLocalDir, setDownloadLocalDir] = useState('');
  const [downloadPhase, setDownloadPhase] = useState<'select' | 'running' | 'success' | 'failed'>('select');
  const [downloadSteps, setDownloadSteps] = useState<DownloadStep[]>([]);
  const [downloadLogs, setDownloadLogs] = useState<string[]>([]);
  const [downloadCopiedFiles, setDownloadCopiedFiles] = useState<number | undefined>(undefined);
  const [downloadTotalFiles, setDownloadTotalFiles] = useState<number | undefined>(undefined);
  const [downloadFinalPath, setDownloadFinalPath] = useState<string | undefined>(undefined);
  const [downloadError, setDownloadError] = useState<string | undefined>(undefined);
  const [downloadRunning, setDownloadRunning] = useState(false);
  const [webBrowseHint, setWebBrowseHint] = useState(false);
  const [remoteLagging, setRemoteLagging] = useState(false);
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [stoppingJob, setStoppingJob] = useState(false);

  const reqSeqRef = useRef<number>(0);
  const hasInitialRefreshed = useRef<boolean>(false);
  const prevSelectedJobIdRef = useRef<string | null | undefined>(undefined);

  const formValues = usePipelineFormStore((s) => s.formValues);
  const remoteResult = useRemoteStore();

  const busy = useUiStore((s) => s.busy);
  const setBusyKey = useUiStore((s) => s.setBusyKey);

  const {data: metadata} = useMetadata();

  const print = useCallback((label: string, payload: unknown) => {
    appendOutput(`${label}\n${JSON.stringify(payload, null, 2)}\n\n`);
  }, [appendOutput]);

  const listLocalJobsMutation = useListLocalJobsMutation();
  const readEventsMutation = useReadLocalEventsMutation();
  const readLogMutation = useReadLocalLogMutation();
  const listRemoteJobsMutation = useListRemoteJobsMutation();
  const readRemoteEventsMutation = useReadRemoteEventsMutation();
  const readRemoteLogMutation = useReadRemoteLogMutation();

  const {jobId: urlJobId} = useParams<{jobId?: string}>();

  const navigate = useNavigate();

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

  const refreshJobs = useCallback(async () => {
    setBusyKey('refreshJobs', true);
    try {
      const localRes = await listLocalJobsMutation.mutateAsync().catch(() => ({jobs: []}));
      let remoteJobs: unknown[] = [];
      if (remoteResult.connected) {
        const remoteStartedAt = Date.now();
        try {
          const remoteRes = await listRemoteJobsMutation.mutateAsync(buildRemotePayload(formValues));
          remoteJobs = Array.isArray(remoteRes.jobs) ? remoteRes.jobs : [];
          setRemoteLagging(remoteRes.ok === false || Date.now() - remoteStartedAt >= 5_000);
        } catch {
          setRemoteLagging(true);
        }
      } else {
        setRemoteLagging(false);
      }
      const localJobs = (Array.isArray(localRes?.jobs) ? localRes.jobs : []).map((j) =>
        normalizeJob(j as Record<string, unknown>, 'Local'),
      );
      const normalizedRemoteJobs = remoteJobs.map((j) => normalizeJob(j as Record<string, unknown>, 'Server'));
      const jobs = sortJobsByStartedAtDesc([...localJobs, ...normalizedRemoteJobs] as Record<string, unknown>[]);
      setLatestJobs(jobs as Record<string, unknown>[]);

      if (urlJobId || selectedJobId) {
        const targetId = urlJobId || selectedJobId;
        const currentJob = jobs.find((j) => (j as {job_id?: string}).job_id === targetId);
        if (currentJob) {
          await loadJobDetails(targetId, currentJob as Record<string, unknown>, {
            resetUi: false,
          });
        }
      }
    } catch (err: unknown) {
      print('Refresh jobs failed', {error: (err as Error).message});
    } finally {
      setBusyKey('refreshJobs', false);
    }
  }, [
    formValues,
    listLocalJobsMutation,
    listRemoteJobsMutation,
    loadJobDetails,
    remoteResult.connected,
    selectedJobId,
    setBusyKey,
    setLatestJobs,
    urlJobId,
    print,
  ]);

  const handleDeleteJob = async (targetJob: Record<string, unknown>) => {
    const jobId = String(targetJob.job_id || '');
    if (!jobId || normalizeJobState(targetJob.state) === 'running') return;
    if (!window.confirm(`Delete job "${jobBasename(targetJob.display_name || jobId)}"?`)) return;

    setDeletingJobId(jobId);
    try {
      const client = new BackendClient(DEFAULT_BACKEND_URL);
      const result =
        String(targetJob.target || 'Local') === 'Server'
          ? await client.deleteRemoteJob({
              ...buildRemotePayload(formValues),
              job_id: jobId,
              remote_job_dir: String(targetJob.remote_job_dir || targetJob.job_dir || ''),
            })
          : await client.deleteLocalJob(jobId);
      if (!result.ok) {
        print('Delete job failed', {error: result.error || 'Unknown error'});
        return;
      }
      if (selectedJobId === jobId) {
        setSelectedJobId(null);
        navigate('/jobs');
      }
      await refreshJobs();
    } catch (err: unknown) {
      print('Delete job failed', {error: (err as Error).message});
    } finally {
      setDeletingJobId(null);
    }
  };

  const handleStopJob = async () => {
    if (!job || normState !== 'running' || isTerminal || stoppingJob) return;
    setStoppingJob(true);
    try {
      const client = new BackendClient(DEFAULT_BACKEND_URL);
      const result = isServerJob
        ? await client.stopRemoteJob({
            ...buildRemotePayload(formValues),
            job_id: String(job.job_id || ''),
            remote_job_dir: String(job.remote_job_dir || job.job_dir || ''),
          })
        : await client.stopLocalJob(String(job.job_id || ''));
      if (!result.ok) {
        print('Stop job failed', {error: result.error || 'Unknown error'});
        return;
      }
      await refreshJobs();
    } catch (err: unknown) {
      print('Stop job failed', {error: (err as Error).message});
    } finally {
      setStoppingJob(false);
    }
  };

  // Sync URL jobId with selectedJobId
  useEffect(() => {
    if (urlJobId) {
      if (urlJobId !== selectedJobId) {
        setSelectedJobId(urlJobId);
      }
    } else {
      if (selectedJobId) {
        setSelectedJobId(null);
      }
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
        Record<string, unknown> | undefined;
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

  // Initial mount auto-refresh if empty
  useEffect(() => {
    if (hasInitialRefreshed.current) return;
    hasInitialRefreshed.current = true;
    const jobs = Array.isArray(latestJobs) ? latestJobs : [];
    if (jobs.length === 0) {
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

  const safeEvents = Array.isArray(jobEvents) ? jobEvents : [];
  const batchImages = deriveBatchImages(safeEvents, job || {});
  const batchSummary = deriveBatchSummary(batchImages);
  const displayMeta = deriveJobDisplayMetadata(job, safeEvents);
  const isTerminal = ['completed', 'failed', 'stopped'].includes(displayMeta.status_reconciled);

  // Refresh job status and selected details every 30 seconds.
  useEffect(() => {
    const interval = setInterval(() => void refreshJobs(), 30_000);
    return () => clearInterval(interval);
  }, [refreshJobs]);

  const reqSummary = (job?.run_request_summary as Record<string, unknown>) || {};
  const selectedTools = React.useMemo(() => {
    const fromJob = (reqSummary.selected_tools as Record<string, string>) || {};
    const mode = String(reqSummary.pipeline_mode || job?.pipeline_mode || '');
    const presets = (metadata?.presets || {}) as Record<string, {tools?: Record<string, string>}>;

    const presetMode = presets[mode]
      ? mode
      : (metadata?.pipeline_modes || []).find((m) => m.id === mode || m.aliases?.includes(mode))?.id || mode;
    const presetTools = presets[presetMode]?.tools || {};

    if (presetMode && presetMode !== 'Custom' && Object.keys(presetTools).length > 0) {
      return {...presetTools, ...fromJob};
    }

    return fromJob;
  }, [
    job?.pipeline_mode,
    metadata?.pipeline_modes,
    metadata?.presets,
    reqSummary.pipeline_mode,
    reqSummary.selected_tools,
  ]);
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

  const filteredLog = filterLogLines(outputText, jobLogSearch, showRawLog);

  const handleDownloadClick = () => {
    if (!job || !isTerminal) return;
    if (isServerJob) {
      const remoteJobDir = String(job?.remote_job_dir || job?.job_dir || '');
      const rawOutputDir = String(job?.effective_output_dir || job?.output_dir || '');
      const remotePath =
        rawOutputDir && rawOutputDir !== 'N/A' ? rawOutputDir : remoteJobDir ? `${remoteJobDir}/outputs` : '';
      setDownloadDialogOpen(true);
      setDownloadLocalDir(formValues.outputDir || '');
      setDownloadPhase('select');
      setDownloadSteps([]);
      setDownloadLogs([]);
      setDownloadCopiedFiles(undefined);
      setDownloadTotalFiles(undefined);
      setDownloadFinalPath(undefined);
      setDownloadError(undefined);
      setDownloadRunning(false);
      setWebBrowseHint(false);
      setDownloadNotice(remotePath ? `Remote output path: ${remotePath}` : null);
    } else {
      const effDir = String(displayMeta.output_dir_str);
      const subDir = String(job?.download_subdir || '');
      const fullPath = subDir && subDir !== 'N/A' ? `${effDir}/${subDir}` : effDir;
      setDownloadNotice(`Local output directory: ${fullPath}`);
      print('Download Outputs', {ok: true, output_path: fullPath, target: 'Local'});
    }
  };

  const handleBrowseDownloadDir = async () => {
    if (!hasTauriInternals()) {
      setWebBrowseHint(true);
      return;
    }
    try {
      const {open} = await import('@tauri-apps/plugin-dialog');
      const selected = await open({directory: true, multiple: false});
      const path = selectedDialogPath(selected);
      if (path) setDownloadLocalDir(path);
    } catch {
      // ignore picker errors
    }
  };

  const handleStartServerDownload = () => {
    const trimmedDir = downloadLocalDir.trim();
    if (!trimmedDir || !job) return;

    const initialSteps: DownloadStep[] = [
      {id: 'connect', label: 'Connecting to server', status: 'pending'},
      {id: 'count', label: 'Counting remote files', status: 'pending'},
      {id: 'copy', label: 'Copying outputs', status: 'pending'},
    ];
    setDownloadSteps(initialSteps);
    setDownloadPhase('running');
    setDownloadLogs([]);
    setDownloadCopiedFiles(undefined);
    setDownloadTotalFiles(undefined);
    setDownloadFinalPath(undefined);
    setDownloadError(undefined);
    setDownloadRunning(true);
    setWebBrowseHint(false);

    const remotePayload = buildRemotePayload(formValues);
    const remoteJobDir = String(job?.remote_job_dir || job?.job_dir || '');
    const rawRemoteOutputDir = String(job?.effective_output_dir || job?.output_dir || '');
    const remoteOutputDir = rawRemoteOutputDir && rawRemoteOutputDir !== 'N/A' ? rawRemoteOutputDir : '';
    const jobId = String(job?.job_id || '');
    const payload = {
      ...remotePayload,
      job_id: jobId,
      remote_job_dir: remoteJobDir,
      remote_output_dir: remoteOutputDir,
      local_target_dir: trimmedDir,
      download_subdir: String(job?.download_subdir || ''),
    };

    const client = new BackendClient(DEFAULT_BACKEND_URL);
    client.startRemoteDownloadStream(
      payload,
      (event, data) => {
        if (event === 'step') {
          const stepId = data.step as string;
          const status = data.status as DownloadStep['status'];
          const detail = (data.detail as string) || '';
          setDownloadSteps((prev) => prev.map((s) => (s.id === stepId ? {...s, status, detail} : s)));
          if (detail && status === 'running') {
            setDownloadLogs((prev) => [...prev, detail]);
          }
          if (data.copied_files != null) setDownloadCopiedFiles(data.copied_files as number);
          if (data.total_files != null) setDownloadTotalFiles(data.total_files as number);
        } else if (event === 'complete') {
          const ok = data.ok as boolean;
          setDownloadRunning(false);
          if (ok) {
            setDownloadPhase('success');
            setDownloadFinalPath(data.local_path as string);
            setDownloadCopiedFiles(data.copied_files as number);
            setDownloadTotalFiles(data.total_files as number);
            setDownloadNotice(`Downloaded to: ${data.local_path}`);
          } else {
            setDownloadPhase('failed');
            setDownloadError((data.error as string) || 'Download failed');
          }
        }
      },
      (error) => {
        setDownloadRunning(false);
        setDownloadPhase('failed');
        setDownloadError(error);
      },
    );
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
  const modalMetricsSeries = modalSubject
    ? deriveMetricsSeries(safeEvents, modalSubject)
    : {cpuSeries: [], ramSeries: [], latestContainer: ''};

  const totalModalStages = modalImageSteps.length;
  const completedModalStages = modalImageSteps.filter((step) => step.status === 'success').length;

  const getSubjectCurrentStepLabel = (img: (typeof batchImages)[0]) => {
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

  if (!selectedJobId && !urlJobId) {
    return (
      <JobsListView
        jobs={jobsList}
        onSelectJob={(id) => {
          setSelectedJobId(id);
          navigate(`/jobs/${encodeURIComponent(id)}`);
        }}
        onRefresh={refreshJobs}
        isRefreshing={busy.refreshJobs}
        onDeleteJob={handleDeleteJob}
        deletingJobId={deletingJobId}
        remoteLagging={remoteLagging}
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col gap-4 overflow-hidden text-cursor-ink p-6">
      {/* 1. Top Grid: Job Detail (Left) + Batch Summary (Right) */}
      <div className="grid flex-none grid-cols-[minmax(0,1fr)_minmax(18rem,24rem)] gap-3">
        {/* Left: Job Detail Card */}
        <Card className="rounded-lg border-cursor-hairline bg-cursor-surface-card shadow-none p-3.5">
          {/* Header: Back Button + Icon + Title + Status Indicators */}
          <div className="flex flex-wrap items-center justify-between gap-2.5 pb-2.5 border-b border-cursor-hairline-soft">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSelectedJobId(null);
                  navigate('/jobs');
                }}
                className="h-7.5 px-2.5 text-xs font-semibold text-cursor-ink border-cursor-hairline bg-cursor-surface-card hover:bg-cursor-canvas-soft flex-none cursor-pointer"
                aria-label="Back to Jobs"
              >
                <ArrowLeft className="h-3.5 w-3.5 mr-1 text-cursor-body" />
                Back to Jobs
              </Button>
              <div className="flex h-7.5 w-7.5 items-center justify-center rounded-md bg-cursor-canvas border border-cursor-hairline text-cursor-primary flex-none">
                <BrainCircuit className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <h2
                  className="m-0 text-base font-semibold tracking-tight text-cursor-ink truncate"
                  title={(job?.display_name as string) || (job?.job_id as string) || ''}
                >
                  {(job?.display_name as string) || (job?.job_id as string) || 'No Job Selected'}
                </h2>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-none">
              <div className="flex items-center gap-1.5 font-medium text-xs text-cursor-ink">
                <StatusDotLarge state={displayMeta.status_reconciled} />
                <span className="capitalize">{displayJobState(displayMeta.status_reconciled)}</span>
              </div>
              {Boolean(job?.target) &&
                job?.target !== 'Local' &&
                !String((job?.display_name as string) || (job?.job_id as string) || '')
                  .toLowerCase()
                  .includes(String(job?.target).toLowerCase()) && (
                  <Badge variant="default">{String(job?.target)}</Badge>
                )}
            </div>
          </div>

          {/* Lazy upload progress (Server target + Local inputs) */}
          {String(job?.target) === 'Server' && (
            <LazyUploadProgress
              jobId={String(job?.job_id || '')}
              remoteJobDir={String(job?.remote_job_dir || job?.job_dir || '')}
            />
          )}

          {/* Perfectly Aligned Unified Metadata Table */}
          {(() => {
            const isCustomMode = String(reqSummary.pipeline_mode || job?.pipeline_mode || '') === 'Custom';
            const neuroflowEnabled =
              reqSummary.neuroflow_enabled !== undefined
                ? Boolean(reqSummary.neuroflow_enabled)
                : reqSummary.neuroflowEnabled !== undefined
                  ? Boolean(reqSummary.neuroflowEnabled)
                  : !isCustomMode;
            const maxConcurrent = Number(
              reqSummary.neuroflow_max_concurrent_tasks ?? reqSummary.neuroflowMaxConcurrentTasks ?? 2,
            );
            const estimationMode = String(
              reqSummary.neuroflow_estimation_mode || reqSummary.neuroflowEstimationMode || 'balanced',
            );
            const warmupEnabled = Boolean(reqSummary.neuroflow_warmup_enabled ?? reqSummary.neuroflowWarmupEnabled);
            const maxRetries = Number(reqSummary.neuroflow_max_retries ?? reqSummary.neuroflowMaxRetries ?? 3);

            const schedulerDisplay =
              neuroflowEnabled && !isCustomMode
                ? 'NeuroFLOW'
                : isCustomMode
                  ? 'Standard Runner (Custom Mode)'
                  : 'Standard Runner';

            const schedulerDetails =
              neuroflowEnabled && !isCustomMode
                ? `${maxConcurrent} tasks · ${estimationMode} · ${warmupEnabled ? 'Warmup: On' : 'Direct'} · ${maxRetries} retries`
                : 'Sequential';

            return (
              <div className="mt-2.5 overflow-hidden rounded-md border border-cursor-hairline bg-cursor-surface-card">
                <table className="w-full text-xs divide-y divide-cursor-hairline-soft table-fixed border-collapse">
                  <tbody className="divide-y divide-cursor-hairline-soft">
                    {/* Row 1: Started & Preset */}
                    <tr className="divide-x divide-cursor-hairline-soft">
                      <td className="w-24 md:w-28 py-1.5 px-2.5 font-medium text-cursor-ink bg-cursor-canvas-soft whitespace-nowrap">
                        Started
                      </td>
                      <td className="py-1.5 px-2.5 text-cursor-body truncate" title={displayMeta.started_at_str}>
                        {displayMeta.started_at_str}
                      </td>
                      <td className="w-24 md:w-28 py-1.5 px-2.5 font-medium text-cursor-ink bg-cursor-canvas-soft whitespace-nowrap">
                        Preset
                      </td>
                      <td
                        className="py-1.5 px-2.5 text-cursor-body truncate"
                        title={String(reqSummary.pipeline_mode || job?.pipeline_mode || 'Custom')}
                      >
                        {String(reqSummary.pipeline_mode || job?.pipeline_mode || 'Custom')}
                      </td>
                    </tr>

                    {/* Row 2: Process PID & Scheduler */}
                    <tr className="divide-x divide-cursor-hairline-soft">
                      <td className="w-24 md:w-28 py-1.5 px-2.5 font-medium text-cursor-ink bg-cursor-canvas-soft whitespace-nowrap">
                        Process PID
                      </td>
                      <td className="py-1.5 px-2.5 text-cursor-body font-mono">{String(job?.pid || 'None')}</td>
                      <td className="w-24 md:w-28 py-1.5 px-2.5 font-medium text-cursor-ink bg-cursor-canvas-soft whitespace-nowrap">
                        Scheduler
                      </td>
                      <td className="py-1.5 px-2.5 text-cursor-body min-w-0">
                        <div className="flex items-center gap-1.5 flex-wrap min-w-0">
                          <span className="font-semibold text-cursor-ink truncate">{schedulerDisplay}</span>
                          {neuroflowEnabled && !isCustomMode && (
                            <span
                              className="inline-flex items-center gap-1 rounded bg-cursor-primary/10 px-1.5 py-0.25 text-2xs font-semibold text-cursor-primary flex-none"
                              title={schedulerDetails}
                            >
                              <Zap className="h-3 w-3" />
                              {maxConcurrent} tasks
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>

                    {/* Row 3: Mode / Device & Threads / RAM */}
                    <tr className="divide-x divide-cursor-hairline-soft">
                      <td className="w-24 md:w-28 py-1.5 px-2.5 font-medium text-cursor-ink bg-cursor-canvas-soft whitespace-nowrap">
                        Mode / Device
                      </td>
                      <td className="py-1.5 px-2.5 text-cursor-body whitespace-nowrap">
                        {String(reqSummary.mode || 'N/A')} / {String(reqSummary.device || 'cpu')}
                      </td>
                      <td className="w-24 md:w-28 py-1.5 px-2.5 font-medium text-cursor-ink bg-cursor-canvas-soft whitespace-nowrap">
                        Threads / RAM
                      </td>
                      <td className="py-1.5 px-2.5 text-cursor-body whitespace-nowrap">
                        {String(reqSummary.threads || 4)} threads · {String(reqSummary.ram_percent || 100)}% RAM
                      </td>
                    </tr>

                    {/* Row 4: Container & Output Path */}
                    <tr className="divide-x divide-cursor-hairline-soft">
                      <td className="w-24 md:w-28 py-1.5 px-2.5 font-medium text-cursor-ink bg-cursor-canvas-soft whitespace-nowrap">
                        Container
                      </td>
                      <td
                        className="py-1.5 px-2.5 text-cursor-body truncate"
                        title={modalMetricsSeries.latestContainer || 'None (Native)'}
                      >
                        {modalMetricsSeries.latestContainer || 'None (Native)'}
                      </td>
                      <td className="w-24 md:w-28 py-1.5 px-2.5 font-medium text-cursor-ink bg-cursor-canvas-soft whitespace-nowrap">
                        Output Path
                      </td>
                      <td className="py-1.5 px-2.5 text-cursor-body min-w-0">
                        <div className="flex items-center justify-between gap-1.5 min-w-0 w-full">
                          <span
                            className="font-mono text-2xs text-cursor-body truncate break-all flex-1"
                            title={displayMeta.output_dir_str}
                          >
                            {displayMeta.output_dir_str}
                          </span>
                          <button
                            type="button"
                            onClick={() => handleCopy('output', displayMeta.output_dir_str)}
                            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-2xs text-cursor-muted hover:text-cursor-ink hover:bg-cursor-canvas flex-none border border-cursor-hairline transition-colors cursor-pointer"
                            title="Copy Output Path"
                          >
                            {copiedField === 'output' ? (
                              <>
                                <Check className="h-3 w-3 text-cursor-semantic-success" />
                                <span className="text-cursor-semantic-success font-medium">Copied</span>
                              </>
                            ) : (
                              <>
                                <Copy className="h-3 w-3" />
                                <span>Copy</span>
                              </>
                            )}
                          </button>
                        </div>
                      </td>
                    </tr>

                    {/* Row 5: Input Path spanning across bottom */}
                    <tr className="divide-x divide-cursor-hairline-soft">
                      <td className="w-24 md:w-28 py-1.5 px-2.5 font-medium text-cursor-ink bg-cursor-canvas-soft whitespace-nowrap">
                        Input Path
                      </td>
                      <td colSpan={3} className="py-1.5 px-2.5 text-cursor-body min-w-0">
                        <div className="flex items-center justify-between gap-2 min-w-0 w-full">
                          <span
                            className="font-mono text-2xs text-cursor-body truncate break-all flex-1"
                            title={displayMeta.input_path_str}
                          >
                            {displayMeta.input_path_str}
                          </span>
                          <button
                            type="button"
                            onClick={() => handleCopy('input', displayMeta.input_path_str)}
                            className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-2xs text-cursor-muted hover:text-cursor-ink hover:bg-cursor-canvas flex-none border border-cursor-hairline transition-colors cursor-pointer"
                            title="Copy Input Path"
                          >
                            {copiedField === 'input' ? (
                              <>
                                <Check className="h-3 w-3 text-cursor-semantic-success" />
                                <span className="text-cursor-semantic-success font-medium">Copied</span>
                              </>
                            ) : (
                              <>
                                <Copy className="h-3 w-3" />
                                <span>Copy</span>
                              </>
                            )}
                          </button>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            );
          })()}
        </Card>

        {/* Right: Batch Summary / Actions Card */}
        {job ? (
          <Card className="rounded-lg border-cursor-hairline bg-cursor-surface-card shadow-none p-3.5 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-2 border-b border-cursor-hairline-soft mb-2.5">
                <div className="flex items-center gap-1.5 min-w-0">
                  <Layers className="h-4 w-4 text-cursor-primary" />
                  <CardTitle className="font-semibold text-base text-cursor-ink">Batch Summary</CardTitle>
                </div>
                <span className="text-2xs font-mono font-semibold text-cursor-ink bg-cursor-surface-strong px-2 py-0.5 rounded-full">
                  {batchSummary.total} {batchSummary.total === 1 ? 'Subject' : 'Subjects'}
                </span>
              </div>

              {/* Solid Pie Chart (Left) + Vertically Aligned Legends (Right) */}
              <div className="flex items-center gap-4 py-1 mb-3">
                <BatchPieChart
                  success={batchSummary.success}
                  failed={batchSummary.failed}
                  running={batchSummary.running}
                  pending={batchSummary.pending}
                  total={batchSummary.total}
                />
                <div className="flex-1 flex flex-col justify-center gap-1.5 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="h-2.5 w-2.5 rounded-full bg-cursor-semantic-success flex-none" />
                      <span className="text-cursor-ink text-xs font-medium">Success</span>
                    </div>
                    <span className="font-semibold text-cursor-ink font-mono">{batchSummary.success}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="h-2.5 w-2.5 rounded-full bg-cursor-semantic-error flex-none" />
                      <span className="text-cursor-ink text-xs font-medium">Failed</span>
                    </div>
                    <span className="font-semibold text-cursor-ink font-mono">{batchSummary.failed}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="h-2.5 w-2.5 rounded-full bg-cursor-primary flex-none" />
                      <span className="text-cursor-ink text-xs font-medium">Running</span>
                    </div>
                    <span className="font-semibold text-cursor-ink font-mono">{batchSummary.running}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="h-2.5 w-2.5 rounded-full bg-cursor-hairline-strong flex-none" />
                      <span className="text-cursor-muted text-xs font-medium">Pending</span>
                    </div>
                    <span className="font-semibold text-cursor-muted font-mono">{batchSummary.pending}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex flex-col gap-1.5">
              {isTerminal && displayMeta.status_reconciled === 'completed' ? (
                <Button
                  variant="default"
                  onClick={handleDownloadClick}
                  disabled={downloadRunning}
                  className="w-full h-8 bg-cursor-primary hover:bg-cursor-primary-active text-white font-medium text-xs shadow-none cursor-pointer"
                >
                  <Download className="h-3.5 w-3.5 mr-1.5" /> Download Outputs
                </Button>
              ) : (
                <Button
                  id="refreshJobsButton"
                  variant="default"
                  onClick={refreshJobs}
                  disabled={busy.refreshJobs}
                  className="w-full h-8 bg-cursor-primary hover:bg-cursor-primary-active text-white font-medium text-xs shadow-none cursor-pointer"
                >
                  {busy.refreshJobs ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> Refreshing...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Refresh Jobs
                    </>
                  )}
                </Button>
              )}

              {(!isTerminal || displayMeta.status_reconciled !== 'completed') && (
                <Button
                  onClick={handleStopJob}
                  disabled={!job || normState !== 'running' || isTerminal || stoppingJob}
                  className="w-full h-8 border-cursor-semantic-error text-cursor-semantic-error bg-cursor-surface-card hover:bg-cursor-semantic-error/5 font-medium text-xs cursor-pointer"
                >
                  {stoppingJob ? (
                    <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                  ) : (
                    <Square className="h-3.5 w-3.5 mr-1.5" />
                  )}{' '}
                  {stoppingJob ? 'Stopping...' : 'Stop Job'}
                </Button>
              )}

              {isTerminal && displayMeta.status_reconciled === 'completed' ? (
                <Button
                  id="refreshJobsButton"
                  variant="outline"
                  onClick={refreshJobs}
                  disabled={busy.refreshJobs}
                  className="w-full h-8 border-cursor-hairline text-cursor-ink bg-cursor-surface-card hover:bg-cursor-canvas-soft font-medium text-xs cursor-pointer"
                >
                  {busy.refreshJobs ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> Refreshing...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Refresh Jobs
                    </>
                  )}
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  onClick={handleDownloadClick}
                  disabled={!job || !isTerminal || downloadRunning}
                  className="w-full h-8 border-cursor-hairline text-cursor-body bg-cursor-surface-card hover:bg-cursor-canvas-soft font-medium text-xs cursor-pointer"
                >
                  <Download className="h-3.5 w-3.5 mr-1.5" /> Download Outputs
                </Button>
              )}

              {downloadNotice && (
                <div className="flex items-center gap-1.5 rounded-md border border-cursor-hairline bg-cursor-canvas px-2.5 py-1.5 text-xs text-cursor-body mt-0.5">
                  <FileCheck className="h-3.5 w-3.5 text-cursor-semantic-success flex-none" />
                  <span className="truncate">{downloadNotice}</span>
                </div>
              )}
            </div>
          </Card>
        ) : (
          <Card className="rounded-lg border-cursor-hairline bg-cursor-surface-card shadow-none p-3.5 flex items-center justify-center text-cursor-muted text-xs italic">
            No active batch job
          </Card>
        )}
      </div>

      {/* 2. Batch Subjects Card */}
      {job ? (
        <Card className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border-cursor-hairline bg-cursor-surface-card p-0 shadow-none">
          {/* Header */}
          <div className="border-b border-cursor-hairline bg-cursor-surface-card px-3.5 py-2.5 flex-none">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 min-w-0">
                <Layers className="h-4 w-4 text-cursor-primary flex-none" />
                <CardTitle className="font-semibold text-base text-cursor-ink">Batch Subjects</CardTitle>
                <span className="ml-1 inline-flex items-center rounded-full bg-cursor-surface-strong px-2 py-0.25 text-2xs font-semibold text-cursor-ink">
                  {filteredBatchImages.length}
                </span>
              </div>
              <div className="flex items-center gap-1 flex-none">
                <button
                  type="button"
                  onClick={() => setSubjectViewMode('grid')}
                  className={`inline-flex items-center justify-center h-7 w-7 rounded-md border transition-colors cursor-pointer ${
                    subjectViewMode === 'grid'
                      ? 'border-cursor-hairline-strong bg-cursor-surface-card text-cursor-ink'
                      : 'border-transparent text-cursor-muted hover:text-cursor-ink'
                  }`}
                  aria-label="Grid view"
                >
                  <LayoutGrid className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => setSubjectViewMode('list')}
                  className={`inline-flex items-center justify-center h-7 w-7 rounded-md border transition-colors cursor-pointer ${
                    subjectViewMode === 'list'
                      ? 'border-cursor-hairline-strong bg-cursor-surface-card text-cursor-ink'
                      : 'border-transparent text-cursor-muted hover:text-cursor-ink'
                  }`}
                  aria-label="List view"
                >
                  <List className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </div>

          {/* Interior: Search + Filter + Grid */}
          <div className="flex min-h-0 flex-1 flex-col bg-cursor-surface-card p-3 overflow-hidden">
            {/* Search & Filter Toolbar */}
            <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2 flex-none">
              <label className="relative m-0 block w-[min(18rem,100%)]">
                <input
                  type="search"
                  placeholder="Search subject ID or #..."
                  value={subjectSearchQuery}
                  onChange={(e) => setSubjectSearchQuery(e.target.value)}
                  className="w-full rounded-md border border-cursor-hairline bg-cursor-canvas-soft px-2.5 py-1 pr-8 text-xs text-cursor-ink placeholder:text-cursor-muted-soft focus:outline-none focus:ring-1 focus:ring-cursor-primary h-8"
                />
                <Search className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-cursor-muted" />
              </label>
              <div className="flex flex-wrap items-center gap-1">
                {(['all', 'success', 'running', 'failed', 'pending'] as const).map((st) => {
                  const label = st === 'success' ? 'OK' : st;
                  const count =
                    st === 'all'
                      ? batchImages.length
                      : st === 'success'
                        ? batchSummary.success
                        : st === 'running'
                          ? batchSummary.running
                          : st === 'failed'
                            ? batchSummary.failed
                            : batchSummary.pending;

                  return (
                    <button
                      key={st}
                      type="button"
                      onClick={() => setSubjectStatusFilter(st)}
                      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors cursor-pointer capitalize border ${
                        subjectStatusFilter === st
                          ? 'border-cursor-hairline-strong bg-cursor-surface-card text-cursor-ink font-semibold'
                          : 'border-transparent text-cursor-body hover:text-cursor-ink'
                      }`}
                    >
                      <span>{label}</span>
                      <span
                        className={`text-2xs font-mono px-1 rounded-full ${
                          subjectStatusFilter === st ? 'bg-cursor-surface-strong text-cursor-ink' : 'text-cursor-muted'
                        }`}
                      >
                        {count}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Subject Grid or List */}
            {subjectViewMode === 'grid' ? (
              <div className="grid grid-cols-[repeat(auto-fill,minmax(16rem,1fr))] gap-2.5 items-start overflow-y-auto flex-1 min-h-0 p-1">
                {(() => {
                  if (filteredBatchImages.length === 0) {
                    if (isLoadingDetails && batchImages.length === 0) {
                      return (
                        <>
                          {[0, 1, 2, 3, 4, 5].map((i) => (
                            <div
                              key={i}
                              className="rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3 min-h-[86px]"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <div className="flex items-center gap-1.5">
                                  <Skeleton className="h-5 w-5 rounded flex-none" />
                                  <Skeleton className="h-2.5 w-10" />
                                </div>
                                <Skeleton className="h-4 w-14 rounded-full" />
                              </div>
                              <div className="my-2">
                                <Skeleton className="h-3 w-3/4" />
                              </div>
                              <div className="pt-1.5 border-t border-cursor-hairline-soft flex items-center justify-between">
                                <Skeleton className="h-2 w-20" />
                                <Skeleton className="h-2 w-10" />
                              </div>
                            </div>
                          ))}
                        </>
                      );
                    }
                    return (
                      <div className="col-span-full flex min-h-[10rem] flex-col items-center justify-center rounded-lg border border-dashed border-cursor-hairline bg-cursor-surface-card p-5 text-center">
                        <ImageIcon className="h-6 w-6 text-cursor-muted-soft mb-2" />
                        <h4 className="m-0 text-sm font-semibold text-cursor-ink mb-0.5">
                          {batchImages.length === 0 ? 'No subject events yet' : 'No subjects match these filters'}
                        </h4>
                        <p className="m-0 text-xs text-cursor-body">
                          {batchImages.length === 0
                            ? 'Subjects will appear as the pipeline processes images.'
                            : 'Try a different status filter or search term.'}
                        </p>
                      </div>
                    );
                  }
                  return filteredBatchImages.map((img) => {
                    const currentStepText = getSubjectCurrentStepLabel(img);
                    return (
                      <button
                        key={img.input_file}
                        type="button"
                        onClick={() => setActiveModalSubjectFile(img.input_file)}
                        className="group flex cursor-pointer flex-col justify-between rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3 text-left transition-all hover:border-cursor-primary hover:bg-cursor-canvas-soft hover:shadow-xs focus:outline-none focus:ring-1 focus:ring-cursor-primary/30 min-h-[86px]"
                      >
                        {/* Card Header: Index & Status Badge */}
                        <div className="flex items-center justify-between gap-2 min-w-0">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <div
                              className={`flex h-5 w-5 items-center justify-center rounded border flex-none ${subjectAccentClasses(img.status)}`}
                            >
                              <BrainCircuit className="h-3 w-3" />
                            </div>
                            <span className="font-mono text-2xs font-semibold uppercase tracking-[0.06em] text-cursor-muted">
                              #{String(img.idx).padStart(3, '0')}
                            </span>
                          </div>
                          <span
                            className={`font-semibold text-2xs uppercase tracking-[0.06em] px-2 py-0.5 rounded-full flex-none ${
                              img.status === 'success'
                                ? 'text-cursor-semantic-success bg-cursor-semantic-success/10 border border-cursor-semantic-success/20'
                                : img.status === 'failed'
                                  ? 'text-cursor-semantic-error bg-cursor-semantic-error/10 border border-cursor-semantic-error/20'
                                  : img.status === 'running'
                                    ? 'text-cursor-primary bg-cursor-primary/10 border border-cursor-primary/20'
                                    : 'text-cursor-muted bg-cursor-canvas-soft border border-cursor-hairline'
                            }`}
                          >
                            {img.status.toUpperCase()}
                          </span>
                        </div>

                        {/* Card Body: Subject ID with full width & 2 lines */}
                        <div className="my-1.5 min-w-0">
                          <h4
                            className="text-xs font-semibold leading-snug text-cursor-ink group-hover:text-cursor-primary transition-colors line-clamp-2 break-all"
                            title={img.subject_id}
                          >
                            {img.subject_id}
                          </h4>
                        </div>

                        {/* Card Footer */}
                        <div className="flex items-center justify-between gap-1.5 pt-1.5 border-t border-cursor-hairline-soft text-2xs text-cursor-muted">
                          <span className="truncate max-w-[70%]" title={currentStepText}>
                            {currentStepText}
                          </span>
                          <span className="font-mono text-3xs text-cursor-body flex-none flex items-center gap-0.5 group-hover:text-cursor-primary transition-colors">
                            Details <ChevronRight className="h-3 w-3" />
                          </span>
                        </div>
                      </button>
                    );
                  });
                })()}
              </div>
            ) : (
              <div className="flex flex-col gap-1.5 overflow-y-auto flex-1 min-h-0 p-0.5">
                {(() => {
                  if (filteredBatchImages.length === 0) {
                    if (isLoadingDetails && batchImages.length === 0) {
                      return (
                        <>
                          {[0, 1, 2, 3, 4, 5].map((i) => (
                            <div
                              key={i}
                              className="flex items-center gap-3 rounded-md border border-cursor-hairline bg-cursor-surface-card px-3 py-2"
                            >
                              <Skeleton className="h-7 w-7 rounded-md flex-none" />
                              <div className="flex-1 space-y-1">
                                <Skeleton className="h-2.5 w-14" />
                                <Skeleton className="h-3.5 w-2/3" />
                              </div>
                              <Skeleton className="h-3.5 w-16 flex-none" />
                            </div>
                          ))}
                        </>
                      );
                    }
                    return (
                      <div className="flex min-h-[10rem] flex-col items-center justify-center rounded-lg border border-dashed border-cursor-hairline bg-cursor-surface-card p-5 text-center">
                        <ImageIcon className="h-6 w-6 text-cursor-muted-soft mb-2" />
                        <h4 className="m-0 text-sm font-semibold text-cursor-ink mb-0.5">
                          {batchImages.length === 0 ? 'No subject events yet' : 'No subjects match these filters'}
                        </h4>
                        <p className="m-0 text-xs text-cursor-body">
                          {batchImages.length === 0
                            ? 'Subjects will appear as the pipeline processes images.'
                            : 'Try a different status filter or search term.'}
                        </p>
                      </div>
                    );
                  }
                  return filteredBatchImages.map((img) => {
                    const currentStepText = getSubjectCurrentStepLabel(img);
                    return (
                      <button
                        key={img.input_file}
                        type="button"
                        onClick={() => setActiveModalSubjectFile(img.input_file)}
                        className="group flex items-center gap-3 cursor-pointer rounded-md border border-cursor-hairline bg-cursor-surface-card px-3 py-2 text-left transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft focus:outline-none focus:ring-1 focus:ring-cursor-primary/30"
                      >
                        <div
                          className={`flex h-7 w-7 items-center justify-center rounded-md border flex-none ${subjectAccentClasses(img.status)}`}
                        >
                          <BrainCircuit className="h-3 w-3" />
                        </div>
                        <div className="flex flex-col min-w-0 flex-1">
                          <span className="text-2xs text-cursor-muted">#{String(img.idx).padStart(3, '0')}</span>
                          <span className="truncate text-sm font-semibold text-cursor-ink group-hover:text-cursor-primary transition-colors">
                            {img.subject_id}
                          </span>
                        </div>
                        <div className="flex items-center gap-4 flex-none">
                          <div className="flex flex-col items-end">
                            <span className="text-2xs uppercase tracking-[0.06em] text-cursor-muted">Stage</span>
                            <span className="text-xs text-cursor-ink">{currentStepText}</span>
                          </div>
                          <span
                            className={`text-xs font-semibold uppercase tracking-[0.06em] min-w-[4rem] text-right ${
                              img.status === 'success'
                                ? 'text-cursor-semantic-success'
                                : img.status === 'failed'
                                  ? 'text-cursor-semantic-error'
                                  : img.status === 'running'
                                    ? 'text-cursor-primary'
                                    : 'text-cursor-muted'
                            }`}
                          >
                            {img.status.toUpperCase()}
                          </span>
                        </div>
                      </button>
                    );
                  });
                })()}
              </div>
            )}
          </div>
        </Card>
      ) : (
        <Card className="p-6 text-center text-cursor-body bg-cursor-surface-card border-cursor-hairline rounded-lg shadow-none">
          <BrainCircuit className="mx-auto mb-2 h-6 w-6 text-cursor-muted" />
          <h3 className="m-0 text-sm font-semibold text-cursor-ink mb-1">No Job Selected</h3>
          <p className="m-0 text-xs text-cursor-muted max-w-sm mx-auto mb-3">
            {jobsList.length === 0
              ? 'There are no active or recent pipeline jobs. Run a pipeline from the Configuration tab or refresh jobs.'
              : 'Select a job from the jobs list above to view its execution progress and details.'}
          </p>
          <Button
            variant="default"
            onClick={refreshJobs}
            disabled={busy.refreshJobs}
            className="bg-cursor-primary hover:bg-cursor-primary-active text-white h-8 text-xs"
          >
            <RefreshCw className="h-3 w-3 mr-1" /> Refresh Jobs List
          </Button>
        </Card>
      )}

      {/* 3. Subject Detail Modal Overlay */}
      {modalSubject && (
        <div
          className="fixed inset-0 z-50 bg-cursor-ink/35 backdrop-blur-[2px] flex items-center justify-center p-3"
          onClick={() => setActiveModalSubjectFile(null)}
        >
          <div
            className="relative bg-cursor-canvas border border-cursor-hairline rounded-xl w-[min(1360px,calc(100vw-1.5rem))] max-h-[92vh] flex flex-col shadow-none overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-cursor-hairline px-4 py-3 bg-cursor-canvas flex-none">
              <div className="flex items-center gap-3 min-w-0">
                <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-cursor-surface-card px-2 py-0.25 text-2xs font-semibold uppercase tracking-[0.08em] text-cursor-muted">
                  #{modalSubject.idx}
                </span>
                <div className="flex flex-col min-w-0 gap-0.5">
                  <h3 className="m-0 text-base font-semibold leading-tight tracking-tight text-cursor-ink truncate">
                    {modalSubject.subject_id}
                  </h3>
                  <span
                    className="inline-block max-w-md truncate rounded bg-cursor-surface-card border border-cursor-hairline-soft px-1.5 py-0.25 font-mono text-2xs text-cursor-body"
                    title={modalSubject.input_file}
                  >
                    {modalSubject.input_file}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-cursor-surface-card px-2 py-0.25 text-2xs font-semibold uppercase tracking-[0.08em] text-cursor-muted">
                  {completedModalStages}/{totalModalStages} stages
                </span>
                <StatusPill state={modalSubject.status}>{modalSubject.status.toUpperCase()}</StatusPill>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setActiveModalSubjectFile(null)}
                  className="h-7 w-7 p-0 rounded-full text-cursor-muted hover:text-cursor-ink hover:bg-cursor-canvas-soft"
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>

            {/* Modal Body: Two-Column Grid */}
            <div className="grid flex-1 min-h-0 gap-3 overflow-hidden p-3.5 bg-cursor-canvas grid-cols-[minmax(0,1.65fr)_minmax(380px,0.85fr)]">
              {/* Left Column: Pipeline Stages */}
              <div className="bg-cursor-surface-card border border-cursor-hairline rounded-lg p-3.5 shadow-none min-h-0 flex flex-col overflow-hidden">
                <div className="p-0 pb-2 flex flex-row items-start justify-between border-b border-cursor-hairline-soft mb-2.5 flex-none">
                  <div className="flex flex-col min-w-0">
                    <h3 className="m-0 text-base font-semibold leading-[1.3] text-cursor-ink">Stage Timeline</h3>
                  </div>
                  <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-cursor-surface-card px-2 py-0.25 text-2xs font-semibold uppercase tracking-[0.08em] text-cursor-muted flex-none mt-0.5">
                    {completedModalStages}/{totalModalStages} complete
                  </span>
                </div>
                <div className="p-0 flex-1 overflow-auto min-h-0">
                  <div className="space-y-1.5">
                    {modalImageSteps.map((step, idx) => (
                      <VerticalTimelineStepRow
                        key={step.stage}
                        step={step}
                        isLast={idx === modalImageSteps.length - 1}
                        toolDisplayNames={toolDisplayNames}
                      />
                    ))}
                  </div>
                </div>
              </div>

              {/* Right Column: Stacked Cards */}
              <div className="flex min-h-0 flex-col gap-3 overflow-hidden">
                {/* Run Telemetry */}
                <div className="bg-cursor-surface-card border border-cursor-hairline rounded-lg p-3.5 shadow-none flex-none">
                  <div className="p-0 pb-2 flex flex-row items-center justify-between">
                    <h3 className="m-0 text-sm font-semibold leading-[1.3] text-cursor-ink">Run Telemetry</h3>
                    <span className="text-xs text-cursor-muted">events.jsonl metrics</span>
                  </div>
                  <div className="p-0">
                    <div className="grid grid-cols-1 gap-2">
                      <MetricSparkline label="CPU Usage" points={modalMetricsSeries.cpuSeries} unit="%" />
                      <MetricSparkline label="RAM Usage" points={modalMetricsSeries.ramSeries} unit="MB" />
                    </div>
                    <div className="mt-2 text-xs text-cursor-muted rounded-md border border-cursor-hairline-soft bg-cursor-canvas-soft px-2.5 py-1.5 flex items-center justify-between">
                      <span>GPU Usage: Not reported (CPU Mode)</span>
                      <span className="inline-flex items-center rounded-full border border-cursor-hairline bg-cursor-surface-card px-1.5 py-0.25 text-2xs font-semibold uppercase tracking-[0.08em] text-cursor-muted">
                        CPU Mode
                      </span>
                    </div>
                  </div>
                </div>

                {/* Operator Console Log */}
                <div className="bg-cursor-surface-card border border-cursor-hairline rounded-lg p-3.5 shadow-none flex-1 min-h-0 flex flex-col">
                  <div className="p-0 pb-2 flex-none">
                    <div className="flex items-center justify-between mb-1.5">
                      <h3 className="m-0 text-sm font-semibold leading-[1.3] text-cursor-ink">Operator Console Log</h3>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setShowRawLog(!showRawLog)}
                        className="h-7 px-2 text-xs border-cursor-hairline text-cursor-body"
                      >
                        {showRawLog ? (
                          <>
                            <EyeOff className="h-3 w-3 mr-1" /> Sanitized
                          </>
                        ) : (
                          <>
                            <Eye className="h-3 w-3 mr-1" /> Raw
                          </>
                        )}
                      </Button>
                      <label className="relative m-0 block w-full max-w-[9rem]">
                        <input
                          type="search"
                          placeholder="Filter..."
                          value={jobLogSearch}
                          onChange={(e) => setJobLogSearch(e.target.value)}
                          className="w-full rounded-md border border-cursor-hairline bg-cursor-surface-card px-2.5 py-1 pr-7 text-xs text-cursor-ink placeholder:text-cursor-muted-soft focus:outline-none focus:ring-1 focus:ring-cursor-primary h-7"
                        />
                        <Search className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-cursor-muted" />
                      </label>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={clearJobLog}
                        className="h-7 px-2 text-xs text-cursor-body"
                      >
                        <Eraser className="h-3 w-3 mr-1" /> Clear
                      </Button>
                    </div>
                  </div>
                  <div className="p-0 flex-1 min-h-0 overflow-hidden">
                    <pre
                      className="h-full min-h-[14rem] w-full overflow-auto whitespace-pre-wrap break-words rounded-md border border-cursor-hairline-soft bg-cursor-canvas-soft p-2.5 font-mono text-xs leading-relaxed text-cursor-ink"
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

      {/* 4. Download Outputs Dialog */}
      <DownloadOutputsDialog
        open={downloadDialogOpen}
        jobId={String(job?.job_id || '')}
        remotePath={(() => {
          const rawOutputDir = String(job?.server_output_dir || job?.remote_output_dir || job?.effective_output_dir || job?.output_dir || '');
          if (rawOutputDir && rawOutputDir !== 'N/A') return rawOutputDir;
          const remoteJobDir = String(job?.remote_job_dir || job?.job_dir || '');
          return remoteJobDir ? `${remoteJobDir}/outputs` : '';
        })()}
        localDir={downloadLocalDir}
        onLocalDirChange={setDownloadLocalDir}
        phase={downloadPhase}
        steps={downloadSteps}
        logs={downloadLogs}
        copiedFiles={downloadCopiedFiles}
        totalFiles={downloadTotalFiles}
        finalPath={downloadFinalPath}
        errorMessage={downloadError}
        onBrowse={handleBrowseDownloadDir}
        onStart={handleStartServerDownload}
        onClose={() => {
          if (!downloadRunning) setDownloadDialogOpen(false);
        }}
        canClose={!downloadRunning}
        webBrowseHint={webBrowseHint}
      />
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
  const isSkipped = status === 'not_scheduled' || status === 'skipped';
  const cls =
    status === 'success'
      ? 'border-cursor-semantic-success/20 bg-cursor-semantic-success/5 text-cursor-semantic-success'
      : status === 'running'
        ? 'border-cursor-primary/20 bg-cursor-primary/5 text-cursor-primary'
        : status === 'failed'
          ? 'border-cursor-semantic-error/20 bg-cursor-semantic-error/5 text-cursor-semantic-error'
          : isSkipped
            ? 'border-cursor-hairline-soft bg-cursor-canvas-soft text-cursor-muted-soft'
            : 'border-cursor-hairline bg-cursor-canvas-soft text-cursor-muted';
  const label =
    status === 'success'
      ? 'OK'
      : status === 'running'
        ? 'RUNNING'
        : status === 'failed'
          ? 'FAIL'
          : isSkipped
            ? 'SKIPPED'
            : 'PENDING';
  return (
    <span
      className={`inline-flex rounded-full border px-2 py-0.5 text-2xs font-semibold uppercase tracking-[0.08em] ${cls}`}
    >
      {label}
    </span>
  );
}

function subjectAccentClasses(status: string) {
  if (status === 'success')
    return 'text-cursor-semantic-success border-cursor-semantic-success/25 bg-cursor-semantic-success/5';
  if (status === 'failed')
    return 'text-cursor-semantic-error border-cursor-semantic-error/25 bg-cursor-semantic-error/5';
  if (status === 'running') return 'text-cursor-primary border-cursor-primary/25 bg-cursor-primary/5';
  return 'text-cursor-muted border-cursor-hairline bg-cursor-canvas-soft';
}

function StageMetric({label, value}: {label: string; value: string}) {
  return (
    <div className="flex items-center gap-1">
      <span className="text-cursor-muted">{label}:</span>
      <span className="font-semibold text-cursor-ink">{value}</span>
    </div>
  );
}

function VerticalTimelineStepRow({
  step,
  isLast,
  toolDisplayNames,
}: {
  step: StageStepDetail;
  isLast: boolean;
  toolDisplayNames: Record<string, string>;
}) {
  const isSkipped = step?.status === 'not_scheduled' || step?.status === 'skipped';

  const rowClass =
    step?.status === 'running'
      ? 'border-cursor-primary/40 bg-cursor-canvas-soft'
      : step?.status === 'failed'
        ? 'border-cursor-semantic-error/20 bg-cursor-canvas-soft'
        : isSkipped
          ? 'border-cursor-hairline-soft bg-cursor-canvas-soft/50 opacity-60'
          : 'border-cursor-hairline bg-cursor-surface-card';

  const dotClass =
    step?.status === 'success'
      ? 'bg-cursor-semantic-success ring-2 ring-cursor-semantic-success/15'
      : step?.status === 'running'
        ? 'bg-cursor-primary animate-pulse ring-4 ring-cursor-primary/15'
        : step?.status === 'failed'
          ? 'bg-cursor-semantic-error ring-2 ring-cursor-semantic-error/15'
          : isSkipped
            ? 'bg-cursor-hairline-strong'
            : 'bg-cursor-surface-card border-2 border-cursor-muted-soft';

  const displayTool = step?.tool ? toolDisplayNames[step.tool] || step.tool : '';
  const toolLabel = isSkipped ? 'Not available' : displayTool || 'Not available';

  return (
    <div className="relative grid grid-cols-[1.25rem_minmax(0,1fr)] gap-2.5">
      <div className="relative flex justify-center pt-3">
        {!isLast && <span className="absolute top-6 bottom-[-0.75rem] w-px bg-cursor-hairline" />}
        <span className={`h-2.5 w-2.5 rounded-full flex-none transition-all ${dotClass}`} />
      </div>
      <div className={`rounded-md border p-2.5 transition-colors ${rowClass}`}>
        <div className="flex min-w-0 items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              <h4
                className={`m-0 text-sm font-semibold leading-[1.3] ${isSkipped ? 'text-cursor-muted' : 'text-cursor-ink'}`}
              >
                {step?.label || step?.stage}
              </h4>
              <StageStatusPill status={step?.status || 'pending'} />
            </div>
            <p
              className={`m-0 mt-0.5 text-xs leading-[1.3] ${isSkipped ? 'text-cursor-muted-soft' : 'text-cursor-body'}`}
            >
              {toolLabel}
            </p>
          </div>
          {!isSkipped && step?.status !== 'not_scheduled' && (
            <div className="flex flex-wrap justify-end overflow-hidden rounded border border-cursor-hairline-soft bg-cursor-canvas-soft px-1.5 py-0.5 text-2xs">
              <StageMetric label="Elapsed" value={formatElapsed(step?.elapsed_sec)} />
              <span className="h-3 w-px bg-cursor-hairline mx-1" />
              <StageMetric label="CPU" value={formatMetricValue(step?.cpu_pct, '%', 1)} />
              <span className="h-3 w-px bg-cursor-hairline mx-1" />
              <StageMetric label="RAM" value={formatMemory(step?.ram_bytes)} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricSparkline({label, points, unit = '%'}: {label: string; points: number[]; unit?: string}) {
  const safePoints = (Array.isArray(points) ? points : []).filter((v) => typeof v === 'number' && Number.isFinite(v));

  const formatValue = (v: number) => {
    if (unit === 'MB' && v >= 1024) return `${(v / 1024).toFixed(1)} GB`;
    return `${v.toFixed(1)}${unit}`;
  };

  const width = 320;
  const height = 80;

  if (safePoints.length === 0) {
    return (
      <div className="flex flex-col justify-between gap-1 rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft p-3">
        <div className="flex items-center justify-between text-xs">
          <span className="font-medium text-cursor-ink">{label}</span>
          <span className="text-xs text-cursor-muted">No samples yet</span>
        </div>
        <div className="flex items-center justify-center h-16 text-xs text-cursor-muted italic">
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
      const y = height - 6 - ((val - yMin) / range) * (height - 12);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  const firstX = 0;
  const lastX = safePoints.length > 1 ? width : 0;
  const baselineY = height - 6;
  const areaPoints = `${firstX},${baselineY} ${pointsStr} ${lastX},${baselineY}`;

  const lastPoint = safePoints[safePoints.length - 1] ?? 0;
  const lastXPos = safePoints.length > 1 ? width : 0;
  const lastYPos = height - 6 - ((lastPoint - yMin) / range) * (height - 12);

  const currentVal = safePoints[safePoints.length - 1] ?? 0;
  const peakVal = Math.max(...safePoints);

  const gridLines = [0, 0.5, 1].map((pct) => {
    const y = height - 6 - pct * (height - 12);
    const val = yMin + pct * range;
    return {y, val};
  });

  return (
    <div className="flex flex-col justify-between gap-1 rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft p-3">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-cursor-ink">{label}</span>
        <span className="font-mono text-cursor-primary font-semibold text-xs">
          {formatValue(currentVal)}{' '}
          <span className="text-2xs text-cursor-muted font-normal">(peak: {formatValue(peakVal)})</span>
        </span>
      </div>
      <div className="relative">
        <svg className="h-20 w-full overflow-visible" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
          {gridLines.map((g) => (
            <line
              key={g.y}
              x1="0"
              y1={g.y}
              x2={width}
              y2={g.y}
              className="stroke-cursor-hairline-soft"
              strokeWidth="1"
            />
          ))}
          <polygon className="fill-cursor-primary/10" points={areaPoints} />
          <polyline className="fill-none stroke-cursor-primary stroke-2" points={pointsStr} />
          {safePoints.length > 1 && (
            <circle cx={lastXPos} cy={lastYPos} r="3" className="fill-white stroke-cursor-primary stroke-2" />
          )}
        </svg>
      </div>
    </div>
  );
}
