import {normalizeJobState} from '../jobFormatters.js';

export function jobProgress(state, eventCount) {
  if (state === 'completed') return 100;
  if (state === 'running') return Math.min(90, Math.max(10, eventCount * 15));
  return 0;
}

export function extractOutputFiles(events) {
  return events.flatMap((event) => (Array.isArray(event.outputs) ? event.outputs : []));
}

export function filterLogLines(text, query) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) {
    return text;
  }
  return String(text || '')
    .split('\n')
    .filter((line) => line.toLowerCase().includes(q))
    .join('\n');
}

export function progressStepEvents(events) {
  return (events || []).filter((event) => event.stage || event.step || event.kind);
}

export function stepEventState(event) {
  return String(event.state || event.status || event.kind || 'unknown').toLowerCase();
}

export function dotClassForState(state) {
  const normalized = normalizeJobState(state);
  if (normalized === 'running') return 'h-2 w-2 flex-none rounded-full bg-cursor-timeline-read animate-pulse';
  if (normalized === 'completed') return 'h-2 w-2 flex-none rounded-full bg-cursor-semantic-success';
  if (normalized === 'failed') return 'h-2 w-2 flex-none rounded-full bg-cursor-semantic-error';
  return 'h-2 w-2 flex-none rounded-full bg-cursor-muted';
}

export function sidebarDotClass(job) {
  if (job.state === 'running') return 'bg-cursor-timeline-read animate-pulse';
  if (job.state === 'completed') return 'bg-cursor-semantic-success';
  return 'bg-cursor-semantic-error';
}
