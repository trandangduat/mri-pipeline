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
  SlidersHorizontal,
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
  type BatchSummary,
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
import {ConfirmDialog} from '../components/ConfirmDialog';
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
  success = 0,
  failed = 0,
  interrupted,
  stopped,
  running = 0,
  pending = 0,
  total = 0,
  size = 80,
}: {
  success?: number;
  failed?: number;
  interrupted?: number;
  stopped?: number;
  running?: number;
  pending?: number;
  total?: number;
  size?: number;
}) {
  const [hovered, setHovered] = useState<{label: string; color: string} | null>(null);
  const radius = 44;
  const center = 50;
  const chartStyle = {width: `${size}px`, height: `${size}px`, minWidth: `${size}px`, minHeight: `${size}px`};
  const stoppedCount = (typeof stopped === 'number' ? stopped : interrupted) || 0;
  const safeTotal = total > 0 ? total : ((success || 0) + (failed || 0) + stoppedCount + (running || 0) + (pending || 0));

  const segments = [
    {count: success || 0, color: '#1f8a65', key: 'success', label: `Finished: ${success || 0}`}, // Semantic Success
    {count: failed || 0, color: '#cf2d56', key: 'failed', label: `Failed: ${failed || 0}`}, // Semantic Error
    {count: stoppedCount, color: '#f59e0b', key: 'interrupted', label: `Stopped: ${stoppedCount}`}, // Semantic Warn
    {count: running || 0, color: '#0077b6', key: 'running', label: `Running: ${running || 0}`}, // Primary
    {count: pending || 0, color: '#cfcdc4', key: 'pending', label: `Pending: ${pending || 0}`}, // Muted / Pending
  ].filter((s) => s.count > 0);

  if (safeTotal <= 0 || segments.length === 0) {
    return (
      <div className="relative flex items-center justify-center flex-none" style={chartStyle}>
        <svg viewBox="0 0 100 100" className="block flex-none" style={chartStyle}>
          <circle cx={center} cy={center} r={radius} fill="#e6e5e0" />
        </svg>
      </div>
    );
  }

  // If only 1 category exists, render a full solid circle
  const singleSeg = segments.length === 1 ? segments[0] : undefined;
  if (singleSeg) {
    return (
      <div className="relative flex items-center justify-center flex-none" style={chartStyle}>
        {hovered && (
          <div className="pointer-events-none absolute -top-7 left-1/2 z-30 -translate-x-1/2 whitespace-nowrap rounded bg-cursor-ink px-2 py-0.75 text-2xs font-medium text-cursor-canvas shadow-md transition-all">
            <div className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full" style={{backgroundColor: hovered.color}} />
              <span>{hovered.label}</span>
            </div>
            <div className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-cursor-ink" />
          </div>
        )}
        <svg viewBox="0 0 100 100" className="block flex-none" style={chartStyle}>
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill={singleSeg.color}
            stroke="#ffffff"
            strokeWidth="1.5"
            className="cursor-pointer transition-opacity duration-200 hover:opacity-85"
            onMouseEnter={() => setHovered({label: singleSeg.label, color: singleSeg.color})}
            onMouseLeave={() => setHovered(null)}
          />
        </svg>
      </div>
    );
  }

  // Multiple segments: generate SVG pie slice paths
  let currentAngle = -Math.PI / 2; // Start from top (12 o'clock)
  const paths = segments.map((seg) => {
    const sliceAngle = (seg.count / safeTotal) * 2 * Math.PI;
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
        className="cursor-pointer transition-all duration-200 hover:opacity-85"
        onMouseEnter={() => setHovered({label: seg.label, color: seg.color})}
        onMouseLeave={() => setHovered(null)}
      />
    );
  });

  return (
    <div className="relative flex items-center justify-center flex-none" style={chartStyle}>
      {hovered && (
        <div className="pointer-events-none absolute -top-7 left-1/2 z-30 -translate-x-1/2 whitespace-nowrap rounded bg-cursor-ink px-2 py-0.75 text-2xs font-medium text-cursor-canvas shadow-md transition-all">
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full" style={{backgroundColor: hovered.color}} />
            <span>{hovered.label}</span>
          </div>
          <div className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-cursor-ink" />
        </div>
      )}
      <svg viewBox="0 0 100 100" className="block flex-none" style={chartStyle}>
        {paths}
      </svg>
    </div>
  );
}

function jobStatusLabel(state: unknown): string {
  const normalized = normalizeJobState(state);
  if (normalized === 'completed') return 'Finished';
  if (normalized === 'stopped') return 'Stopped';
  if (normalized === 'failed') return 'Failed';
  if (normalized === 'running') return 'Running';
  return 'Unknown';
}

function jobStatusBadgeClasses(state: unknown): string {
  const normalized = normalizeJobState(state);
  if (normalized === 'completed')
    return 'bg-cursor-semantic-success/10 text-cursor-semantic-success';
  if (normalized === 'stopped')
    return 'bg-cursor-semantic-warn/10 text-cursor-semantic-warn';
  if (normalized === 'failed')
    return 'bg-cursor-semantic-error/10 text-cursor-semantic-error';
  if (normalized === 'running')
    return 'bg-cursor-primary/10 text-cursor-primary';
  return 'bg-cursor-surface-strong/70 text-cursor-body';
}

function formatRelativeTime(timestampSeconds: number): string {
  if (!timestampSeconds || timestampSeconds <= 0) return 'Not started';
  const nowSec = Math.floor(Date.now() / 1000);
  const diffSec = Math.max(0, nowSec - timestampSeconds);
  if (diffSec < 60) return 'just now';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin} ${diffMin === 1 ? 'minute' : 'minutes'} ago`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours} ${diffHours === 1 ? 'hour' : 'hours'} ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays} ${diffDays === 1 ? 'day' : 'days'} ago`;
  const diffMonths = Math.floor(diffDays / 30);
  if (diffMonths < 12) return `${diffMonths} ${diffMonths === 1 ? 'month' : 'months'} ago`;
  const diffYears = Math.floor(diffDays / 365);
  return `${diffYears} ${diffYears === 1 ? 'year' : 'years'} ago`;
}

