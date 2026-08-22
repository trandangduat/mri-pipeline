# Lazy Upload of Local Inputs for Server Runtime

## Goal

When Runtime Target = **Server** and Input Source = **Local**, let the user pick local MRI inputs, a server staging path, and a server output path — then start a remote job where each image is uploaded to the server **only when the NeuroFLOW scheduler schedules it** (lazy upload), with upload progress in the UI, cancel-with-cleanup, and an app-close confirmation that warns the job will be cancelled.

## User-Visible Requirements

- With target = Server, the Input & Output section shows exactly three fields:
  1. **Input location (local)** — native file/folder browse, same UX as today's Local flow (no size limits, no extension filters).
  2. **Input location (server)** — staging path on the server (server browser modal).
  3. **Output location (server)** — server path; NOT validated against workspace rules; created if missing.
- Upload is lazy: image N's data is uploaded when the scheduler schedules N's first stage, not upfront. At most `neuroflow_max_concurrent_tasks` images are uploading/in-flight at once.
- Upload progress (%) per image is visible while the job runs.
- Closing the app mid-job shows a confirm dialog: "A remote job is running; closing will cancel it." Only proceeds if the user agrees.
- Cancelling during upload aborts the transfer AND deletes partial files (`*.part`) on the server.
- Existing flows (Local target; Server source with Server target) behave exactly as before.

## Investigation Summary

All line numbers verified against current code.

### Backend validation / request plumbing
- `app_backend/run_request.py:162-168` — `validate_run_request_input` hard-forbids `run_target == "Server"` with `input_source != "Server"` (line 165-166). Lines 187-190 already skip local file-existence checks for remote jobs.
- `RunRequestInput` dataclass at `run_request.py:21-49` already has `server_output_dir` (line 28) but has **no staging/input-server-dir field**.
- `_base_request` (`run_request.py:215-255`) passes `server_output_dir` through (line 231); no staging field.

### Remote runner
- `remote/remote_runner.py:531-556` — `upload_job()` never uploads images; line 550 logs `"Using MRI input paths already on the server."`. Output dir is forced through `_require_workspace_child` at lines 535-538 (must be relaxed for user-supplied output).
- `RemoteRunConfig` dataclass at `remote_runner.py:60-93` takes input paths verbatim; has `lazy_watch: bool` flag (line 82) as precedent for a mode flag.
- `_write_job_metadata` at `remote_runner.py:615-629` hardcodes `"input_source": "Server"` (line 623).
- `_remote_input_request` at `remote_runner.py:631-666` builds subject maps from local-style paths (`_derive_subject_id`, `build_subject_id_map`).
- `_write_job_config` at `remote_runner.py:668-698` writes `job_config.json` consumed by `job_worker._run_job`.
- Path safety helpers: `_require_workspace_child` (`remote_runner.py:128`), `_job_child_path` (140-143). `read_remote_events` at 915-937 reads `events.jsonl` via SFTP with byte offset. `request_pause` (959-966) writes a `stop_requested` file — existing remote-stop primitive. There is currently **no HTTP route exposing remote stop** (only `/jobs/local/stop`, `app_backend/server.py:136`).

### SSH transport
- `remote/ssh_client.py`: `mkdir_p` 127-137, `expand_path` 139-144, `upload_file` 146-151 (**`self.sftp.put(local, remote)` — paramiko `put` accepts a `callback(transferred, total)` we can pass for progress**), `upload_dir` 153-175 (recursive walk, no progress callback).

### Worker / scheduler
- `pipeline/job_worker.py:115-117` — `image_start_cb` emits `image_start` into `events.jsonl` (`_emit_event` 30-34).
- `job_worker.py:144-149` — guard rejects neuroflow + lazy-watch ("NeuroFLOW scheduler is not supported for lazy-watch jobs yet."). A new lazy-upload mode must not trip this.
- Lazy-watch precedent: `.upload_done` marker polled by worker (`job_worker.py:198`, checked 234-235); `.tmp` files excluded from discovery (line 203).
- `pipeline/neuroflow_adapter.py`:
  - `_ImageRunContext.input_for_stage` 73-83 — only the FIRST executed stage consumes `context.config.input_file`; later stages consume prior-stage outputs. ⇒ one upload per image suffices.
  - Contexts built at 393-424; `image_id == subject_id` (line 415); `ImageSpec.metadata["input_file"]` carries the original path (422).
  - Launch loop 587-621: `scheduler.request_launches(...)` (590-592), launches loop 594-614. `on_image_start` fires at 601-602 **when the scheduler returns the LaunchInstruction**, before `confirm_started` (603) and `executor.submit` (613). This is the approved EARLY scheduling point for a new `image_awaiting_input` event.
  - `_run_launch_stage` defined 446-520; calls `run_pipeline_stage` at 466-476 with `input_for_stage=context.input_for_stage(local_stage)`.
