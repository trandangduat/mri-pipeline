import {create} from 'zustand';

export interface FontScaleStop {
  value: number;
  label: string;
}

export const FONT_SCALE_STOPS: FontScaleStop[] = [
  {value: 0.8, label: '80%'},
  {value: 0.9, label: '90%'},
  {value: 1.0, label: '100%'},
  {value: 1.1, label: '110%'},
  {value: 1.2, label: '120%'},
];

export const DEFAULT_FONT_SCALE = 1.0;
export const MIN_FONT_SCALE = 0.8;
export const MAX_FONT_SCALE = 1.2;

interface FontScaleState {
  scale: number;
  setScale: (scale: number) => void;
  increaseScale: () => void;
  decreaseScale: () => void;
  resetScale: () => void;
}

const STORAGE_KEY = 'neuroflow-font-scale';

function getInitialScale(): number {
  if (typeof window === 'undefined') return DEFAULT_FONT_SCALE;
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      const parsed = parseFloat(saved);
      if (!isNaN(parsed) && parsed >= MIN_FONT_SCALE && parsed <= MAX_FONT_SCALE) {
        return parsed;
      }
    }
  } catch {
    // fallback if localStorage is unavailable
  }
  return DEFAULT_FONT_SCALE;
}

export function applyFontScaleToDocument(scale: number): void {
  if (typeof document !== 'undefined') {
    const root = document.documentElement;
    root.style.setProperty('--font-scale', String(scale));
    root.style.fontSize = `${14 * scale}px`;
  }
}

export const useFontScaleStore = create<FontScaleState>((set, get) => {
  const initialScale = getInitialScale();
  applyFontScaleToDocument(initialScale);

  return {
    scale: initialScale,
    setScale: (newScale: number) => {
      const clamped = Math.round(Math.min(Math.max(newScale, MIN_FONT_SCALE), MAX_FONT_SCALE) * 10) / 10;
      try {
        localStorage.setItem(STORAGE_KEY, String(clamped));
      } catch {
        // ignore storage errors
      }
      applyFontScaleToDocument(clamped);
      set({scale: clamped});
    },
    increaseScale: () => {
      const current = get().scale;
      const next = Math.min(Math.round((current + 0.1) * 10) / 10, MAX_FONT_SCALE);
      get().setScale(next);
    },
    decreaseScale: () => {
      const current = get().scale;
      const prev = Math.max(Math.round((current - 0.1) * 10) / 10, MIN_FONT_SCALE);
      get().setScale(prev);
    },
    resetScale: () => {
      get().setScale(DEFAULT_FONT_SCALE);
    },
  };
});
