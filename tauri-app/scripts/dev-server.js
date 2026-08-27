import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const rootDir = path.resolve(__dirname, "..", "..");
const tauriAppDir = path.resolve(__dirname, "..");
const isWin = process.platform === "win32";

function getPythonPath() {
  const venvPython = isWin
    ? path.join(rootDir, ".venv", "Scripts", "python.exe")
    : path.join(rootDir, ".venv", "bin", "python");

  if (fs.existsSync(venvPython)) {
    return venvPython;
  }
  return isWin ? "python" : "python3";
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

backend.on("close", (code) => {
  if (code !== 0 && code !== null) {
    console.error(`[Dev] Backend exited unexpectedly with code ${code}`);
  }
});
