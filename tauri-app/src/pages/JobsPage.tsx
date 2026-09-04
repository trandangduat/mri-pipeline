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
import {toast} from 'sonner';
import {
  REMOTE_DETAIL_TIMEOUT_MS,
  REMOTE_JOBS_TIMEOUT_MS,
  isAbortError,
  isBackendUnreachableMessage,
  isSshConnectionMessage,
} from '../lib/connection';
import {StatusPill, StatusDotLarge, statusDotClasses} from '../components/ui';
import {normalizeJob, normalizeJobState, sortJobsByStartedAtDesc, jobBasename} from '../jobFormatters';
import {
  deriveBatchImages,
  reduceBatchImages,
  deriveBatchSummary,
  deriveImageSteps,
  deriveJobDisplayMetadata,
  deriveMetricsSeries,
  deriveSubjectStageInfo,
  displayJobState,
  filterLogLines,
  type BatchSummary,
  StageStepDetail,
  DEFAULT_STAGE_ORDER,
  DEFAULT_STAGE_LABELS,
} from '../lib/jobs';
import {
  useListLocalJobsMutation,
  useReadLocalEventsMutation,
  useReadLocalLogMutation,
  useReadLocalMetricsMutation,
} from '../query/useJobs';
import {
  useListRemoteJobsMutation,
  useReadRemoteEventsMutation,
  useReadRemoteLogMutation,
  useReadRemoteMetricsMutation,
} from '../query/useRemote';
import {useMetadata} from '../query/useEnvironment';
import {useJobsStore, capLogLines} from '../stores/jobsStore';
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

function selectedDialogPath(selected: unknown) {
  if (Array.isArray(selected)) return selected[0] || '';
  return (selected as string) || '';
}

export function canonicalJobId(id: string | null | undefined): string {
  if (!id) return '';
  return id.startsWith('remote_') ? id.slice(7) : id;
}

