import React, {type ReactNode, type ButtonHTMLAttributes} from 'react';
import {BUTTON, inputCls, labelCls, statusPillClasses, statusDotClasses} from '../lib/uiTokens';

export {BUTTON, inputCls, labelCls, statusPillClasses, statusDotClasses};

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
