import path from 'node:path';

export function resolvePythonPath({rootDir, isWin, environment = process.env, exists = () => false}) {
  const configured = String(environment.MRI_PIPELINE_PYTHON || '').trim();
  if (configured) return configured;

  const venvPython = isWin
    ? path.join(rootDir, '.venv', 'Scripts', 'python.exe')
    : path.join(rootDir, '.venv', 'bin', 'python');
  if (exists(venvPython)) return venvPython;
  return isWin ? 'python' : 'python3';
}