export function matchesJobId(a: string | null | undefined, b: string | null | undefined): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  return canonicalJobId(a) === canonicalJobId(b);
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
  deleteBlocked = false,
  deleteBlockedReason,
}: {
  job: Record<string, unknown>;
  onClick: () => void;
  onDelete: () => void;
  deleting: boolean;
  deleteBlocked?: boolean;
  deleteBlockedReason?: string;
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
      className="group flex flex-col gap-2 rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3 text-left hover:border-cursor-primary hover:bg-cursor-canvas-soft hover:shadow-xs cursor-pointer"
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
            title={
              deleteBlocked && deleteBlockedReason
                ? deleteBlockedReason
                : normState === 'running'
                  ? 'Stop the job before deleting it'
                  : 'Delete job'
            }
            disabled={normState === 'running' || deleting || deleteBlocked}
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
  isInitialLoading,
  onDeleteJob,
  deletingJobId,
  serverActionsBlocked,
  localActionsBlocked,
  serverActionsBlockedReason,
  localActionsBlockedReason,
}: {
  jobs: Record<string, unknown>[];
  runtimeTarget?: string;
  onSelectJob: (jobId: string) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
  isInitialLoading?: boolean;
  onDeleteJob: (job: Record<string, unknown>) => void;
  deletingJobId: string | null;
  serverActionsBlocked: boolean;
  localActionsBlocked: boolean;
  serverActionsBlockedReason: string;
  localActionsBlockedReason: string;
}) {
  if (isInitialLoading || (isRefreshing && jobs.length === 0)) {
    return (
      <div className="h-full w-full overflow-y-auto p-4 flex flex-col gap-4 text-cursor-ink">
        <div className="flex items-center gap-2 text-sm text-cursor-muted">
          <Loader2 className="h-4 w-4 animate-spin text-cursor-muted" />
          <span>Loading...</span>
        </div>
      </div>
    );
  }

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
      className="h-8 px-3 text-sm font-medium border-cursor-hairline bg-cursor-surface-card hover:bg-cursor-canvas-soft flex-none cursor-pointer"
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

      {localJobs.length > 0 && (
        <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(22rem,1fr))]">
          {localJobs.map((j) => (
            <JobCard
              key={String(j.job_id || j.display_name)}
              job={j}
              onClick={() => onSelectJob(String(j.job_id))}
              onDelete={() => onDeleteJob(j)}
              deleting={deletingJobId === String(j.job_id)}
              deleteBlocked={localActionsBlocked}
              deleteBlockedReason={localActionsBlockedReason}
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

      {serverJobs.length > 0 && (
        <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(22rem,1fr))]">
          {serverJobs.map((j) => (
            <JobCard
              key={String(j.job_id || j.display_name)}
              job={j}
              onClick={() => onSelectJob(String(j.job_id))}
              onDelete={() => onDeleteJob(j)}
              deleting={deletingJobId === String(j.job_id)}
              deleteBlocked={serverActionsBlocked}
              deleteBlockedReason={serverActionsBlockedReason}
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
  const hasLoadedInitialJobs = useJobsStore((s) => s.hasLoadedInitialJobs);
  const setHasLoadedInitialJobs = useJobsStore((s) => s.setHasLoadedInitialJobs);

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
  const [isLogExpanded, setIsLogExpanded] = useState<boolean>(false);

  const isLogExpandedRef = useRef<boolean>(false);
  isLogExpandedRef.current = isLogExpanded;
  const activeModalSubjectFileRef = useRef<string | null>(null);
  activeModalSubjectFileRef.current = activeModalSubjectFile;
  const [modalMetricsEvents, setModalMetricsEvents] = useState<PipelineEvent[]>([]);
  const modalMetricsOffsetRef = useRef<number>(0);
  const prevModalSubjectRef = useRef<string | null>(null);

  // Reset accumulated telemetry whenever the modal subject changes (including
  // close). Byte offsets are per-file; reusing a stale offset from another
  // subject/job seeks past EOF and returns empty metrics forever.
  useEffect(() => {
    if (prevModalSubjectRef.current !== activeModalSubjectFile) {
      prevModalSubjectRef.current = activeModalSubjectFile;
      setModalMetricsEvents([]);
      modalMetricsOffsetRef.current = 0;
    }
  }, [activeModalSubjectFile]);

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
  const detailsAbortRef = useRef<AbortController | null>(null);

  const closeSubjectModal = useCallback(() => {
    // Legacy jobs can have very large telemetry files. Abort detail reads as
    // soon as the subject view is no longer visible.
    reqSeqRef.current += 1;
    detailsAbortRef.current?.abort();
    detailsAbortRef.current = null;
    activeModalSubjectFileRef.current = null;
    isLogExpandedRef.current = false;
    prevModalSubjectRef.current = null;
    modalMetricsOffsetRef.current = 0;
    setModalMetricsEvents([]);
    setActiveModalSubjectFile(null);
    setIsLogExpanded(false);
  }, []);

  const formValues = usePipelineFormStore((s) => s.formValues);
  const remoteResult = useRemoteStore();
  const sshStatus = useRemoteStore((s) => s.sshStatus);
  const backendStatus = useRemoteStore((s) => s.backendStatus);

  // Channel health (see lib/connection.ts):
  // - backendDown: HTTP link UI -> local backend is down. Everything remote or
  //   local that needs the backend is blocked, auto-polling pauses.
  // - sshDown: backend is alive but the SSH leg backend -> server just failed.
  //   Only Server jobs are stale/blocked; Local jobs keep working.
  // The global status line above the footer (all pages) appears on the first
  // failure. Recovery is always manual (Retry).
  const backendDown = backendStatus === 'down';
  const sshDown = sshStatus === 'disconnected';
  const serverActionsBlocked = backendDown || sshDown;
  const localActionsBlocked = backendDown;
  const serverActionsBlockedReason = backendDown
    ? 'Unavailable: the local backend is unreachable. Retry once it is running again.'
    : 'Unavailable: the SSH connection to the server is down. Reconnect from Pipeline Configuration.';
  const localActionsBlockedReason =
    'Unavailable: the local backend is unreachable. Retry once it is running again.';

  const busy = useUiStore((s) => s.busy);
  const setBusyKey = useUiStore((s) => s.setBusyKey);

  const {data: metadata} = useMetadata();

  const print = useCallback((label: string, payload: unknown) => {
    appendOutput(`${label}\n${JSON.stringify(payload, null, 2)}\n\n`);
  }, [appendOutput]);

  const listLocalJobsMutation = useListLocalJobsMutation();
  const readEventsMutation = useReadLocalEventsMutation();
  const readLocalMetricsMutation = useReadLocalMetricsMutation();
  const readLogMutation = useReadLocalLogMutation();
  const listRemoteJobsMutation = useListRemoteJobsMutation();
  const readRemoteEventsMutation = useReadRemoteEventsMutation();
  const readRemoteMetricsMutation = useReadRemoteMetricsMutation();
  const readRemoteLogMutation = useReadRemoteLogMutation();

  // useMutation() returns a NEW result object identity on every render
  // (`{...result, mutate, mutateAsync}`). Depending on the whole objects in
  // useCallback/useEffect dep arrays recreates the callbacks every render and
  // re-fires the detail-fetch effects in a loop. Only `mutateAsync` is
  // referentially stable, so depend on these instead.
  const listLocalJobsAsync = listLocalJobsMutation.mutateAsync;
  const readEventsAsync = readEventsMutation.mutateAsync;
  const readLocalMetricsAsync = readLocalMetricsMutation.mutateAsync;
  const readLogAsync = readLogMutation.mutateAsync;
  const listRemoteJobsAsync = listRemoteJobsMutation.mutateAsync;
  const readRemoteEventsAsync = readRemoteEventsMutation.mutateAsync;
  const readRemoteMetricsAsync = readRemoteMetricsMutation.mutateAsync;
  const readRemoteLogAsync = readRemoteLogMutation.mutateAsync;

  const {jobId: urlJobId} = useParams<{jobId?: string}>();

  const navigate = useNavigate();

  const loadJobDetails = useCallback(
    async (
      jobId: string | null,
      targetJob?: Record<string, unknown> | null,
      options: {resetUi?: boolean; fetchLog?: boolean; force?: boolean; trackHealth?: boolean} = {},
    ) => {
      const seq = ++reqSeqRef.current;
      if (!jobId) {
        detailsAbortRef.current?.abort();
        detailsAbortRef.current = null;
        activeModalSubjectFileRef.current = null;
        isLogExpandedRef.current = false;
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

      const isJobChanged = !matchesJobId(currentJobIdRef.current, jobId);
      currentJobIdRef.current = canonicalJobId(jobId);

      const currentEvents = useJobsStore.getState().jobEvents || [];
      const isInitial =
        options.resetUi === true ||
        isJobChanged ||
        (eventsOffsetRef.current === 0 && currentEvents.length === 0);

      if (isInitial) {
        // A new job must not inherit a modal subject or its telemetry query.
        activeModalSubjectFileRef.current = null;
        eventsOffsetRef.current = 0;
        logOffsetRef.current = 0;
        setIsLoadingDetails(true);
        setJobEvents([]);
        setOutputText('');
        setDetailsNotice(null);
        setActiveModalSubjectFile(null);
      }

      if (!targetJob) {
        const jobs = (useJobsStore.getState().latestJobs || []) as Record<string, unknown>[];
        targetJob = (jobs.find((j) => j && matchesJobId((j as {job_id?: string}).job_id, jobId)) as Record<string, unknown> | undefined) || null;
      }

      const isRemote =
        String(targetJob?.target || '').toLowerCase() === 'server' ||
        (!targetJob && (useRemoteStore.getState().connected || formValues.runtimeTarget === 'Server'));

      // Fail fast while a channel is down: don't hang the detail view on a
      // request that is known to fail. Manual retries pass `force: true`.
      if (!options.force) {
        const health = useRemoteStore.getState();
        if (health.backendStatus === 'down') {
          if (seq === reqSeqRef.current) {
            if (isInitial) {
              setJobEvents([]);
              setOutputText('');
            }
            setDetailsNotice({
              type: 'error',
              message: 'Cannot load job details: the local backend is unreachable. Retry once it is running again.',
            });
            setIsLoadingDetails(false);
          }
          return;
        }
        if (isRemote && health.sshStatus === 'disconnected') {
          if (seq === reqSeqRef.current) {
            if (isInitial) {
              setJobEvents([]);
              setOutputText('');
            }
            setDetailsNotice({
              type: 'error',
              message:
                'Cannot load server job details: the SSH connection is down. Reconnect from Pipeline Configuration, then retry.',
            });
            setIsLoadingDetails(false);
          }
          return;
        }
      }

      const eventOffset = isInitial ? 0 : eventsOffsetRef.current;
      const logOffset = isInitial ? 0 : logOffsetRef.current;
      const shouldFetchLog = Boolean(
        options.fetchLog || (isLogExpandedRef.current && activeModalSubjectFileRef.current),
      );
      const shouldFetchMetrics = Boolean(activeModalSubjectFileRef.current);
      const controller = new AbortController();
      detailsAbortRef.current?.abort();
      detailsAbortRef.current = controller;

      type EventsResult = {ok?: boolean; aborted?: boolean; error?: string; events?: PipelineEvent[]; next_offset?: number; events_file_found?: boolean};
      type LogResult = {ok?: boolean; text?: string; next_offset?: number};
      let newEvents: PipelineEvent[] = [];
      let newLogText = '';
      let notice: {type: 'error' | 'info'; message: string} | null = null;
      let evRes: EventsResult | null = null;

      try {
        if (isRemote) {
          const remotePayload = buildRemotePayload(formValues);
          const jobWorkspace = String(targetJob?.remote_workspace || '');
          if (jobWorkspace) remotePayload.workspace = jobWorkspace;
          const remoteJobDir = String(targetJob?.remote_job_dir || targetJob?.job_dir || jobId);
          const eventFetch = readRemoteEventsAsync({
              ...remotePayload,
              remote_job_dir: remoteJobDir,
              job_id: jobId,
              offset: eventOffset,
              limit: 10000,
              signal: controller.signal,
              timeoutMs: REMOTE_DETAIL_TIMEOUT_MS,
            })
            .catch((err: unknown) =>
              // Only the detail controller aborting means the user moved on
              // (navigation/modal close). Internal request timeouts abort a
              // different controller and must still count as failures.
              isAbortError(err) && controller.signal.aborted
                ? ({ok: false, aborted: true, events: []}) as EventsResult
                : ({ok: false, error: (err as Error).message, events: []}) as EventsResult,
            );
          const logFetch = shouldFetchLog
            ? (readRemoteLogAsync({
                  ...remotePayload,
                  remote_job_dir: remoteJobDir,
                  job_id: jobId,
                  offset: logOffset,
                  signal: controller.signal,
                  timeoutMs: REMOTE_DETAIL_TIMEOUT_MS,
                })
                .catch(() => ({text: ''})) as Promise<LogResult>)
            : Promise.resolve({text: '', next_offset: logOffset} as LogResult);
          const metricsFetch = shouldFetchMetrics
            ? (readRemoteMetricsAsync({
                  ...remotePayload,
                  remote_job_dir: remoteJobDir,
                  job_id: jobId,
                  offset: modalMetricsOffsetRef.current,
                  limit: 5000,
                  input_file: activeModalSubjectFileRef.current || '',
                  signal: controller.signal,
                  timeoutMs: REMOTE_DETAIL_TIMEOUT_MS,
                })
                .catch(() => ({events: []})) as Promise<EventsResult>)
            : Promise.resolve({events: [], next_offset: modalMetricsOffsetRef.current} as EventsResult);
          const [eventsResult, logResult, metricsResult] = await Promise.all([eventFetch, logFetch, metricsFetch]);
          evRes = eventsResult as EventsResult;
          const metRes = metricsResult as EventsResult;
          newEvents = Array.isArray(evRes?.events) ? (evRes.events as PipelineEvent[]) : [];
          newLogText = logResult?.text || '';
          const newMetrics = Array.isArray(metRes?.events) ? (metRes.events as PipelineEvent[]) : [];
          if (newMetrics.length > 0) {
            setModalMetricsEvents((prev) => [...prev, ...newMetrics]);
          }
          if (typeof metRes?.next_offset === 'number' && metRes.next_offset > 0) {
            modalMetricsOffsetRef.current = metRes.next_offset;
          }
          if (typeof evRes?.next_offset === 'number' && evRes.next_offset > 0) {
            eventsOffsetRef.current = evRes.next_offset;
          }
          if (typeof logResult?.next_offset === 'number' && logResult.next_offset > 0) {
            logOffsetRef.current = logResult.next_offset;
          }
          if (evRes?.ok === false && evRes?.error) {
            // Connection breakdowns stay silent here: the global status line
            // above the footer already warns, and stale data stays on screen.
            // Only app-level errors (unknown job, ...) get an inline notice.
            notice =
              isSshConnectionMessage(evRes.error) || isBackendUnreachableMessage(evRes.error)
                ? null
                : {type: 'error', message: evRes.error};
          } else if (isInitial && newEvents.length === 0 && evRes?.events_file_found === false) {
            notice = {type: 'info', message: 'No metric data recorded for this job (events.jsonl not found on the server).'};
          }
        } else {
          const eventFetch = readEventsAsync({jobId, offset: eventOffset, limit: 100000, signal: controller.signal})
            .catch((err: unknown) =>
              isAbortError(err) && controller.signal.aborted
                ? ({ok: false, aborted: true, events: []}) as EventsResult
                : ({ok: false, error: (err as Error).message, events: []}) as EventsResult,
            );
          const logFetch = shouldFetchLog
            ? (readLogAsync({jobId, offset: logOffset, maxBytes: 65536, signal: controller.signal})
                .catch(() => ({text: ''})) as Promise<LogResult>)
            : Promise.resolve({text: '', next_offset: logOffset} as LogResult);
          const metricsFetch = shouldFetchMetrics
            ? (readLocalMetricsAsync({
                  jobId,
                  offset: modalMetricsOffsetRef.current,
                  limit: 5000,
                  inputFile: activeModalSubjectFileRef.current || '',
                  signal: controller.signal,
                })
                .catch(() => ({events: []})) as Promise<EventsResult>)
            : Promise.resolve({events: [], next_offset: modalMetricsOffsetRef.current} as EventsResult);
          const [eventsResult, logResult, metricsResult] = await Promise.all([eventFetch, logFetch, metricsFetch]);
          evRes = eventsResult as EventsResult;
          const metRes = metricsResult as EventsResult;
          newEvents = Array.isArray(evRes?.events) ? (evRes.events as PipelineEvent[]) : [];
          newLogText = logResult?.text || '';
          const newMetrics = Array.isArray(metRes?.events) ? (metRes.events as PipelineEvent[]) : [];
          if (newMetrics.length > 0) {
            setModalMetricsEvents((prev) => [...prev, ...newMetrics]);
          }
          if (typeof metRes?.next_offset === 'number' && metRes.next_offset > 0) {
            modalMetricsOffsetRef.current = metRes.next_offset;
          }
          if (typeof evRes?.next_offset === 'number' && evRes.next_offset > 0) {
            eventsOffsetRef.current = evRes.next_offset;
          }
          if (typeof logResult?.next_offset === 'number' && logResult.next_offset > 0) {
            logOffsetRef.current = logResult.next_offset;
          }
          if (evRes?.ok === false && evRes?.error) {
            notice =
              isBackendUnreachableMessage(evRes.error)
                ? null
                : {type: 'error', message: evRes.error};
          } else if (isInitial && newEvents.length === 0 && evRes?.events_file_found === false) {
            notice = {type: 'info', message: 'No metric data recorded for this job (events.jsonl not found).'};
          }
        }
        if (seq !== reqSeqRef.current) return;
        // Feed channel health from the main events fetch so a terminal detail
        // view (whose list auto-poll is paused) still goes stale when its
        // channel drops. Aborts, superseded requests, and app-level errors
        // (unknown job, ...) never touch the counters. refreshJobs passes
        // trackHealth: false for its internal reload to avoid counting one
        // round twice (list + detail).
        if (options.trackHealth !== false && !controller.signal.aborted) {
          const conn = useRemoteStore.getState();
          if (isRemote && conn.connected) {
            if (evRes?.ok === true) conn.reportSshSuccess();
            else if (evRes?.aborted !== true && evRes?.error && isSshConnectionMessage(evRes.error)) {
              conn.reportSshFailure(evRes.error);
            }
          } else if (!isRemote) {
            if (evRes?.ok === true) conn.reportBackendSuccess();
            else if (evRes?.aborted !== true && evRes?.error && isBackendUnreachableMessage(evRes.error)) {
              conn.reportBackendFailure(evRes.error);
            }
          }
        }
      } finally {
        if (detailsAbortRef.current === controller) detailsAbortRef.current = null;
        if (seq === reqSeqRef.current) {
          lastSyncedAtRef.current = Date.now();
          if (isInitial) {
            setJobEvents(newEvents);
            setOutputText(newLogText ? capLogLines(newLogText) : '');
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
      readEventsAsync,
      readLocalMetricsAsync,
      readLogAsync,
      readRemoteEventsAsync,
      readRemoteMetricsAsync,
      readRemoteLogAsync,
      setJobEvents,
      setOutputText,
    ],
  );

  // Idempotency key for the modal fetch below. Even with stable callback
  // identities, any unrelated rerender must not restart the telemetry
  // download for the already-open subject.
  const modalFetchKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (activeModalSubjectFile && (selectedJobId || urlJobId)) {
      const jId = selectedJobId || urlJobId || null;
      const fetchKey = `${jId}::${activeModalSubjectFile}`;
      if (modalFetchKeyRef.current === fetchKey) return;
      modalFetchKeyRef.current = fetchKey;
      void loadJobDetails(jId);
    } else {
      modalFetchKeyRef.current = null;
    }
  }, [activeModalSubjectFile, selectedJobId, urlJobId, loadJobDetails]);

  // Refresh both channels and track their health independently.
  // - Backend channel: proven alive by a local-jobs request that gets a
  //   usable HTTP response. Only transport-level throws count as failures;
  //   an `{ok: false}` payload means the backend answered, so the channel
  //   itself is fine (and the last good list is kept, not wiped).
  // - SSH channel: counted only while the user is connected. Any throw
  //   counts (local already proved the backend is up in this round), plus
  //   `{ok: false}` payloads with connection-like errors (backend-reported
  //   "SSH ..." failures). Other app errors leave the counters alone.
  // While a leg is down it is skipped unless this is a manual retry
  // (`force: true`). Failed/skipped legs keep their previous jobs so the
  // status line describes genuinely stale data instead of an emptied list.
  // The warning appears on the first consecutive failure (MAX = 1).
  // Manual retries get an immediate toast so the user is never left staring
  // at a spinner; automatic polling stays silent.
  const refreshJobs = useCallback(
    async (options: {force?: boolean} = {}) => {
      const force = options.force === true;
      const health = () => useRemoteStore.getState();
      setBusyKey('refreshJobs', true);
      try {
        const prevJobs = (useJobsStore.getState().latestJobs || []) as Record<string, unknown>[];
        const prevLocalJobs = prevJobs.filter((j) => String(j?.target || 'Local') !== 'Server');
        const prevServerJobs = prevJobs.filter((j) => String(j?.target || 'Local') === 'Server');
        let freshLocalJobs: Record<string, unknown>[] | null = null;
        let freshRemoteJobs: Record<string, unknown>[] | null = null;

        let backendOkThisRound = health().backendStatus !== 'down' || force;
        try {
          const localRes = await listLocalJobsAsync();
          if (localRes && localRes.ok === false) {
            print('Refresh local jobs failed', {error: localRes.error || 'Unknown error'});
          } else {
            const rawJobs = Array.isArray(localRes?.jobs) ? (localRes.jobs as unknown[]) : [];
            freshLocalJobs = rawJobs.map((j) => normalizeJob(j as Record<string, unknown>, 'Local'));
          }
          health().reportBackendSuccess();
          backendOkThisRound = true;
        } catch (err: unknown) {
          const message = (err as Error)?.message || 'Backend request failed.';
          print('Refresh jobs failed', {error: message});
          if (isBackendUnreachableMessage(message)) {
            health().reportBackendFailure(message);
            backendOkThisRound = false;
            if (force) {
              toast.error('Cannot reach the local backend.');
            }
          } else {
            // The backend answered but the payload was unusable: the channel
            // itself is alive, so don't trip the offline warning.
            health().reportBackendSuccess();
            backendOkThisRound = true;
          }
        }

        const {connected, sshStatus: currentSsh} = health();
        if (connected && backendOkThisRound && (currentSsh !== 'disconnected' || force)) {
          try {
            const remoteRes = await listRemoteJobsAsync({
              ...buildRemotePayload(formValues),
              timeoutMs: REMOTE_JOBS_TIMEOUT_MS,
            });
            if (remoteRes.ok === false) {
              const message = remoteRes.error || 'Server jobs request failed.';
              print('Refresh server jobs failed', {error: message});
              if (isSshConnectionMessage(message)) {
                health().reportSshFailure(message);
                if (force) {
                  toast.error('Cannot reach the server.');
                }
              }
            } else {
              freshRemoteJobs = (Array.isArray(remoteRes.jobs) ? remoteRes.jobs : []).map((j) =>
                normalizeJob(j as Record<string, unknown>, 'Server'),
              );
              health().reportSshSuccess();
            }
          } catch (err: unknown) {
            const message = (err as Error)?.message || 'Server jobs request failed.';
            health().reportSshFailure(message);
            print('Refresh server jobs failed', {error: message});
            if (force) {
              toast.error('Cannot reach the server.');
            }
          }
        }
        const jobs = sortJobsByStartedAtDesc([
          ...((freshLocalJobs ?? prevLocalJobs) as Record<string, unknown>[]),
          ...((freshRemoteJobs ?? prevServerJobs) as Record<string, unknown>[]),
        ] as Record<string, unknown>[]);
        setLatestJobs(jobs as Record<string, unknown>[]);

        if (urlJobId || selectedJobId) {
          const targetId = urlJobId || selectedJobId;
          const currentJob = jobs.find((j) => matchesJobId((j as {job_id?: string}).job_id, targetId));
          if (currentJob) {
            const st = health();
            const targetIsServer =
              String((currentJob as {target?: unknown}).target || 'Local') === 'Server';
            const channelDown =
              st.backendStatus === 'down' || (targetIsServer && st.sshStatus === 'disconnected');
            if (!channelDown) {
              // trackHealth: false — the list leg already counted this round.
              await loadJobDetails(targetId, currentJob as Record<string, unknown>, {
                force,
                trackHealth: false,
              });
            } else if (!force) {
              // Fail-fast path only: surfaces the stale-data notice without
              // hanging on a request that is known to fail.
              await loadJobDetails(targetId, currentJob as Record<string, unknown>);
            }
            // Manual retry while still down: skip the detail fetch entirely.
            // The banner + toast already explain; stale data stays on screen.
          }
        }
      } catch (err: unknown) {
        print('Refresh jobs failed', {error: (err as Error).message});
      } finally {
        setHasLoadedInitialJobs(true);
        setBusyKey('refreshJobs', false);
      }
    },
    [
      formValues,
      listLocalJobsAsync,
      listRemoteJobsAsync,
      loadJobDetails,
      selectedJobId,
      setBusyKey,
      setHasLoadedInitialJobs,
      setLatestJobs,
      urlJobId,
      print,
    ],
  );

  const isServerTarget = (targetJob: Record<string, unknown>) =>
    String(targetJob?.target || 'Local') === 'Server';

  const actionBlockedReason = (serverJob: boolean): string | null => {
    const st = useRemoteStore.getState();
    if (st.backendStatus === 'down') return localActionsBlockedReason;
    if (serverJob && st.sshStatus === 'disconnected') return serverActionsBlockedReason;
    return null;
  };

  const handleDeleteJob = (targetJob: Record<string, unknown>) => {
    const jobId = String(targetJob.job_id || '');
    if (!jobId || normalizeJobState(targetJob.state) === 'running') return;
    const blocked = actionBlockedReason(isServerTarget(targetJob));
    if (blocked) {
      toast.error(blocked);
      return;
    }
    setJobToDelete(targetJob);
  };

  const handleConfirmDeleteJob = async () => {
    if (!jobToDelete) return;
    const jobId = String(jobToDelete.job_id || '');
    if (!jobId) return;
    const blocked = actionBlockedReason(isServerTarget(jobToDelete));
    if (blocked) {
      print('Delete job blocked', {error: blocked});
      toast.error(blocked);
      setJobToDelete(null);
      return;
    }

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
      if (matchesJobId(selectedJobId, jobId)) {
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
    const blocked = actionBlockedReason(isServerJob);
    if (blocked) {
      toast.error(blocked);
      return;
    }
    setShowStopConfirm(true);
  };

  const handleConfirmStopJob = async () => {
    if (!job || normState !== 'running' || isTerminal || stoppingJob) return;
    const blocked = actionBlockedReason(isServerJob);
    if (blocked) {
      print('Stop job blocked', {error: blocked});
      toast.error(blocked);
      setShowStopConfirm(false);
      return;
    }
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
      if (!matchesJobId(urlJobId, selectedJobId)) {
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
    if (matchesJobId(prevSelectedJobIdRef.current, selectedJobId)) {
      return;
    }
    prevSelectedJobIdRef.current = selectedJobId;

    if (selectedJobId) {
      const jobs = (useJobsStore.getState().latestJobs || []) as Record<string, unknown>[];
      const jobObj = jobs.find((j) => j && matchesJobId((j as {job_id?: string}).job_id, selectedJobId)) as
        Record<string, unknown> | undefined;
      queueMicrotask(() => {
        void loadJobDetails(selectedJobId, jobObj, {resetUi: true});
      });
    } else {
      queueMicrotask(() => {
        setJobEvents([]);
        setOutputText('Log stream is idle.');
        closeSubjectModal();
        setIsLoadingDetails(false);
      });
    }
  }, [closeSubjectModal, selectedJobId, loadJobDetails, setJobEvents, setOutputText]);

  // Initial mount auto-refresh if empty
  useEffect(() => {
    if (hasInitialRefreshed.current) return;
    hasInitialRefreshed.current = true;
    const jobs = Array.isArray(latestJobs) ? latestJobs : [];
    if (jobs.length === 0) {
      void refreshJobs();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keyboard Escape listener to close subject modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeSubjectModal();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [closeSubjectModal]);

  const jobsList = Array.isArray(latestJobs) ? latestJobs : [];
  const rawJob = React.useMemo(
    () => jobsList.find((j) => j && matchesJobId((j as {job_id?: string}).job_id, selectedJobId)) || null,
    [jobsList, selectedJobId],
  );
  const job = rawJob as Record<string, unknown> | null;
  const stateStr = (job?.state as string) || 'unknown';
  const normState = normalizeJobState(stateStr);
  const isServerJob = String(job?.target || 'Local') === 'Server';

  const safeEvents = Array.isArray(jobEvents) ? jobEvents : [];
  const batchImages = React.useMemo(() => deriveBatchImages(safeEvents, job || {}), [safeEvents, job]);
  const batchSummary = React.useMemo(() => deriveBatchSummary(batchImages), [batchImages]);
  const displayMeta = React.useMemo(() => deriveJobDisplayMetadata(job, safeEvents, batchImages), [job, safeEvents, batchImages]);
  const isTerminal = ['completed', 'failed', 'stopped'].includes(displayMeta.status_reconciled);

  useEffect(() => {
    if (isLogExpanded && selectedJobId) {
      void loadJobDetails(selectedJobId, null, {fetchLog: true});
    }
  }, [isLogExpanded, selectedJobId, loadJobDetails]);

  // Adaptive polling:
  // - If looking at a running job: poll every 30s with lightweight delta fetch
  // - If looking at a terminal job: do not poll (paused)
  // - If on jobs list: poll every 20s
  // - If the backend is down: pause entirely. The status-line Retry is the
  //   manual path (no auto-reconnect). SSH-down still polls Local jobs; the
  //   remote leg is skipped inside refreshJobs until a manual retry.
  // Ticks never overlap: a tick while a refresh is in flight is skipped.
  useEffect(() => {
    if (backendDown) {
      return;
    }
    if (selectedJobId && isTerminal) {
      return;
    }
    const pollDelay = selectedJobId && normState === 'running' ? 30_000 : 20_000;
    const interval = setInterval(() => {
      if (useUiStore.getState().busy.refreshJobs) return;
      void refreshJobs();
    }, pollDelay);
    return () => clearInterval(interval);
  }, [refreshJobs, selectedJobId, isTerminal, normState, backendDown]);

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
  const stageOrder = metadata?.stage_order || DEFAULT_STAGE_ORDER;
  const stageLabels = React.useMemo(() => {
    const labels: Record<string, string> = {...DEFAULT_STAGE_LABELS};
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
      const blocked = actionBlockedReason(true);
      if (blocked) {
        toast.error(blocked);
        return;
      }
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
    } else {
      const effDir = String(displayMeta.output_dir_str);
      const subDir = String(job?.download_subdir || '');
      const fullPath = subDir && subDir !== 'N/A' ? `${effDir}/${subDir}` : effDir;
      print('Download Outputs', {ok: true, output_path: fullPath, target: 'Local'});
    }
  };

  const handleBrowseDownloadDir = async () => {
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
    const blocked = actionBlockedReason(true);
    if (blocked) {
      setDownloadPhase('failed');
      setDownloadError(blocked);
      return;
    }

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

  const modalEvents = React.useMemo(() => {
    const lifecycleEvents = safeEvents.filter((event) => event.kind !== 'metrics');
    if (modalMetricsEvents.length === 0) return lifecycleEvents;
    return [...lifecycleEvents, ...modalMetricsEvents];
  }, [safeEvents, modalMetricsEvents]);

  const modalImageSteps = React.useMemo(() => {
    return modalSubject
      ? deriveImageSteps(modalEvents, modalSubject, selectedTools, stageOrder, stageLabels)
      : [];
  }, [modalEvents, modalSubject, selectedTools, stageOrder, stageLabels]);

  const modalMetricsSeries = React.useMemo(() => {
    return modalSubject
      ? deriveMetricsSeries(modalEvents, modalSubject)
      : {cpuSeries: [], ramSeries: [], latestContainer: ''};
  }, [modalEvents, modalSubject]);

  const subjectStageInfoMap = React.useMemo(() => {
    const map = new Map<
      string,
      {
        label: string;
        status: 'running' | 'success' | 'failed' | 'stopped' | 'pending';
        isBeforeStart?: boolean;
      }
    >();

    for (const img of batchImages) {
      const steps = deriveImageSteps(safeEvents, img, selectedTools, stageOrder, stageLabels);
      map.set(img.input_file, deriveSubjectStageInfo(img, steps));
    }
    return map;
  }, [batchImages, safeEvents, selectedTools, stageOrder, stageLabels]);

  const getSubjectStageInfo = (img: (typeof batchImages)[0]) => {
    return (
      subjectStageInfoMap.get(img.input_file) || {
        label: 'Processing...',
        status: 'pending' as const,
      }
    );
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
          onRefresh={() => void refreshJobs({force: true})}
          isRefreshing={busy.refreshJobs}
          isInitialLoading={(!hasLoadedInitialJobs || busy.refreshJobs) && jobsList.length === 0}
          onDeleteJob={handleDeleteJob}
          deletingJobId={deletingJobId}
          serverActionsBlocked={serverActionsBlocked}
          localActionsBlocked={localActionsBlocked}
          serverActionsBlockedReason={serverActionsBlockedReason}
          localActionsBlockedReason={localActionsBlockedReason}
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

  const stopBlockedReason = actionBlockedReason(isServerJob);
  const serverDownloadBlockedReason = isServerJob ? actionBlockedReason(true) : null;

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col gap-4 overflow-hidden text-cursor-ink p-6">
      {/* 0. Top Bar: Back Button + Status Badge + Job Title */}
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
          <div className="flex flex-wrap items-center justify-between gap-2.5 flex-none">
            <div className="flex items-center gap-2.5 min-w-0 flex-1">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  closeSubjectModal();
                  setSelectedJobId(null);
                  navigate('/jobs');
                }}
                className="h-7.5 px-2.5 text-xs font-semibold text-cursor-ink border-cursor-hairline bg-cursor-surface-card hover:bg-cursor-canvas-soft flex-none cursor-pointer"
                aria-label="Back to Jobs"
              >
                <ArrowLeft className="h-3.5 w-3.5 mr-1 text-cursor-body" />
                Back to Jobs
              </Button>
              <Badge
                variant={
                  displayMeta.status_reconciled === 'completed'
                    ? 'success'
                    : displayMeta.status_reconciled === 'running'
                      ? 'primary'
                      : displayMeta.status_reconciled === 'failed'
                        ? 'error'
                        : displayMeta.status_reconciled === 'stopped'
                          ? 'warning'
                          : 'secondary'
                }
                className="flex-none gap-1.5 px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.06em]"
              >
                <StatusDotLarge state={displayMeta.status_reconciled} className="h-2 w-2" />
                {displayJobState(displayMeta.status_reconciled)}
              </Badge>
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

      {/* 1. Top Grid: Jobs Metadata (Left) + Batch Summary (Right) */}
      <div className="grid flex-none grid-cols-[minmax(0,1fr)_minmax(18rem,24rem)] items-stretch gap-3">
        {/* Left: Jobs Metadata Card */}
        <Card className="rounded-lg border-cursor-hairline bg-cursor-surface-card shadow-none p-3.5 flex flex-col">
          <div className="flex items-center justify-between pb-2 border-b border-cursor-hairline-soft mb-2.5">
            <div className="flex items-center gap-1.5 min-w-0">
              <BrainCircuit className="h-4 w-4 text-cursor-primary flex-none" />
              <CardTitle className="font-semibold text-base text-cursor-ink">Job Metadata</CardTitle>
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
              <div className="mt-2.5 flex flex-1 flex-col overflow-hidden rounded-md border border-cursor-hairline bg-cursor-surface-card">
                <table className="w-full flex-1 h-full text-xs divide-y divide-cursor-hairline-soft table-fixed border-collapse">
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
                      <td className="py-1.5 px-2.5 text-cursor-body">{String(job?.pid || 'None')}</td>
                      <td className="w-24 md:w-28 py-1.5 px-2.5 font-medium text-cursor-ink bg-cursor-canvas-soft whitespace-nowrap">
                        Scheduler
                      </td>
                      <td className="py-1.5 px-2.5 text-cursor-body min-w-0">
                        <div className="flex items-center gap-1.5 flex-wrap min-w-0">
                          <span className="font-semibold text-cursor-ink truncate">{schedulerDisplay}</span>
                          {neuroflowEnabled && !isCustomMode && (
                            <Badge
                              variant="primary"
                              className="gap-1 px-1.5 py-0.25 text-2xs font-semibold flex-none"
                              title={schedulerDetails}
                            >
                              <Zap className="h-3 w-3" />
                              {maxConcurrent} tasks
                            </Badge>
                          )}
                        </div>
                      </td>
                    </tr>

                    {/* Row 3: Mode / Device & Threads */}
                    <tr className="divide-x divide-cursor-hairline-soft">
                      <td className="w-24 md:w-28 py-1.5 px-2.5 font-medium text-cursor-ink bg-cursor-canvas-soft whitespace-nowrap">
                        Mode / Device
                      </td>
                      <td className="py-1.5 px-2.5 text-cursor-body whitespace-nowrap">
                        {String(reqSummary.mode || 'N/A')} / {String(reqSummary.device || 'cpu')}
                      </td>
                      <td className="w-24 md:w-28 py-1.5 px-2.5 font-medium text-cursor-ink bg-cursor-canvas-soft whitespace-nowrap">
                        Threads
                      </td>
                      <td className="py-1.5 px-2.5 text-cursor-body whitespace-nowrap">
                        {String(reqSummary.threads || 4)} threads
                      </td>
                    </tr>

                    {/* Row 4: Container & RAM */}
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
                        RAM
                      </td>
                      <td className="py-1.5 px-2.5 text-cursor-body whitespace-nowrap">
                        {String(reqSummary.ram_percent || 100)}% RAM
                      </td>
                    </tr>

                    {/* Row 5: Input Path & Output Path */}
                    <tr className="divide-x divide-cursor-hairline-soft">
                      <td className="w-24 md:w-28 py-1.5 px-2.5 font-medium text-cursor-ink bg-cursor-canvas-soft whitespace-nowrap">
                        Input Path
                      </td>
                      <td className="py-1.5 px-2.5 text-cursor-body min-w-0">
                        <div className="flex items-center justify-between gap-1.5 min-w-0 w-full">
                          <span
                            className="text-xs text-cursor-body truncate flex-1"
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
                      <td className="w-24 md:w-28 py-1.5 px-2.5 font-medium text-cursor-ink bg-cursor-canvas-soft whitespace-nowrap">
                        Output Path
                      </td>
                      <td className="py-1.5 px-2.5 text-cursor-body min-w-0">
                        <div className="flex items-center justify-between gap-1.5 min-w-0 w-full">
                          <span
                            className="text-xs text-cursor-body truncate flex-1"
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
                    <span className="font-semibold text-cursor-ink">{batchSummary.success}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="h-2.5 w-2.5 rounded-full bg-cursor-semantic-error flex-none" />
                      <span className="text-cursor-ink text-xs font-medium">Failed</span>
                    </div>
                    <span className="font-semibold text-cursor-ink">{batchSummary.failed}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="h-2.5 w-2.5 rounded-full bg-cursor-semantic-warn flex-none" />
                      <span className="text-cursor-ink text-xs font-medium">Stopped</span>
                    </div>
                    <span className="font-semibold text-cursor-ink">{batchSummary.stopped ?? batchSummary.interrupted ?? 0}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="h-2.5 w-2.5 rounded-full bg-cursor-primary flex-none" />
                      <span className="text-cursor-ink text-xs font-medium">Running</span>
                    </div>
                    <span className="font-semibold text-cursor-ink">{batchSummary.running}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="h-2.5 w-2.5 rounded-full bg-cursor-hairline-strong flex-none" />
                      <span className="text-cursor-muted text-xs font-medium">Pending</span>
                    </div>
                    <span className="font-semibold text-cursor-muted">{batchSummary.pending}</span>
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
                  disabled={downloadRunning || (isServerJob && serverDownloadBlockedReason !== null)}
                  title={isServerJob ? serverDownloadBlockedReason || undefined : undefined}
                  className="w-full h-8 bg-cursor-primary hover:bg-cursor-primary-active text-white font-medium text-xs shadow-none cursor-pointer"
                >
                  <Download className="h-3.5 w-3.5 mr-1.5" /> Download Outputs
                </Button>
              ) : (
                <Button
                  id="refreshJobsButton"
                  variant="default"
                  onClick={() => void refreshJobs({force: true})}
                  disabled={busy.refreshJobs}
                  className="w-full h-8 bg-cursor-primary hover:bg-cursor-primary-active text-white font-medium text-xs shadow-none cursor-pointer"
                >
                  {busy.refreshJobs ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> Refreshing...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Refresh Job
                    </>
                  )}
                </Button>
              )}

              {(!isTerminal || displayMeta.status_reconciled !== 'completed') && (
                <Button
                  onClick={handleStopJob}
                  disabled={!job || normState !== 'running' || isTerminal || stoppingJob || stopBlockedReason !== null}
                  title={stopBlockedReason || undefined}
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
                  onClick={() => void refreshJobs({force: true})}
                  disabled={busy.refreshJobs}
                  className="w-full h-8 border-cursor-hairline text-cursor-ink bg-cursor-surface-card hover:bg-cursor-canvas-soft font-medium text-xs cursor-pointer"
                >
                  {busy.refreshJobs ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> Refreshing...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Refresh Job
                    </>
                  )}
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  onClick={handleDownloadClick}
                  disabled={!job || !isTerminal || downloadRunning || (isServerJob && serverDownloadBlockedReason !== null)}
                  title={isServerJob ? serverDownloadBlockedReason || undefined : undefined}
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
            {/* Job Data Notice: info only (e.g. no metric file). Error/warning
                lines are intentionally never shown here — connection problems
                already surface in the global status line above the footer. */}
            {detailsNotice?.type === 'info' && (
              <div className="mb-2.5 flex-none rounded-md border border-cursor-hairline bg-cursor-canvas-soft px-3 py-2 text-xs leading-relaxed text-cursor-body">
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
                  className="w-full rounded-md border border-cursor-hairline bg-cursor-surface-card px-2.5 py-1 pr-8 text-xs text-cursor-ink placeholder:text-cursor-muted-soft outline-none focus:border-cursor-hairline-strong focus:ring-1 focus:ring-cursor-primary/30 h-8"
                />
                <Search className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-cursor-muted" />
              </label>
              <div className="hidden sm:block h-4 w-px bg-cursor-hairline flex-none" />
              <div className="flex flex-wrap items-center gap-1.5">
                {(['all', 'success', 'running', 'stopped', 'failed', 'pending'] as const).map((st) => {
                  const label =
                    st === 'all'
                      ? 'ALL'
                      : st === 'success'
                        ? 'SUCCESS'
                        : st === 'running'
                          ? 'RUNNING'
                          : st === 'stopped'
                            ? 'STOPPED'
                            : st === 'failed'
                              ? 'FAILED'
                              : 'PENDING';

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

                  const isSelected = subjectStatusFilter === st;

                  // Compute semantic badge styling for each filter
                  let filterStyle = 'border border-cursor-hairline bg-cursor-surface-card text-cursor-ink hover:bg-cursor-canvas-soft';
                  if (st === 'all') {
                    filterStyle = isSelected
                      ? 'border-cursor-hairline-strong bg-cursor-canvas text-cursor-ink font-semibold ring-1 ring-cursor-ink/20'
                      : 'border-cursor-hairline bg-cursor-surface-card text-cursor-body hover:text-cursor-ink hover:bg-cursor-canvas-soft';
                  } else if (st === 'success') {
                    filterStyle = isSelected
                      ? 'border-cursor-semantic-success/30 bg-cursor-semantic-success/15 text-cursor-semantic-success font-semibold ring-1 ring-cursor-semantic-success/30'
                      : 'border-cursor-semantic-success/20 bg-cursor-semantic-success/5 text-cursor-semantic-success hover:bg-cursor-semantic-success/10';
                  } else if (st === 'running') {
                    filterStyle = isSelected
                      ? 'border-cursor-primary/30 bg-cursor-primary/15 text-cursor-primary font-semibold ring-1 ring-cursor-primary/30'
                      : 'border-cursor-primary/20 bg-cursor-primary/5 text-cursor-primary hover:bg-cursor-primary/10';
                  } else if (st === 'stopped') {
                    filterStyle = isSelected
                      ? 'border-cursor-semantic-warn/30 bg-cursor-semantic-warn/15 text-cursor-semantic-warn font-semibold ring-1 ring-cursor-semantic-warn/30'
                      : 'border-cursor-semantic-warn/20 bg-cursor-semantic-warn/5 text-cursor-semantic-warn hover:bg-cursor-semantic-warn/10';
                  } else if (st === 'failed') {
                    filterStyle = isSelected
                      ? 'border-cursor-semantic-error/30 bg-cursor-semantic-error/15 text-cursor-semantic-error font-semibold ring-1 ring-cursor-semantic-error/30'
                      : 'border-cursor-semantic-error/20 bg-cursor-semantic-error/5 text-cursor-semantic-error hover:bg-cursor-semantic-error/10';
                  } else if (st === 'pending') {
                    filterStyle = isSelected
                      ? 'border-cursor-hairline-strong bg-cursor-surface-strong/80 text-cursor-ink font-semibold ring-1 ring-cursor-ink/20'
                      : 'border-cursor-hairline bg-cursor-canvas-soft text-cursor-muted hover:text-cursor-ink hover:bg-cursor-surface-strong/50';
                  }

                  return (
                    <button
                      key={st}
                      type="button"
                      onClick={() => setSubjectStatusFilter(st)}
                      className={`inline-flex items-center rounded px-2.5 py-1 text-xs font-medium cursor-pointer ${filterStyle}`}
                    >
                      <span>
                        {label} ({count})
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Subject Grid or List */}
            {isLoadingDetails && safeEvents.length === 0 ? (
              <div className="flex min-h-[14rem] flex-1 flex-col items-center justify-center rounded-lg border border-cursor-hairline bg-cursor-surface-card p-6 text-center">
                <Loader2 className="h-7 w-7 animate-spin text-cursor-primary mb-2" />
                <p className="m-0 text-xs text-cursor-muted">Loading batch subjects...</p>
              </div>
            ) : subjectViewMode === 'grid' ? (
              <div className="grid grid-cols-[repeat(auto-fill,minmax(18rem,1fr))] content-start gap-3 overflow-y-auto flex-1 min-h-0 p-0.5">
                {(() => {
                  if (filteredBatchImages.length === 0) {
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
                    const stageInfo = getSubjectStageInfo(img);
                    const statusVariant =
                      img.status === 'success'
                        ? 'success'
                        : img.status === 'failed'
                          ? 'error'
                          : img.status === 'stopped' || (img.status as string) === 'interrupted'
                            ? 'warning'
                            : img.status === 'running'
                              ? 'primary'
                              : 'secondary';

                    const dotClass =
                      stageInfo.status === 'success'
                        ? 'bg-cursor-semantic-success ring-2 ring-cursor-semantic-success/20'
                        : stageInfo.status === 'running'
                          ? 'bg-cursor-primary animate-pulse ring-4 ring-cursor-primary/20'
                          : stageInfo.status === 'failed'
                            ? 'bg-cursor-semantic-error ring-2 ring-cursor-semantic-error/20'
                            : stageInfo.status === 'stopped'
                              ? stageInfo.isBeforeStart
                                ? 'bg-cursor-muted/40'
                                : 'bg-cursor-semantic-warn ring-2 ring-cursor-semantic-warn/20'
                              : 'bg-cursor-surface-card border border-cursor-muted-soft';

                    const textClass =
                      stageInfo.status === 'running'
                        ? 'text-cursor-primary font-semibold'
                        : stageInfo.status === 'success'
                          ? 'text-cursor-semantic-success font-medium'
                          : stageInfo.status === 'failed'
                            ? 'text-cursor-semantic-error font-medium'
                            : stageInfo.status === 'stopped'
                              ? stageInfo.isBeforeStart
                                ? 'text-cursor-muted italic'
                                : 'text-cursor-semantic-warn font-medium'
                              : 'text-cursor-muted font-medium';

                    return (
                      <button
                        key={img.input_file}
                        type="button"
                        onClick={() => setActiveModalSubjectFile(img.input_file)}
                        className="group flex cursor-pointer flex-col justify-between rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3.5 text-left hover:border-cursor-primary hover:bg-cursor-canvas-soft hover:shadow-xs focus:outline-none focus:ring-1 focus:ring-cursor-primary/30 min-h-[100px]"
                      >
                        {/* Card Header: Index Text & Status Badge */}
                        <div className="flex items-center justify-between gap-2 min-w-0">
                          <span className="text-xs font-semibold text-cursor-muted tracking-tight">
                            #{String(img.idx).padStart(3, '0')}
                          </span>
                          <Badge variant={statusVariant} className="flex-none">
                            {img.status === 'success' ? 'SUCCESS' : (img.status === 'stopped' || (img.status as string) === 'interrupted') ? 'STOPPED' : img.status.toUpperCase()}
                          </Badge>
                        </div>

                        {/* Card Body: Subject ID with max 2 lines */}
                        <div className="my-2 min-w-0">
                          <h4
                            className="text-xs font-bold leading-snug text-cursor-ink group-hover:text-cursor-primary line-clamp-2 break-all"
                            title={img.subject_id}
                          >
                            {img.subject_id}
                          </h4>
                        </div>

                        {/* Card Footer: Text-Only Current Step with Status Color + Circular Dot */}
                        <div className="pt-2 border-t border-cursor-hairline-soft w-full min-w-0 flex items-center justify-between text-xs">
                          <div
                            className={`flex items-center gap-1.5 min-w-0 flex-1 ${textClass}`}
                            title={stageInfo.label}
                          >
                            <span className="flex h-3.5 w-3.5 items-center justify-center flex-none">
                              <span className={`h-2 w-2 rounded-full flex-none ${dotClass}`} />
                            </span>
                            <span className="truncate">{stageInfo.label}</span>
                          </div>
                          <ChevronRight className="h-3.5 w-3.5 text-cursor-muted group-hover:text-cursor-primary flex-none ml-1" />
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
                    const stageInfo = getSubjectStageInfo(img);
                    const statusVariant =
                      img.status === 'success'
                        ? 'success'
                        : img.status === 'failed'
                          ? 'error'
                          : img.status === 'stopped' || (img.status as string) === 'interrupted'
                            ? 'warning'
                            : img.status === 'running'
                              ? 'primary'
                              : 'secondary';

                    const dotClass =
                      stageInfo.status === 'success'
                        ? 'bg-cursor-semantic-success ring-2 ring-cursor-semantic-success/20'
                        : stageInfo.status === 'running'
                          ? 'bg-cursor-primary animate-pulse ring-4 ring-cursor-primary/20'
                          : stageInfo.status === 'failed'
                            ? 'bg-cursor-semantic-error ring-2 ring-cursor-semantic-error/20'
                            : stageInfo.status === 'stopped'
                              ? stageInfo.isBeforeStart
                                ? 'bg-cursor-muted/40'
                                : 'bg-cursor-semantic-warn ring-2 ring-cursor-semantic-warn/20'
                              : 'bg-cursor-surface-card border border-cursor-muted-soft';

                    const textClass =
                      stageInfo.status === 'running'
                        ? 'text-cursor-primary font-semibold'
                        : stageInfo.status === 'success'
                          ? 'text-cursor-semantic-success font-medium'
                          : stageInfo.status === 'failed'
                            ? 'text-cursor-semantic-error font-medium'
                            : stageInfo.status === 'stopped'
                              ? stageInfo.isBeforeStart
                                ? 'text-cursor-muted italic'
                                : 'text-cursor-semantic-warn font-medium'
                              : 'text-cursor-muted font-medium';

                    return (
                      <button
                        key={img.input_file}
                        type="button"
                        onClick={() => setActiveModalSubjectFile(img.input_file)}
                        className="group flex items-center gap-3 cursor-pointer rounded-md border border-cursor-hairline bg-cursor-surface-card px-3 py-2 text-left hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft focus:outline-none focus:ring-1 focus:ring-cursor-primary/30"
                      >
                        <span className="text-xs font-semibold text-cursor-muted flex-none w-10">
                          #{String(img.idx).padStart(3, '0')}
                        </span>
                        <div className="flex flex-col min-w-0 flex-1">
                          <span className="truncate text-sm font-bold text-cursor-ink group-hover:text-cursor-primary">
                            {img.subject_id}
                          </span>
                        </div>
                        <div className="flex items-center gap-4 flex-none">
                          <div className="flex items-center gap-1.5">
                            <span className="text-3xs uppercase tracking-[0.06em] text-cursor-muted font-medium">Stage:</span>
                            <span
                              className={`inline-flex items-center gap-1.5 text-xs ${textClass}`}
                              title={stageInfo.label}
                            >
                              <span className="flex h-3.5 w-3.5 items-center justify-center flex-none">
                                <span className={`h-2 w-2 rounded-full flex-none ${dotClass}`} />
                              </span>
                              <span>{stageInfo.label}</span>
                            </span>
                          </div>
                          <Badge variant={statusVariant} className="min-w-[3.5rem] justify-center">
                            {img.status === 'success' ? 'SUCCESS' : (img.status === 'stopped' || (img.status as string) === 'interrupted') ? 'STOPPED' : img.status.toUpperCase()}
                          </Badge>
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
            onClick={() => void refreshJobs({force: true})}
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
          onClick={closeSubjectModal}
        >
          <div
            className="relative bg-cursor-canvas border border-cursor-hairline rounded-xl w-[min(1360px,calc(100vw-1.5rem))] max-h-[92vh] flex flex-col shadow-none overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header: [status badge] [#idx + subject name] */}
            <div className="flex items-center justify-between border-b border-cursor-hairline px-4 py-3 bg-cursor-canvas flex-none">
              <div className="flex items-center gap-2.5 min-w-0 flex-1 mr-3">
                <Badge
                  variant={
                    modalSubject.status === 'success'
                      ? 'success'
                      : modalSubject.status === 'failed'
                        ? 'error'
                        : modalSubject.status === 'stopped' || (modalSubject.status as string) === 'interrupted'
                          ? 'warning'
                          : modalSubject.status === 'running'
                            ? 'primary'
                            : 'secondary'
                  }
                  className="flex-none"
                >
                  {modalSubject.status === 'success'
                    ? 'SUCCESS'
                    : modalSubject.status === 'stopped' || (modalSubject.status as string) === 'interrupted'
                      ? 'STOPPED'
                      : modalSubject.status.toUpperCase()}
                </Badge>
                <div className="min-w-0 flex-1">
                  <h3
                    className="m-0 text-base font-semibold leading-tight tracking-tight text-cursor-ink truncate"
                    title={`[#${modalSubject.idx}] ${modalSubject.subject_id}`}
                  >
                    <span className="text-cursor-muted font-medium">#{modalSubject.idx}</span>{' '}
                    {modalSubject.subject_id}
                  </h3>
                </div>
              </div>
              <div className="flex items-center gap-2 flex-none">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={closeSubjectModal}
                  className="h-7 w-7 p-0 rounded text-cursor-muted hover:text-cursor-ink hover:bg-cursor-canvas-soft"
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
                  </div>
                  <div className="p-0">
                    <div className="grid grid-cols-1 gap-2.5">
                      <MetricSparkline label="CPU Usage" points={modalMetricsSeries.cpuSeries} unit="%" />
                      <MetricSparkline label="RAM Usage" points={modalMetricsSeries.ramSeries} unit="MB" />
                    </div>
                    {String(reqSummary.device || job?.device || '').toLowerCase().includes('gpu') && (
                      <div className="mt-2 text-xs text-cursor-muted rounded-md border border-cursor-hairline-soft bg-cursor-canvas-soft px-2.5 py-1.5 flex items-center justify-between">
                        <span>GPU Usage: Active</span>
                        <Badge variant="primary" className="text-2xs font-semibold uppercase tracking-[0.08em]">
                          GPU Mode
                        </Badge>
                      </div>
                    )}
                  </div>
                </div>

                {/* Operator Console Log - Collapsible and Collapsed by Default */}
                <div className="bg-cursor-surface-card border border-cursor-hairline rounded-lg p-3.5 shadow-none flex flex-col transition-all">
                  <div className="p-0 flex items-center justify-between">
                    <button
                      type="button"
                      onClick={() => setIsLogExpanded(!isLogExpanded)}
                      className="flex items-center gap-1.5 text-sm font-semibold leading-[1.3] text-cursor-ink hover:text-cursor-primary cursor-pointer bg-transparent border-none p-0"
                    >
                      <ChevronRight className={`h-4 w-4 transition-transform duration-200 ${isLogExpanded ? 'rotate-90' : ''}`} />
                      <span>Operator Console Log</span>
                    </button>
                    {!isLogExpanded ? (
                      <span className="text-2xs text-cursor-muted font-normal italic">Collapsed (click to view)</span>
                    ) : (
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setShowRawLog(!showRawLog)}
                          className="h-6 px-2 text-2xs border-cursor-hairline text-cursor-body"
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
                        <label className="relative m-0 block w-full max-w-[8rem]">
                          <input
                            type="search"
                            placeholder="Filter..."
                            value={jobLogSearch}
                            onChange={(e) => setJobLogSearch(e.target.value)}
                            className="w-full rounded-md border border-cursor-hairline bg-cursor-surface-card px-2 py-0.5 pr-6 text-2xs text-cursor-ink placeholder:text-cursor-muted-soft focus:outline-none focus:ring-1 focus:ring-cursor-primary h-6"
                          />
                          <Search className="pointer-events-none absolute right-1.5 top-1/2 h-3 w-3 -translate-y-1/2 text-cursor-muted" />
                        </label>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={clearJobLog}
                          className="h-6 px-1.5 text-2xs text-cursor-body"
                        >
                          <Eraser className="h-3 w-3 mr-1" /> Clear
                        </Button>
                      </div>
                    )}
                  </div>
                  {isLogExpanded && (
                    <div className="p-0 pt-2.5 flex-1 min-h-0 overflow-hidden">
                      <pre
                        className="h-full max-h-[18rem] min-h-[10rem] w-full overflow-auto whitespace-pre-wrap break-words rounded-md border border-cursor-hairline-soft bg-cursor-canvas-soft p-2.5 text-xs leading-relaxed text-cursor-ink font-mono"
                        aria-live="polite"
                      >
                        {filteredLog || 'Log stream is empty.'}
                      </pre>
                    </div>
                  )}
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
  const rounded = Math.round(seconds);
  if (rounded >= 60) return `${Math.floor(rounded / 60)}m ${rounded % 60}s`;
  return `${rounded}s`;
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
    <div className="flex items-center gap-1.5">
      <span className="text-cursor-muted font-normal">{label}:</span>
      <span className="font-semibold text-cursor-ink">{value}</span>
    </div>
  );
}

function LiveStepElapsed({
  elapsed_sec,
  isRunning,
  lastSyncedAt,
}: {
  elapsed_sec?: number | undefined;
  isRunning: boolean;
  lastSyncedAt?: number | undefined;
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
        : (step?.status as string) === 'stopped' || (step?.status as string) === 'interrupted'
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
          : (step?.status as string) === 'stopped' || (step?.status as string) === 'interrupted'
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
            <div className="flex flex-wrap items-center justify-end overflow-hidden rounded-md border border-cursor-hairline bg-cursor-canvas-soft px-2.5 py-1 text-xs gap-1.5 shadow-2xs">
              <LiveStepElapsed
                elapsed_sec={step?.elapsed_sec}
                isRunning={step?.status === 'running'}
                lastSyncedAt={lastSyncedAt}
              />
              <span className="h-3.5 w-px bg-cursor-hairline mx-0.5" />
              <StageMetric label="CPU" value={formatMetricValue(step?.cpu_pct, '%', 1)} />
              <span className="h-3.5 w-px bg-cursor-hairline mx-0.5" />
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
  const height = 110;

  if (safePoints.length === 0) {
    return (
      <div className="flex flex-col justify-between gap-1 rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft p-3">
        <div className="flex items-center justify-between text-xs">
          <span className="font-medium text-cursor-ink">{label}</span>
          <span className="text-xs text-cursor-muted">Connecting...</span>
        </div>
        <div className="flex items-center justify-center h-28 text-xs text-cursor-muted gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-cursor-primary" />
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
        <span className="text-cursor-primary font-semibold text-xs">
          {formatValue(currentVal)}{' '}
          <span className="text-2xs text-cursor-muted font-normal">(peak: {formatValue(peakVal)})</span>
        </span>
      </div>
      <div className="relative">
        <svg className="h-28 w-full overflow-visible" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
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
