import React, {useRef, useState} from 'react';

export function SplitPaneForm({left, right, initialWidth = 56, min = 34, max = 68, className = ''}) {
  const [leftWidth, setLeftWidth] = useState(initialWidth);
  const containerRef = useRef(null);
  const draggingRef = useRef(false);

  function onPointerDown(event) {
    draggingRef.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    document.body.classList.add('is-resizing-pipeline');
  }

  function onPointerMove(event) {
    if (!draggingRef.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const rawPercent = ((event.clientX - rect.left) / rect.width) * 100;
    setLeftWidth(Math.min(max, Math.max(min, rawPercent)));
  }

  function onPointerUp(event) {
    draggingRef.current = false;
    event.currentTarget.releasePointerCapture(event.pointerId);
    document.body.classList.remove('is-resizing-pipeline');
  }

  return (
    <div
      ref={containerRef}
      className={`grid min-h-0 h-[calc(100vh-8rem)] gap-0 grid-cols-[minmax(22rem,var(--pipeline-left-width))_12px_minmax(20rem,1fr)] max-[1080px]:h-auto max-[1080px]:grid-cols-1 ${className}`}
      style={{'--pipeline-left-width': `${leftWidth}%`}}
    >
      {left}
      <button
        type="button"
        aria-label="Resize pipeline configuration panes"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        className="h-full w-3 cursor-col-resize rounded-none border-0 bg-transparent p-0 before:mx-auto before:block before:h-full before:w-px before:bg-cursor-hairline before:content-[''] hover:before:bg-cursor-primary focus-visible:before:bg-cursor-primary max-[1080px]:hidden"
      />
      {right}
    </div>
  );
}
