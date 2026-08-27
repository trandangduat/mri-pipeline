import React, {useState, useRef, useEffect} from 'react';
import {Type, Check, RotateCcw, Plus, Minus} from 'lucide-react';
import {useFontScaleStore, FONT_SCALE_PRESETS, DEFAULT_FONT_SCALE} from '../stores/fontScaleStore';

export function FontScaleToggle({className = ''}: {className?: string}) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const scale = useFontScaleStore((s) => s.scale);
  const setScale = useFontScaleStore((s) => s.setScale);
  const increaseScale = useFontScaleStore((s) => s.increaseScale);
  const decreaseScale = useFontScaleStore((s) => s.decreaseScale);
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
          className="absolute left-0 top-full mt-1.5 z-50 w-56 rounded-lg border border-cursor-hairline bg-cursor-surface-card p-2 shadow-xl backdrop-blur-md animate-in fade-in-50 zoom-in-95"
          role="menu"
          aria-orientation="vertical"
        >
          {/* Header & Quick Stepper */}
          <div className="mb-2 flex items-center justify-between border-b border-cursor-hairline pb-2 px-1">
            <span className="text-xs font-semibold text-cursor-ink">UI Font Size</span>
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

          {/* Stepper Controls */}
          <div className="mb-2 flex items-center justify-between rounded-md bg-cursor-canvas-soft p-1 border border-cursor-hairline">
            <button
              type="button"
              onClick={decreaseScale}
              disabled={scale <= 0.8}
              className="inline-flex h-7 w-7 items-center justify-center rounded text-cursor-body hover:bg-cursor-surface-card hover:text-cursor-ink disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
              title="Decrease font size"
              aria-label="Decrease font size"
            >
              <Minus className="h-3.5 w-3.5" />
            </button>
            <span className="text-xs font-semibold text-cursor-ink">{percentage}%</span>
            <button
              type="button"
              onClick={increaseScale}
              disabled={scale >= 1.5}
              className="inline-flex h-7 w-7 items-center justify-center rounded text-cursor-body hover:bg-cursor-surface-card hover:text-cursor-ink disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer transition-colors"
              title="Increase font size"
              aria-label="Increase font size"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Presets List */}
          <div className="space-y-0.5">
            {FONT_SCALE_PRESETS.map((preset) => {
              const isSelected = Math.abs(preset.value - scale) < 0.01;
              return (
                <button
                  key={preset.value}
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setScale(preset.value);
                    setIsOpen(false);
                  }}
                  className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-xs text-left transition-colors cursor-pointer ${
                    isSelected
                      ? 'bg-cursor-primary/10 font-medium text-cursor-primary'
                      : 'text-cursor-body hover:bg-cursor-canvas-soft hover:text-cursor-ink'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">{preset.label}</span>
                    <span className="text-[11px] text-cursor-muted">({preset.desc})</span>
                  </div>
                  {isSelected && <Check className="h-3.5 w-3.5 text-cursor-primary" />}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
