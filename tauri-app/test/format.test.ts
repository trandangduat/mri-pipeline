import {expect, test} from 'vitest';
import {formatBytes, formatTime} from '../src/lib/format';

test('formatBytes returns unknown for falsy values', () => {
  expect(formatBytes(0)).toBe('unknown');
  expect(formatBytes(null)).toBe('unknown');
  expect(formatBytes(undefined)).toBe('unknown');
  expect(formatBytes('')).toBe('unknown');
});

test('formatBytes formats GiB with one decimal below 10', () => {
  expect(formatBytes(1024 ** 3)).toBe('1.0 GiB');
  expect(formatBytes(5 * 1024 ** 3)).toBe('5.0 GiB');
});

test('formatBytes drops decimal at or above 10 GiB', () => {
  expect(formatBytes(10 * 1024 ** 3)).toBe('10 GiB');
  expect(formatBytes(16 * 1024 ** 3)).toBe('16 GiB');
});

test('formatTime returns Unknown for missing or invalid values', () => {
  expect(formatTime(0)).toBe('Unknown');
  expect(formatTime(null)).toBe('Unknown');
  expect(formatTime('not-a-date')).toBe('Unknown');
});

test('formatTime renders a valid epoch seconds timestamp', () => {
  const text = formatTime(1600000000);
  expect(typeof text).toBe('string');
  expect(text).not.toBe('Unknown');
});

test('formatTime renders a valid ISO string', () => {
  const text = formatTime('2020-01-01T00:00:00Z');
  expect(typeof text).toBe('string');
  expect(text).not.toBe('Unknown');
});
