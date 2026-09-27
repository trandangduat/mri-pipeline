import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {printPythonRemediation, probeBackendPython} from './backend-preflight.mjs';
import {resolvePythonPath} from './python-resolution.mjs';

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const isWin = process.platform === 'win32';
const pythonExe = resolvePythonPath({rootDir, isWin, exists: fs.existsSync});
const probe = probeBackendPython(pythonExe, rootDir);
if (!probe.ok) {
  printPythonRemediation({pythonExe, probe, isWin});
  process.exit(1);
}

const command = process.argv[2];
const args = command === 'cleanup'
  ? ['-m', 'app_backend.dev_cleanup', '--host', '127.0.0.1', '--port', '8765', '--backend-root', '.']
  : ['-m', 'app_backend.server', '--host', '127.0.0.1', '--port', '8765'];
const result = spawnSync(pythonExe, args, {cwd: rootDir, stdio: 'inherit'});
process.exit(result.status ?? 1);
