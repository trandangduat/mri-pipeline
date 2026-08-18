# Windows Portable NeuroFlow Plan

## Goal

Create a Windows-first portable application distribution for NeuroFlow.

The user wants an "Orange-style" folder that can be copied to a Windows machine and started by double-clicking a shortcut or executable. The app should open the Tauri UI and start the local backend automatically. Docker itself and Docker images are allowed to remain host prerequisites.

## Current Architecture

- Frontend/desktop shell: `tauri-app` using Tauri v2, Vite, React.
- Tauri currently starts the backend in `tauri-app/src-tauri/src/lib.rs` with `python -m app_backend.server --host 127.0.0.1 --port 8765`.
- Tauri bundle resources currently include `app_backend`, `pipeline`, `remote`, `pipeline_runner.py`, and `requirements.txt` in `tauri-app/src-tauri/tauri.conf.json`.
- Python dependencies are small in `requirements.txt`: `pandas`, `sv-ttk`, `Pillow`, `paramiko`, `psutil`.
- Local processing requires host `docker` and `ssh` commands. Do not bundle Docker or Docker images for this first phase.
- Runtime state currently defaults under `PROJECT_ROOT`: `configs`, `outputs/jobs`, and `configs/licenses`.
- Local job workers are launched from Python using `sys.executable -m pipeline.job_worker`.

## Target Distribution Shape

The executor should produce a build process that generates a folder similar to:

```text
dist-portable/windows/NeuroFlowPortable/
  NeuroFlow.exe
  NeuroFlow Debug.lnk          optional
  NeuroFlow.lnk                optional
  backend/
    neuroflow-backend.exe
    ...backend runtime files if using PyInstaller one-dir...
  resources/
    app_backend/
    pipeline/
    remote/
    pipeline_runner.py
    requirements.txt
  config/
  outputs/
    jobs/
  logs/
  licenses/
  README-PORTABLE.txt
```

Exact Tauri resource layout may differ, but the final app must be copyable as one folder.

## Non-Goals For This Phase

- Do not bundle Docker Desktop, Docker Engine, WSL, or Podman.
- Do not bundle or preload Docker image tarballs.
- Do not solve GPU setup on Windows.
- Do not implement macOS or Linux packaging yet.
- Do not add an installer as the primary output. Folder distribution is the target.

## Required User-Facing Behavior

- Double-clicking the Windows app starts the Tauri UI.
- The Python backend starts automatically without requiring a system Python or repo `.venv`.
- Closing the app stops the backend process.
- Local Environment screen should still report Docker and SSH status from the host.
- If Docker is missing or stopped, the app should show the existing environment/tool errors rather than crash.
- Configs, uploaded licenses, job registry, and logs should live inside the portable folder by default.
- Existing development flow on Linux should keep working.

## Implementation Steps

### 1. Add Portable Runtime Path Support

Update Python backend/runtime code to support explicit portable roots using environment variables.

Add a small runtime-path module, for example `app_backend/paths.py`, with behavior like:

- `NEUROFLOW_PORTABLE_ROOT`: root folder for portable runtime data.
- `NEUROFLOW_CONFIG_ROOT`: optional override for saved app configs.
- `NEUROFLOW_JOBS_ROOT`: optional override for local job registry/job metadata.
- `NEUROFLOW_LICENSE_ROOT`: optional override for uploaded licenses.
- If no env vars are set, preserve current defaults.

Use this module in:

- `app_backend.config_store.ConfigStore`
- `app_backend.jobs.LocalJobService`
- `app_backend.licenses.LicenseStore`
- Any other backend code discovered to write under `PROJECT_ROOT` for app-owned state.

Important: pipeline outputs selected by the user should remain controlled by the selected `output_dir`. Do not silently redirect user-selected data outputs into the portable folder.

### 2. Make Backend Worker Launch Portable-Safe

Currently `LocalJobService.start_local_job()` launches workers using `sys.executable -m pipeline.job_worker`.

When the backend is frozen as `neuroflow-backend.exe`, `sys.executable` will point to the backend executable, not a normal Python interpreter. The executor must handle this before packaging.

Preferred minimal approach:

- Add a CLI mode to the backend executable so the same frozen exe can run the worker.
- Example: package an entry point that dispatches:
  - `neuroflow-backend.exe server --host 127.0.0.1 --port 8765`
  - `neuroflow-backend.exe worker --job-config <path>`
- Update `LocalJobService` to accept or resolve a worker command.
- In normal source/dev mode, keep using `[sys.executable, "-m", "pipeline.job_worker", ...]`.
- In frozen mode, use `[sys.executable, "worker", "--job-config", ...]`.

Alternative acceptable approach:

- Build a separate `neuroflow-worker.exe` sidecar.
- Configure backend to launch that exe through an env var such as `NEUROFLOW_WORKER_EXE`.

Choose the smaller reliable implementation after testing PyInstaller behavior.

### 3. Build Python Backend Executable For Windows

Use PyInstaller first unless there is a concrete reason to choose Nuitka.

Add a Windows backend packaging script/spec, for example:

- `packaging/windows/neuroflow-backend.spec`
- `packaging/windows/build-backend.ps1`

The backend executable must include/import:

- `app_backend`
- `pipeline`
- `remote`
- `pipeline_runner.py` if still needed by runtime flows
- dependencies from `requirements.txt`
- hidden imports required by `pandas`, `Pillow`, `paramiko`, and project modules

Prefer PyInstaller one-dir mode for easier debugging and smaller startup risk:

```powershell
pyinstaller packaging/windows/neuroflow-backend.spec --noconfirm
```

Do not use one-file mode initially because this app launches long-running backend plus job workers, and one-file extraction can complicate subprocesses and antivirus behavior.

