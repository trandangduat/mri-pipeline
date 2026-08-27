import {render, screen, fireEvent} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {describe, it, expect, beforeEach} from 'vitest';
import {FontScaleToggle} from '../src/components/FontScaleToggle';
import {useFontScaleStore, DEFAULT_FONT_SCALE} from '../src/stores/fontScaleStore';

describe('FontScaleToggle and fontScaleStore (Presets)', () => {
  beforeEach(() => {
    useFontScaleStore.getState().resetScale();
    localStorage.clear();
  });

  it('renders the font scale toggle button with initial percentage', () => {
    render(<FontScaleToggle />);
    const button = screen.getByRole('button', {name: /Adjust UI font size/i});
    expect(button).toBeInTheDocument();
    expect(button).toHaveAttribute('aria-haspopup', 'true');
    expect(button).toHaveAttribute('aria-expanded', 'false');
  });

  it('toggles presets menu on button click', async () => {
    const user = userEvent.setup();
    render(<FontScaleToggle />);

    const button = screen.getByRole('button', {name: /Adjust UI font size/i});
    await user.click(button);

    expect(screen.getByText('UI Font Size')).toBeInTheDocument();
    expect(screen.getByText('80%')).toBeInTheDocument();
    expect(screen.getByText('90%')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText('110%')).toBeInTheDocument();
    expect(screen.getByText('120%')).toBeInTheDocument();
  });

  it('updates scale when selecting a preset item', async () => {
    const user = userEvent.setup();
    render(<FontScaleToggle />);

    await user.click(screen.getByRole('button', {name: /Adjust UI font size/i}));
    await user.click(screen.getByRole('menuitem', {name: /120%/i}));

    expect(useFontScaleStore.getState().scale).toBe(1.2);
    expect(document.documentElement.style.getPropertyValue('--font-scale')).toBe('1.2');
    expect(localStorage.getItem('neuroflow-font-scale')).toBe('1.2');
  });

  it('resets scale to default 100%', async () => {
    const user = userEvent.setup();
    useFontScaleStore.getState().setScale(1.2);

    render(<FontScaleToggle />);
    await user.click(screen.getByRole('button', {name: /Adjust UI font size/i}));

    const resetButton = screen.getByRole('button', {name: /Reset/i});
    expect(resetButton).toBeInTheDocument();
    await user.click(resetButton);

    expect(useFontScaleStore.getState().scale).toBe(DEFAULT_FONT_SCALE);
    expect(document.documentElement.style.getPropertyValue('--font-scale')).toBe('1');
  });

  it('closes menu when Escape is pressed', async () => {
    const user = userEvent.setup();
    render(<FontScaleToggle />);

    await user.click(screen.getByRole('button', {name: /Adjust UI font size/i}));
    expect(screen.getByText('UI Font Size')).toBeInTheDocument();

    fireEvent.keyDown(document, {key: 'Escape'});
    expect(screen.queryByText('UI Font Size')).toBeNull();
  });
});
