# Implement Server Download Outputs

## Goal

Implement `Download Outputs` for jobs whose runtime target is `Server`.

User flow:

1. User clicks `Download Outputs` on the Job Progress page for a terminal Server job.
2. A modal opens and asks for a local save location.
3. User confirms.
4. The modal changes into a copy progress tracker while the backend copies the remote job outputs into a job-specific folder under the selected local folder over SSH/SFTP.
5. On completion, the modal shows success/failure and the final local path.

Do not implement local-runtime downloads in this pass unless needed for safe fallback. For local jobs, keep the existing behavior or a non-copying “local output directory” notice.

## Existing Context

- Job UI: `tauri-app/src/pages/JobsPage.tsx`
- Current `Download Outputs` handler only computes and prints a path. It does not call any API.
- Tauri directory picker is already available via `@tauri-apps/plugin-dialog` and used in `tauri-app/src/pages/PipelinePage.tsx`.
- Streaming API pattern exists in `BackendClient.startPipelineStream()` and backend `_write_sse_headers()` / `_send_sse_event()`.
- Remote copy implementation already exists in `remote/remote_runner.py::download_outputs(local_target_dir)`.
- `RemoteRunner.download_outputs()` uses `self.config.download_subdir` to append batch subdir to the local target.
- `RemoteSSHClient.download_dir()` currently logs each file, but does not provide byte-level progress callbacks.
- `RemoteRunner.count_download_files()` already counts remote output files and job artifacts.
- Remote job summaries include `remote_job_dir`, `output_dir`, `effective_output_dir`, and `download_subdir` in `app_backend/remote.py::_job_summary()` and local registry summaries.
- Remote payload construction: `tauri-app/src/api/runConfig.ts::buildRemotePayload()`.

## Design Direction

Use `DESIGN.md` visual language:

- White card modal, no shadow, warm ink, hairline borders, `rounded-xl`.
- Primary action uses sea blue `bg-cursor-primary` / `hover:bg-cursor-primary-active`.
- Secondary/cancel actions use white surface with hairline borders.
- Progress tracker should feel like an in-product timeline, not a generic spinner-only dialog.
- Use concise copy and monospace path surfaces for local/remote paths.
- Avoid deep shadows and dark IDE-style panels.

Suggested modal layout:

- Title: `Download Server Outputs`
- Intro state:
  - Small Server badge or line: `Remote job: <job id>`
  - Read-only remote path block: remote output path from job metadata.
  - Local destination row: text input plus `Browse` button.
  - Helper text: `A job folder will be created inside this destination.`
  - Preview row: `Final folder: <destination>/<job_id or remote job basename>`.
  - Actions: `Cancel`, `Start Download`
- Progress state:
  - Title changes to `Copying Outputs...`
  - Linear progress bar with percent when total file count is known.
  - Step rows: `Connect`, `Count files`, `Copy outputs`, `Copy artifacts`, `Complete`.
  - Current file/log detail in a small monospace/hairline box, capped height.
  - Disable close while running unless adding cancellation. Cancellation is optional and not required.
- Complete state:
  - Success: `Download Complete`, local path in monospace block, `Close` action.
  - Failure: `Download Failed`, error text, `Back` or `Close` action.

## Backend Plan

### 1. Add Remote Download Streaming Service

In `app_backend/remote.py`, add a method on `RemoteJobService`, for example:

```python
def stream_download_outputs(self, data: dict[str, object]) -> Iterator[SSEEvent]:
```

Expected request fields:

- Remote connection fields parsed by `parse_remote_config()`:
  - `host`, `port`, `username`, `password`, `key_path`, `workspace`, `remote_python`/`python`
- Job fields:
  - `remote_job_dir` required, fallback `job_id` only if it is a path-like remote dir is already consistent with current read events/log behavior.
  - `remote_output_dir` optional. Use if supplied; otherwise `remote_job_dir/outputs`.
  - `local_target_dir` required. This is the parent destination chosen by user, not the final copy directory.
  - `download_subdir` optional. Pass through to `RemoteRunConfig(download_subdir=...)` so existing runner behavior appends it.
  - `job_id` optional but recommended for final local folder naming.

Important destination behavior:

- The selected local destination is a parent folder only.
- Backend must create/use a child folder for this job and copy all files there.
- Final local target should be:
  - `<local_target_dir>/<safe_job_folder>`
  - where `safe_job_folder` is preferably `job_id` if present, otherwise the basename of `remote_job_dir`.
