# Tauri Migration Plan

This document is the working migration plan for replacing the Tkinter GUI with a Tauri frontend while keeping the Python backend as the MRI pipeline engine.

## Migration Principles

- Keep Docker, SSH, job execution, reports, presets, and pipeline orchestration in Python.
- Build a headless Python application interface that never imports `tkinter`.
- Make Tauri a client of the headless interface, not a second implementation of pipeline logic.
- Migrate vertically: each phase must leave a runnable and testable slice.
- Preserve remote server safety checks. Any remote path mutation must remain validated by the existing remote runner safeguards or stricter checks.
- Keep the Tkinter GUI available as a fallback until the Tauri app covers local jobs, progress, config, remote jobs, and tool management.

## Phase 0: Migration Contract

Plan:

- Define the seam between the Tauri frontend and Python backend.
- Capture frontend-facing capabilities as JSON-compatible contracts.
- Document guardrails before moving code.

Todo:

- Create this migration plan in `docs/`.
- Select the first headless interface for implementation.
- Keep the first slice small enough to validate without Docker, SSH, or Tauri packaging.

Guardrails before moving to Phase 1:

- The chosen seam does not import `tkinter`.
- The contract is JSON-serializable.
- The contract can be tested through a public interface.
- No existing Tkinter behavior is removed.

Status:

- Completed. The first seam is `app_backend.metadata.get_app_metadata()`.

## Phase 1: Headless Backend Interface

Plan:

- Add a Python package for frontend-facing backend capabilities.
- Start with read-only metadata required by a Tauri configuration screen.
- Add a headless run-request preparation interface for local runs.
- Keep implementation as a thin adapter over existing source-of-truth modules: `pipeline.config`, `pipeline.presets`, `pipeline.registry`, and `pipeline.stats`.

Todo:

- Add `app_backend/metadata.py`.
- Expose pipeline modes, presets, stages, tools, export items, stats vectors, and atlases.
- Strip non-serializable tool fields such as `command_builder`.
- Add tests proving the interface is JSON-serializable and independent of `tkinter`.
- Add `app_backend/run_request.py` for local run validation and request building.
- Return deterministic validation errors instead of showing dialogs.
- Preserve the existing request shape consumed by `pipeline/job_worker.py`.

Guardrails before moving to Phase 2:

- `app_backend` imports no `tkinter` modules.
- `get_app_metadata()` returns plain Python data that `json.dumps()` accepts.
- `prepare_run_request()` returns plain Python data that `json.dumps()` accepts.
- Metadata values are sourced from existing pipeline modules, not duplicated constants.
- Local file, multi-file, DICOM-folder, and batch-directory inputs are covered by tests.
- Remote run/request preparation is explicitly deferred and blocked with a structured validation error.
- Existing tests still pass for touched areas.

Status:

- Metadata slice completed. Local run-request and validation slice completed. Remaining Phase 1 work is to wire the legacy Tkinter controller to this seam or move on to the sidecar strategy.
- Subtask review was used for the local run-request slice. Remote request preparation is intentionally blocked until Phase 6.

## Phase 2: Sidecar Runtime Strategy

Plan:

- Choose how Tauri starts and communicates with the Python backend.
- Prefer a local Python sidecar process with HTTP plus either polling, Server-Sent Events, or WebSocket for progress.
- Keep the initial implementation development-friendly before solving packaging.
- Start with a dependency-free stdlib HTTP sidecar for health, metadata, and run-request preparation.

Todo:

- Use stdlib HTTP for the first sidecar slice to avoid new packaging dependencies.
- Add a development server entrypoint.
- Add health and metadata endpoints.
- Add a run-request preparation endpoint backed by `app_backend.run_request.prepare_run_request()`.
- Add lifecycle management expectations for Tauri spawning and shutdown.

Guardrails before moving to Phase 3:

- The sidecar can start from the repo without Tauri.
- The sidecar exposes health and metadata endpoints.
- The sidecar exposes run-request preparation but no long-running job start endpoint yet.
- The sidecar has deterministic error responses.
- No long-running job endpoint is added before the job contract is defined.
- Request bodies are size-bounded and JSON-only.

Status:

- First stdlib HTTP sidecar slice completed with health, metadata, and run-request preparation endpoints. Long-running job endpoints remain deferred to Phase 3.

## Phase 3: Local Job MVP

Plan:

- Implement the smallest local-run flow in the headless backend.
- Reuse `pipeline/job_worker.py` and the existing job files as the source of progress truth.
- Add local job service methods for start, list, and stop; defer resume/attach to a later Phase 3 slice.
- Keep subprocess launching behind an injectable runner so tests never execute Docker or the real worker.

Todo:

- Define `StartJobRequest` and `JobSummary` contracts.
- Move or wrap Tkinter-free run-request building and validation.
- Start local background jobs.
- List local jobs from the registry.
- Stop local jobs via the existing stop-file mechanism.
- Add sidecar endpoints for local job start/list/stop.
- Add tests for service behavior and endpoint JSON responses.

