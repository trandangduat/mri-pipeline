import {expect, test} from 'vitest';
import {ALERT, BUTTON, inputCls, labelCls, statusDotClasses, statusPillClasses} from '../src/lib/uiTokens';

test('BUTTON.variants produce distinct class strings', () => {
  expect(BUTTON.primary).not.toBe(BUTTON.ghost);
  expect(BUTTON.primary).toMatch(/bg-cursor-primary/);
  expect(BUTTON.ghost).toMatch(/bg-cursor-surface-card/);
  expect(BUTTON.danger).toMatch(/bg-cursor-semantic-error/);
});

test('inputCls exposes input styling tokens', () => {
  expect(inputCls).toMatch(/border-cursor-hairline/);
  expect(inputCls).toMatch(/rounded-md/);
});

test('labelCls exposes field label tokens', () => {
  expect(labelCls).toMatch(/text-cursor-body/);
});

test('statusPillClasses maps success states to success color', () => {
  ['installed', 'ok', 'completed', 'done', 'success'].forEach((state) => {
    expect(statusPillClasses(state)).toMatch(/bg-cursor-semantic-success/, state);
    expect(statusPillClasses(state)).toMatch(/rounded-full/);
  });
});

test('statusPillClasses maps error states to error color', () => {
  ['missing', 'failed', 'error'].forEach((state) => {
    expect(statusPillClasses(state)).toMatch(/bg-cursor-semantic-error/, state);
  });
});

test('statusPillClasses maps running/checking to read color', () => {
  expect(statusPillClasses('running')).toMatch(/bg-cursor-timeline-read/);
  expect(statusPillClasses('checking')).toMatch(/bg-cursor-timeline-read/);
});

test('statusPillClasses falls back to hairline for unknown states', () => {
  expect(statusPillClasses('unknown')).toMatch(/bg-cursor-hairline/);
  expect(statusPillClasses('mystery')).toMatch(/bg-cursor-hairline/);
});

test('statusDotClasses colors each runtime state', () => {
  expect(statusDotClasses('running')).toMatch(/animate-pulse/);
  expect(statusDotClasses('completed')).toMatch(/bg-cursor-semantic-success/);
  expect(statusDotClasses('failed')).toMatch(/bg-cursor-semantic-error/);
  expect(statusDotClasses('anything')).toMatch(/bg-cursor-muted/);
});

test('StatusDotLarge renders radar pulse for running and solid dot for completed', async () => {
  const React = await import('react');
  const {render} = await import('@testing-library/react');
  const {StatusDotLarge} = await import('../src/components/ui');

  const {container: runningContainer} = render(React.createElement(StatusDotLarge, {state: 'running'}));
  expect(runningContainer.querySelector('.animate-ping')).not.toBeNull();
  expect(runningContainer.querySelector('.bg-cursor-primary')).not.toBeNull();

  const {container: completedContainer} = render(React.createElement(StatusDotLarge, {state: 'completed'}));
  expect(completedContainer.querySelector('.bg-cursor-semantic-success')).not.toBeNull();
  expect(completedContainer.querySelector('.ring-4')).toBeNull();
});

test('StatusDotLarge renders orange warn dot for stopped state', async () => {
  const React = await import('react');
  const {render} = await import('@testing-library/react');
  const {StatusDotLarge} = await import('../src/components/ui');

  const {container} = render(React.createElement(StatusDotLarge, {state: 'stopped'}));
  expect(container.querySelector('.bg-cursor-semantic-warn')).not.toBeNull();
});

test('ALERT variants reference their semantic tokens', () => {
  expect(ALERT.warning.text).toMatch(/text-cursor-semantic-warn/);
  expect(ALERT.warning.border).toMatch(/border-cursor-semantic-warn/);
  expect(ALERT.error.text).toMatch(/text-cursor-semantic-error/);
  expect(ALERT.error.bg).toMatch(/bg-cursor-semantic-error/);
  expect(ALERT.warning).not.toEqual(ALERT.error);
  expect(ALERT.sm).not.toBe(ALERT.md);
});


