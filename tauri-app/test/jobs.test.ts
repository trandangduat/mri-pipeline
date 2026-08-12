import {expect, test} from 'vitest';
import {
  jobProgress,
  extractOutputFiles,
  filterLogLines,
  progressStepEvents,
  stepEventState,
  dotClassForState,
  sidebarDotClass,
} from '../src/lib/jobs';

test('jobProgress maps states to percentages', () => {
  expect(jobProgress('completed', 0)).toBe(100);
  expect(jobProgress('running', 0)).toBe(10);
  expect(jobProgress('running', 5)).toBe(75);
  expect(jobProgress('running', 100)).toBe(90);
  expect(jobProgress('failed', 4)).toBe(0);
});

test('extractOutputFiles flattens event outputs', () => {
  const events = [{stage: 'a', outputs: ['x.nii.gz']}, {stage: 'b'}, {stage: 'c', outputs: ['y.nii.gz', 'z.nii.gz']}];
  expect(extractOutputFiles(events)).toEqual(['x.nii.gz', 'y.nii.gz', 'z.nii.gz']);
});

test('filterLogLines returns original text for empty query', () => {
  expect(filterLogLines('hello\nworld', '')).toBe('hello\nworld');
  expect(filterLogLines('hello\nworld', '  ')).toBe('hello\nworld');
});

test('filterLogLines filters lines by query', () => {
  expect(filterLogLines('hello\nworld\nhello again', 'hello')).toBe('hello\nhello again');
  expect(filterLogLines('hello\nworld', 'WORLD')).toBe('world');
});

test('progressStepEvents keeps only events with a step descriptor', () => {
  const events = [{stage: 'a'}, {kind: 'event'}, {foo: 'bar'}];
  expect(progressStepEvents(events).length).toBe(2);
});

test('stepEventState extracts a normalized event state', () => {
  expect(stepEventState({state: 'RUNNING'})).toBe('running');
  expect(stepEventState({status: 'Done'})).toBe('done');
  expect(stepEventState({kind: 'Launch'})).toBe('launch');
  expect(stepEventState({})).toBe('unknown');
});

test('dotClassForState matches status colors', () => {
  expect(dotClassForState('running')).toMatch(/animate-pulse/);
  expect(dotClassForState('completed')).toMatch(/bg-cursor-semantic-success/);
  expect(dotClassForState('failed')).toMatch(/bg-cursor-semantic-error/);
  expect(dotClassForState('weird')).toMatch(/bg-cursor-muted/);
});

test('sidebarDotClass colors by job state', () => {
  expect(sidebarDotClass({state: 'running'})).toMatch(/animate-pulse/);
  expect(sidebarDotClass({state: 'completed'})).toMatch(/bg-cursor-semantic-success/);
  expect(sidebarDotClass({state: 'failed'})).toMatch(/bg-cursor-semantic-error/);
});