function jobBatchSummary(job: Record<string, unknown>): BatchSummary {
  const normState = normalizeJobState(job.state);
  const raw = job.batch_summary;
  let total = 0;
  let success = 0;
  let failed = 0;
  let running = 0;
  let pending = 0;
  let stopped = 0;

  if (raw && typeof raw === 'object') {
    const summary = raw as Partial<BatchSummary>;
    total = Number(summary.total || 0);
    success = Number(summary.success || 0);
    failed = Number(summary.failed || 0);
    running = Number(summary.running || 0);
    pending = Number(summary.pending || 0);
    stopped = Number(summary.stopped || summary.interrupted || 0);
  }

  // Fallback total if total <= 0
  if (total <= 0) {
    if (Array.isArray(job.input_files) && job.input_files.length > 0) {
      total = job.input_files.length;
    } else if (job.input_file) {
      total = 1;
    } else if (normState !== 'unknown') {
      total = 1;
    }
  }

  // Terminal state reconciliation
  if (normState === 'completed') {
    if (success === 0 && failed === 0 && stopped === 0) {
      success = total;
      running = 0;
      pending = 0;
    }
  } else if (normState === 'stopped') {
    if (stopped === 0 && success === 0 && failed === 0) {
      stopped = total;
      running = 0;
      pending = 0;
    } else {
      stopped = stopped + running + pending;
      running = 0;
      pending = 0;
    }
    if (stopped === 0 && failed > 0) {
      stopped = failed;
      failed = 0;
    } else if (stopped === 0 && success === total && total > 0) {
      stopped = total;
      success = 0;
    }
  } else if (normState === 'failed') {
    if (failed === 0 && success === 0 && stopped === 0) {
      failed = total;
      running = 0;
      pending = 0;
    }
  } else if (normState === 'running') {
    if (running === 0 && pending === 0 && success === 0) {
      running = total;
    }
  }

  const completed = success + failed + stopped;
  return {
    total,
    success,
    failed,
    running,
    pending,
    stopped,
    interrupted: stopped,
    completedPercent: total > 0 ? Math.round((completed / total) * 100) : 0,
  };
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
  const batchSummary = jobBatchSummary(job);
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
      className="group flex flex-col gap-2 rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3 text-left transition-all hover:border-cursor-primary hover:bg-cursor-canvas-soft hover:shadow-xs cursor-pointer"
    >
      {/* Top Header Row: Full Job Name + Status Badges */}
      <div className="flex items-center justify-between gap-2 min-w-0">
        <strong
          className="min-w-0 flex-1 truncate text-sm font-semibold text-cursor-ink transition-colors group-hover:text-cursor-primary"
          title={title}
        >
          {title}
        </strong>
        <div className="flex shrink-0 items-center gap-1">
          {lagging && (
            <span className="inline-flex items-center rounded bg-cursor-semantic-warn/10 text-cursor-semantic-warn px-2 py-0.5 text-2xs font-semibold uppercase tracking-[0.06em]">
              Lagging
            </span>
          )}
          <span
            className={`inline-flex items-center rounded px-2 py-0.5 text-2xs font-semibold uppercase tracking-[0.06em] ${jobStatusBadgeClasses(normState)}`}
          >
            {jobStatusLabel(normState)}
          </span>
        </div>
      </div>

      {/* Body: Left Pie Chart + Right Details (Preset, Started, Actions) */}
      <div className="relative flex items-center gap-3.5 border-t border-cursor-hairline-soft pt-2">
        <div className="flex items-center justify-center shrink-0" title="Batch summary">
          <BatchPieChart {...batchSummary} size={64} />
        </div>
        <div className="flex min-w-0 flex-1 flex-col justify-center gap-1.5 pr-8">
          <div className="flex items-center gap-1.5 text-xs text-cursor-body min-w-0" title={`Preset: ${mode}`}>
            <SlidersHorizontal className="h-3.5 w-3.5 text-cursor-muted shrink-0" />
            <span className="text-cursor-muted shrink-0 font-normal">Preset:</span>
            <span className="font-medium text-cursor-ink truncate">{mode}</span>
          </div>

          <div className="flex items-center gap-1.5 text-xs text-cursor-body min-w-0" title={`Started: ${startedStr}`}>
            <Clock className="h-3.5 w-3.5 text-cursor-muted shrink-0" />
            <span className="text-cursor-muted shrink-0 font-normal">Started:</span>
            <span className="font-medium text-cursor-ink truncate">{formatRelativeTime(startedAt)}</span>
          </div>
        </div>

        {/* Bottom Right Actions */}
        <div className="absolute right-0 bottom-0 flex items-center gap-1">
          <button
            type="button"
            aria-label={`Delete ${title}`}
            title={normState === 'running' ? 'Stop the job before deleting it' : 'Delete job'}
            disabled={normState === 'running' || deleting}
            onClick={(event) => {
              event.stopPropagation();
              onDelete();
            }}
            className="inline-flex h-6.5 w-6.5 items-center justify-center rounded text-cursor-muted transition-colors hover:bg-cursor-semantic-error/10 hover:text-cursor-semantic-error disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
          >
            {deleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>
    </div>
  );
}

