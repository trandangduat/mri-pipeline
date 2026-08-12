import {expect, test} from 'vitest';
import {BUTTON, inputCls, labelCls, statusDotClasses, statusPillClasses} from '../src/lib/uiTokens';

test('BUTTON.variants produce distinct class strings', () => {
  expect(BUTTON.primary).not.toBe(BUTTON.ghost);
  expect(BUTTON.primary).toMatch(/bg-cursor-primary/);
  expect(BUTTON.ghost).toMatch(/bg-white/);
  expect(BUTTON.danger).toMatch(/bg-cursor-semantic-error/);
});

test('inputCls exposes input styling tokens', () => {
  expect(inputCls).toMatch(/border-cursor-hairline/);
  expect(inputCls).toMatch(/rounded-lg/);
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
