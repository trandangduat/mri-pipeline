import React, {type ReactNode, type ButtonHTMLAttributes} from 'react';
import {BUTTON, inputCls, labelCls, statusPillClasses} from '../lib/uiTokens';

export {BUTTON, inputCls, labelCls, statusPillClasses};

export interface PanelProps {
  icon?: ReactNode;
  title: ReactNode;
  children: ReactNode;
  className?: string;
  titleRight?: ReactNode;
}

export function Panel({icon, title, children, className = '', titleRight}: PanelProps) {
  return (
    <section className={`rounded-xl border border-cursor-hairline bg-white p-6 ${className}`}>
      <div className="mb-5 flex items-center justify-between gap-4">
        <h2 className="m-0 flex items-center gap-2 text-[18px] font-semibold leading-[1.4] text-cursor-ink">
          {icon ? <span className="flex h-5 w-5 items-center">{icon}</span> : null}
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

export function EmptyBox({message}: {message: string}) {
  return (
    <div className="mt-4 whitespace-pre-wrap rounded-lg border border-cursor-hairline bg-white p-4 text-cursor-body">
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
