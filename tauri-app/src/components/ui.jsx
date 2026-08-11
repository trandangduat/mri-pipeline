import React from 'react';
import {BUTTON, inputCls, labelCls, statusPillClasses} from '../lib/uiTokens.js';

export {BUTTON, inputCls, labelCls, statusPillClasses};

export function Panel({icon, title, children, className = '', titleRight}) {
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

export function StatusPill({state, children}) {
  return <span className={statusPillClasses(state)}>{children}</span>;
}

export function EmptyBox({message}) {
  return <div className="mt-4 whitespace-pre-wrap rounded-lg border border-cursor-hairline bg-white p-4 text-cursor-body">{message}</div>;
}

export function Button({variant = 'ghost', type = 'button', className = '', icon, children, ...rest}) {
  return (
    <button type={type} className={`${BUTTON.base} ${BUTTON[variant]} ${className}`} {...rest}>
      {icon ? <span className="flex h-4 w-4 items-center">{icon}</span> : null}
      {children}
    </button>
  );
}

export function Field({label, children, className = ''}) {
  return (
    <label className={`${labelCls} ${className}`}>
      {label}
      {children}
    </label>
  );
}
