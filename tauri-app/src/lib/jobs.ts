import {formatTime} from './format';
import {formatDuration, normalizeJobState} from '../jobFormatters';
import type {JobState, LocalJobSummary, PipelineEvent, RemoteJobSummary} from '../types/backend';

type AnyJob = Partial<LocalJobSummary> & Partial<RemoteJobSummary> & Record<string, unknown>;

export interface BatchImageItem {
  input_file: string;
  subject_id: string;
  idx: number;
  total: number;
  status: 'pending' | 'running' | 'success' | 'failed';
  duration_sec?: number | undefined;
}

export interface BatchSummary {
  total: number;
  success: number;
  failed: number;
  running: number;
  pending: number;
  completedPercent: number;
}

export interface StageStepDetail {
  stage: string;
  label: string;
  tool: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'not_scheduled' | 'skipped';
  elapsed_sec?: number;
  cpu_pct?: number;
  ram_bytes?: number;
  gpu_pct?: number;
  container_name?: string;
}

export interface MetricsSeries {
  cpuSeries: number[];
  ramSeries: number[];
  gpuSeries: number[];
  latestContainer: string;
}

export function deriveSubjectLabel(filePath: string, idx = 1): {subject_id: string; filename: string} {
  if (!filePath) {
    return {subject_id: `subj_${idx}`, filename: 'file.mgz'};
  }
  const parts = filePath.replace(/\\/g, '/').split('/').filter(Boolean);
  const filename = parts.pop() || filePath;
  const baseName = filename.replace(/\.(nii|nii\.gz|mgz)$/i, '');

  const genericNames = ['001', 'orig', 'raw', 't1', 't2', 'flair', 'image', 'file', 'input'];
  const isGeneric = genericNames.includes(baseName.toLowerCase()) || /^\d+$/.test(baseName);

  if (isGeneric && parts.length > 0) {
    const parentFolder = parts[parts.length - 1] || '';
    if (parentFolder && ['nifti', 'raw_data', 'mri', 'anat', 'scans', 'inputs'].includes(parentFolder.toLowerCase()) && parts.length > 1) {
      return {subject_id: parts[parts.length - 2] || `subj_${idx}`, filename};
    }
    return {subject_id: parentFolder || `subj_${idx}`, filename};
  }

  return {subject_id: baseName || `subj_${idx}`, filename};
}

export function sanitizeTerminalLog(text: string | null | undefined, showRaw = false): string {
  if (!text) return '';
  if (showRaw) return text;
  return text
    .split('\n')
    .filter((line) => {
      const trimmed = line.trim();
      return !trimmed.startsWith('MRI_EVENT {') && !trimmed.startsWith('MRI_EVENT\t{');
    })
    .join('\n');
}

export function filterLogLines(text: string | null | undefined, query: string, showRaw = false): string {
  const sanitized = sanitizeTerminalLog(text, showRaw);
  const q = String(query || '').trim().toLowerCase();
  if (!q) {
    return sanitized;
  }
  return sanitized
    .split('\n')
    .filter((line) => line.toLowerCase().includes(q))
    .join('\n');
}

export function displayJobState(state: unknown): string {
  const norm = normalizeJobState(state);
  if (norm === 'running') return 'Running';
  if (norm === 'completed') return 'Success';
  if (norm === 'failed') return 'Failed';
  if (norm === 'stopped') return 'Stopped';
  return 'Unknown';
}

export function jobProgress(state: JobState | string, eventCount: number): number {
  if (state === 'completed') return 100;
  if (state === 'running') return Math.min(90, Math.max(10, eventCount * 15));
  return 0;
}

export function extractOutputFiles(events: PipelineEvent[]): string[] {
  return events.flatMap((event) => (Array.isArray(event.outputs) ? event.outputs : []));
}

export function progressStepEvents(events: PipelineEvent[] | null | undefined): PipelineEvent[] {
  return (events || []).filter((event) => event.stage || event.step || event.kind);
}

export function stepEventState(event: PipelineEvent): string {
  return String(event.state || event.status || event.kind || 'unknown').toLowerCase();
}

export function dotClassForState(state: JobState | string): string {
  const normalized = normalizeJobState(state);
  if (normalized === 'running') return 'h-2 w-2 flex-none rounded-full bg-cursor-timeline-read animate-pulse';
  if (normalized === 'completed') return 'h-2 w-2 flex-none rounded-full bg-cursor-semantic-success';
  if (normalized === 'failed') return 'h-2 w-2 flex-none rounded-full bg-cursor-semantic-error';
  return 'h-2 w-2 flex-none rounded-full bg-cursor-muted';
}

export function sidebarDotClass(job: AnyJob): string {
  return dotClassForState(job.state as string);
}

