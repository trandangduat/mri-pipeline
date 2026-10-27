import React, {useRef, useState, type ReactNode, type PointerEvent} from 'react';
import {GripVertical} from 'lucide-react';

export interface SplitPaneFormProps {
  left: ReactNode;
  right: ReactNode;
  initialWidth?: number;
  min?: number;
  max?: number;
  className?: string;
  storageKey?: string;
}

export function SplitPaneForm({
  left,
  right,
  initialWidth = 47,
  min = 32,
  max = 64,
  className = '',
  storageKey = 'neuroflow_pipeline_split_width',
}: SplitPaneFormProps) {
  const [leftWidth, setLeftWidth] = useState<number>(() => {
    if (typeof window !== 'undefined' && storageKey) {
      try {
        const saved = window.localStorage.getItem(storageKey);
        if (saved) {
          const parsed = Number(saved);
          if (!Number.isNaN(parsed) && parsed >= min && parsed <= max) {
            return parsed;
          }
        }
      } catch {
        // ignore
      }
    }
    return initialWidth;
  });

  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const leftWidthRef = useRef(leftWidth);

  function onPointerDown(event: PointerEvent<HTMLButtonElement>) {
    draggingRef.current = true;
    setIsDragging(true);
    event.currentTarget.setPointerCapture(event.pointerId);
    document.body.classList.add('is-resizing-pipeline');
  }

  function onPointerMove(event: PointerEvent<HTMLButtonElement>) {
    if (!draggingRef.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const rawPercent = ((event.clientX - rect.left) / rect.width) * 100;
    const nextWidth = Math.min(max, Math.max(min, rawPercent));
    leftWidthRef.current = nextWidth;
    setLeftWidth(nextWidth);
  }

  function onPointerUp(event: PointerEvent<HTMLButtonElement>) {
    draggingRef.current = false;
    setIsDragging(false);
    event.currentTarget.releasePointerCapture(event.pointerId);
    document.body.classList.remove('is-resizing-pipeline');
    if (typeof window !== 'undefined' && storageKey) {
      try {
        window.localStorage.setItem(storageKey, String(leftWidthRef.current));
      } catch {
        // ignore
      }
    }
  }

  function onDoubleClick() {
    setLeftWidth(initialWidth);
    leftWidthRef.current = initialWidth;
    if (typeof window !== 'undefined' && storageKey) {
      try {
        window.localStorage.removeItem(storageKey);
      } catch {
        // ignore
      }
    }
  }

  return (
    <div
      ref={containerRef}
      className={`grid min-h-0 h-full w-full gap-0 grid-cols-[minmax(22rem,var(--pipeline-left-width))_16px_minmax(22rem,1fr)] ${className}`}
      style={{'--pipeline-left-width': `${leftWidth}%`} as React.CSSProperties}
    >
      {left}
      <button
        type="button"
        aria-label="Resize pipeline configuration panes"
        title="Drag to resize panes, double-click to reset"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onDoubleClick={onDoubleClick}
        className="group relative flex h-full w-4 cursor-col-resize items-center justify-center border-0 bg-transparent p-0 outline-hidden transition-colors"
      >
        {/* Full-height divider line */}
        <span
          className={`pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2 transition-colors duration-150 ${
            isDragging
              ? 'bg-cursor-primary'
              : 'bg-cursor-hairline group-hover:bg-cursor-hairline-strong group-focus-visible:bg-cursor-primary'
          }`}
        />

        {/* Visual Grab Indicator Handle */}
        <span
          className={`pointer-events-none relative z-10 flex h-7 w-3.5 items-center justify-center rounded-full border bg-cursor-surface-card transition-colors duration-150 ${
            isDragging
              ? 'border-cursor-primary bg-cursor-surface-strong text-cursor-primary'
              : 'border-cursor-hairline text-cursor-muted group-hover:border-cursor-hairline-strong group-hover:bg-cursor-canvas-soft group-hover:text-cursor-ink'
          }`}
        >
          <GripVertical className="h-3 w-3 shrink-0" />
        </span>
      </button>
      {right}
    </div>
  );
}