- `NeuroFLOW-private` scheduler lib stays untouched/pure (no file or OS access) — all lazy logic lives in adapter/worker/client.

### Frontend
- `tauri-app/src/pages/PipelinePage.tsx` — `InputOutputSection` at 1703:
  - Effect forcing `inputSource='Local'` when target=Local: 1738-1742; source RadioGroup `disabled={isLocal}` at 1831-1837 (radio itself is NOT disabled for Server target — only forced off for Local target).
  - Stub "Upload data to server" button: handler 1816-1820, render 1843-1852 ("Not wired yet - upload feature coming soon.").
  - Local path fields + native browse handlers: 1891-1939 and 1756-1805 (file browse includes a catch-all `'*'` filter already; folder browse uses `open({directory:true})`).
  - Server-source path fields: only two fields rendered at 1942-1963; `ServerBrowserModal` usage 1969-2026.
- `tauri-app/src/api/runConfig.ts` — `buildRunConfig` 69-117 (`input_source` at 85, `output_dir` at 96); `DEFAULT_FORM_VALUES` 38-67.
- Start flow: `AppHeader.tsx:73-102` posts `{...buildRemotePayload, run_request}` to `/remote/jobs/start/stream` (line 93). SSE consumption in `hooks/useStartPipelineStream.ts` (REMOTE_STEPS list lines 5-14; event handling 41-69). The stream ends at `complete` and navigates to Jobs page — so ongoing lazy-upload progress needs its own channel after start.
- Progress precedent: download progress streams via SSE from `stream_download_outputs` (`app_backend/remote.py:359+`) using a Queue + log-line parsing; rendered by `components/DownloadProgress.tsx`.
- Jobs page polls remote events/log via `readRemoteEventsMutation` (`pages/JobsPage.tsx:472-484`) and parses `image_start` kind in `lib/jobs.ts:158,296,431`.

### App close
- No `onCloseRequested` / close interception exists anywhere in `tauri-app/src`.
- `tauri-app/src-tauri/src/lib.rs:234-238` — `on_window_event(CloseRequested)` **immediately kills the Python backend sidecar**, which would kill any in-flight SFTP uploads without cleanup. Confirmation must happen before this point (frontend `onCloseRequested` + `api.preventDefault()`, or Rust-side dialog before shutdown).

## Implementation Plan

### 1. Backend: relax validation & extend run-request schema

`app_backend/run_request.py`:

- Add field `input_server_dir: str = ""` (staging dir on server) to `RunRequestInput` (after line 28) and parse it in `from_dict`.
- In `validate_run_request_input` (162-168): replace the blanket rejection (165-166) with:

```python
if is_remote and config.input_source == "Local" and not config.input_server_dir.strip():
    return ["Provide an input location on the server (staging directory) for uploaded local inputs."]
```

(Server+Server stays valid unchanged; Local target + Server source keeps its existing rejection.)

- In `_base_request` add `"input_server_dir": config.input_server_dir.strip(),` next to `server_output_dir` (line 231).
- Keep lines 187-190 as-is (local existence checks skipped for Server target — but see step 1b).

1b. **Local source existence check**: since inputs ARE local now, do validate them locally when `is_remote and input_source == "Local"` — reuse the existing mode checks (192-210) instead of early-returning. Simplest: change line 189 `if is_remote:` to `if is_remote and config.input_source != "Local":`.

### 2. Backend: thread new fields into RemoteJobService / RemoteRunConfig

`app_backend/remote.py`:

- In `stream_start_job`, extend the `RemoteRunConfig(...)` construction (267-295) with:
  - `input_source=str(run_request.get("input_source", "Local"))`,
  - `input_server_dir=str(run_request.get("input_server_dir", ""))`,
  - `lazy_upload=bool(run_request.get("input_source") == "Local")` (new dataclass flag).