export function deriveBatchImages(events: PipelineEvent[] = [], job: AnyJob = {}): BatchImageItem[] {
  const reqSummary = (job.run_request_summary as Record<string, unknown>) || {};
  let initialFiles: string[] = [];

  if (Array.isArray(job.input_files) && job.input_files.length > 0) {
    initialFiles = job.input_files.map(String);
  } else if (Array.isArray(reqSummary.input_files) && reqSummary.input_files.length > 0) {
    initialFiles = (reqSummary.input_files as unknown[]).map(String);
  } else if (reqSummary.input_file) {
    initialFiles = [String(reqSummary.input_file)];
  } else if (job.input_file) {
    initialFiles = [String(job.input_file)];
  }

  const imagesMap = new Map<string, BatchImageItem>();

  initialFiles.forEach((file, idx) => {
    const {subject_id} = deriveSubjectLabel(file, idx + 1);
    imagesMap.set(file, {
      input_file: file,
      subject_id,
      idx: idx + 1,
      total: initialFiles.length,
      status: 'pending',
    });
  });

  for (const event of events) {
    const kind = String(event.kind || '');
    if (kind === 'image_start') {
      const file = String(event.input_file || '');
      const idx = Number(event.idx || 1);
      const total = Number(event.total || initialFiles.length || 1);
      const existing = imagesMap.get(file);
      if (existing) {
        existing.status = 'running';
        existing.idx = idx;
        existing.total = total;
      } else if (file) {
        const {subject_id} = deriveSubjectLabel(file, idx);
        imagesMap.set(file, {
          input_file: file,
          subject_id,
          idx,
          total,
          status: 'running',
        });
      }
    } else if (kind === 'image_done') {
      const file = String(event.input_file || '');
      const idx = Number(event.idx || 1);
      const total = Number(event.total || initialFiles.length || 1);
      const success = Boolean(event.success);
      const duration_sec = typeof event.duration_sec === 'number' ? event.duration_sec : undefined;
      const subject_id = String(event.subject_id || '');
      const existing = imagesMap.get(file);
      const computedSubj = subject_id || deriveSubjectLabel(file, idx).subject_id;

      if (existing) {
        existing.status = success ? 'success' : 'failed';
        if (computedSubj) existing.subject_id = computedSubj;
        if (duration_sec !== undefined) existing.duration_sec = duration_sec;
      } else if (file) {
        const item: BatchImageItem = {
          input_file: file,
          subject_id: computedSubj,
          idx,
          total,
          status: success ? 'success' : 'failed',
        };
        if (duration_sec !== undefined) item.duration_sec = duration_sec;
        imagesMap.set(file, item);
      }
    }
  }

  // Reconcile status with job.state if terminal
  const normState = normalizeJobState(job.state);
  if (normState === 'completed') {
    imagesMap.forEach((img) => {
      if (img.status === 'running' || img.status === 'pending') {
        img.status = 'success';
      }
    });
  } else if (normState === 'failed' || normState === 'stopped') {
    imagesMap.forEach((img) => {
      if (img.status === 'running' || img.status === 'pending') {
        img.status = 'failed';
      }
    });
  }

  return Array.from(imagesMap.values());
}

export function deriveBatchSummary(images: BatchImageItem[]): BatchSummary {
  const total = images.length;
  let success = 0;
  let failed = 0;
  let running = 0;
  let pending = 0;

  for (const img of images) {
    if (img.status === 'success') success++;
    else if (img.status === 'failed') failed++;
    else if (img.status === 'running') running++;
    else pending++;
  }

  const completed = success + failed;
  const completedPercent = total > 0 ? Math.round((completed / total) * 100) : 0;

  return {total, success, failed, running, pending, completedPercent};
}

const STAGE_KEYWORD_MAP: Record<string, string[]> = {
  format_conversion: ['format', 'reorientation', 'resize', 'convert', 'nifti'],
  brain_extraction: ['brain', 'skull', 'extraction', 'bet'],
  tissue_segmentation: ['tissue', 'seg', 'segmentation', 'fast'],
  cortical_reconstruction: ['cortical', 'surface', 'recon'],
  subcortical_segmentation: ['subcortical', 'aseg'],
  parcellation: ['parcellation', 'aparc', 'atlas'],
  stat_calculation: ['stat', 'volume', 'thickness'],
  export_conversion: ['export'],
  aggregate_reporting: ['aggregate', 'report'],
};

