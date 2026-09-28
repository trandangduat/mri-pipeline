# NeuroFlow Windows Portable Build

This directory contains scripts to build a portable Windows distribution of NeuroFlow.

## Release / signing status (read me)

Builds from this tree on a typical developer Windows host are **unsigned internal-test** only (see `UNSIGNED-INTERNAL-TEST.txt` next to artifacts). Public multi-OS release requires Authenticode + timestamp, native Linux AppImage CI, native macOS arm64/x64 signed+notarized DMGs, atlas redistribution rights, and the verification gates listed under **External blockers** in `.agents/plans/cross-platform-single-download-release.md`. Do not claim Linux/macOS artifacts from a Windows-only build machine.


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
2. Stage the complete backend directory at `build/tauri-resources/backend/` for Tauri bundling.
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

- **Tauri** starts `neuroflow-backend.exe server --host 127.0.0.1 --port 8765` from the bundled `backend/` directory and sets `NEUROFLOW_RESOURCE_ROOT` to `backend/_internal` (PyInstaller 6 one-dir contents). Specs keep COLLECT(contents_directory="_internal"); do not point the resource root at the executable parent. Portable/mutable data remains beside the app.
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

## Unsigned internal-test artifact (current Windows smoke)

Public Authenticode signing is **not** available on this machine. Treat all
Windows outputs as **unsigned internal test** only (see also **Release /
signing status** above and External blockers in
`.agents/plans/cross-platform-single-download-release.md`).

| Path | Contents |
| --- | --- |
| `dist/neuroflow-backend/` | PyInstaller one-directory backend (`neuroflow-backend.exe` + `_internal/`). Marked `UNSIGNED-INTERNAL-TEST.txt`. |
| `dist-portable/windows/NeuroFlowPortable/` | Portable shell: `NeuroFlow.exe` beside `backend/` (+ data dirs). Marked unsigned. |
| `tauri-app/src-tauri/target/release/bundle/nsis/NeuroFlow_0.1.0_x64-setup.exe` | Unsigned NSIS setup from `build-portable.ps1`. Marked unsigned beside the installer. |

Verified on this checkout (`build-backend.ps1` + `build-portable.ps1`, 2026-09-28):

- Token auth: `/capabilities/runtime` returns **401** without bearer; with token, Paramiko `ssh.ok == true`.
- `/metadata` `project_root` resolves under `backend\_internal`.
- Brief GUI launch of portable `NeuroFlow.exe`: process stayed up; `/health` on `127.0.0.1:8765` returned ok.
- Do **not** claim Linux/macOS artifacts or a public release from this Windows host.
