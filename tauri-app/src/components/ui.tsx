import React, {type ReactNode, type ButtonHTMLAttributes} from 'react';
import {AlertTriangle, AlertCircle, CheckCircle2, Info} from 'lucide-react';
import {ALERT, BUTTON, BADGE, inputCls, labelCls, statusPillClasses, statusDotClasses, type AlertSeverity} from '../lib/uiTokens';

export {ALERT, BUTTON, BADGE, inputCls, labelCls, statusPillClasses, statusDotClasses};
export type {AlertSeverity};

export interface AlertProps {
  severity: AlertSeverity;
  size?: 'sm' | 'md';
  icon?: boolean | ReactNode;
  badgeLabel?: ReactNode;
  children?: ReactNode;
  className?: string;
}

const ALERT_ICONS: Record<AlertSeverity, ReactNode> = {
  warning: (
    <svg className="h-4 w-4 flex-none" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
        clipRule="evenodd"
      />
    </svg>
  ),
  error: (
    <svg className="h-4 w-4 flex-none" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
        clipRule="evenodd"
      />
    </svg>
  ),
  success: (
    <svg className="h-4 w-4 flex-none" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
        clipRule="evenodd"
      />
    </svg>
  ),
  info: (
    <svg className="h-4 w-4 flex-none" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path
        fillRule="evenodd"
        d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z"
        clipRule="evenodd"
      />
    </svg>
  ),
};

export function Alert({
  severity,
  size = 'md',
  icon = true,
  badgeLabel,
  children,
  className = '',
}: AlertProps) {
  const v = ALERT[severity] || ALERT.warning;
  const badgeText = badgeLabel !== undefined ? badgeLabel : v.label;

  return (
    <div role="alert" className={`${ALERT.base} ${ALERT[size]} ${v.bg} ${v.text} ${className}`}>
      <div className="flex items-center">
        <span
          className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-0.5 text-xs font-bold text-white shadow-xs ${v.badgeBg}`}
        >
          {icon !== false && (
            <span className="flex h-4 w-4 items-center justify-center">
              {icon === true ? ALERT_ICONS[severity] : icon}
            </span>
          )}
          {badgeText ? <span>{badgeText}</span> : null}
        </span>
      </div>
      <div className="min-w-0 flex-1 px-1 text-sm leading-relaxed text-cursor-ink">
        {children}
      </div>
    </div>
  );
}

export interface PanelProps {
  icon?: ReactNode;
  title: ReactNode;
  children: ReactNode;
  className?: string;
  titleRight?: ReactNode;
}

export function Panel({icon, title, children, className = '', titleRight}: PanelProps) {
  return (
    <section className={`rounded-xl border border-cursor-hairline bg-cursor-surface-card p-4 ${className}`}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="m-0 flex items-center gap-2 text-base font-semibold leading-[1.3] text-cursor-ink">
          {icon ? <span className="flex h-4 w-4 items-center">{icon}</span> : null}
          {title}
        </h2>
        {titleRight}
      </div>
      {children}
    </section>
  );
}

export function StatusPill({state, children}: {state: string; children?: ReactNode}) {
  return <span className={statusPillClasses(state)}>{children}</span>;
}

export function StatusDotLarge({state, className = ''}: {state: unknown; className?: string}) {
  const normalized = String(state || 'unknown').toLowerCase();
  if (normalized === 'running') {
    return (
      <span className={`relative flex h-3 w-3 flex-none ${className}`}>
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cursor-primary opacity-75" />
        <span className="relative inline-flex rounded-full h-3 w-3 bg-cursor-primary" />
      </span>
    );
  }
  if (['completed', 'success', 'ok', 'done'].includes(normalized)) {
    return <span className={`h-3 w-3 rounded-full bg-cursor-semantic-success flex-none ${className}`} />;
  }
  if (['failed', 'error'].includes(normalized)) {
    return <span className={`h-3 w-3 rounded-full bg-cursor-semantic-error flex-none ${className}`} />;
  }
  if (['stopped', 'warn', 'warning'].includes(normalized)) {
    return <span className={`h-3 w-3 rounded-full bg-cursor-semantic-warn flex-none ${className}`} />;
  }
  return <span className={`h-3 w-3 rounded-full bg-cursor-hairline-strong flex-none ${className}`} />;
}

export function EmptyBox({message}: {message: string}) {
  return (
    <div className="mt-3 whitespace-pre-wrap rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3 text-xs text-cursor-body">
      {message}
    </div>
  );
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof BUTTON;
  icon?: ReactNode;
}

export function Button({variant = 'ghost', type = 'button', className = '', icon, children, ...rest}: ButtonProps) {
  const variantCls = BUTTON[variant] || BUTTON.ghost;
  return (
    <button type={type} className={`${BUTTON.base} ${variantCls} ${className}`} {...rest}>
      {icon ? <span className="flex h-4 w-4 items-center">{icon}</span> : null}
      {children}
    </button>
  );
}

export function Field({label, children, className = ''}: {label: ReactNode; children: ReactNode; className?: string}) {
  return (
    <label className={`${labelCls} ${className}`}>
      {label}
      {children}
    </label>
  );
}
