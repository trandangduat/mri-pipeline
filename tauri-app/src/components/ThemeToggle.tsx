import React from 'react';
import {Sun, Moon} from 'lucide-react';
import {useThemeStore} from '../stores/themeStore';

export function ThemeToggle({className = ''}: {className?: string}) {
  const resolvedTheme = useThemeStore((s) => s.resolvedTheme);
  const toggleTheme = useThemeStore((s) => s.toggleTheme);

  const isDark = resolvedTheme === 'dark';

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className={`inline-flex h-8 w-8 items-center justify-center rounded-md border border-cursor-hairline bg-cursor-surface-card text-cursor-body transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft hover:text-cursor-ink cursor-pointer ${className}`}
      title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
      aria-label={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
    >
      {isDark ? (
        <Sun className="h-4 w-4 text-amber-400 transition-transform hover:rotate-45" />
      ) : (
        <Moon className="h-4 w-4 text-cursor-body transition-transform hover:-rotate-12" />
      )}
    </button>
  );
}