- Sanitize `safe_job_folder` to a filesystem-safe basename: strip slashes, replace path separators and suspicious characters with `_`, and fall back to `server_job_outputs`.
- Pass this computed final folder as `local_target_dir` to `runner.download_outputs()`.
- Avoid double nesting for batch jobs: if `RemoteRunner.download_outputs()` appends `download_subdir`, either do not pass `download_subdir` for this endpoint or intentionally set final folder to `<parent>/<job_id>` and allow batch subdir under it. Required behavior from user: create a job folder inside the chosen destination. The final copied files must not be placed directly in the chosen destination.

Streaming sequence:

1. Validate payload. If invalid, emit failed `step` and `complete` with `ok: false`.
2. Emit `step`: `connect`, `running`, `Connecting to server...`.
3. Compute `final_local_job_dir` from `local_target_dir` plus safe job folder. Create `RemoteRunConfig` with parsed SSH/workspace/python and `output_dir=final_local_job_dir`. Pass `download_subdir` only if the desired final path should include the batch subfolder inside the job folder.
4. Create runner with an `on_log` callback that captures/streams log lines as `step` events. Use a local closure around `self.runner_factory` if practical; otherwise instantiate default runner only if that aligns with existing factory tests. Prefer preserving testability with `runner_factory`.
5. Attach the existing remote job:
   - If runner has `attach_job`, call `runner.attach_job(remote_job_dir, remote_output_dir)`.
   - Otherwise set `runner.remote_job_dir = remote_job_dir` and `runner.remote_output_dir = remote_output_dir` for compatible fakes.
6. Emit `connect` done after initial validation/runner attach. If connection is only opened inside count/download, the step can be marked done before `count` starts.
7. Emit `count`, `running`; call `count_download_files()` if available. On success emit `count`, `done`, detail like `Found N files`. On count failure, do not fail immediately unless needed; emit a warning detail and proceed with unknown total.
8. Emit `copy`, `running`, with `total_files` when known.
9. Call `runner.download_outputs(final_local_job_dir)`.
10. Use `on_log` lines from `RemoteSSHClient` to stream file-level updates. For lines beginning with `Downloading file:` increment a copied file counter and include `copied_files`, `total_files`, and `pct` in the event data.
11. Emit `copy`, `done` after `download_outputs` returns.
12. Emit `complete`, `ok: true`, `local_path`, `copied_files`, `total_files`. `local_path` must be the actual final folder that received files, not the parent selected by the user.
13. On exception, emit failed `step` and `complete` with `ok: false`, sanitized error message.

Important: `SSEEvent` is currently a dict with `event` and `data`. `step_event()` may not include extra fields like counts. Either extend emitted events manually with:

```python
yield {"event": "step", "data": {"step": "copy", "status": "running", "detail": line, "copied_files": copied, "total_files": total, "pct": pct}}
```

or add a small helper in `app_backend/remote.py`. Keep it minimal.

### 2. Add Backend Route

In `app_backend/server.py`:

- Add a POST route in `_handle_post()`:

```python
if self.path == "/remote/jobs/download/stream":
    self._handle_remote_download_stream(payload)
    return
```

- Add `_handle_remote_download_stream()` mirroring `_handle_remote_start_stream()`:

```python
def _handle_remote_download_stream(self, payload: dict[str, JsonValue]) -> None:
    self._write_sse_headers()
    try:
        for sse_event in self._remote_jobs().stream_download_outputs(payload):
            self._send_sse_event(str(sse_event["event"]), sse_event["data"])
    except Exception as exc:
        self._send_sse_event("step", {"step": "error", "status": "failed", "detail": str(exc)})
        self._send_sse_event("complete", {"ok": False, "error": str(exc)})
```

### 3. Progress Granularity

Minimal acceptable progress:

- Total file count from `count_download_files()` if available.
- Copied count incremented by parsing `Downloading file:` log lines.
- Percent = `copied / total` clamped to `0..1`.

Do not attempt byte-level progress unless it is straightforward. File-count progress is enough for this feature.

If `RemoteSSHClient.download_dir()` log lines are insufficient for artifacts, note that `download_file_if_exists()` also logs `Downloading file:`. That should count both outputs and artifacts.

### 4. Security / Safety

- Reject empty `local_target_dir`.
- Reject empty `remote_job_dir`.
- Reject NUL bytes in paths.
- Never copy directly into the selected parent destination; always use a job child folder.
- Rely on `RemoteRunner.attach_job()` / `_require_workspace_child()` for remote workspace guardrails.
- Do not log secrets. Do not echo password/key path in SSE details.
- Local target is user-selected; allow existing directories. Do not delete or clean destination.

