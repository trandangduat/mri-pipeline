import {formatTime} from './format';
import {formatDuration, normalizeJobState} from '../jobFormatters';
import type {JobState, LocalJobSummary, PipelineEvent, RemoteJobSummary} from '../types/backend';

export type AnyJob = Partial<LocalJobSummary> & Partial<RemoteJobSummary> & Record<string, unknown>;

export interface BatchImageItem {
  input_file: string;
  subject_id: string;
  idx: number;
  total: number;
  status: 'pending' | 'running' | 'success' | 'failed' | 'stopped';
  duration_sec?: number | undefined;
}

export interface BatchSummary {
  total: number;
  success: number;
  failed: number;
  running: number;
  pending: number;
  stopped?: number;
  interrupted?: number;
  completedPercent: number;
}

export interface StageStepDetail {
  stage: string;
  label: string;
  tool: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'stopped' | 'not_scheduled' | 'skipped';
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

export function deriveSubjectLabel(
  filePath: string,
  idx = 1,
  datasetRoot = '',
): {subject_id: string; filename: string} {
  if (!filePath) {
    return {subject_id: `subj_${idx}`, filename: 'file.mgz'};
  }
  const normalizedPath = filePath.replace(/\\/g, '/');
  const parts = normalizedPath.split('/').filter(Boolean);
  const filename = parts[parts.length - 1] || filePath;
  const baseName = filename.replace(/\.(nii|nii\.gz|mgz|dcm|dicom|ima)$/i, '');

  if (datasetRoot) {
    const normalizedRoot = datasetRoot.replace(/\\/g, '/').replace(/\/+$/, '');
    if (normalizedPath.startsWith(normalizedRoot)) {
      const rel = normalizedPath.slice(normalizedRoot.length).replace(/^\/+/, '');
      const relParts = rel.split('/').filter(Boolean);
      if (relParts.length > 1) {
        relParts[relParts.length - 1] = relParts[relParts.length - 1].replace(/\.(nii|nii\.gz|mgz|dcm|dicom|ima)$/i, '');
        return {subject_id: relParts.join('__'), filename};
      }
    }
  }

  const genericNames = ['001', '002', '003', 'orig', 'raw', 't1', 't1w', 't2', 'flair', 'image', 'file', 'input', 'data', 'brain', 'scan'];
  const isGeneric = genericNames.includes(baseName.toLowerCase()) || /^\d{1,6}$/.test(baseName);

  if (isGeneric && parts.length > 1) {
    const parentFolder = parts[parts.length - 2] || '';
    if (parentFolder && ['nifti', 'raw_data', 'mri', 'anat', 'scans', 'inputs'].includes(parentFolder.toLowerCase()) && parts.length > 2) {
      return {subject_id: parts[parts.length - 3] || `subj_${idx}`, filename};
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
  const req = (job.run_request as Record<string, unknown>) || {};
  const datasetRoot = String(
    job.dataset_root ||
      job.input_dir ||
      job.input_path ||
      job.effective_input_dir ||
      reqSummary.input_dir ||
      req.input_dir ||
      '',
  );
  let initialFiles: string[] = [];

  if (Array.isArray(job.input_files) && job.input_files.length > 0) {
    initialFiles = job.input_files.map(String);
  } else if (Array.isArray(reqSummary.input_files) && reqSummary.input_files.length > 0) {
    initialFiles = (reqSummary.input_files as unknown[]).map(String);
  } else if (Array.isArray(req.input_files) && req.input_files.length > 0) {
    initialFiles = (req.input_files as unknown[]).map(String);
  } else if (reqSummary.input_file) {
    initialFiles = [String(reqSummary.input_file)];
  } else if (job.input_file) {
    initialFiles = [String(job.input_file)];
  }

  const imagesMap = new Map<string, BatchImageItem>();

  initialFiles.forEach((file, idx) => {
    const {subject_id} = deriveSubjectLabel(file, idx + 1, datasetRoot);
    imagesMap.set(file, {
      input_file: file,
      subject_id,
      idx: idx + 1,
      total: initialFiles.length,
      status: 'pending',
    });
  });

  function findMatchingImage(file: string, idx: number, subjectHint?: string): BatchImageItem | undefined {
    if (file && imagesMap.has(file)) return imagesMap.get(file);
    const {subject_id} = deriveSubjectLabel(file, idx, datasetRoot);
    const targetSubject = subjectHint || subject_id;
    for (const item of imagesMap.values()) {
      if (item.subject_id === targetSubject || item.idx === idx) {
        return item;
      }
    }
    return undefined;
  }

  for (const event of events) {
    const kind = String(event.kind || '');
    if (kind === 'image_start') {
      const file = String(event.input_file || '');
      const idx = Number(event.idx || 1);
      const total = Number(event.total || initialFiles.length || 1);
      const existing = findMatchingImage(file, idx, event.subject_id ? String(event.subject_id) : undefined);
      if (existing) {
        existing.status = 'running';
        existing.idx = idx;
        existing.total = total;
        if (event.subject_id) {
          existing.subject_id = String(event.subject_id);
        }
      } else if (file) {
        const {subject_id} = deriveSubjectLabel(file, idx, datasetRoot);
        imagesMap.set(file, {
          input_file: file,
          subject_id: event.subject_id ? String(event.subject_id) : subject_id,
          idx,
          total,
          status: 'running',
        });
      }
    } else if (kind === 'image_done') {
      const file = String(event.input_file || '');
      const idx = Number(event.idx || 1);
      const total = Number(event.total || initialFiles.length || 1);
      let success = Boolean(event.success);
      const duration_sec = typeof event.duration_sec === 'number' ? event.duration_sec : undefined;
      const subject_id = String(event.subject_id || '');
      const existing = findMatchingImage(file, idx, subject_id || undefined);
      const computedSubj = subject_id || deriveSubjectLabel(file, idx, datasetRoot).subject_id;
      const logText = String(event.log_text || '');

      if (success && logText) {
        const req = ((job?.run_request || job?.run_request_summary || {}) as Record<string, unknown>) || {};
        const tools = ((req.selected_tools || {}) as Record<string, string>) || {};
        const isScheduledTool = (t: unknown) =>
          Boolean(t) && t !== 'none' && t !== 'null' && t !== 'undefined' && t !== 'disabled';
        const scheduledCount = Object.values(tools).filter(isScheduledTool).length;
        if (scheduledCount > 0) {
          const okLines = (logText.match(/\[.*?\]\s*.*?\s*-\s*(OK|SUCCESS)/gi) || []).length;
          if (okLines < scheduledCount) {
            success = false;
          }
        }
      }

      const eventStatus = String(event.status || '').toLowerCase();
      const finalStatus: BatchImageItem['status'] =
        eventStatus === 'stopped' ? 'stopped' : success ? 'success' : 'failed';

      if (existing) {
        existing.status = finalStatus;
        if (computedSubj) existing.subject_id = computedSubj;
        if (duration_sec !== undefined) existing.duration_sec = duration_sec;
      } else if (file) {
        const item: BatchImageItem = {
          input_file: file,
          subject_id: computedSubj,
          idx,
          total,
          status: finalStatus,
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
  } else if (normState === 'stopped') {
    imagesMap.forEach((img) => {
      if (img.status !== 'success') {
        img.status = 'stopped';
      }
    });
  } else if (normState === 'failed') {
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
  let stopped = 0;

  for (const img of images) {
    if (img.status === 'success') success++;
    else if (img.status === 'failed') failed++;
    else if (img.status === 'stopped' || (img.status as string) === 'interrupted') stopped++;
    else if (img.status === 'running') running++;
    else pending++;
  }

  const completed = success + failed + stopped;
  const completedPercent = total > 0 ? Math.round((completed / total) * 100) : 0;

  return {total, success, failed, running, pending, stopped, interrupted: stopped, completedPercent};
}

export const DEFAULT_STAGE_ORDER = [
  'reorientation',
  'brain_extraction',
  'segmentation',
  'template_registration',
  'bias_correction',
  'white_matter_segmentation',
  'surface_reconstruction',
  'surface_registration',
  'stats_extraction',
];

export const DEFAULT_STAGE_LABELS: Record<string, string> = {
  reorientation: 'Reorientation, resize',
  brain_extraction: 'Brain Extraction',
  segmentation: 'Subcortical Segmentation',
  template_registration: 'Template Registration',
  bias_correction: 'Image standardization',
  white_matter_segmentation: 'WM Segmentation',
  surface_reconstruction: 'Surface Reconstruction',
  surface_registration: 'Surface Registration',
  stats_extraction: 'Statistics & Atlas Mapping',
};

const STAGE_KEYWORD_MAP: Record<string, string[]> = {
  reorientation: ['reorientation', 'resize', 'format', 'convert', 'conformed', 'nifti'],
  brain_extraction: ['brain', 'skull', 'extraction', 'bet', 'synthstrip'],
  segmentation: ['subcortical', 'aseg', 'segmentation', 'synthseg', 'fastsurfer'],
  template_registration: ['template', 'registration', 'affine'],
  bias_correction: ['bias', 'standardization', 'nu', 'n3', 'n4', 'conform'],
  white_matter_segmentation: ['wm', 'white_matter', 'white matter', 'fast'],
  surface_reconstruction: ['surface_reconstruction', 'surface reconstruction', 'recon-all', 'cortical', 'surface', 'recon'],
  surface_registration: ['surface_registration', 'surface registration', 'sphere', 'spherical'],
  stats_extraction: ['stat', 'stats', 'atlas', 'parcellation', 'aparc', 'volume', 'thickness', 'report', 'aggregate', 'export'],
};

export function isEventForImage(event: PipelineEvent, image: BatchImageItem | null): boolean {
  if (!image) return false;
  if (event.input_file) return String(event.input_file) === image.input_file;
  if (event.subject_id) return String(event.subject_id) === image.subject_id;
  if (event.container_name) {
    const cName = String(event.container_name);
    if (image.subject_id && cName.includes(image.subject_id)) return true;
    const sanitizedSubj = (image.subject_id || '').replace(/[/\\:]/g, '_');
    if (sanitizedSubj && cName.includes(sanitizedSubj)) return true;
    const sanitizedFile = (image.input_file || '').replace(/[/\\:]/g, '_');
    if (sanitizedFile && cName.includes(sanitizedFile)) return true;
    const parts = (image.input_file || '').split('/').filter(Boolean);
    if (parts.length >= 2) {
      const folderSubj = parts[parts.length - 2] + '__' + parts[parts.length - 1];
      if (cName.includes(folderSubj)) return true;
    }

    // Match truncated container names generated by _safe_container_name(*parts)
    // Docker container name format: mri-<subject_core...>-<uuid8>
    const core = cName.replace(/^mri-/, '').replace(/-[0-9a-fA-F]{8,}$/, '');
    if (core && core.length >= 6) {
      const rawSubj = image.subject_id || '';
      const safeSubj = rawSubj.replace(/[^A-Za-z0-9_.-]+/g, '-');
      if (rawSubj && (rawSubj.startsWith(core) || core.startsWith(rawSubj))) return true;
      if (safeSubj && (safeSubj.startsWith(core) || core.startsWith(safeSubj))) return true;
      if (sanitizedSubj && (sanitizedSubj.startsWith(core) || core.startsWith(sanitizedSubj))) return true;
      // Also match if cName contains a significant prefix of the subject_id (>= 20 chars)
      if (rawSubj.length >= 20 && cName.includes(rawSubj.slice(0, 20))) return true;
      if (safeSubj.length >= 20 && cName.includes(safeSubj.slice(0, 20))) return true;
    }
  }
  return false;
}

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
      const isTargeted = Boolean(event.input_file || event.subject_id || event.container_name);
      const activeMatch = isTargeted ? isEventForImage(event, image) : (currentActiveFile ? currentActiveFile === image.input_file : true);
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
          const isStoppedMsg = String(event.msg || event.message || event.error || '').toLowerCase().includes('stopped');
          if (['running', 'start', 'started'].includes(rawStatus)) {
            markPriorActiveStagesSuccess(step.stage);
            step.status = 'running';
          } else if (['ok', 'done', 'completed', 'success'].includes(rawStatus)) {
            step.status = 'success';
          } else if (['stopped', 'stop', 'interrupted', 'cancelled'].includes(rawStatus) || isStoppedMsg) {
            step.status = 'stopped';
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
      const match = isEventForImage(event, image) || (!event.input_file && !event.subject_id && !event.container_name && (currentActiveFile ? currentActiveFile === image.input_file : true));
      if (match) {
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
      const match = doneFile === image.input_file || (event.subject_id && String(event.subject_id) === image.subject_id);
      if (match) {
        const logText = String(event.log_text || '');
        if (logText) {
          const lines = logText.split('\n');
          for (const line of lines) {
            const parsed = line.match(/^\[(.*?)\]\s*(.*?)\s*-\s*(OK|SUCCESS|FAIL|FAILED|STOPPED)(?:\s*\(([\d.]+)\s*s\))?/i);
            if (parsed && parsed[1] && parsed[3]) {
              const stg = parsed[1].toLowerCase();
              const res = parsed[3].toUpperCase();
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
                const toolName = (parsed[2] || '').trim();
                if (toolName) step.tool = toolName;
                if (isUnscheduledStep(step) && !toolName) continue;
                if (parsed[4]) {
                  step.elapsed_sec = parseFloat(parsed[4]);
                }
                if (res === 'OK' || res === 'SUCCESS') {
                  step.status = 'success';
                } else if (res === 'STOPPED') {
                  step.status = 'stopped';
                } else {
                  step.status = 'failed';
                }
              }
            }
          }
        }
      }
    }
  }

  // Final reconcile based on image status
  if (image.status === 'success') {
    stepMap.forEach((s) => {
      if (s.tool && s.status !== 'failed' && s.status !== 'not_scheduled' && s.status !== 'skipped') {
        s.status = 'success';
      }
    });
  } else if (image.status === 'stopped') {
    stepMap.forEach((s) => {
      if (s.tool && s.status !== 'success' && s.status !== 'not_scheduled' && s.status !== 'skipped') {
        s.status = 'stopped';
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
      const activeMatch = image
        ? isEventForImage(event, image) ||
          (!event.input_file &&
            !event.subject_id &&
            !event.container_name &&
            (currentActiveFile ? currentActiveFile === image.input_file : true))
        : true;
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
  const allImagesTerminal =
    batchImages.length > 0 &&
    batchImages.every((img) => img.status === 'success' || img.status === 'failed');

  let hasTerminalEvent = false;
  let hasFailedEvent = false;
  for (const ev of events) {
    const kind = String(
      ev.kind || (ev as Record<string, unknown>).event || (ev as Record<string, unknown>).type || '',
    );
    if (
      kind === 'pipeline_completed' ||
      kind === 'job_completed' ||
      kind === 'complete' ||
      kind === 'pipeline_success'
    ) {
      hasTerminalEvent = true;
    } else if (
      kind === 'pipeline_failed' ||
      kind === 'job_failed' ||
      kind === 'error' ||
      kind === 'pipeline_error'
    ) {
      hasTerminalEvent = true;
      hasFailedEvent = true;
    }
  }

  let status_reconciled = normState;
  if (normState === 'stopped') {
    status_reconciled = 'stopped';
  } else if (hasTerminalEvent) {
    status_reconciled = hasFailedEvent || anyImageFailed ? 'failed' : 'completed';
  } else if (allImagesTerminal) {
    status_reconciled = anyImageFailed ? 'failed' : 'completed';
  } else if (normState === 'running') {
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
