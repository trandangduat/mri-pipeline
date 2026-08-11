import assert from 'node:assert/strict';
import {test} from 'node:test';
import {jobProgress, extractOutputFiles, filterLogLines, progressStepEvents, stepEventState, dotClassForState, sidebarDotClass} from '../src/lib/jobs.js';

test('jobProgress maps states to percentages', () => {
  assert.equal(jobProgress('completed', 0), 100);
  assert.equal(jobProgress('running', 0), 10);
  assert.equal(jobProgress('running', 5), 75);
  assert.equal(jobProgress('running', 100), 90);
  assert.equal(jobProgress('failed', 4), 0);
});

test('extractOutputFiles flattens event outputs', () => {
  const events = [
    {stage: 'a', outputs: ['x.nii.gz']},
    {stage: 'b'},
    {stage: 'c', outputs: ['y.nii.gz', 'z.nii.gz']},
  ];
  assert.deepEqual(extractOutputFiles(events), ['x.nii.gz', 'y.nii.gz', 'z.nii.gz']);
});

test('filterLogLines returns original text for empty query', () => {
  assert.equal(filterLogLines('hello\nworld', ''), 'hello\nworld');
  assert.equal(filterLogLines('hello\nworld', '  '), 'hello\nworld');
});

test('filterLogLines filters lines by query', () => {
  assert.equal(filterLogLines('hello\nworld\nhello again', 'hello'), 'hello\nhello again');
  assert.equal(filterLogLines('hello\nworld', 'WORLD'), 'world');
});

test('progressStepEvents keeps only events with a step descriptor', () => {
  const events = [{stage: 'a'}, {kind: 'event'}, {foo: 'bar'}];
  assert.equal(progressStepEvents(events).length, 2);
});

test('stepEventState extracts a normalized event state', () => {
  assert.equal(stepEventState({state: 'RUNNING'}), 'running');
  assert.equal(stepEventState({status: 'Done'}), 'done');
  assert.equal(stepEventState({kind: 'Launch'}), 'launch');
  assert.equal(stepEventState({}), 'unknown');
});

test('dotClassForState matches status colors', () => {
  assert.match(dotClassForState('running'), /animate-pulse/);
  assert.match(dotClassForState('completed'), /bg-cursor-semantic-success/);
  assert.match(dotClassForState('failed'), /bg-cursor-semantic-error/);
  assert.match(dotClassForState('weird'), /bg-cursor-muted/);
});

test('sidebarDotClass colors by job state', () => {
  assert.match(sidebarDotClass({state: 'running'}), /animate-pulse/);
  assert.match(sidebarDotClass({state: 'completed'}), /bg-cursor-semantic-success/);
  assert.match(sidebarDotClass({state: 'failed'}), /bg-cursor-semantic-error/);
});
