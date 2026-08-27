import React, {useRef, useState, type ReactNode, type PointerEvent} from 'react';
import {GripVertical} from 'lucide-react';

export interface SplitPaneFormProps {
  left: ReactNode;
  right: ReactNode;
  initialWidth?: number;
  min?: number;
  max?: number;
  className?: string;
}

export function SplitPaneForm({
  left,
  right,
  initialWidth = 54,
  min = 32,
  max = 64,
  className = '',
}: SplitPaneFormProps) {
  const [leftWidth, setLeftWidth] = useState(initialWidth);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);

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
    setLeftWidth(Math.min(max, Math.max(min, rawPercent)));
  }

  function onPointerUp(event: PointerEvent<HTMLButtonElement>) {
    draggingRef.current = false;
    setIsDragging(false);
    event.currentTarget.releasePointerCapture(event.pointerId);
    document.body.classList.remove('is-resizing-pipeline');
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
        title="Drag to resize panes"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
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
