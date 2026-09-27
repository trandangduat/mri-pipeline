import assert from 'node:assert/strict';
import test from 'node:test';
import {probeBackendPython, pythonFailureDiagnostic} from './backend-preflight.mjs';

test('probe distinguishes an unavailable interpreter from failed imports', () => {
  const unavailable = probeBackendPython('python', 'C:/project', () => ({error: new Error('ENOENT'), status: null, stdout: '', stderr: ''}));
  assert.equal(unavailable.kind, 'interpreter-unavailable');
  assert.equal(unavailable.ok, false);

  let calls = 0;
  const missingImports = probeBackendPython('python', 'C:/project', () => {
    calls += 1;
    if (calls === 1) {
      return {error: null, status: 1, stdout: '{"executable":"C:/project/.venv/Scripts/python.exe","base_executable":"C:/Python/python.exe","version":"3.13","missing":["paramiko"]}', stderr: ''};
    }
    return {error: null, status: 0, stdout: 'C:/Python/python.exe', stderr: ''};
  });
  assert.equal(missingImports.kind, 'missing-imports');
  assert.equal(missingImports.basePython, 'C:/Python/python.exe');
});

test('unavailable Python is not misreported as missing dependencies', () => {
  const diagnostic = pythonFailureDiagnostic({
    pythonExe: 'python',
    probe: {kind: 'interpreter-unavailable', details: null, basePython: null, error: 'ENOENT'},
    isWin: true,
  });

  assert.equal(diagnostic.title, 'Backend unavailable');
  assert.match(diagnostic.message, /Python could not be started/);
  assert.doesNotMatch(diagnostic.message, /Missing components/);
  assert.doesNotMatch(diagnostic.message, /py -3/);
});

test('missing imports use a verified base executable without py launcher ambiguity', () => {
  const diagnostic = pythonFailureDiagnostic({
    pythonExe: 'python',
    probe: {
      kind: 'missing-imports',
      details: {executable: 'C:/project/.venv/Scripts/python.exe', missing: ['paramiko']},
      basePython: 'C:/Program Files/Python/python.exe',
      error: '',
    },
    isWin: true,
  });

  assert.equal(diagnostic.title, 'Backend diagnostics');
  assert.match(diagnostic.message, /Missing components: paramiko/);
  assert.match(diagnostic.message, /"C:\/Program Files\/Python\/python\.exe" -m venv/);
  assert.doesNotMatch(diagnostic.message, /py -3/);
});
