import {create} from 'zustand';

export type Theme = 'light' | 'dark' | 'system';

interface ThemeState {
  theme: Theme;
  resolvedTheme: 'light' | 'dark';
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const STORAGE_KEY = 'neuroflow-theme';

function getSystemTheme(): 'light' | 'dark' {
  if (typeof window === 'undefined' || !window.matchMedia) return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'system';
  try {
    const saved = localStorage.getItem(STORAGE_KEY) as Theme | null;
    if (saved === 'light' || saved === 'dark' || saved === 'system') {
      return saved;
    }
  } catch {
    // fallback if localStorage is unavailable
  }
  return 'system';
}

export function applyThemeToDocument(theme: Theme): 'light' | 'dark' {
  const resolved = theme === 'system' ? getSystemTheme() : theme;
  if (typeof document !== 'undefined') {
    const root = document.documentElement;
    if (resolved === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
    root.style.colorScheme = resolved;
  }
  return resolved;
}

export const useThemeStore = create<ThemeState>((set, get) => {
  const initialTheme = getInitialTheme();
  const initialResolved = applyThemeToDocument(initialTheme);

  // Listen to system preference changes
  if (typeof window !== 'undefined' && window.matchMedia) {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    mediaQuery.addEventListener('change', () => {
      const currentTheme = get().theme;
      if (currentTheme === 'system') {
        const newResolved = applyThemeToDocument('system');
        set({resolvedTheme: newResolved});
      }
    });
  }

  return {
    theme: initialTheme,
    resolvedTheme: initialResolved,
    setTheme: (theme: Theme) => {
      try {
        localStorage.setItem(STORAGE_KEY, theme);
      } catch {
        // ignore storage error
      }
      const resolved = applyThemeToDocument(theme);
      set({theme, resolvedTheme: resolved});
    },
    toggleTheme: () => {
      const currentResolved = get().resolvedTheme;
      const nextTheme = currentResolved === 'dark' ? 'light' : 'dark';
      get().setTheme(nextTheme);
    },
  };
});
