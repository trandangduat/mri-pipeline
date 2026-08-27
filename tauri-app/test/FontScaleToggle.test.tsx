import {render, screen, fireEvent} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {describe, it, expect, beforeEach} from 'vitest';
import {FontScaleToggle} from '../src/components/FontScaleToggle';
import {useFontScaleStore, DEFAULT_FONT_SCALE} from '../src/stores/fontScaleStore';

describe('FontScaleToggle and fontScaleStore (Slider)', () => {
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

  it('toggles slider popover on button click', async () => {
    const user = userEvent.setup();
    render(<FontScaleToggle />);

    const button = screen.getByRole('button', {name: /Adjust UI font size/i});
    await user.click(button);

    expect(screen.getByText('UI Font Size')).toBeInTheDocument();
    expect(screen.getByRole('slider', {name: /Font scale slider/i})).toBeInTheDocument();
    expect(screen.getByText('80%')).toBeInTheDocument();
    expect(screen.getByText('90%')).toBeInTheDocument();
    expect(screen.getByText('110%')).toBeInTheDocument();
    expect(screen.getByText('120%')).toBeInTheDocument();
  });

  it('updates scale when moving the slider', async () => {
    const user = userEvent.setup();
    render(<FontScaleToggle />);

    await user.click(screen.getByRole('button', {name: /Adjust UI font size/i}));
    const slider = screen.getByRole('slider', {name: /Font scale slider/i});

    fireEvent.change(slider, {target: {value: '1.2'}});

    expect(useFontScaleStore.getState().scale).toBe(1.2);
    expect(document.documentElement.style.getPropertyValue('--font-scale')).toBe('1.2');
    expect(document.documentElement.style.fontSize).toBe(`${14 * 1.2}px`);
    expect(localStorage.getItem('neuroflow-font-scale')).toBe('1.2');
  });

  it('updates scale when clicking tick mark stops', async () => {
    const user = userEvent.setup();
    render(<FontScaleToggle />);

    await user.click(screen.getByRole('button', {name: /Adjust UI font size/i}));
    
    // Click 80%
    await user.click(screen.getByText('80%'));
    expect(useFontScaleStore.getState().scale).toBe(0.8);
    expect(document.documentElement.style.getPropertyValue('--font-scale')).toBe('0.8');

    // Click 110%
    await user.click(screen.getByText('110%'));
    expect(useFontScaleStore.getState().scale).toBe(1.1);
    expect(document.documentElement.style.getPropertyValue('--font-scale')).toBe('1.1');
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

  it('closes popover when Escape is pressed', async () => {
    const user = userEvent.setup();
    render(<FontScaleToggle />);

    await user.click(screen.getByRole('button', {name: /Adjust UI font size/i}));
    expect(screen.getByText('UI Font Size')).toBeInTheDocument();

    fireEvent.keyDown(document, {key: 'Escape'});
    expect(screen.queryByText('UI Font Size')).toBeNull();
  });
});
