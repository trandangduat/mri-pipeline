import {normalizeJobState} from '../jobFormatters';
import type {JobState, LocalJobSummary, PipelineEvent, RemoteJobSummary} from '../types/backend';

type AnyJob = Partial<LocalJobSummary> & Partial<RemoteJobSummary> & Record<string, unknown>;

export function jobProgress(state: JobState | string, eventCount: number): number {
  if (state === 'completed') return 100;
  if (state === 'running') return Math.min(90, Math.max(10, eventCount * 15));
  return 0;
}

export function extractOutputFiles(events: PipelineEvent[]): string[] {
  return events.flatMap((event) => (Array.isArray(event.outputs) ? event.outputs : []));
}

export function filterLogLines(text: string | null | undefined, query: string): string {
  const q = String(query || '')
    .trim()
    .toLowerCase();
  if (!q) {
    return text ?? '';
  }
  return String(text || '')
    .split('\n')
    .filter((line) => line.toLowerCase().includes(q))
    .join('\n');
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
  if (job.state === 'running') return 'bg-cursor-timeline-read animate-pulse';
  if (job.state === 'completed') return 'bg-cursor-semantic-success';
  return 'bg-cursor-semantic-error';
}