Guardrails before moving to Phase 4:

- Starting a job does not require importing `ui/`.
- Job status is observable through `job_status.json`, `events.jsonl`, and `run.log`.
- Stop behavior is covered by tests using temporary job directories or mocks.
- No Docker execution is required for unit tests.
- Start job writes `job_config.json`, `launcher_status.json`, `job_status.json`, and a registry entry before returning.
- Stop job only writes a `stop_requested` marker inside the selected local job directory.
- Sidecar does not expose remote job mutation endpoints in this phase.

Status:

- First local job slice completed: backend service and sidecar endpoints support local start/list/stop. Resume/attach/detail progress remain deferred to later Phase 3/4 slices.

## Phase 4: Progress and Logs

Plan:

- Replace the Tkinter progress controller with frontend-readable event streams.
- Treat `events.jsonl` as structured state and `run.log` as human-readable output.
- Start with read-only local job progress endpoints for events and log tailing.
- Resolve jobs through the registry instead of accepting arbitrary filesystem paths.

Todo:

- Add event polling or streaming endpoint.
- Add log tail endpoint with offset support.
- Add frontend progress timeline and log viewer.
- Add CPU/RAM chart data mapping from metrics events.
- Add tests for malformed event lines and bounded log reads.

Guardrails before moving to Phase 5:

- Progress can recover after frontend refresh/restart.
- Log reads are bounded by offset or byte limit.
- Malformed event lines do not crash the backend.
- Multiple jobs can be monitored without shared mutable UI state.
- Progress endpoints are read-only and local-job scoped in this slice.
- Sidecar does not accept arbitrary job paths from the frontend.

Status:

- First read-only local progress slice completed: backend service and sidecar endpoints expose bounded `events.jsonl` and `run.log` reads by `job_id`.

## Phase 5: Config, Presets, and Workspace

Plan:

- Move Tkinter state into plain JSON frontend state and backend validation.
- Reuse existing workspace and preset file formats where possible.
- Start with a headless config store for save/load/list of workspace and preset JSON files.
- Keep config file access confined to the configured `configs/` root.

Todo:

- Add workspace save/load endpoints.
- Add preset save/load endpoints.
- Add run-config validation endpoint.
- Add frontend state store for configuration.
- Add tests for path traversal rejection and password redaction.

Guardrails before moving to Phase 6:

- Workspace JSON remains backward-readable where practical.
- Passwords are not persisted unless explicitly designed and approved.
- Validation messages are deterministic and frontend-friendly.
- Tkinter `StringVar`, `BooleanVar`, and `IntVar` are not used outside legacy UI.
- Config names are sanitized and cannot traverse outside the config root.
- Sidecar config endpoints are JSON-only and do not accept arbitrary file paths.

Status:

- First headless config store slice completed: workspace/preset save, load, and list are available through backend modules and sidecar endpoints with password redaction and path traversal guardrails.

## Phase 6: Remote Server Jobs

Plan:

- Migrate SSH connection, remote browsing, remote run, attach/resume, download, and cleanup after local jobs are stable.
- Keep path validation in `remote/remote_runner.py` as the authoritative safety layer.
- Start with read-only remote config validation and remote job listing.
- Use injected runner factories in tests so no test connects to the professor's server.

Todo:

- Add SSH connection test endpoint.
- Add read-only remote job listing endpoint.
- Add remote input browse endpoint.
- Add remote job start endpoint.
- Add attach/resume endpoint.
- Add remote download and cleanup endpoints.
- Add tests proving remote service calls are mocked and secrets are not echoed.

Guardrails before moving to Phase 7:

- Every destructive remote action validates strict containment in the configured workspace or approved output path.
- Integration tests are mocked by default and never touch the professor's server.
- Any real server integration test is explicitly marked, read-only, or confined to a dedicated test directory.
- Remote errors include safe diagnostics without leaking secrets.
- This first slice exposes no destructive remote operation.
- Remote credentials are accepted only in request bodies and never returned.

Status:

- First read-only remote slice completed: SSH config validation and remote job listing are available through backend modules and sidecar endpoints with mocked tests and no destructive remote operations.

## Phase 7: Tool and Environment Management

Plan:

- Migrate Docker image management and Python/NeuroFLOW environment checks after core job flows work.
- Start with read-only local Docker image status for images referenced by selected tools or all registered tools.
- Keep pull/build/delete and remote image status for later slices.

Todo:

- Add local image status endpoint.
- Add local pull/build/delete endpoints.
- Add remote image status endpoint.
- Add remote Python environment check/install endpoints.
- Add mocked command-runner tests so no Docker daemon is required in unit tests.

Guardrails before moving to Phase 8:

- Long-running tool operations expose progress and cancellation where possible.
- Delete operations are explicit and confirmed by the frontend.
- Unit tests mock Docker and SSH.
- Backend commands do not execute through shell unless existing code requires it and inputs are quoted/validated.
- This first slice exposes no mutating Docker operation.
- Command execution uses argument lists, not shell strings.

