import assert from 'node:assert/strict';
import {test} from 'node:test';
import {formatBytes, formatTime} from '../src/lib/format.js';

test('formatBytes returns unknown for falsy values', () => {
  assert.equal(formatBytes(0), 'unknown');
  assert.equal(formatBytes(null), 'unknown');
  assert.equal(formatBytes(undefined), 'unknown');
  assert.equal(formatBytes(''), 'unknown');
});

test('formatBytes formats GiB with one decimal below 10', () => {
  assert.equal(formatBytes(1024 ** 3), '1.0 GiB');
  assert.equal(formatBytes(5 * 1024 ** 3), '5.0 GiB');
});

test('formatBytes drops decimal at or above 10 GiB', () => {
  assert.equal(formatBytes(10 * 1024 ** 3), '10 GiB');
  assert.equal(formatBytes(16 * 1024 ** 3), '16 GiB');
});

test('formatTime returns Unknown for missing or invalid values', () => {
  assert.equal(formatTime(0), 'Unknown');
  assert.equal(formatTime(null), 'Unknown');
  assert.equal(formatTime('not-a-date'), 'Unknown');
});

test('formatTime renders a valid epoch seconds timestamp', () => {
  const text = formatTime(1600000000);
  assert.equal(typeof text, 'string');
  assert.notEqual(text, 'Unknown');
});

test('formatTime renders a valid ISO string', () => {
  const text = formatTime('2020-01-01T00:00:00Z');
  assert.equal(typeof text, 'string');
  assert.notEqual(text, 'Unknown');
});