- Pass-through happens automatically once `RemoteRunConfig` gains the fields.

`remote/remote_runner.py`:

- Add to `RemoteRunConfig` (after line 82): `input_source: str = "Local"`, `input_server_dir: str = ""`, `lazy_upload: bool = False`.
- `upload_job()` (531-556):
  - When `config.server_output_dir` is set, replace `_require_workspace_child` with plain normalization + `ssh.mkdir_p` (create if missing, no workspace containment):
    ```python
    self.remote_output_dir = self._remote_path(ssh, self.config.server_output_dir)
    ssh.mkdir_p(self.remote_output_dir)   # mkdir_p already creates parents (ssh_client.py:127)
    ```
  - When `config.lazy_upload`: rewrite the effective input request so every image points at its staging path. Add helper:
    ```python
    def _staging_path(self, local_input: str, subject_id: str) -> str:
        base = posixpath.join(ssh-expanded(config.input_server_dir), subject_id)
        return posixpath.join(base, Path(local_input).name)   # flat per-subject folder
    ```
    Then in `_remote_input_request()` (631-666), when `config.lazy_upload`, emit the SAME structure (`mode`/`input_files`/`subject_id_map`) but with each `input_files[i]` replaced by its staging path, and include `"lazy_upload": True` plus `"source_paths": {staging_path: local_path, ...}` in `job_config.json` (extend `_write_job_config` dict at 668-698). Keeping original paths only in `source_paths` preserves subject-id derivation (which keys off filenames) and lets events map back to local files client-side.
  - `_write_job_metadata` (615-629): `"input_source": "Server" if not config.lazy_upload else "Local"` (dynamic instead of hardcoded line 623).
  - Log line 550 becomes conditional: `"Inputs will be uploaded lazily as the scheduler schedules them."`

### 3. Worker-side: early `image_awaiting_input` event + marker wait

`pipeline/neuroflow_adapter.py` (adapter may touch filesystem/job_dir; NeuroFLOW-private stays pure):

- Thread a new callback `on_image_awaiting_input(input_file, subject_id, stage_id)` through `run_neuroflow_batch(...)`.
- In the launch loop, inside `if response.launches:` (594), BEFORE `confirm_started` (603) and deduped per image (a set `awaiting_emitted: set[str]`), fire:
  ```python
  if context.image_id not in awaiting_emitted:
      awaiting_emitted.add(context.image_id)
      if on_image_awaiting_input:
          on_image_awaiting_input(context.input_file, context.subject_id, str(launch.stage_id))
  ```
  This overlaps upload with compute of other images and finishes before stage 1 starts.
- In `_run_launch_stage` (446-520), before `run_pipeline_stage` (466), block ONLY when the stage is the first executed one for the image and lazy upload is on:
  ```python
  if req_lazy_upload and context.input_for_stage(local_stage) is None:
      marker = Path(context.config.input_file + ".ready")     # sibling of staged file
      deadline = time.monotonic() + LAZY_UPLOAD_TIMEOUT_SEC   # e.g. env-configurable, default 3600
      while not marker.exists():
          if should_stop(): raise/return cancelled
          if time.monotonic() > deadline:
              fail the stage with clear error "...input upload timed out..."
          time.sleep(1.0)
      _log/_emit_event(job_dir, "input_ready", ...)
  ```
  Pass `req`/`should_stop`/`job_dir` into the closure (already available in `run_neuroflow_batch` scope).

`pipeline/job_worker.py`:

- Replace the blanket guard at 147-149 so it still rejects neuroflow+lazy-watch but allows neuroflow+lazy-upload:
  ```python
  if req.get("neuroflow_enabled"):
      if is_lazy_watch:            # unchanged legacy rejection
          ...
      lazy_upload = bool(req.get("lazy_upload"))
      def image_awaiting_cb(f, sid, stage): 
          _log(job_dir, f"Awaiting upload: {sid}")
          _emit_event(job_dir, "image_awaiting_input", input_file=f, subject_id=sid, stage=stage)
      # pass on_image_awaiting_input=image_awaiting_cb and req into run_neuroflow_batch
  ```
- Non-neuroflow / Local-target flows untouched: they never see `lazy_upload` in their config.

### 4. Client-side lazy-upload orchestrator