Status:

- First read-only local tool slice completed: local Docker image status is available through backend module and sidecar endpoint with mocked tests and no mutating Docker operations.

## Phase 8: Tauri Frontend and Packaging

Plan:

- Build the Tauri frontend against the stable backend interface.
- Solve packaging only after the dev sidecar flow is reliable.
- Start with a Tauri-ready web shell because Rust/Cargo is not available in the current environment.
- Keep the frontend sidecar client isolated so it can be reused by the future Tauri wrapper.

Todo:

- Create Tauri app skeleton.
- Build metadata/config screens.
- Build local job start/progress screens.
- Add sidecar startup/shutdown handling.
- Package Python dependencies and verify Docker CLI availability.
- Add a minimal web shell that calls `/health`, `/metadata`, `/run-request/prepare`, local job, log, and event endpoints.
- Add Node tests for the sidecar API client without requiring Tauri or Cargo.

Guardrails before moving to Phase 9:

- The packaged app starts the Python backend reliably.
- Failure to find Python, Docker, or SSH dependencies is reported clearly.
- The app works on the primary target OS before expanding platform support.
- No remote destructive operation is reachable without explicit confirmation.
- Until Rust/Cargo is available, frontend verification must not depend on native Tauri build steps.
- The frontend must not expose remote destructive operations before Phase 6 mutating endpoints exist.

Status:

- First frontend slice completed: `tauri-app/` contains a Tauri-ready web shell, tested sidecar API client, and native Tauri wrapper files under `tauri-app/src-tauri/`.
- Rust/Cargo was installed per-user with `rustup`; `tauri-cli 2.11.4` is available through npm.
- Native Linux `cargo check` and `npm run tauri -- build` pass after installing Tauri Linux prerequisites. Release binary is produced at `tauri-app/src-tauri/target/release/mri-pipeline-tauri`.
- Tauri startup now attempts to launch the Python backend sidecar automatically, preferring bundled backend resources and falling back to the development checkout or `MRI_PIPELINE_ROOT`.
- Packaged resource lookup is covered by Rust tests for both direct resource roots and Tauri's `_up_/_up_` relative-resource layout.
- Frontend startup waits briefly for the Python sidecar health endpoint before loading metadata, with Node tests covering transient backend startup failures.
- Local dependency status is exposed through `GET /environment/local` and displayed in the Tauri shell for Python, Docker, and SSH.
- The first shell UI has been refactored into responsibility-based sections: Local Run, Jobs, SSH Remote, Tools, and Logs.
- SSH Remote UI supports read-only config validation and remote job listing through the existing safe sidecar endpoints; destructive remote operations remain unavailable.
- Lucide icons are used in the shell with tree-shaken per-icon imports to keep the frontend bundle small.
- The shell UI was redesigned with Geist Sans, a flatter compact visual style, a minimizable sidebar, and three primary tabs: Pipeline Configuration, Tools Configuration, and Jobs Monitor.
- Pipeline Configuration now groups Input/Output, Pipeline Steps, Stats/Atlas Mapping, Runtime/SSH, and a sticky Action Panel.
- Tools Configuration now separates Python environment status, Docker image table controls, and an image log panel. Mutating image actions remain displayed but intentionally disabled at the backend layer for this safety slice.
- Jobs Monitor now separates job list, step progress, terminal log view, flat metrics placeholders, and output download placeholders.
- The desktop shell branding was renamed to NeuroFlow. The sidebar is fixed to full viewport height, supports collapse without overlapping its contents, and the main workspace now owns the side padding.
- Tailwind CSS is integrated through the Vite plugin. Geist Sans is installed with `@fontsource/geist-sans` and bundled locally into the production assets.
- `DESIGN.md` has been applied to the Tauri shell: warm cream canvas, near-black ink, Sea Blue primary actions, hairline cards without shadows, timeline-style semantic pills, and JetBrains Mono for log/code surfaces. Geist Sans remains bundled locally as the practical sans implementation/fallback for the unavailable CursorGothic face.
- Remaining Phase 8 packaging work: bundle or validate the Python runtime/dependencies and surface missing Python, Docker, or SSH dependencies clearly in the UI.
- Current UI can be run from `tauri-app/` with `npm run tauri -- dev`; the release binary is rebuilt by `npm run tauri -- build`.

## Phase 9: Tkinter Retirement

Plan:

- Retire Tkinter only after Tauri covers the same required operational flows.

Todo:

- Mark `gui.py` as legacy or remove it.
- Remove unused Tkinter modules after a fallback window.
- Update docs and commands.
- Keep regression tests for backend interfaces.

Guardrails for completion:

- Tauri supports local runs, progress, config, remote runs, and tool management.
- Existing backend CLI remains available.
- No pipeline behavior regresses during UI removal.
- Release notes explain the migration and fallback status.

Status:

- Not started.
