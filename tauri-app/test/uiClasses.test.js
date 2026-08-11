import assert from 'node:assert/strict';
import {test} from 'node:test';
import {BUTTON, inputCls, labelCls, statusDotClasses, statusPillClasses} from '../src/lib/uiTokens.js';

test('BUTTON.variants produce distinct class strings', () => {
  assert.notEqual(BUTTON.primary, BUTTON.ghost);
  assert.match(BUTTON.primary, /bg-cursor-primary/);
  assert.match(BUTTON.ghost, /bg-white/);
  assert.match(BUTTON.danger, /bg-cursor-semantic-error/);
});

test('inputCls exposes input styling tokens', () => {
  assert.match(inputCls, /border-cursor-hairline/);
  assert.match(inputCls, /rounded-lg/);
});

test('labelCls exposes field label tokens', () => {
  assert.match(labelCls, /text-cursor-body/);
});

test('statusPillClasses maps success states to success color', () => {
  ['installed', 'ok', 'completed', 'done', 'success'].forEach((state) => {
    const classes = statusPillClasses(state);
    assert.match(classes, /bg-cursor-semantic-success/, state);
    assert.match(classes, /rounded-full/);
  });
});

test('statusPillClasses maps error states to error color', () => {
  ['missing', 'failed', 'error'].forEach((state) => {
    assert.match(statusPillClasses(state), /bg-cursor-semantic-error/, state);
  });
});

test('statusPillClasses maps running/checking to read color', () => {
  assert.match(statusPillClasses('running'), /bg-cursor-timeline-read/);
  assert.match(statusPillClasses('checking'), /bg-cursor-timeline-read/);
});

test('statusPillClasses falls back to hairline for unknown states', () => {
  assert.match(statusPillClasses('unknown'), /bg-cursor-hairline/);
  assert.match(statusPillClasses('mystery'), /bg-cursor-hairline/);
});

test('statusDotClasses colors each runtime state', () => {
  assert.match(statusDotClasses('running'), /animate-pulse/);
  assert.match(statusDotClasses('completed'), /bg-cursor-semantic-success/);
  assert.match(statusDotClasses('failed'), /bg-cursor-semantic-error/);
  assert.match(statusDotClasses('anything'), /bg-cursor-muted/);
});