### 4. Update Tauri Backend Launch For Portable Windows

Update `tauri-app/src-tauri/src/lib.rs` so production Windows builds prefer the bundled backend executable.

Behavior:

- Development mode keeps current behavior using `MRI_PIPELINE_PYTHON`, `.venv`, or `python3`.
- Packaged Windows mode locates `neuroflow-backend.exe` in a bundled sidecar/resource directory.
- Tauri sets these env vars when spawning the backend:
  - `NEUROFLOW_PORTABLE_ROOT=<folder beside NeuroFlow.exe or configured app root>`
  - `NEUROFLOW_CONFIG_ROOT=<portable-root>\config`
  - `NEUROFLOW_JOBS_ROOT=<portable-root>\outputs\jobs`
  - `NEUROFLOW_LICENSE_ROOT=<portable-root>\licenses`
- Tauri starts the backend on `127.0.0.1:8765`.
- Tauri cleanup should still kill the backend child on app shutdown.

Keep the existing `MRI_PIPELINE_ROOT` override for development/testing.

Avoid hardcoding absolute build-machine paths.

### 5. Configure Tauri Bundle Resources/External Binaries

Update `tauri-app/src-tauri/tauri.conf.json` for Windows packaging.

Options:

- Use Tauri external binaries/sidecars if appropriate for `neuroflow-backend.exe`.
- Or bundle the backend folder as resources and locate it via `app.path().resource_dir()`.

The executor should choose the simplest implementation compatible with Tauri v2.

Expected outcome:

- `npm run tauri build` for Windows includes frontend assets and backend runtime.
- The generated app can find backend files after copying the portable folder elsewhere.

### 6. Create Windows Portable Assembly Script

Add a script that creates the final folder after backend and Tauri builds.

Suggested file:

- `packaging/windows/build-portable.ps1`

Responsibilities:

- Verify it is running on Windows.
- Verify Node/npm, Rust/Cargo, Python, and PyInstaller are available.
- Install/build frontend dependencies as needed or clearly document prerequisites.
- Build backend executable.
- Build Tauri app.
- Copy the built `NeuroFlow.exe` and required Tauri runtime files into `dist-portable/windows/NeuroFlowPortable`.
- Copy backend one-dir output into `backend/` if not already included by Tauri resources.
- Create `config`, `outputs/jobs`, `logs`, and `licenses` directories.
- Write `README-PORTABLE.txt` with host prerequisites.
- Optionally create `.lnk` shortcuts with PowerShell COM automation.

Keep the script idempotent: delete/recreate only its own `dist-portable/windows/NeuroFlowPortable` output, not user data or source files.

### 7. Add Portable README

Add `packaging/windows/README-PORTABLE.md` or generated `README-PORTABLE.txt` describing:

- How to start NeuroFlow.
- Host prerequisites: Windows 10/11, Docker Desktop running, required Docker images, SSH client availability, FreeSurfer license if needed.
- How to check images in the Tools Configuration screen.
- Where portable data is stored.
- How to move/copy the folder.
- Known limitations: GPU/WSL/Docker Desktop setup, large Docker images, Apple/Linux builds not included.

### 8. Add Tests

Add or update Python tests for portable path behavior:

- `ConfigStore` respects `NEUROFLOW_CONFIG_ROOT` or injected config root.
- `LocalJobService` respects `NEUROFLOW_JOBS_ROOT` or injected jobs root.
- `LicenseStore` respects `NEUROFLOW_LICENSE_ROOT`.
- Worker command resolution chooses frozen executable mode when simulated.

Add or update Rust tests for backend executable/resource resolution:

- Finds backend executable in expected portable resource/backend path.
- Falls back to current dev Python path when backend executable is unavailable.
- Correct portable env vars are computed without absolute build paths.

Do not require Docker in unit tests.

### 9. Verification Commands

On the development machine, run:

```bash
pytest
cd tauri-app && npm run typecheck
cd tauri-app && npm run test
cd tauri-app/src-tauri && cargo test
```

On a Windows build machine, run:

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build-portable.ps1
```

Manual Windows verification:

- Copy `dist-portable/windows/NeuroFlowPortable` to a different path, such as `C:\Temp\NeuroFlowPortable`.
- Double-click `NeuroFlow.exe` or `NeuroFlow.lnk`.
- Confirm `/health` backend request succeeds through the UI.
- Confirm Environment screen shows Python/backend OK from bundled backend and Docker/SSH from host.
- Confirm app does not require system Python by testing on a machine or VM without Python in `PATH`.
- Confirm config save creates files under `NeuroFlowPortable\config`.
- Confirm uploaded license creates files under `NeuroFlowPortable\licenses`.
- Confirm job registry creates files under `NeuroFlowPortable\outputs\jobs`.
- Confirm Docker-missing case shows a clear error and does not crash.
- Confirm Docker-present/images-present case can start a small available local job or at least image-status check.

## Risks And Decisions

- PyInstaller hidden imports may need iteration, especially for `pandas` and `paramiko`.
- Frozen backend subprocess behavior is the largest technical risk; solve worker launch before polishing packaging.
- Tauri's exact resource/sidecar layout on Windows must be verified on Windows, not inferred from Linux.
- Windows Defender may dislike one-file executables. Prefer one-dir backend packaging first.
- Docker Desktop is not portable and may need admin/WSL setup on the host. This is accepted by the user.

## Acceptance Criteria

- A Windows portable folder can be built by one documented PowerShell command.
- The copied folder starts the app by double-click without system Python.
- Backend starts automatically and is stopped on app exit.
- App-owned config/license/job registry data is written inside the portable folder.
- Docker remains a host prerequisite and failures are handled gracefully.
- Existing dev workflow and tests remain working.
