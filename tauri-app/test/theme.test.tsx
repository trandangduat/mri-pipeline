import React from 'react';
import {render, screen} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {beforeEach, describe, expect, it, vi} from 'vitest';
import {useThemeStore, applyThemeToDocument} from '../src/stores/themeStore';
import {ThemeToggle} from '../src/components/ThemeToggle';

describe('Theme management & ThemeToggle', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = '';
    document.documentElement.style.colorScheme = '';
  });

  it('applyThemeToDocument sets dark class and colorScheme', () => {
    applyThemeToDocument('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe('dark');

    applyThemeToDocument('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(document.documentElement.style.colorScheme).toBe('light');
  });

  it('themeStore toggles between light and dark and persists to localStorage', () => {
    const store = useThemeStore.getState();

    store.setTheme('light');
    expect(useThemeStore.getState().theme).toBe('light');
    expect(useThemeStore.getState().resolvedTheme).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
    expect(localStorage.getItem('neuroflow-theme')).toBe('light');

    store.toggleTheme();
    expect(useThemeStore.getState().resolvedTheme).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(localStorage.getItem('neuroflow-theme')).toBe('dark');

    store.toggleTheme();
    expect(useThemeStore.getState().resolvedTheme).toBe('light');
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('ThemeToggle renders button with accessible label and toggles theme on click', async () => {
    const user = userEvent.setup();
    useThemeStore.getState().setTheme('light');

    render(<ThemeToggle />);

    const toggleBtn = screen.getByRole('button', {name: /Switch to Dark Mode/i});
    expect(toggleBtn).toBeInTheDocument();

    await user.click(toggleBtn);
    expect(useThemeStore.getState().resolvedTheme).toBe('dark');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(screen.getByRole('button', {name: /Switch to Light Mode/i})).toBeInTheDocument();
  });
});
