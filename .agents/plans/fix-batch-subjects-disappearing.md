# Fix: Batch subjects disappear during running remote job

## Problem

On the job progress page, the Batch Subjects Workspace briefly shows image cards then immediately displays "No batch subjects matching the current search or status filter." — even though the job is running with 2 images in the batch.

## Root Causes

### Root Cause 1 (Primary): Polling fetches events from wrong endpoint for remote jobs

**File:** `tauri-app/src/pages/JobsPage.tsx:264-273`

The 2-second polling effect calls `loadJobDetails(selectedJobId)` without passing `targetJob`:

```ts
// Line 269
useEffect(() => {
    if (!selectedJobId || normState !== 'running') return;
    const interval = setInterval(() => {
      void loadJobDetails(selectedJobId);  // ← no targetJob!
    }, 2000);
    ...
```

Inside `loadJobDetails` (line 98), when `targetJob` is undefined:
```ts
const isRemote = String(targetJob?.target || 'Local') === 'Server';  // → false
```

This causes the function to fetch events from the **local** endpoint (`/jobs/local/events`) instead of the remote endpoint (`/remote/jobs/events`). The local endpoint doesn't have the remote job → returns empty events.

**Chain of failure:**
1. Initial page load: `refreshJobs()` fetches jobs, `loadJobDetails(jobId, job)` correctly detects remote → fetches events from remote endpoint → images appear ✓
2. 2 seconds later: polling fires `loadJobDetails(jobId)` without `targetJob` → defaults to local → `setJobEvents([])` first clears events → fetch returns empty → `deriveBatchImages([], job)` returns empty (because `job.input_files` is also empty — see RC2) → "No batch subjects matching..."

This explains the "glimpse then disappear" behavior.

### Root Cause 2: `input_files` is empty for remote "dir" mode jobs with selected files

**Files:**
- `remote/remote_runner.py:575-600` (`_remote_input_request`)
- `remote/remote_runner.py:31-58` (`RemoteRunConfig`)

When the workspace config has `input_mode: "dir"` with `selected_files`, the `prepare_run_request` in `run_request.py` correctly transforms this to `mode: "files"` with `input_files` list (line 118-122). However, the remote runner reconstructs its own request independently:

```python
# remote_runner.py:575-600
def _remote_input_request(self) -> dict:
    if self.config.input_mode == "file" and self.config.input_file:
        return {"mode": "file", "input_file": ...}
    if self.config.input_mode == "files" and self.config.input_files:
        return {"mode": "files", "input_files": ...}
    return {"mode": "dir", "input_dir": ..., "recursive": ...}  # ← no input_files!
```

The `RemoteRunConfig` dataclass doesn't have a `selected_files` field, so `stream_start_job` in `remote.py` (line 251-273) can't pass it through:

```python
remote_config = RemoteRunConfig(
    input_mode=str(run_request.get("mode", "file")),  # "files" after prepare_run_request
    input_file=str(run_request.get("input_file", "")),
    input_files=list(run_request.get("input_files") or []),  # ← this IS populated
    input_dir=str(run_request.get("input_dir", "")),
    ...
)
```

Wait — after `prepare_run_request`, `run_request.get("mode")` is actually `"files"` and `run_request.get("input_files")` IS populated. So `RemoteRunConfig.input_files` should have the files.

Let me re-check the actual `mode` value after `prepare_run_request` for this workspace config:
- Input: `input_mode="dir"`, `selected_files=["path1", "path2"]`
- `prepare_run_request` line 118-122: `if run_config.selected_files:` → `request["mode"] = "files"`, `request["input_files"] = files`
- So `run_request["mode"]` = `"files"`, `run_request["input_files"]` = `["path1", "path2"]`

Then in `stream_start_job`:
```python
remote_config = RemoteRunConfig(
    input_mode="files",
    input_files=["path1", "path2"],
    ...
)
```

And `_remote_input_request` would hit the `"files"` branch and return `input_files`. So the job_config.json on the server SHOULD have `input_files`.

**BUT** — `list_background_jobs` (line 740-821) reads `job_config.json` and constructs:
```python
'input_files': cfg.get('input_files') or ([cfg.get('input_file')] if cfg.get('input_file') else []),
```

If `cfg.get('input_files')` returns the list `["path1", "path2"]`, this should work.