New module `remote/lazy_upload.py` (keep `RemoteRunner` focused; orchestrator owns state):

```python
class LazyUploadOrchestrator(threading.Thread):
    """Watches remote events.jsonl; uploads each scheduled image exactly-once;
    writes .ready markers; supports cancel + partial cleanup."""
    def __init__(self, runner_factory, ssh_cfg, plan, on_progress, poll_interval=2.0): ...
        # plan = {staging_path: {"local": Path, "subject_id": str, "size": int}}
        # state per image: PENDING -> UPLOADING -> READY | FAILED | CANCELLED

    # Marker protocol:
    #   1. sftp.put(local, staging_path + ".part", callback=self._progress)   # progress % per image
    #   2. sftp.posix_rename(staging+".part", staging)                        # atomic publish
    #   3. write marker file staging + ".ready" (json: {"local": name, "size": n})
    # Worker waits on ".ready"; rename guarantees the final path is complete.

    def run(self):
        offset = 0
        active: dict[str, UploadHandle] = {}          # staging_path -> handle(thread + sftp ref)
        sem = threading.BoundedSemaphore(plan.max_concurrent)   # batch semantics: <=N in flight
        while not self.cancel_event.is_set():
            res = runner.read_remote_events(offset=offset)       # remote_runner.py:915
            offset = res["next_offset"]
            for ev in res["events"]:
                if ev.get("kind") == "image_awaiting_input":
                    staging = reverse_map[ev["input_file"]]
                    if staging not in active and staging not in done:
                        acquire(sem); active[staging] = spawn_upload(staging)
                elif ev.get("kind") == "image_done":
                    mark_done(ev["subject_id"]); release slot
                elif ev.get("kind") in ("batch_done", "job_exit"): break outer loop
            reap finished threads; on_progress(snapshot)   # [{subject, pct, state}]
            if all states terminal: break
        if self.cancel_event.is_set():
            self.abort_and_cleanup(active)   # join threads, delete "*.part", delete stray ".ready"

    def abort_and_cleanup(self, active):
        for h in active.values():
            h.cancel_flag.set(); h.sftp_channel.close(timeout=2)   # forces put() to raise
            try: ssh.sftp.remove(staging + ".part")
            except OSError: pass
```

- Progress callback: paramiko `put(callback=f)` invokes `f(transferred, total)` — compute `pct = transferred/total*100`, throttled to ~4 updates/sec, pushed to `on_progress`.
- Failure/retry policy (decided): an upload error marks that image **FAILED with reason** (emitted into the UI snapshot and logged), cancels its slot, and the rest of the batch continues. Rationale: one bad/unreadable local file should not kill a long batch; retry can be a manual re-run of failed subjects later (worker timeout surfaces a clear error server-side if the marker never arrives).
- Orchestration lifetime: instantiate in `RemoteJobService.stream_start_job` right after `runner.start_remote_detached()` (`app_backend/remote.py:313`) when lazy mode, register in a service-level dict keyed by `job_id` (same pattern as `register_remote_job` at 320-337). Expose:
  - `POST /remote/jobs/upload/state` → current snapshot (poll fallback),
  - `POST /remote/jobs/upload/cancel` → sets `cancel_event` (used both by Stop button and app-close path).
- Add routes in `app_backend/server.py:_handle_post` (~line 179 block).

### 5. Progress transport to frontend

Mirror the download-progress SSE pattern:

- New endpoint `POST /remote/jobs/upload/stream` handled like `_handle_remote_download_stream` (`server.py:374-383`): subscribes to the registered orchestrator's queue and yields `step` events `{"step":"upload","subject":..., "pct":..., "state":...}` until terminal.
- New client method `streamUploadState(path, payload, onEvent, onError)` in `api/client.ts` (reuse the fetch-SSE reader used by `startPipelineStream`).
- New store slice (e.g. `stores/uploadStore.ts`): `Record<subjectId, {pct:number; state:'pending'|'uploading'|'ready'|'failed'|'cancelled'; error?:string}>` — modeled on `toolsStore.ImageDownloadState` used by `DownloadProgress.tsx`.
- Rendering: reuse the `DownloadProgress` card pattern — a small `LazyUploadProgress.tsx` list under the pipeline status area on the Job detail view in `pages/JobsPage.tsx` (which already polls remote events at 472-484). Show aggregate "Uploading inputs 3/12 · 45%" plus per-image expandable rows.

