import {create} from 'zustand';

export interface FontScalePreset {
  value: number;
  label: string;
  desc: string;
}

export const FONT_SCALE_PRESETS: FontScalePreset[] = [
  {value: 0.8, label: '80%', desc: 'Small'},
  {value: 1.0, label: '100%', desc: 'Default'},
  {value: 1.2, label: '120%', desc: 'Large'},
  {value: 1.5, label: '150%', desc: 'Extra large'},
  {value: 2.0, label: '200%', desc: 'Largest'},
];

export const DEFAULT_FONT_SCALE = 1.0;
export const MIN_FONT_SCALE = 0.8;
export const MAX_FONT_SCALE = 2.0;

interface FontScaleState {
  scale: number;
  setScale: (scale: number) => void;
  increaseScale: () => void;
  decreaseScale: () => void;
  resetScale: () => void;
}

const STORAGE_KEY = 'neuroflow-font-scale';

function normalizeFontScale(scale: number): number {
  if (!Number.isFinite(scale)) return DEFAULT_FONT_SCALE;
  const percentage = Math.min(Math.max(scale, MIN_FONT_SCALE), MAX_FONT_SCALE) * 100;
  // Compare percentages so legacy 90% and 110% values round up on a tie.
  return FONT_SCALE_PRESETS.reduce((closest, preset) =>
    Math.abs(preset.value * 100 - percentage) <= Math.abs(closest.value * 100 - percentage) ? preset : closest,
  ).value;
}

function saveScale(scale: number): void {
  try {
    if (typeof window !== 'undefined') window.localStorage.setItem(STORAGE_KEY, String(scale));
  } catch {
    // Keep the current session usable when storage is unavailable.
  }
}

function getInitialScale(): number {
  if (typeof window === 'undefined') return DEFAULT_FONT_SCALE;
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    const scale = normalizeFontScale(saved?.trim() ? Number(saved) : DEFAULT_FONT_SCALE);
    if (saved !== String(scale)) saveScale(scale);
    return scale;
  } catch {
    // fallback if localStorage is unavailable
  }
  return DEFAULT_FONT_SCALE;
}

export function applyFontScaleToDocument(scale: number): void {
  if (typeof document !== 'undefined') {
    const root = document.documentElement;
    root.style.setProperty('--font-scale', String(scale));
  }
}

export const useFontScaleStore = create<FontScaleState>((set, get) => {
  const initialScale = getInitialScale();
  applyFontScaleToDocument(initialScale);

  return {
    scale: initialScale,
    setScale: (newScale: number) => {
      const scale = normalizeFontScale(newScale);
      saveScale(scale);
      applyFontScaleToDocument(scale);
      set({scale});
    },
    increaseScale: () => {
      const next = FONT_SCALE_PRESETS.find((preset) => preset.value > get().scale);
      get().setScale(next?.value ?? MAX_FONT_SCALE);
    },
    decreaseScale: () => {
      const index = FONT_SCALE_PRESETS.findIndex((preset) => preset.value === get().scale);
      get().setScale(FONT_SCALE_PRESETS[index - 1]?.value ?? MIN_FONT_SCALE);
    },
    resetScale: () => {
      get().setScale(DEFAULT_FONT_SCALE);
    },
  };
});