So the `input_files` should actually be populated. The primary issue is Root Cause 1 (polling fetching from wrong endpoint). Without events and with potentially empty `input_files` (if there's an edge case), the UI shows nothing.

**Revised analysis:** The main issue is RC1. The `input_files` may be correctly stored on the server, but since polling fetches from the local endpoint, the frontend never sees them. The job in `latestJobs` (from `listRemoteJobs` → `_job_summary` → `list_background_jobs`) does have `input_files`, but the polling clears events and the local endpoint returns empty events, causing `deriveBatchImages` to rely solely on `job.input_files`. If that's populated, the images should persist. If it's not (due to some edge case), they disappear.

Given the user's symptom (glimpse then disappear), the most likely explanation is:
- `job.input_files` is actually EMPTY in the frontend's `latestJobs`
- This could be because `list_background_jobs` on the server doesn't return `input_files` correctly for this specific job
- OR the `normalizeJob` / frontend processing drops the field

### Root Cause 3 (Minor): BrokenPipeError in backend logs

**File:** `app_backend/server.py:220-221`

When the client disconnects before the server finishes writing the response, `_write_exception` tries to write to a closed socket, causing `BrokenPipeError`. This is non-critical but noisy.

## Fixes

### Fix 1: Pass targetJob to polling loadJobDetails

**File:** `tauri-app/src/pages/JobsPage.tsx`

Change the polling effect to look up the current job object and pass it to `loadJobDetails`:

```ts
// Lines 264-273: Update polling effect
useEffect(() => {
    if (!selectedJobId || normState !== 'running') return;
    const interval = setInterval(() => {
      const jobs = Array.isArray(latestJobs) ? latestJobs : [];
      const targetJob = jobs.find((j) => j && (j as {job_id?: string}).job_id === selectedJobId) as
        | Record<string, unknown>
        | undefined;
      void loadJobDetails(selectedJobId, targetJob);
    }, 2000);
    return () => clearInterval(interval);
}, [selectedJobId, normState, loadJobDetails, latestJobs]);
```

### Fix 2: Ensure input_files is populated for remote "dir+selected_files" jobs

**File:** `remote/remote_runner.py`

In `_remote_input_request`, when `input_mode == "dir"` and there are selected files in the config, treat it as "files" mode:

```python
def _remote_input_request(self) -> dict:
    subject_id_map: dict[str, str] = {}
    if self.config.input_mode == "file" and self.config.input_file:
        # ... existing code ...
    if self.config.input_mode == "files" and self.config.input_files:
        # ... existing code ...
    # NEW: handle "dir" mode with specific selected files
    if self.config.input_files:
        ids = build_subject_id_map(self.config.input_files, self.config.input_dir)
        for path in self.config.input_files:
            subject_id_map[path] = ids.get(path, _derive_subject_id(path))
        return {
            "mode": "files",
            "input_files": list(self.config.input_files),
            "input_dir": self.config.input_dir,
            "subject_id_map": subject_id_map,
        }
    return {
        "mode": "dir",
        "input_dir": self.config.input_dir,
        "recursive": self.config.recursive,
        "subject_id_map": subject_id_map,
    }
```

Note: After `prepare_run_request`, the mode should already be "files" for this case, so `RemoteRunConfig.input_files` should be populated. This fix is a safety net for cases where `input_mode` is "dir" but `input_files` is set.

### Fix 3: Catch BrokenPipeError in _write_exception

**File:** `app_backend/server.py`

Wrap the error response writing in a try/except to handle broken pipes gracefully:

```python
def _write_exception(self, exc: Exception) -> None:
    try:
        self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "Internal server error"})
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
```

## Verification

1. Start a remote job with batch input (2+ images)
2. Navigate to the job progress page
3. Verify that the Batch Subjects Workspace shows the image cards continuously (not just a glimpse)
4. Verify that the cards update their status as the job progresses
5. Check `npm run dev` logs for absence of BrokenPipeError
6. Run existing tests: `cd tauri-app && npm test` and `python -m pytest tests/`

## Files to Modify

1. `tauri-app/src/pages/JobsPage.tsx` — Fix polling to pass targetJob (Fix 1)
2. `remote/remote_runner.py` — Ensure input_files for dir+selected_files (Fix 2)
3. `app_backend/server.py` — Catch BrokenPipeError (Fix 3)
