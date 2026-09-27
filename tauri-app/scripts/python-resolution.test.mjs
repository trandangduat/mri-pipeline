import assert from 'node:assert/strict';
import test from 'node:test';
import path from 'node:path';
import {resolvePythonPath} from './python-resolution.mjs';

test('development startup uses one deterministic Python resolution order', () => {
  const rootDir = 'C:/project';
  const venv = path.join(rootDir, '.venv', 'Scripts', 'python.exe');
  assert.equal(resolvePythonPath({rootDir, isWin: true, environment: {MRI_PIPELINE_PYTHON: 'C:/custom/python.exe'}, exists: () => true}), 'C:/custom/python.exe');
  assert.equal(resolvePythonPath({rootDir, isWin: true, environment: {}, exists: (candidate) => candidate === venv}), venv);
  assert.equal(resolvePythonPath({rootDir, isWin: true, environment: {}, exists: () => false}), 'python');
});