## Frontend Plan

### 1. Add API Client Method

In `tauri-app/src/api/client.ts`, add a streaming method similar to `startPipelineStream()`:

```ts
async startRemoteDownloadStream(
  payload: Record<string, unknown>,
  onEvent: (event: string, data: Record<string, unknown>) => void,
  onError: (error: string) => void,
): Promise<void> {
  return this.startPipelineStream('/remote/jobs/download/stream', payload, onEvent, onError);
}
```

No schema parse is needed for SSE, matching the current pipeline streaming approach.

### 2. Add Dialog Component

Create a focused component, for example:

`tauri-app/src/components/DownloadOutputsDialog.tsx`

Props should include:

- `open: boolean`
- `jobId: string`
- `remotePath: string`
- `defaultLocalDir: string`
- `localDir: string`
- `onLocalDirChange(path: string): void`
- `phase: 'select' | 'running' | 'success' | 'failed'`
- `steps: DownloadStep[]`
- `logs: string[]`
- `copiedFiles?: number`
- `totalFiles?: number`
- `finalPath?: string`
- `errorMessage?: string`
- `onBrowse(): void`
- `onStart(): void`
- `onClose(): void`
- optional `canClose`

Keep the component presentational; stream state should live in `JobsPage.tsx` unless the component remains simple enough to own it.

Use icons from `lucide-react`: `Download`, `FolderOpen`, `Loader2`, `CheckCircle2`, `XCircle`, `Circle`.

Use existing `Button` from `@/components/ui/button` or `../components/ui` consistently with `JobsPage.tsx` imports. Avoid adding a new UI library.

### 3. Integrate Dialog in JobsPage

In `tauri-app/src/pages/JobsPage.tsx`:

- Import `open` from `@tauri-apps/plugin-dialog`.
- Reuse or copy small helpers from `PipelinePage.tsx`:
  - `hasTauriInternals()`
  - `selectedDialogPath()`
- Import `useClient()` from `../query/useEnvironment` if not already available.
- Add state for dialog:
  - `downloadDialogOpen`
  - `downloadLocalDir`
  - `downloadPhase`
  - `downloadSteps`
  - `downloadLogs`
  - `downloadCopiedFiles`
  - `downloadTotalFiles`
  - `downloadFinalPath`
  - `downloadError`

Modify `handleDownloadClick()`:

- If no job or not terminal, return.
- If `isServerJob`:
  - Open the modal instead of printing only a path.
  - Set default local dir from current form output dir if present: `formValues.outputDir`, else `job.output_dir`, else empty.
  - If the remote output path display is `N/A`/empty, derive a useful fallback for the dialog from `job.effective_output_dir`, `job.output_dir`, or `<remote_job_dir>/outputs`. Do not show `N/A` in the modal if `remote_job_dir` exists.
  - Reset progress state.
- If local job:
  - Preserve current behavior.

Add `handleBrowseDownloadDir()`:

- If Tauri internals available, call:

```ts
const selected = await open({directory: true, multiple: false});
```

- Set `downloadLocalDir` from selected path.
- If not in Tauri/web mode, the native folder picker is unavailable. The Browse button must still do something visible: focus/select the local destination text input and show a small inline hint like `Type or paste a local folder path in this web preview.` Do not silently do nothing.

Add `handleStartServerDownload()`:

- Validate `downloadLocalDir.trim()`.
- Build payload:

```ts
const remotePayload = buildRemotePayload(formValues);
const remoteJobDir = String(job?.remote_job_dir || job?.job_dir || '');
const rawRemoteOutputDir = String(job?.effective_output_dir || job?.output_dir || '');
const remoteOutputDir = rawRemoteOutputDir && rawRemoteOutputDir !== 'N/A' ? rawRemoteOutputDir : '';
const payload = {
  ...remotePayload,
  job_id: String(job?.job_id || ''),
  remote_job_dir: remoteJobDir,
  remote_output_dir: remoteOutputDir,
  local_target_dir: downloadLocalDir.trim(),
  download_subdir: String(job?.download_subdir || ''),
};
```

Important nuances:

- For remote jobs, `job.effective_output_dir` is the remote output path according to current backend summaries. If this is empty or `N/A`, backend should fall back to `<remote_job_dir>/outputs`.
- Frontend should preview the final local folder as `<selected destination>/<job id>`, matching backend behavior. The backend remains source of truth and returns the final `local_path`.