export function deriveImageSteps(
  events: PipelineEvent[] = [],
  image: BatchImageItem | null,
  selectedTools: Record<string, string> = {},
  stageOrder: string[] = [],
  stageLabels: Record<string, string> = {},
): StageStepDetail[] {
  const steps: StageStepDetail[] = stageOrder.map((stage) => {
    const tool = selectedTools[stage] || '';
    return {
      stage,
      label: stageLabels[stage] || stage,
      tool,
      status: tool ? 'pending' : 'not_scheduled',
    };
  });

  if (!image) return steps;

  const stepMap = new Map<string, StageStepDetail>();
  steps.forEach((s) => stepMap.set(s.stage, s));

  const isUnscheduledStep = (step: StageStepDetail) => !step.tool && (step.status === 'not_scheduled' || step.status === 'skipped');

  let currentActiveFile: string | null = null;

  const markPriorActiveStagesSuccess = (currentStage: string) => {
    const currentIndex = stageOrder.indexOf(currentStage);
    if (currentIndex < 0) return;
    for (let i = 0; i < currentIndex; i += 1) {
      const prior = stepMap.get(stageOrder[i] || '');
      if (!prior || prior.status === 'not_scheduled' || prior.status === 'failed') continue;
      if (prior.status === 'running' || prior.status === 'pending') {
        prior.status = 'success';
      }
    }
  };

  for (const event of events) {
    const kind = String(event.kind || '');
    if (kind === 'image_start') {
      currentActiveFile = String(event.input_file || '');
    } else if (kind === 'progress' || kind === 'step' || kind === 'stage') {
      const activeMatch = currentActiveFile ? currentActiveFile === image.input_file : true;
      if (activeMatch) {
        const rawStageKey = String(event.stage || event.step || event.message || '').toLowerCase();
        let step = stepMap.get(rawStageKey);

        if (!step && rawStageKey) {
          for (const [stageKey, keywords] of Object.entries(STAGE_KEYWORD_MAP)) {
            if (keywords.some((kw) => rawStageKey.includes(kw))) {
              step = stepMap.get(stageKey);
              if (step) break;
            }
          }
        }

        if (step) {
          const eventTool = event.tool ? String(event.tool) : '';
          if (eventTool) step.tool = eventTool;
          if (isUnscheduledStep(step) && !eventTool) continue;
          const rawStatus = String(event.status || event.state || '').toLowerCase();
          if (['running', 'start', 'started'].includes(rawStatus)) {
            markPriorActiveStagesSuccess(step.stage);
            step.status = 'running';
          } else if (['ok', 'done', 'completed', 'success'].includes(rawStatus)) {
            step.status = 'success';
          } else if (['failed', 'error'].includes(rawStatus)) {
            step.status = 'failed';
          } else if (['skipped', 'skip', 'not_scheduled', 'not scheduled'].includes(rawStatus)) {
            step.status = 'skipped';
          }
          if (typeof event.elapsed_sec === 'number') step.elapsed_sec = event.elapsed_sec;
          if (typeof event.pct === 'number' && event.pct === 100) step.status = 'success';
        }
      }
    } else if (kind === 'metrics') {
      const activeMatch = currentActiveFile ? currentActiveFile === image.input_file : true;
      if (activeMatch) {
        const rawStageKey = String(event.stage || '').toLowerCase();
        let step = stepMap.get(rawStageKey);
        if (!step && rawStageKey) {
          for (const [stageKey, keywords] of Object.entries(STAGE_KEYWORD_MAP)) {
            if (keywords.some((kw) => rawStageKey.includes(kw))) {
              step = stepMap.get(stageKey);
              if (step) break;
            }
          }
        }
        if (step) {
          const eventTool = event.tool ? String(event.tool) : '';
          if (eventTool) step.tool = eventTool;
          if (isUnscheduledStep(step) && !eventTool) continue;
          if (typeof event.cpu_pct === 'number') step.cpu_pct = Math.max(step.cpu_pct || 0, event.cpu_pct);
          if (typeof event.ram_bytes === 'number') step.ram_bytes = Math.max(step.ram_bytes || 0, event.ram_bytes);
          if (typeof event.gpu_pct === 'number') step.gpu_pct = Math.max(step.gpu_pct || 0, event.gpu_pct);
          if (typeof event.elapsed === 'number') step.elapsed_sec = event.elapsed;
          if (event.container_name) step.container_name = String(event.container_name);
          if (step.status === 'pending' || step.status === 'not_scheduled') {
            markPriorActiveStagesSuccess(step.stage);
            step.status = 'running';
          }
        }
      }
    } else if (kind === 'image_done') {
      const doneFile = String(event.input_file || '');
      if (doneFile === image.input_file) {
        const logText = String(event.log_text || '');
        if (logText) {
          const lines = logText.split('\n');
          for (const line of lines) {
            const match = line.match(/^\[(.*?)\]\s*(.*?)\s*-\s*(OK|FAIL)/i);
            if (match && match[1] && match[3]) {
              const stg = match[1].toLowerCase();
              const toolName = match[2] || '';
              const res = match[3];
              let step = stepMap.get(stg);
              if (!step) {
                for (const [stageKey, keywords] of Object.entries(STAGE_KEYWORD_MAP)) {
                  if (keywords.some((kw) => stg.includes(kw))) {
                    step = stepMap.get(stageKey);
                    if (step) break;
                  }
                }
              }
              if (step) {
                const toolName = (match[2] || '').trim();
                if (toolName) step.tool = toolName;
                if (isUnscheduledStep(step) && !toolName) continue;
                step.status = res.toUpperCase() === 'OK' ? 'success' : 'failed';
              }
            }
          }
        }
        if (event.success === true) {
          stepMap.forEach((s) => {
            if (s.status === 'running' || (s.tool && s.status === 'pending')) {
              s.status = 'success';
            }
          });
        } else if (event.success === false) {
          stepMap.forEach((s) => {
            if (s.status === 'running') {
              s.status = 'failed';
            }
          });
        }
      }
      if (currentActiveFile === doneFile) {
        currentActiveFile = null;
      }
    }
  }

  // If image is completed (success), ensure scheduled active stages are marked success
  if (image.status === 'success') {
    stepMap.forEach((s) => {
      if (s.status === 'running' || (s.tool && s.status === 'pending')) {
        s.status = 'success';
      }
    });
  }

  return Array.from(stepMap.values());
}

