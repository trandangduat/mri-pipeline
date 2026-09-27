import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { resolvePythonPath } from "./python-resolution.mjs";
import { printPythonRemediation, probeBackendPython, pythonFailureDiagnostic } from "./backend-preflight.mjs";
import { waitForBackendReadiness } from "./backend-readiness.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const rootDir = path.resolve(__dirname, "..", "..");
const tauriAppDir = path.resolve(__dirname, "..");
const isWin = process.platform === "win32";

function getPythonPath() {
  return resolvePythonPath({ rootDir, isWin, exists: fs.existsSync });
}

function showNativeStartupFailure(diagnostic) {
  const {title, message} = diagnostic;
  if (isWin) {
    const encodedTitle = Buffer.from(title, 'utf8').toString('base64');
    const body = Buffer.from(message, 'utf8').toString('base64');
    const script = [
      'Add-Type -AssemblyName PresentationFramework',
      `$title = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${encodedTitle}'))`,
      `$body = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${body}'))`,
      '[System.Windows.MessageBox]::Show($body, $title, [System.Windows.MessageBoxButton]::OK, [System.Windows.MessageBoxImage]::Error) | Out-Null',
    ].join('; ');
    spawnSync('powershell', ['-NoProfile', '-WindowStyle', 'Hidden', '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')], {stdio: 'ignore'});
  } else {
    spawnSync('zenity', ['--error', `--title=${title}`, `--text=${message}`], {stdio: 'ignore'});
  }
}

function freePort(port) {
  try {
    if (isWin) {
      spawnSync(
        "powershell",
        [
          "-NoProfile",
          "-Command",
          `Get-NetTCPConnection -LocalPort ${port} -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }`,
        ],
        { stdio: "ignore" }
      );
    } else {
      spawnSync("fuser", ["-k", `${port}/tcp`], { stdio: "ignore" });
    }
  } catch (_) {}
}

const pythonExe = getPythonPath();
const viteJs = path.join(tauriAppDir, "node_modules", "vite", "bin", "vite.js");
const backendDir = path.join(tauriAppDir, "src-tauri", "backend");
const iconPng = path.join(tauriAppDir, "src-tauri", "icons", "icon.png");
const iconIco = path.join(tauriAppDir, "src-tauri", "icons", "icon.ico");

if (!fs.existsSync(backendDir)) {
  fs.mkdirSync(backendDir, { recursive: true });
}

if (!fs.existsSync(iconIco) && fs.existsSync(iconPng)) {
  try {
    spawnSync(
      pythonExe,
      [
        "-c",
        `from PIL import Image; img = Image.open(r'${iconPng}').convert('RGBA'); img.save(r'${iconIco}', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])`,
      ],
      { stdio: "ignore" }
    );
  } catch (_) {}
}

console.log(`[Dev] Using Python: ${pythonExe}`);
const pythonProbe = probeBackendPython(pythonExe, rootDir);
if (!pythonProbe.ok) {
  printPythonRemediation({ pythonExe, probe: pythonProbe, isWin });
  showNativeStartupFailure(pythonFailureDiagnostic({pythonExe, probe: pythonProbe, isWin}));
  process.exit(1);
}
console.log(`[Dev] Python probe: ${pythonProbe.details?.executable || pythonExe} (${pythonProbe.details?.version || 'unknown version'}); required backend imports available.`);
console.log("[Dev] Cleaning up stale backend and vite instances...");

try {
  freePort(1420);
  spawnSync(
    pythonExe,
    ["-m", "app_backend.dev_cleanup", "--host", "127.0.0.1", "--port", "8765", "--backend-root", "."],
    { cwd: rootDir, stdio: "inherit" }
  );
} catch (err) {
  console.warn("[Dev] dev_cleanup warning:", err.message);
}

console.log("[Dev] Starting NeuroFlow Backend at http://127.0.0.1:8765...");
const backend = spawn(
  pythonExe,
  ["-m", "app_backend.server", "--host", "127.0.0.1", "--port", "8765"],
  { cwd: rootDir, stdio: "inherit" }
);

const readiness = await waitForBackendReadiness();
if (!readiness.ok) {
  const probe = readiness.missing.length > 0
    ? {...pythonProbe, kind: 'missing-imports', details: {...pythonProbe.details, missing: readiness.missing}}
    : {...pythonProbe, kind: 'interpreter-unavailable', details: pythonProbe.details};
  const diagnostic = readiness.missing.length > 0
    ? pythonFailureDiagnostic({pythonExe, probe, isWin})
    : {
      title: 'Backend unavailable',
      message: [
        'NeuroFlow could not start before its main window was created.',
        '',
        `Selected runtime: ${pythonProbe.details?.executable || pythonExe}`,
        readiness.error,
      ].join('\n'),
    };
  console.error(`[Dev] ${diagnostic.title}: ${diagnostic.message.replaceAll('\n', ' ')}`);
  showNativeStartupFailure(diagnostic);
  try {
    if (isWin && backend.pid) spawnSync('taskkill', ['/pid', backend.pid.toString(), '/f', '/t']);
    else backend.kill('SIGTERM');
  } catch (_) {}
  process.exit(1);
}

console.log("[Dev] Starting Vite frontend server at http://127.0.0.1:1420...");
const vite = spawn(
  process.execPath,
  [viteJs, "--host", "127.0.0.1", "--port", "1420"],
  {
    cwd: tauriAppDir,
    stdio: "inherit",
  }
);

function cleanup() {
  console.log("\n[Dev] Shutting down backend and vite...");
  try {
    if (backend && !backend.killed && backend.pid) {
      if (isWin) {
        spawnSync("taskkill", ["/pid", backend.pid.toString(), "/f", "/t"]);
      } else {
        backend.kill("SIGTERM");
      }
    }
  } catch (e) {}

  try {
    if (vite && !vite.killed && vite.pid) {
      if (isWin) {
        spawnSync("taskkill", ["/pid", vite.pid.toString(), "/f", "/t"]);
      } else {
        vite.kill("SIGTERM");
      }
    }
  } catch (e) {}
}

process.on("SIGINT", () => {
  cleanup();
  process.exit(0);
});

process.on("SIGTERM", () => {
  cleanup();
  process.exit(0);
});

vite.on("close", (code) => {
  cleanup();
  process.exit(code ?? 0);
});

backend?.on("close", (code) => {
  if (code !== 0 && code !== null) {
    console.error(`[Dev] Backend exited unexpectedly with code ${code}`);
  }
});