- Call `client.startRemoteDownloadStream(payload, onEvent, onError)`.
- On `step` event:
  - Update matching step status/detail.
  - Append detail lines to logs when useful.
  - Update counts from `copied_files`, `total_files`, `pct` if present.
- On `complete` event:
  - If `ok`, phase `success`, final path from `local_path`.
  - Else phase `failed`, error message.
- On fetch/stream error: phase `failed`.
- Keep `downloadNotice` in sync on success if desired: `Downloaded to: <local_path>`.

Disable `Download Outputs` while a server download is running.

### 4. Tests

Backend tests:

- Add a unit test in `tests/test_app_backend_server.py` for `/remote/jobs/download/stream` using a fake `RemoteJobService.stream_download_outputs()` that yields a `step` and `complete`. Read the SSE response as text and assert frames contain `event: step` and `event: complete`.
- Add service-level tests in a suitable test file, likely `tests/test_app_backend_server.py` or new `tests/test_app_backend_remote_download.py`, with a fake runner:
  - Valid payload yields count/copy/complete events and calls `download_outputs(local_target_dir)`.
  - Missing `local_target_dir` produces `complete` with `ok: false`.
  - Missing `remote_job_dir` produces `complete` with `ok: false`.
- Reuse style from existing tests; avoid real SSH.

Frontend tests:

- Add/update Vitest tests for `JobsPage` if there is existing test infrastructure. At minimum test the new presentational dialog component:
  - Select phase renders local destination input and Start button disabled without a path.
  - Running phase renders progress counts/percent and disables close/start.
  - Success phase renders final path.
  - Failed phase renders error.
- If testing `JobsPage` directly is too heavy, component tests plus typecheck are acceptable.

### 5. Verification Commands

Run targeted backend tests:

```bash
pytest tests/test_app_backend_server.py tests/test_remote_runner.py
```

Run frontend checks:

```bash
npm run typecheck
npm run test
```

Use workdir `tauri-app` for npm commands.

If full `npm run test` is too broad or flaky, run targeted Vitest file(s) and report what was skipped.

## Edge Cases To Handle

- User cancels the folder picker: keep modal open and local path unchanged.
- Web/non-Tauri Browse button: focus/select manual destination input and show an inline hint; do not silently no-op.
- User closes before starting: allowed.
- User tries to close while running: either disable close or ignore overlay click. Do not leave ambiguous UI state.
- Backend count fails but copy can proceed: show indeterminate/copying state and complete normally if copy succeeds.
- Total files is zero: still call copy; show `Preparing files...` or `0 files found`, and complete if runner succeeds.
- Remote job has `download_subdir`: ensure files still land under the job child folder, not directly under the selected destination. If preserving batch subfolder, final shape can be `<destination>/<job_id>/<download_subdir>/...`.
- Remote job summary has empty `effective_output_dir`: backend fallback should use `<remote_job_dir>/outputs`.

## Non-Goals

- No cancellation/abort of an in-progress SFTP transfer.
- No zip/tar archive creation.
- No local job output copying.
- No byte-level transfer progress unless trivial.

## Expected Files To Touch

- `app_backend/remote.py`
- `app_backend/server.py`
- `remote/remote_runner.py` only if a small compatibility helper is required; avoid large changes.
- `tauri-app/src/api/client.ts`
- `tauri-app/src/pages/JobsPage.tsx`
- `tauri-app/src/components/DownloadOutputsDialog.tsx` new file
- `tauri-app/src/api/schemas.ts` / `tauri-app/src/types/backend.ts` only if adding typed non-SSE responses; likely not required.
- Tests under `tests/` and `tauri-app/test/`.

## Acceptance Criteria

- For Server terminal jobs, clicking `Download Outputs` opens a modal instead of only printing a path.
- User can choose or type a local destination folder.
- Confirming starts a backend SSE download request.
- Modal shows live copy progress from backend events.
- Remote output files and job artifacts are copied using existing `RemoteRunner.download_outputs()` behavior into a job-specific child folder under the chosen destination.
- Success state shows the final local job folder path.
- Modal does not show `N/A` as remote output path when it can derive `<remote_job_dir>/outputs`.
- Browse button has a visible fallback in web/non-Tauri mode.
- Failure state shows a clear error.
- Existing local behavior is not regressed.
- Backend and frontend targeted tests pass.