function JobsListView({
  jobs,
  runtimeTarget,
  onSelectJob,
  onRefresh,
  isRefreshing,
  onDeleteJob,
  deletingJobId,
  remoteLagging,
}: {
  jobs: Record<string, unknown>[];
  runtimeTarget?: string;
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
  const isServerFirst = runtimeTarget === 'Server';

  const refreshButton = (
    <Button
      variant="outline"
      size="sm"
      onClick={onRefresh}
      disabled={isRefreshing}
      className="h-8 px-3 text-xs font-medium border-cursor-hairline bg-cursor-surface-card hover:bg-cursor-canvas-soft flex-none cursor-pointer"
    >
      {isRefreshing ? (
        <>
          <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> Refreshing...
        </>
      ) : (
        <>
          <RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Refresh
        </>
      )}
    </Button>
  );

  const localSection = (
    <section key="local-jobs">
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="flex items-center gap-1.5">
          <HardDrive className="h-4 w-4 text-cursor-primary" />
          <h2 className="text-base font-semibold text-cursor-ink">Local Jobs ({localJobs.length})</h2>
        </div>
        {!isServerFirst && refreshButton}
      </div>

      {localJobs.length === 0 ? (
        <p className="text-xs italic text-cursor-muted mt-1">
          No local jobs found. Run a local pipeline to start.
        </p>
      ) : (
        <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(22rem,1fr))]">
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
  );

  const serverSection = (
    <section key="server-jobs">
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="flex items-center gap-1.5">
          <Server className="h-4 w-4 text-cursor-primary" />
          <h2 className="text-base font-semibold text-cursor-ink">Server Jobs ({serverJobs.length})</h2>
        </div>
        {isServerFirst && refreshButton}
      </div>

      {serverJobs.length === 0 ? (
        <p className="text-xs italic text-cursor-muted mt-1">
          No server jobs found. Connect SSH and start a remote pipeline.
        </p>
      ) : (
        <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(22rem,1fr))]">
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
  );

  return (
    <div className="h-full w-full overflow-y-auto p-4 flex flex-col gap-4 text-cursor-ink">
      {isServerFirst ? (
        <>
          {serverSection}
          {localSection}
        </>
      ) : (
        <>
          {localSection}
          {serverSection}
        </>
      )}
    </div>
  );
}

function shortCopyDetail(raw: string): string {
  if (!raw) return '';
  const head = (raw.replace(/^Downloading file:\s*/i, '').split('→')[0] ?? raw).trim();
  const parts = head.split('/').filter(Boolean);
  const name = parts.length ? parts[parts.length - 1] || head : head;
  return name || raw;
}

export function JobsPage() {
  const storeLatestJobs = useJobsStore((s) => s.latestJobs);
  const latestJobs = React.useMemo(() => storeLatestJobs || [], [storeLatestJobs]);

  const setLatestJobs = useJobsStore((s) => s.setLatestJobs);
  const selectedJobId = useJobsStore((s) => s.selectedJobId);
  const setSelectedJobId = useJobsStore((s) => s.setSelectedJobId);
  const jobEvents = useJobsStore((s) => s.jobEvents) || [];
  const setJobEvents = useJobsStore((s) => s.setJobEvents);
  const appendJobEvents = useJobsStore((s) => s.appendJobEvents);
  const jobLogSearch = useJobsStore((s) => s.jobLogSearch) || '';
  const setJobLogSearch = useJobsStore((s) => s.setJobLogSearch);
  const outputText = useJobsStore((s) => s.outputText) || '';
  const setOutputText = useJobsStore((s) => s.setOutputText);
  const appendOutputText = useJobsStore((s) => s.appendOutputText);
  const clearJobLog = useJobsStore((s) => s.clearJobLog);
  const appendOutput = useJobsStore((s) => s.appendOutput);

  const [isLoadingDetails, setIsLoadingDetails] = useState<boolean>(false);
  const [detailsNotice, setDetailsNotice] = useState<{type: 'error' | 'info'; message: string} | null>(null);
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
  const [subjectStatusFilter, setSubjectStatusFilter] = useState<
    'all' | 'success' | 'running' | 'stopped' | 'interrupted' | 'failed' | 'pending'
  >('all');
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
  const [jobToDelete, setJobToDelete] = useState<Record<string, unknown> | null>(null);
  const [stoppingJob, setStoppingJob] = useState(false);
  const [showStopConfirm, setShowStopConfirm] = useState(false);

  const reqSeqRef = useRef<number>(0);
  const hasInitialRefreshed = useRef<boolean>(false);
  const prevSelectedJobIdRef = useRef<string | null | undefined>(undefined);
  const eventsOffsetRef = useRef<number>(0);
  const logOffsetRef = useRef<number>(0);
  const lastSyncedAtRef = useRef<number>(Date.now());
  const currentJobIdRef = useRef<string | null>(null);

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
      const seq = ++reqSeqRef.current;
      if (!jobId) {
        currentJobIdRef.current = null;
        eventsOffsetRef.current = 0;
        logOffsetRef.current = 0;
        if (seq === reqSeqRef.current) {
          setJobEvents([]);
          setOutputText('Log stream is idle.');
          setDetailsNotice(null);
          setActiveModalSubjectFile(null);
          setIsLoadingDetails(false);
        }
        return;
      }

      const isJobChanged = currentJobIdRef.current !== jobId;
      currentJobIdRef.current = jobId;

      const isInitial =
        options.resetUi === true ||
        isJobChanged ||
        eventsOffsetRef.current === 0 ||
        jobEvents.length === 0;

      if (isInitial) {
        eventsOffsetRef.current = 0;
        logOffsetRef.current = 0;
        setIsLoadingDetails(true);
        setJobEvents([]);
        setOutputText('');
        setDetailsNotice(null);
        setActiveModalSubjectFile(null);
      }

      if (!targetJob) {
        const jobs = Array.isArray(latestJobs) ? latestJobs : [];
        targetJob = (jobs.find((j) => j && (j as {job_id?: string}).job_id === jobId) as Record<string, unknown> | undefined) || null;
      }

      const isRemote =
        String(targetJob?.target || '').toLowerCase() === 'server' ||
        (!targetJob && (remoteResult.connected || formValues.runtimeTarget === 'Server'));

      const eventOffset = isInitial ? 0 : eventsOffsetRef.current;
      const logOffset = isInitial ? 0 : logOffsetRef.current;

      type EventsResult = {ok?: boolean; error?: string; events?: PipelineEvent[]; next_offset?: number; events_file_found?: boolean};
      type LogResult = {ok?: boolean; text?: string; next_offset?: number};
      let newEvents: PipelineEvent[] = [];
      let newLogText = '';
      let notice: {type: 'error' | 'info'; message: string} | null = null;

      try {
        if (isRemote) {
          const remotePayload = buildRemotePayload(formValues);
          const jobWorkspace = String(targetJob?.remote_workspace || '');
          if (jobWorkspace) remotePayload.workspace = jobWorkspace;
          const remoteJobDir = String(targetJob?.remote_job_dir || targetJob?.job_dir || jobId);
          const [eventsResult, logResult] = await Promise.all([
            readRemoteEventsMutation
              .mutateAsync({...remotePayload, remote_job_dir: remoteJobDir, job_id: jobId, offset: eventOffset, limit: 0})
              .catch((err: unknown) => ({ok: false, error: (err as Error).message, events: []}) as EventsResult),
            readRemoteLogMutation
              .mutateAsync({...remotePayload, remote_job_dir: remoteJobDir, job_id: jobId, offset: logOffset})
              .catch(() => ({text: ''})) as Promise<LogResult>,
          ]);
          const evRes = eventsResult as EventsResult;
          newEvents = Array.isArray(evRes?.events) ? (evRes.events as PipelineEvent[]) : [];
          newLogText = logResult?.text || '';
          if (typeof evRes?.next_offset === 'number' && evRes.next_offset > 0) {
            eventsOffsetRef.current = evRes.next_offset;
          }
          if (typeof logResult?.next_offset === 'number' && logResult.next_offset > 0) {
            logOffsetRef.current = logResult.next_offset;
          }
          if (evRes?.ok === false && evRes?.error) {
            notice = {type: 'error', message: evRes.error};
          } else if (isInitial && newEvents.length === 0 && evRes?.events_file_found === false) {
            notice = {type: 'info', message: 'No metric data recorded for this job (events.jsonl not found on the server).'};
          }
        } else {
          const [eventsResult, logResult] = await Promise.all([
            readEventsMutation.mutateAsync({jobId, offset: eventOffset, limit: 100000}).catch((err: unknown) => ({ok: false, error: (err as Error).message, events: []}) as EventsResult),
            readLogMutation.mutateAsync({jobId, offset: logOffset, maxBytes: 65536}).catch(() => ({text: ''})) as Promise<LogResult>,
          ]);
          const evRes = eventsResult as EventsResult;
          newEvents = Array.isArray(evRes?.events) ? (evRes.events as PipelineEvent[]) : [];
          newLogText = logResult?.text || '';
          if (typeof evRes?.next_offset === 'number' && evRes.next_offset > 0) {
            eventsOffsetRef.current = evRes.next_offset;
          }
          if (typeof logResult?.next_offset === 'number' && logResult.next_offset > 0) {
            logOffsetRef.current = logResult.next_offset;
          }
          if (evRes?.ok === false && evRes?.error) {
            notice = {type: 'error', message: evRes.error};
          } else if (isInitial && newEvents.length === 0 && evRes?.events_file_found === false) {
            notice = {type: 'info', message: 'No metric data recorded for this job (events.jsonl not found).'};
          }
        }
      } finally {
        if (seq === reqSeqRef.current) {
          lastSyncedAtRef.current = Date.now();
          if (isInitial) {
            setJobEvents(newEvents);
            setOutputText(newLogText || '');
          } else {
            if (newEvents.length > 0) {
              appendJobEvents(newEvents);
            }
            if (newLogText) {
              appendOutputText(newLogText);
            }
          }
          setDetailsNotice(notice);
          setIsLoadingDetails(false);
        }
      }
    },
    [
      appendJobEvents,
      appendOutputText,
      formValues,
      jobEvents.length,
      latestJobs,
      readEventsMutation,
      readLogMutation,
      readRemoteEventsMutation,
      readRemoteLogMutation,
      remoteResult.connected,
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
          await loadJobDetails(targetId, currentJob as Record<string, unknown>);
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

  const handleDeleteJob = (targetJob: Record<string, unknown>) => {
    const jobId = String(targetJob.job_id || '');
    if (!jobId || normalizeJobState(targetJob.state) === 'running') return;
    setJobToDelete(targetJob);
  };

  const handleConfirmDeleteJob = async () => {
    if (!jobToDelete) return;
    const jobId = String(jobToDelete.job_id || '');
    if (!jobId) return;

    setDeletingJobId(jobId);
    try {
      const client = new BackendClient(DEFAULT_BACKEND_URL);
      const result =
        String(jobToDelete.target || 'Local') === 'Server'
          ? await client.deleteRemoteJob({
              ...buildRemotePayload(formValues),
              job_id: jobId,
              remote_job_dir: String(jobToDelete.remote_job_dir || jobToDelete.job_dir || ''),
            })
          : await client.deleteLocalJob(jobId);
      if (!result.ok) {
        print('Delete job failed', {error: result.error || 'Unknown error'});
        return;
      }
      setJobToDelete(null);
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

  const handleStopJob = () => {
    if (!job || normState !== 'running' || isTerminal || stoppingJob) return;
    setShowStopConfirm(true);
  };

  const handleConfirmStopJob = async () => {
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
      setShowStopConfirm(false);
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
        void loadJobDetails(selectedJobId, jobObj, {resetUi: true});
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
  const rawJob = React.useMemo(
    () => jobsList.find((j) => j && (j as {job_id?: string}).job_id === selectedJobId) || null,
    [jobsList, selectedJobId],
  );
  const job = rawJob as Record<string, unknown> | null;
  const stateStr = (job?.state as string) || 'unknown';
  const normState = normalizeJobState(stateStr);
  const isServerJob = String(job?.target || 'Local') === 'Server';

  const safeEvents = Array.isArray(jobEvents) ? jobEvents : [];
  const batchImages = React.useMemo(() => deriveBatchImages(safeEvents, job || {}), [safeEvents, job]);
  const batchSummary = React.useMemo(() => deriveBatchSummary(batchImages), [batchImages]);
  const displayMeta = React.useMemo(() => deriveJobDisplayMetadata(job, safeEvents), [job, safeEvents]);
  const isTerminal = ['completed', 'failed', 'stopped'].includes(displayMeta.status_reconciled);

  // Adaptive polling:
  // - If looking at a running job: poll every 5s with lightweight delta fetch
  // - If looking at a terminal job: do not poll (paused)
  // - If on jobs list: poll every 20s
  useEffect(() => {
    if (selectedJobId && isTerminal) {
      return;
    }
    const pollDelay = selectedJobId && normState === 'running' ? 5_000 : 20_000;
    const interval = setInterval(() => void refreshJobs(), pollDelay);
    return () => clearInterval(interval);
  }, [refreshJobs, selectedJobId, isTerminal, normState]);

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
  const stageLabels = React.useMemo(() => {
    const labels: Record<string, string> = {};
    if (metadata?.stages && Array.isArray(metadata.stages)) {
      metadata.stages.forEach((s) => {
        if (s?.id && s?.label) {
          labels[s.id] = s.label;
        }
      });
    }
    return labels;
  }, [metadata?.stages]);

  const toolDisplayNames = React.useMemo(() => {
    const tools = (metadata?.tools || {}) as Record<string, {display_name?: string}>;
    return Object.fromEntries(Object.entries(tools).map(([key, tool]) => [key, tool.display_name || key]));
  }, [metadata?.tools]);

  const filteredLog = React.useMemo(
    () => filterLogLines(outputText, jobLogSearch, showRawLog),
    [outputText, jobLogSearch, showRawLog],
  );

  const handleDownloadClick = () => {
    if (!job || !isTerminal) return;
    if (isServerJob) {
      const remoteJobDir = String(job?.remote_job_dir || job?.job_dir || '');
      const rawOutputDir = String(job?.effective_output_dir || job?.output_dir || '');
      const remotePath =
        rawOutputDir && rawOutputDir !== 'N/A' ? rawOutputDir : remoteJobDir ? `${remoteJobDir}/outputs` : '';
      setDownloadDialogOpen(true);
      setDownloadPhase('select');
      setDownloadSteps([]);
      setDownloadLogs([]);
      setDownloadCopiedFiles(undefined);
      setDownloadTotalFiles(undefined);
      setDownloadFinalPath(undefined);
      setDownloadError(undefined);
      setDownloadRunning(false);
      setWebBrowseHint(false);
    } else {
      const effDir = String(displayMeta.output_dir_str);
      const subDir = String(job?.download_subdir || '');
      const fullPath = subDir && subDir !== 'N/A' ? `${effDir}/${subDir}` : effDir;
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
          const rawDetail = (data.detail as string) || '';
          const detail = stepId === 'copy' && status === 'running' ? shortCopyDetail(rawDetail) : rawDetail;
          setDownloadSteps((prev) => prev.map((s) => (s.id === stepId ? {...s, status, detail} : s)));
          if (rawDetail && status === 'running') {
            setDownloadLogs((prev) => [...prev, rawDetail]);
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
  const filteredBatchImages = React.useMemo(() => {
    const q = subjectSearchQuery.trim().toLowerCase();
    return batchImages.filter((img) => {
      const matchesStatus =
        subjectStatusFilter === 'all'
          ? true
          : subjectStatusFilter === 'pending'
            ? img.status === 'pending'
            : subjectStatusFilter === 'stopped'
              ? img.status === 'stopped' || (img.status as string) === 'interrupted'
              : img.status === subjectStatusFilter;

      if (!q) return matchesStatus;

      const matchesText =
        img.subject_id.toLowerCase().includes(q) ||
        img.input_file.toLowerCase().includes(q) ||
        `#${img.idx}`.includes(q) ||
        String(img.idx) === q;

      return matchesStatus && matchesText;
    });
  }, [batchImages, subjectStatusFilter, subjectSearchQuery]);

  // Modal active subject
  const modalSubject = React.useMemo(() => {
    return batchImages.find((img) => img.input_file === activeModalSubjectFile) || null;
  }, [batchImages, activeModalSubjectFile]);

  const modalImageSteps = React.useMemo(() => {
    return modalSubject
      ? deriveImageSteps(safeEvents, modalSubject, selectedTools, stageOrder, stageLabels)
      : [];
  }, [safeEvents, modalSubject, selectedTools, stageOrder, stageLabels]);

  const modalMetricsSeries = React.useMemo(() => {
    return modalSubject
      ? deriveMetricsSeries(safeEvents, modalSubject)
      : {cpuSeries: [], ramSeries: [], latestContainer: ''};
  }, [safeEvents, modalSubject]);

  const totalModalStages = modalImageSteps.length;
  const completedModalStages = modalImageSteps.filter((step) => step.status === 'success').length;

  const subjectStepLabelsMap = React.useMemo(() => {
    const map = new Map<string, string>();
    for (const img of batchImages) {
      if (img.status === 'success') {
        map.set(img.input_file, 'Completed');
      } else if (img.status === 'failed') {
        map.set(img.input_file, 'Failed');
      } else if (img.status === 'pending') {
        map.set(img.input_file, 'Waiting in queue');
      } else {
        const steps = deriveImageSteps(safeEvents, img, selectedTools, stageOrder, stageLabels);
        const runningStep = steps.find((s) => s.status === 'running');
        if (runningStep) {
          map.set(img.input_file, runningStep.label || runningStep.stage);
        } else {
          const lastSuccess = [...steps].reverse().find((s) => s.status === 'success');
          if (lastSuccess) {
            map.set(img.input_file, `After ${lastSuccess.label || lastSuccess.stage}`);
          } else if (img.status === 'stopped' || (img.status as string) === 'interrupted') {
            map.set(img.input_file, 'Stopped before start');
          } else {
            map.set(img.input_file, 'Processing...');
          }
        }
      }
    }
    return map;
  }, [batchImages, safeEvents, selectedTools, stageOrder, stageLabels]);

  const getSubjectCurrentStepLabel = (img: (typeof batchImages)[0]) => {
    return subjectStepLabelsMap.get(img.input_file) || 'Processing...';
  };

  if (!selectedJobId && !urlJobId) {
    return (
      <>
        <JobsListView
          jobs={jobsList}
          runtimeTarget={formValues.runtimeTarget}
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

        <ConfirmDialog
          open={jobToDelete !== null}
          title="Delete Job"
          entityName={jobToDelete ? jobBasename(jobToDelete.display_name || jobToDelete.job_id) : undefined}
          description="Are you sure you want to delete this job? All associated output files, execution logs, and benchmark records will be permanently removed from disk."
          confirmLabel="Delete Job"
          confirmLoadingLabel="Deleting..."
          isLoading={deletingJobId !== null}
          onConfirm={handleConfirmDeleteJob}
          onClose={() => {
            if (deletingJobId === null) setJobToDelete(null);
          }}
        />
      </>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col gap-4 overflow-hidden text-cursor-ink p-6">
      {/* 1. Top Grid: Job Detail (Left) + Batch Summary (Right) */}
      <div className="grid flex-none grid-cols-[minmax(0,1fr)_minmax(18rem,24rem)] gap-3">
        {/* Left: Job Detail Card */}
        <Card className="rounded-lg border-cursor-hairline bg-cursor-surface-card shadow-none p-3.5">
          {/* Header: Back Button + Status Badge + Job Title */}
          {(() => {
            const isServerJob =
              String(job?.target || '').toLowerCase() === 'server' ||
              String(job?.job_id || '').startsWith('remote_job_') ||
              String(job?.display_name || '').startsWith('remote_job_');
            const baseJobTitle = (job?.display_name as string) || (job?.job_id as string) || 'No Job Selected';
            const jobTitle =
              isServerJob && !baseJobTitle.startsWith('[Server]') && !baseJobTitle.startsWith('[server]')
                ? `[Server] ${baseJobTitle}`
                : baseJobTitle;

            return (
              <div className="flex flex-wrap items-center justify-between gap-2.5 pb-2.5 border-b border-cursor-hairline-soft">
                <div className="flex items-center gap-2.5 min-w-0 flex-1">
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
                  <span
                    className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.06em] flex-none ${jobStatusBadgeClasses(displayMeta.status_reconciled)}`}
                  >
                    <StatusDotLarge state={displayMeta.status_reconciled} className="h-2 w-2" />
                    {displayJobState(displayMeta.status_reconciled)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <h2
                      className="m-0 text-base font-semibold tracking-tight text-cursor-ink truncate"
                      title={jobTitle}
                    >
                      {jobTitle}
                    </h2>
                  </div>
                </div>
              </div>
            );
          })()}

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
              </div>

              {/* Solid Pie Chart (Left) + Vertically Aligned Legends (Right) */}
              <div className="flex items-center gap-4 py-1 mb-3">
                <BatchPieChart
                  success={batchSummary.success}
                  failed={batchSummary.failed}
                  interrupted={batchSummary.stopped || batchSummary.interrupted || 0}
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
                  {Boolean((batchSummary.stopped || batchSummary.interrupted) && (batchSummary.stopped || batchSummary.interrupted)! > 0) && (
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="h-2.5 w-2.5 rounded-full bg-cursor-semantic-warn flex-none" />
                        <span className="text-cursor-ink text-xs font-medium">Stopped</span>
                      </div>
                      <span className="font-semibold text-cursor-ink font-mono">{batchSummary.stopped ?? batchSummary.interrupted}</span>
                    </div>
                  )}
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
                <CardTitle className="font-semibold text-base text-cursor-ink">
                  Batch Subjects ({batchImages.length})
                </CardTitle>
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
          <div className="flex min-h-0 flex-1 flex-col bg-cursor-surface-card p-3.5 overflow-hidden">
            {/* Job Data Notice */}
            {detailsNotice && (
              <div
                className={`mb-2.5 flex-none rounded-md border px-3 py-2 text-xs leading-relaxed ${
                  detailsNotice.type === 'error'
                    ? 'border-cursor-semantic-error/30 bg-cursor-semantic-error/5 text-cursor-semantic-error'
                    : 'border-cursor-hairline bg-cursor-canvas-soft text-cursor-body'
                }`}
              >
                {detailsNotice.type === 'error' ? 'Could not read job data: ' : ''}
                {detailsNotice.message}
              </div>
            )}
            {/* Search & Filter Toolbar */}
            <div className="mb-3 flex flex-wrap items-center justify-start gap-3 flex-none">
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
              <div className="hidden sm:block h-4 w-px bg-cursor-hairline-strong flex-none" />
              <div className="flex flex-wrap items-center gap-1.5">
                {(
                  Boolean((batchSummary.stopped || batchSummary.interrupted) && (batchSummary.stopped || batchSummary.interrupted)! > 0)
                    ? (['all', 'success', 'running', 'stopped', 'failed', 'pending'] as const)
                    : (['all', 'success', 'running', 'failed', 'pending'] as const)
                ).map((st) => {
                  const label = st === 'success' ? 'SUCCESS' : st === 'stopped' ? 'Stopped' : st;
                  const count =
                    st === 'all'
                      ? batchImages.length
                      : st === 'success'
                        ? batchSummary.success
                        : st === 'running'
                          ? batchSummary.running
                          : st === 'stopped'
                            ? batchSummary.stopped ?? batchSummary.interrupted ?? 0
                            : st === 'failed'
                              ? batchSummary.failed
                              : batchSummary.pending;

                  return (
                    <button
                      key={st}
                      type="button"
                      onClick={() => setSubjectStatusFilter(st)}
                      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.75 text-xs font-medium transition-colors cursor-pointer capitalize border ${
                        subjectStatusFilter === st
                          ? 'border-cursor-hairline-strong bg-cursor-canvas text-cursor-ink font-semibold shadow-2xs'
                          : 'border-transparent text-cursor-body hover:text-cursor-ink hover:bg-cursor-canvas-soft'
                      }`}
                    >
                      <span>{label}</span>
                      <span
                        className={`text-2xs font-mono px-1.5 py-0.2 rounded-full ${
                          subjectStatusFilter === st ? 'bg-cursor-surface-strong text-cursor-ink font-bold' : 'text-cursor-muted'
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
              <div className="grid grid-cols-[repeat(auto-fill,minmax(18rem,1fr))] content-start gap-3 overflow-y-auto flex-1 min-h-0 p-0.5">
                {(() => {
                  if (filteredBatchImages.length === 0) {
                    if (isLoadingDetails && batchImages.length === 0) {
                      return (
                        <>
                          {[0, 1, 2, 3, 4, 5].map((i) => (
                            <div
                              key={i}
                              className="rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3.5 min-h-[96px]"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <div className="flex items-center gap-1.5">
                                  <Skeleton className="h-5 w-5 rounded flex-none" />
                                  <Skeleton className="h-2.5 w-10" />
                                </div>
                                <Skeleton className="h-4 w-14 rounded-full" />
                              </div>
                              <div className="my-2">
                                <Skeleton className="h-3.5 w-3/4" />
                              </div>
                              <div className="pt-2 border-t border-cursor-hairline-soft flex items-center justify-between">
                                <Skeleton className="h-3 w-24" />
                                <Skeleton className="h-3 w-12" />
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
                        className="group flex cursor-pointer flex-col justify-between rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3.5 text-left transition-all hover:border-cursor-primary hover:bg-cursor-canvas-soft hover:shadow-xs focus:outline-none focus:ring-1 focus:ring-cursor-primary/30 min-h-[96px]"
                      >
                        {/* Card Header: Index & Status Badge */}
                        <div className="flex items-center justify-between gap-2 min-w-0">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <div
                              className={`flex h-5 w-5 items-center justify-center rounded border flex-none ${subjectAccentClasses(img.status)}`}
                            >
                              <BrainCircuit className="h-3 w-3" />
                            </div>
                            <span className="font-mono text-2xs font-semibold uppercase tracking-[0.06em] text-cursor-muted bg-cursor-canvas-soft px-1.5 py-0.5 rounded border border-cursor-hairline-soft">
                              #{String(img.idx).padStart(3, '0')}
                            </span>
                          </div>
                          <span
                            className={`font-semibold text-2xs uppercase tracking-[0.06em] px-2 py-0.5 rounded flex-none ${
                              img.status === 'success'
                                 ? 'text-cursor-semantic-success bg-cursor-semantic-success/10'
                                 : img.status === 'failed'
                                   ? 'text-cursor-semantic-error bg-cursor-semantic-error/10'
                                   : img.status === 'stopped' || (img.status as string) === 'interrupted'
                                     ? 'text-cursor-semantic-warn bg-cursor-semantic-warn/10'
                                     : img.status === 'running'
                                       ? 'text-cursor-primary bg-cursor-primary/10'
                                       : 'text-cursor-muted bg-cursor-surface-strong/70'
                            }`}
                          >
                            {img.status === 'success' ? 'SUCCESS' : (img.status === 'stopped' || (img.status as string) === 'interrupted') ? 'STOPPED' : img.status.toUpperCase()}
                          </span>
                        </div>

                        {/* Card Body: Subject ID with prominent mono font */}
                        <div className="my-2 min-w-0">
                          <h4
                            className="text-xs font-bold leading-snug text-cursor-ink font-mono group-hover:text-cursor-primary transition-colors line-clamp-1 break-all"
                            title={img.subject_id}
                          >
                            {img.subject_id}
                          </h4>
                        </div>

                        {/* Card Footer: Full-Width Current Step Badge */}
                        <div className="pt-2 border-t border-cursor-hairline-soft w-full min-w-0">
                          <span
                            className={`flex items-center justify-between gap-1.5 w-full text-2xs font-semibold px-2.5 py-1 rounded-md border transition-colors ${
                              img.status === 'running'
                                ? 'bg-cursor-primary/10 text-cursor-primary border-cursor-primary/20'
                                : img.status === 'success'
                                  ? 'bg-cursor-semantic-success/10 text-cursor-semantic-success border-cursor-semantic-success/20 font-medium'
                                  : img.status === 'failed'
                                    ? 'bg-cursor-semantic-error/10 text-cursor-semantic-error border-cursor-semantic-error/20 font-medium'
                                    : img.status === 'stopped' || (img.status as string) === 'interrupted'
                                      ? 'bg-cursor-semantic-warn/10 text-cursor-semantic-warn border-cursor-semantic-warn/20 font-medium'
                                      : 'bg-cursor-canvas-soft text-cursor-body border-cursor-hairline-soft font-medium'
                            }`}
                            title={currentStepText}
                          >
                            <span className="flex items-center gap-1.5 min-w-0 truncate flex-1">
                              {img.status === 'running' && (
                                <span className="h-1.5 w-1.5 rounded-full bg-cursor-primary animate-pulse flex-none" />
                              )}
                              <span className="truncate">{currentStepText}</span>
                            </span>
                            <ChevronRight className="h-3.5 w-3.5 text-cursor-muted group-hover:text-cursor-primary group-hover:translate-x-0.5 transition-all flex-none" />
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
                          <span className="truncate text-sm font-bold font-mono text-cursor-ink group-hover:text-cursor-primary transition-colors">
                            {img.subject_id}
                          </span>
                        </div>
                        <div className="flex items-center gap-4 flex-none">
                          <div className="flex items-center gap-2">
                            <span className="text-3xs uppercase tracking-[0.06em] text-cursor-muted font-medium">Stage:</span>
                            <span
                              className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-0.75 rounded-md font-semibold border ${
                                img.status === 'running'
                                  ? 'bg-cursor-primary/10 text-cursor-primary border-cursor-primary/20'
                                  : img.status === 'success'
                                    ? 'bg-cursor-semantic-success/10 text-cursor-semantic-success border-cursor-semantic-success/20'
                                    : img.status === 'failed'
                                      ? 'bg-cursor-semantic-error/10 text-cursor-semantic-error border-cursor-semantic-error/20'
                                      : img.status === 'stopped' || (img.status as string) === 'interrupted'
                                        ? 'bg-cursor-semantic-warn/10 text-cursor-semantic-warn border-cursor-semantic-warn/20'
                                        : 'bg-cursor-canvas-soft text-cursor-body border-cursor-hairline-soft'
                              }`}
                            >
                              {img.status === 'running' && (
                                <span className="h-1.5 w-1.5 rounded-full bg-cursor-primary animate-pulse flex-none" />
                              )}
                              {currentStepText}
                            </span>
                          </div>
                          <span
                            className={`inline-flex items-center justify-center rounded px-2 py-0.5 text-2xs font-semibold uppercase tracking-[0.06em] min-w-[3.5rem] ${
                              img.status === 'success'
                                ? 'text-cursor-semantic-success bg-cursor-semantic-success/10'
                                : img.status === 'failed'
                                  ? 'text-cursor-semantic-error bg-cursor-semantic-error/10'
                                  : img.status === 'stopped' || (img.status as string) === 'interrupted'
                                    ? 'text-cursor-semantic-warn bg-cursor-semantic-warn/10'
                                    : img.status === 'running'
                                      ? 'text-cursor-primary bg-cursor-primary/10'
                                      : 'text-cursor-muted bg-cursor-surface-strong/70'
                            }`}
                          >
                            {img.status === 'success' ? 'SUCCESS' : (img.status === 'stopped' || (img.status as string) === 'interrupted') ? 'STOPPED' : img.status.toUpperCase()}
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
                <StatusPill state={modalSubject.status}>
                  {modalSubject.status === 'success'
                    ? 'SUCCESS'
                    : modalSubject.status === 'stopped' || (modalSubject.status as string) === 'interrupted'
                      ? 'STOPPED'
                      : modalSubject.status.toUpperCase()}
                </StatusPill>
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
                        lastSyncedAt={lastSyncedAtRef.current}
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

      {/* 5. Delete Job Confirm Dialog */}
      <ConfirmDialog
        open={jobToDelete !== null}
        title="Delete Job"
        entityName={jobToDelete ? jobBasename(jobToDelete.display_name || jobToDelete.job_id) : undefined}
        description="Are you sure you want to delete this job? All associated output files, execution logs, and benchmark records will be permanently removed from disk."
        confirmLabel="Delete Job"
        confirmLoadingLabel="Deleting..."
        isLoading={deletingJobId !== null}
        onConfirm={handleConfirmDeleteJob}
        onClose={() => {
          if (deletingJobId === null) setJobToDelete(null);
        }}
      />

      {/* 6. Stop Job Confirm Dialog */}
      <ConfirmDialog
        open={showStopConfirm}
        title="Stop Job"
        entityName={job ? jobBasename(job.display_name || job.job_id) : undefined}
        description="Are you sure you want to stop this running pipeline job? Current active processing stages will be cancelled immediately."
        confirmLabel="Stop Job"
        confirmLoadingLabel="Stopping..."
        isLoading={stoppingJob}
        onConfirm={handleConfirmStopJob}
        onClose={() => {
          if (!stoppingJob) setShowStopConfirm(false);
        }}
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
      ? 'bg-cursor-semantic-success/10 text-cursor-semantic-success'
      : status === 'running'
        ? 'bg-cursor-primary/10 text-cursor-primary'
        : status === 'failed'
          ? 'bg-cursor-semantic-error/10 text-cursor-semantic-error'
          : status === 'stopped' || status === 'interrupted'
            ? 'bg-cursor-semantic-warn/10 text-cursor-semantic-warn'
            : isSkipped
              ? 'bg-cursor-canvas-soft text-cursor-muted-soft'
              : 'bg-cursor-surface-strong/70 text-cursor-muted';
  const label =
    status === 'success'
      ? 'SUCCESS'
      : status === 'running'
        ? 'RUNNING'
        : status === 'failed'
          ? 'FAIL'
          : status === 'stopped' || status === 'interrupted'
            ? 'STOPPED'
            : isSkipped
              ? 'SKIPPED'
              : 'PENDING';
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-2xs font-semibold uppercase tracking-[0.06em] flex-none ${cls}`}
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
  if (status === 'stopped' || status === 'interrupted')
    return 'text-cursor-semantic-warn border-cursor-semantic-warn/25 bg-cursor-semantic-warn/5';
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

function LiveStepElapsed({
  elapsed_sec,
  isRunning,
  lastSyncedAt,
}: {
  elapsed_sec?: number;
  isRunning: boolean;
  lastSyncedAt?: number;
}) {
  const [now, setNow] = useState<number>(() => Date.now());

  useEffect(() => {
    if (!isRunning || elapsed_sec === undefined) return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [isRunning, elapsed_sec]);

  const delta =
    isRunning && elapsed_sec !== undefined && lastSyncedAt
      ? Math.max(0, Math.floor((now - lastSyncedAt) / 1000))
      : 0;
  const effective = elapsed_sec !== undefined ? elapsed_sec + delta : undefined;

  return <StageMetric label="Elapsed" value={formatElapsed(effective)} />;
}

function VerticalTimelineStepRow({
  step,
  isLast,
  toolDisplayNames,
  lastSyncedAt,
}: {
  step: StageStepDetail;
  isLast: boolean;
  toolDisplayNames: Record<string, string>;
  lastSyncedAt?: number;
}) {
  const isSkipped = step?.status === 'not_scheduled' || step?.status === 'skipped';

  const rowClass =
    step?.status === 'running'
      ? 'border-cursor-primary/40 bg-cursor-canvas-soft'
      : step?.status === 'failed'
        ? 'border-cursor-semantic-error/20 bg-cursor-canvas-soft'
        : step?.status === 'stopped' || step?.status === 'interrupted'
          ? 'border-cursor-semantic-warn/30 bg-cursor-canvas-soft'
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
          : step?.status === 'stopped' || step?.status === 'interrupted'
            ? 'bg-cursor-semantic-warn ring-2 ring-cursor-semantic-warn/15'
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
              <LiveStepElapsed
                elapsed_sec={step?.elapsed_sec}
                isRunning={step?.status === 'running'}
                lastSyncedAt={lastSyncedAt}
              />
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
