# NeuroFlow Windows Portable Build

This directory contains scripts to build a portable Windows distribution of NeuroFlow.

## Prerequisites

- **Windows 10/11** (or CI environment)
- **Node.js** (LTS recommended) and npm
- **Rust** toolchain (via [rustup](https://rustup.rs/))
- **Python 3.10+** with pip (a `.venv` in the project root is recommended)
- **PyInstaller** (installed automatically by the build script if missing)

## Build

From the project root, run:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-portable.ps1
```

This will:

1. Build `neuroflow-backend.exe` (PyInstaller one-dir mode) into `dist/neuroflow-backend/`.
2. Copy the backend into `tauri-app/src-tauri/backend/` for Tauri bundling.
3. Build the Tauri desktop app (`npm run tauri build`).
4. Assemble the portable folder at `dist-portable/windows/NeuroFlowPortable/`.

## Portable Folder Structure

```
NeuroFlowPortable/
  NeuroFlow.exe              Main application
  NeuroFlow.lnk              Shortcut
  NeuroFlow Debug.lnk        Debug shortcut (opens console)
  backend/
    neuroflow-backend.exe    Python backend (PyInstaller one-dir)
    ...
  config/                    App configuration (auto-created)
  outputs/
    jobs/                    Job registry (auto-created)
  logs/                      Application logs (auto-created)
  licenses/                  FreeSurfer license files
  README-PORTABLE.txt        End-user instructions
```

## How It Works

- **Tauri** starts `neuroflow-backend.exe server --host 127.0.0.1 --port 8765` from the bundled `backend/` directory.
- Environment variables (`NEUROFLOW_PORTABLE_ROOT`, etc.) are set so all app data is written inside the portable folder.
- When a job is launched, the backend runs `neuroflow-backend.exe worker --job-config <path>` (frozen mode) instead of `python -m pipeline.job_worker`.
- Closing the Tauri window kills the backend process.

## Host Requirements (End User)

- Docker Desktop installed and running
- Docker images pulled for the tools they want to use
- SSH client (included in Windows 10/11)
- FreeSurfer license (if using FreeSurfer-based tools)

## Development Workflow

The portable build does not affect the existing development flow:

- `npm run tauri:dev` still uses the system Python backend.
- `MRI_PIPELINE_ROOT` and `MRI_PIPELINE_PYTHON` env vars still work for dev overrides.
- Linux/macOS development continues to work unchanged.
