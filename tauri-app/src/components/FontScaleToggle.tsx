import React, {useState, useRef, useEffect} from 'react';
import {Type, RotateCcw} from 'lucide-react';
import {useFontScaleStore, FONT_SCALE_STOPS, DEFAULT_FONT_SCALE} from '../stores/fontScaleStore';

export function FontScaleToggle({className = ''}: {className?: string}) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const scale = useFontScaleStore((s) => s.scale);
  const setScale = useFontScaleStore((s) => s.setScale);
  const resetScale = useFontScaleStore((s) => s.resetScale);

  const percentage = Math.round(scale * 100);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  return (
    <div ref={containerRef} className="relative inline-flex items-center">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className={`inline-flex h-8 w-8 items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card text-cursor-body transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft hover:text-cursor-ink cursor-pointer ${className} ${
          isOpen ? 'border-cursor-primary text-cursor-primary' : ''
        }`}
        title={`Adjust UI font size (${percentage}%)`}
        aria-label={`Adjust UI font size (${percentage}%)`}
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        <Type className="h-4 w-4 transition-transform hover:scale-110" />
      </button>

      {isOpen && (
        <div
          className="absolute left-0 top-full mt-1.5 z-50 w-64 rounded-lg border border-cursor-hairline bg-cursor-surface-card p-3 animate-in fade-in-50 zoom-in-95"
          role="dialog"
          aria-label="UI Font Size Adjustment"
        >
          {/* Header */}
          <div className="mb-3 flex items-center justify-between border-b border-cursor-hairline pb-2">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-cursor-ink">UI Font Size</span>
              <span className="rounded bg-cursor-primary/10 px-1.5 py-0.5 text-[11px] font-semibold text-cursor-primary">
                {percentage}%
              </span>
            </div>
            {scale !== DEFAULT_FONT_SCALE && (
              <button
                type="button"
                onClick={resetScale}
                className="inline-flex items-center gap-1 text-[11px] text-cursor-muted hover:text-cursor-primary transition-colors cursor-pointer"
                title="Reset to default (100%)"
              >
                <RotateCcw className="h-3 w-3" />
                <span>Reset</span>
              </button>
            )}
          </div>

          {/* Slider with Small Text (left) and Large Text (right) icons */}
          <div className="mb-2 flex items-center gap-3">
            <span
              className="flex h-5 w-5 shrink-0 items-center justify-center text-xs font-semibold text-cursor-muted select-none"
              title="Small text (80%)"
              aria-hidden="true"
            >
              A
            </span>

            <input
              type="range"
              min="0.8"
              max="1.2"
              step="0.1"
              value={scale}
              onChange={(e) => setScale(parseFloat(e.target.value))}
              aria-label="Font scale slider"
              className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-cursor-hairline accent-cursor-primary outline-hidden transition-colors hover:bg-cursor-hairline-strong focus-visible:ring-1 focus-visible:ring-cursor-primary"
            />

            <span
              className="flex h-5 w-5 shrink-0 items-center justify-center text-base font-bold text-cursor-ink select-none"
              title="Large text (120%)"
              aria-hidden="true"
            >
              A
            </span>
          </div>

          {/* Tick Marks & Scale Stops */}
          <div className="flex items-center justify-between px-3.5">
            {FONT_SCALE_STOPS.map((stop) => {
              const isCurrent = Math.abs(stop.value - scale) < 0.01;
              return (
                <button
                  key={stop.value}
                  type="button"
                  onClick={() => setScale(stop.value)}
                  className={`text-[10px] transition-colors cursor-pointer ${
                    isCurrent
                      ? 'font-bold text-cursor-primary'
                      : 'text-cursor-muted hover:text-cursor-ink font-normal'
                  }`}
                >
                  {stop.label}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
