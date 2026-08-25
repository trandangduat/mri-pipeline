const pillBase =
  'inline-flex w-fit items-center rounded-full px-2 py-0.5 text-2xs font-semibold uppercase tracking-[0.08em]';

export const BUTTON = {
  base: 'inline-flex h-8 cursor-pointer items-center justify-center gap-1.5 rounded-md border px-3 text-sm font-medium leading-none transition-colors [&_svg]:block',
  primary:
    'border-cursor-primary bg-cursor-primary text-white hover:border-cursor-primary-active hover:bg-cursor-primary-active',
  ink: 'border-cursor-ink bg-cursor-ink text-cursor-canvas hover:bg-cursor-ink',
  ghost:
    'border-cursor-hairline bg-cursor-surface-card text-cursor-ink hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft',
  danger: 'border-cursor-semantic-error bg-cursor-semantic-error text-white hover:bg-cursor-semantic-error',
};

export const inputCls =
  'h-8 w-full rounded-md border border-cursor-hairline bg-cursor-surface-card px-2.5 text-sm font-normal text-cursor-ink outline-none focus:border-cursor-hairline-strong';
export const labelCls = 'grid gap-1.5 text-xs font-normal leading-[1.3] text-cursor-body';

export type AlertSeverity = 'warning' | 'error' | 'success' | 'info';

export const ALERT = {
  base: 'flex flex-col border-none leading-[1.4]',
  sm: 'rounded-lg px-4 py-2.5 gap-2',
  md: 'rounded-xl px-5 py-3.5 gap-2.5',
  warning: {
    bg: 'bg-amber-500/10 dark:bg-amber-500/15',
    text: 'text-amber-950 dark:text-amber-100',
    badgeBg: 'bg-amber-700 text-white dark:bg-amber-600',
    label: 'Warning',
  },
  error: {
    bg: 'bg-rose-500/10 dark:bg-rose-500/15',
    text: 'text-rose-950 dark:text-rose-100',
    badgeBg: 'bg-rose-700 text-white dark:bg-rose-700',
    label: 'Error',
  },
  success: {
    bg: 'bg-emerald-500/10 dark:bg-emerald-500/15',
    text: 'text-emerald-950 dark:text-emerald-100',
    badgeBg: 'bg-emerald-700 text-white dark:bg-emerald-700',
    label: 'Success',
  },
  info: {
    bg: 'bg-sky-500/10 dark:bg-sky-500/15',
    text: 'text-sky-950 dark:text-sky-100',
    badgeBg: 'bg-sky-700 text-white dark:bg-sky-700',
    label: 'Info',
  },
} as const;

export const BADGE = {
  base: 'inline-flex w-fit items-center gap-1 rounded px-2 py-0.5 text-2xs font-semibold uppercase tracking-[0.06em] transition-colors',
  primary: 'bg-cursor-primary/10 text-cursor-primary',
  success: 'bg-cursor-semantic-success/10 text-cursor-semantic-success',
  error: 'bg-cursor-semantic-error/10 text-cursor-semantic-error',
  warning: 'bg-cursor-semantic-warn/10 text-cursor-semantic-warn',
  neutral: 'bg-cursor-surface-strong/70 text-cursor-body',
  muted: 'bg-cursor-hairline text-cursor-muted',
} as const;

export function statusPillClasses(state: string | null | undefined): string {
  const normalized = String(state || 'unknown').toLowerCase();
  if (['installed', 'ok', 'completed', 'done', 'success', 'ready'].includes(normalized)) {
    return `${BADGE.base} ${BADGE.success}`;
  }
  if (['missing', 'failed', 'error', 'fail'].includes(normalized)) {
    return `${BADGE.base} ${BADGE.error}`;
  }
  if (['running', 'checking', 'in_progress'].includes(normalized)) {
    return `${BADGE.base} ${BADGE.primary}`;
  }
  if (['stopped', 'lagging', 'warn', 'warning'].includes(normalized)) {
    return `${BADGE.base} ${BADGE.warning}`;
  }
  return `${BADGE.base} ${BADGE.neutral}`;
}

export function statusDotClasses(state: string | null | undefined): string {
  const normalized = String(state || 'unknown').toLowerCase();
  if (normalized === 'running') return 'h-2 w-2 flex-none rounded-full bg-cursor-timeline-read animate-pulse';
  if (normalized === 'completed') return 'h-2 w-2 flex-none rounded-full bg-cursor-semantic-success';
  if (normalized === 'failed') return 'h-2 w-2 flex-none rounded-full bg-cursor-semantic-error';
  return 'h-2 w-2 flex-none rounded-full bg-cursor-muted';
}
