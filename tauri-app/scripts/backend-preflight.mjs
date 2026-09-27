import {spawnSync} from 'node:child_process';

const REQUIRED_IMPORTS = ['pandas', 'PIL', 'paramiko', 'psutil', 'yaml'];

export function probeBackendPython(pythonExe, rootDir, run = spawnSync) {
  const probe = [
    'import importlib, json, sys',
    `required = ${JSON.stringify(REQUIRED_IMPORTS)}`,
    'missing = []',
    'for name in required:',
    '    try: importlib.import_module(name)',
    '    except Exception: missing.append(name)',
    "print(json.dumps({'executable': sys.executable, 'base_executable': getattr(sys, '_base_executable', sys.executable), 'version': sys.version.split()[0], 'missing': missing}))",
    'raise SystemExit(1 if missing else 0)',
  ].join('\n');
  const result = run(pythonExe, ['-c', probe], {cwd: rootDir, encoding: 'utf8'});
  let details = null;
  try { details = JSON.parse(String(result.stdout || '').trim()); } catch (_) {}
  if (result.error || !details) {
    return {ok: false, kind: 'interpreter-unavailable', details: null, basePython: null, error: result.error?.message || String(result.stderr || '').trim()};
  }

  const missing = Array.isArray(details.missing) ? details.missing : [];
  const baseCandidate = String(details.base_executable || '').trim();
  const baseResult = baseCandidate
    ? run(baseCandidate, ['-c', 'import sys; print(sys.executable)'], {cwd: rootDir, encoding: 'utf8'})
    : null;
  const basePython = baseResult && !baseResult.error && baseResult.status === 0 ? baseCandidate : null;
  return {
    ok: result.status === 0 && missing.length === 0,
    kind: missing.length > 0 ? 'missing-imports' : 'ready',
    details,
    basePython,
    error: String(result.stderr || '').trim(),
  };
}

function quoteCommandPath(value) {
  return value.includes(' ') ? `"${value}"` : value;
}

export function pythonFailureDiagnostic({pythonExe, probe, isWin}) {
  const runtime = probe.details?.executable || pythonExe;
  if (probe.kind === 'interpreter-unavailable') {
    return {
      title: 'Backend unavailable',
      message: [
        'NeuroFlow could not start before its main window was created.',
        '',
        `Selected runtime: ${runtime}`,
        'Python could not be started, so backend dependencies were not checked.',
        '',
        'Repair or install Python, then restart NeuroFlow.',
      ].join('\n'),
    };
  }

  const missing = probe.details?.missing?.join(', ') || 'required backend dependencies';
  const setup = probe.basePython
    ? isWin
      ? `${quoteCommandPath(probe.basePython)} -m venv .venv && .venv\\Scripts\\python.exe -m pip install -r requirements.txt`
      : `${quoteCommandPath(probe.basePython)} -m venv .venv && .venv/bin/python -m pip install -r requirements.txt`
    : null;
  return {
    title: 'Backend diagnostics',
    message: [
      'NeuroFlow could not start before its main window was created.',
      '',
      `Selected runtime: ${runtime}`,
      `Missing components: ${missing}.`,
      '',
      ...(setup ? ['Create the project environment with:', setup] : ['Repair or install Python, then restart NeuroFlow.']),
    ].join('\n'),
  };
}

export function printPythonRemediation({pythonExe, probe, isWin}) {
  const diagnostic = pythonFailureDiagnostic({pythonExe, probe, isWin});
  console.error(`[Dev] ${diagnostic.title}: ${diagnostic.message.replaceAll('\n', ' ')}`);
  if (probe.error) console.error(`[Dev] Probe detail: ${probe.error}`);
}
