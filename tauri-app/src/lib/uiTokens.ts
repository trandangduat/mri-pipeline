const pillBase =
  'inline-flex w-fit items-center rounded-full px-2 py-0.5 text-2xs font-semibold uppercase tracking-[0.08em]';

export const BUTTON = {
  base: 'inline-flex h-8 cursor-pointer items-center justify-center gap-1.5 rounded-md border px-3 text-sm font-medium leading-none transition-colors [&_svg]:block',
  primary:
    'border-cursor-primary bg-cursor-primary text-white hover:border-cursor-primary-active hover:bg-cursor-primary-active',
  ink: 'border-cursor-ink bg-cursor-ink text-cursor-canvas hover:bg-cursor-ink',
  ghost:
    'border-cursor-hairline bg-white text-cursor-ink hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft',
  danger: 'border-cursor-semantic-error bg-cursor-semantic-error text-white hover:bg-cursor-semantic-error',
};

export const inputCls =
  'h-8 w-full rounded-md border border-cursor-hairline bg-white px-2.5 text-sm font-normal text-cursor-ink outline-none focus:border-cursor-hairline-strong';
export const labelCls = 'grid gap-1.5 text-xs font-normal leading-[1.3] text-cursor-body';

export function statusPillClasses(state: string | null | undefined): string {
  const normalized = String(state || 'unknown').toLowerCase();
  if (['installed', 'ok', 'completed', 'done', 'success'].includes(normalized)) {
    return `${pillBase} bg-cursor-semantic-success text-white`;
  }
  if (['missing', 'failed', 'error'].includes(normalized)) {
    return `${pillBase} bg-cursor-semantic-error text-white`;
  }
  if (['running', 'checking'].includes(normalized)) {
    return `${pillBase} bg-cursor-timeline-read text-cursor-ink`;
  }
  if (['downloading', 'editing'].includes(normalized)) {
    return `${pillBase} bg-cursor-timeline-edit text-cursor-ink`;
  }
  return `${pillBase} bg-cursor-hairline text-cursor-body`;
}

export function statusDotClasses(state: string | null | undefined): string {
  const normalized = String(state || 'unknown').toLowerCase();
  if (normalized === 'running') return 'h-2 w-2 flex-none rounded-full bg-cursor-timeline-read animate-pulse';
  if (normalized === 'completed') return 'h-2 w-2 flex-none rounded-full bg-cursor-semantic-success';
  if (normalized === 'failed') return 'h-2 w-2 flex-none rounded-full bg-cursor-semantic-error';
  return 'h-2 w-2 flex-none rounded-full bg-cursor-muted';
}