### 6. UI changes in PipelinePage InputOutputSection

`tauri-app/src/pages/PipelinePage.tsx` (1703-2026):

- Keep the force-Local effect (1738-1742) — it only applies when target=Local, which stays correct.
- Remove the stub button + notice (1843-1852) and `handleUploadToServer`/`uploadNotice` state (1816-1820, 1722) — lazy upload replaces the concept entirely (upload happens automatically at start).
- Field layout:
  - Source radio stays enabled for Server target (already true; only `disabled={isLocal}` at 1836).
  - When `runtimeTarget === 'Server' && inputSource === 'Local'` render THREE fields:
    1. `PathField id="inputPath"` label "Input location (local)" wired to existing `handleLocalBrowseFile` / `handleLocalBrowseFolder` handlers (1756-1789) — no extension filter changes needed (filters already end with `'*'`; keep them permissive).
    2. `PathField id="inputServerDir"` label "Input location (server)" → `setFormField('inputServerDir', v)` + `ServerBrowserModal` (new modal instance mirroring 1969-1996, writing to `inputServerDir`). Placeholder `~/mri-uploads`.
    3. `PathField id="outputDir"` label "Output location (server)" — existing server output modal (1999-2026).
  - Existing Server-source two-field layout (1942-1963) remains for `inputSource === 'Server'`.
- Batch cache key (1726) gains `formValues.inputServerDir` so scans invalidate correctly.

`tauri-app/src/api/runConfig.ts`:

- `PipelineFormValues` += `inputServerDir: string;` (+ default `''` in `DEFAULT_FORM_VALUES` ~line 43).
- `buildRunConfig` += `input_server_dir: formValues.inputServerDir || '',` (next to `output_dir`, line 96).
- Workspace save/load (`AppHeader.tsx:144-192`, `pipelineFormStore.ts:78`): persist/restore `input_server_dir` alongside `input_path` (small addition, keeps round-trips lossless).

### 7. App-close confirmation

Current behavior: `lib.rs:234-238` kills the backend sidecar instantly on CloseRequested — must be gated.

- Frontend-first approach (keeps Rust minimal):
  - In `App.tsx` (or a dedicated `useCloseGuard` hook), subscribe once:
    ```ts
    import {getCurrentWindow} from '@tauri-apps/api/window';
    const unlisten = await getCurrentWindow().onCloseRequested(async (evt) => {
      if (!hasActiveRemoteWork()) return;              // jobsStore/uploadStore check
      evt.preventDefault();
      const ok = await ask('A remote job is running. Closing will CANCEL it...', {kind:'warning'});
      if (!ok) return;
      await client.post('/remote/jobs/upload/cancel', {...});  // abort uploads + delete *.part
      await stopRemoteJob(payload);                            // writes stop_requested via request_pause
      getCurrentWindow().destroy();
    });
    ```
  - Needs Tauri capability additions in `src-tauri/capabilities/default.json`: `core:window:allow-destroy` (and `core:event:default` for listen) — verify exact identifiers against the installed tauri v2 version during implementation.
  - `ask()` comes from `@tauri-apps/plugin-dialog` (already a dependency, `dialog:default` permitted in capabilities).
- Rust fallback/guard: in `lib.rs` CloseRequested handler, only shutdown the sidecar after a short grace delay OR rely on frontend preventDefault; if implementing purely in Rust is preferred, use `tauri_plugin_dialog` blocking ask — but frontend approach avoids blocking the main thread and is recommended.
- Backend safety net regardless of UI: orchestrator threads are daemonic; on process exit paramiko sockets die mid-PUT leaving `*.part`. On next start of an orchestrator for the same staging dir, sweep-and-delete stale `*.part` files older than the current session (cheap best-effort cleanup in `LazyUploadOrchestrator.__init__`).

### 8. Remote job stop wiring

- Add `POST /remote/jobs/stop` route (`server.py`) → `RemoteRunner.request_pause()` (writes `stop_requested`, `remote_runner.py:959-966`) + orchestrator cancel. Wire the Jobs-page Stop button and the app-close path to it. This is also required for "Cancel during upload → abort AND delete partials".

## Tests

Unit-testable (pytest, following `tests/test_app_backend_run_request.py` conventions):