export function deriveMetricsSeries(events: PipelineEvent[] = [], image: BatchImageItem | null = null): MetricsSeries {
  const cpuSeries: number[] = [];
  const ramSeries: number[] = [];
  const gpuSeries: number[] = [];
  let latestContainer = 'None';
  let currentActiveFile: string | null = null;

  for (const event of events) {
    const kind = String(event.kind || '');
    if (kind === 'image_start') {
      currentActiveFile = String(event.input_file || '');
    } else if (kind === 'metrics') {
      const activeMatch = image ? currentActiveFile === image.input_file : true;
      if (activeMatch) {
        const cpu = typeof event.cpu_pct === 'number' ? event.cpu_pct : 0;
        const ram = typeof event.ram_bytes === 'number' ? Math.round(event.ram_bytes / (1024 * 1024)) : 0;
        const gpu = typeof event.gpu_pct === 'number' ? event.gpu_pct : 0;
        cpuSeries.push(cpu);
        ramSeries.push(ram);
        gpuSeries.push(gpu);
        if (event.container_name) {
          latestContainer = String(event.container_name);
        }
      }
    } else if (kind === 'image_done') {
      if (currentActiveFile === String(event.input_file || '')) {
        currentActiveFile = null;
      }
    }
  }

  return {
    cpuSeries: cpuSeries.slice(-180),
    ramSeries: ramSeries.slice(-180),
    gpuSeries: gpuSeries.slice(-180),
    latestContainer,
  };
}

export interface JobDisplayMetadata {
  started_at_str: string;
  finished_at_str: string;
  duration_str: string;
  input_path_str: string;
  output_dir_str: string;
  status_reconciled: string;
}

export function deriveJobDisplayMetadata(job: AnyJob | null, events: PipelineEvent[] = []): JobDisplayMetadata {
  const reqSummary = (job?.run_request_summary as Record<string, unknown>) || {};
  const jobStateRaw = String(job?.state || 'unknown');
  const normState = normalizeJobState(jobStateRaw);

  const batchImages = deriveBatchImages(events, job || {});
  const anyImageRunning = batchImages.some((img) => img.status === 'running');
  const anyImageFailed = batchImages.some((img) => img.status === 'failed');

  let status_reconciled = normState;
  if (normState === 'running') {
    status_reconciled = 'running';
  } else if (anyImageRunning) {
    status_reconciled = 'running';
  } else if (normState === 'completed' && anyImageFailed) {
    status_reconciled = 'failed';
  }

  const firstEv = events[0];
  const lastEv = events[events.length - 1];
  const firstEventTime = typeof firstEv?.time === 'number' ? (firstEv.time as number) : null;
  const lastEventTime = typeof lastEv?.time === 'number' ? (lastEv.time as number) : null;

  const startedAt = (job?.started_at || job?.created_at || firstEventTime) as string | number | null | undefined;
  const finishedAt = (job?.finished_at || lastEventTime) as string | number | null | undefined;

  const started_at_str = formatTime(startedAt);
  const finished_at_str = formatTime(finishedAt);
  const duration_str = formatDuration(startedAt, finishedAt);

  const input_path_str = String(
    reqSummary.input_file ||
      reqSummary.input_dir ||
      (Array.isArray(job?.input_files) ? job.input_files.join(', ') : '') ||
      job?.input_file ||
      'N/A',
  );

  const output_dir_str = String(
    job?.effective_output_dir || job?.output_dir || job?.remote_job_dir || job?.job_dir || reqSummary.output_dir || 'N/A',
  );

  return {
    started_at_str,
    finished_at_str,
    duration_str,
    input_path_str,
    output_dir_str,
    status_reconciled,
  };
}