1. `tests/test_app_backend_run_request.py`:
   - Server target + Local source + staging dir present → valid; request contains `input_server_dir`.
   - Server target + Local source + empty staging dir → error mentioning server staging.
   - Local target + Server source → still rejected.
   - Server+Local now runs LOCAL existence checks (missing input file rejected).
2. Marker protocol state machine (`remote/lazy_upload.py`) with a fake SSH/SFTP object (pattern: `FakeSSH` classes in `tests/test_app_backend_remote.py:358,405`):
   - pending→uploading→ready ordering: `.part` removed, final renamed, `.ready` written last.
   - put failure → state FAILED, no `.ready`, no final file, slot released.
   - cancel mid-upload → cancel flag set, `.part` deleted, no `.ready`.
   - concurrency cap respected (≤ max_concurrent simultaneous handles).
   - duplicate `image_awaiting_input` for same image → single upload.
3. Staging-path mapping in `RemoteRunner._remote_input_request` (fake SSH): input_files rewritten to `<staging>/<subject>/<filename>`, `source_paths` maps back, subject ids preserved; metadata `input_source` dynamic.
4. Output-dir relaxation: fake SSH asserting `mkdir_p` called for arbitrary (non-workspace-child) output path and no `ValueError` raised.
5. Worker wait hook: extract the wait loop into a small function `_wait_for_marker(marker, deadline, should_stop)` in `neuroflow_adapter.py` and unit-test timeout/cancel/success paths directly.

Integration checklist (real SSH, manual):

- Single-file job: upload completes before stage 1 logs appear; `events.jsonl` contains `image_awaiting_input` → `input_ready` → `image_start`.
- Batch of 3 with max_concurrent=2: at most 2 concurrent PUTs; third uploads only after a slot frees; total bytes ≈ sum of file sizes (no upfront upload).
- Cancel mid-upload: `.part` gone on server; worker exits via stop_requested.
- App close → warning → agree: uploads aborted, partials cleaned, remote worker stopped; disagree: continues.
- Regression: Local-target run unchanged; Server-source run unchanged; output dir outside workspace gets created.

Frontend: `npm run typecheck` and `npm run test` in `tauri-app/`; backend: `pytest tests/test_app_backend_run_request.py tests/test_app_backend_remote.py tests/test_lazy_upload.py tests/test_job_worker.py tests/test_neuroflow_adapter.py`.

## Risks & Open Questions

- **Event latency vs. stage start race**: polling `events.jsonl` every 2s means the worker may hit the marker-wait briefly. Acceptable (worker just blocks), but a very short first-stage container spin-up could waste GPU/CPU reservation time — the early-emission design minimizes this. Default `LAZY_UPLOAD_TIMEOUT_SEC` = 3600s, env-overridable via `LAZY_UPLOAD_TIMEOUT_SEC` (decided).
- **Staging collisions (DECIDED)**: nest uploads under `<input_server_dir>/<job_id>/<subject>/<filename>` by default — job-scoped isolation prevents cross-job collisions and makes cleanup trivial (`rm -r <staging>/<job_id>` on cancel); the user-chosen path remains the root. Document the layout in the UI placeholder.
- **DICOM series folders (DECIDED — part of core scope)**: an input may be a DICOM series DIRECTORY; the upload unit is then the whole folder. Implementation: walk the folder client-side, upload each file as `<staging>.part/<relpath>`, then write ONE `.ready` marker per subject covering all files after the last part renames into place. Branch in the orchestrator on directory-vs-file input; progress % aggregates bytes across the folder's files.
- **`posix_rename` availability**: OpenSSH SFTP ext should exist everywhere modern; implement a helper with fallback to `remove(final)+rename(part)` if `posix_rename` raises.
- **Backend restart resilience**: if the desktop backend dies (crash, sidecar kill) mid-job, uploads stop and the remote worker eventually times out waiting for markers. Job recovery/re-attach with resume-upload is out of scope here; document as follow-up.
- **Close-guard capability identifiers**: exact Tauri v2 permission names (`core:window:allow-destroy`, event listen) must be validated against the pinned tauri version in `src-tauri/Cargo.toml`.
- **Stop button scope**: adding `/remote/jobs/stop` touches shared job-control surface beyond lazy upload; keep the route thin (delegate to `request_pause`) to limit blast radius.
