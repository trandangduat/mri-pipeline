# Fix Remote Start Job Summary Selected Tools

## Goal

Fix remote jobs started from the dialog showing pending scheduled stages as `SKIPPED` / `Not available` until those stages emit events.

Confirmed example:

- Remote job path: `/home/catcd1/neuroflow-test/job_20260814_022334`
- Remote `job_config.json` contains:
  - `pipeline_mode: FreeSurfer 8 + Volume`
  - `reorientation: fs8_reduced54_reorientation`
  - `segmentation: synthseg_freesurfer_fs8`
  - `stats_extraction: fs8_reduced54_stats`
- UI shows stage 1 and stage 3 correctly once events arrive, but stage 9 remains grey/skipped before its events arrive.

## Root Cause

The remote start SSE complete payload in `app_backend/remote.py` returns an incomplete job object:

```py
yield complete_event(True, job={
    "job_id": job_id,
    "target": "Server",
    "state": remote_status.get("state", "running"),
    "remote_job_dir": remote_job_dir,
    "started_at": remote_status.get("started_at"),
    "pid": remote_status.get("pid"),
})
```

It does not include `run_request_summary`, `selected_tools`, `pipeline_mode`, or `input_files`.

The frontend immediately merges this `dialogJob` into the jobs store and navigates to Jobs. At that point the selected job has no scheduled stage metadata, so `deriveImageSteps()` initializes all no-event stages as `not_scheduled`. Runtime events later recover only stages that have emitted a `tool`, so stage 9 stays skipped until its first event.

Remote `list_background_jobs()` can read `job_config.json` and return `run_request_summary`, but that only helps after an explicit refresh. The newly started job must be complete immediately.

## Relevant Files

- `app_backend/remote.py`
- `tauri-app/src/pages/PipelinePage.tsx`
- `tauri-app/src/pages/JobsPage.tsx`
- Tests if available:
  - backend remote service tests, or
  - frontend jobs tests if easier

## Implementation Plan

### 1. Add Run Request Summary To Remote Start Complete Payload

In `app_backend/remote.py`, inside `RemoteJobService.stream_start_job()`, update the `complete_event(True, job=...)` payload around lines 312-319.

Import/use `_make_run_request_summary` from `app_backend.jobs` in this scope.

Suggested implementation:

```py
from app_backend.jobs import _make_run_request_summary

yield complete_event(True, job={
    "job_id": job_id,
    "target": "Server",
    "state": remote_status.get("state", "running"),
    "remote_job_dir": remote_job_dir,
    "job_dir": remote_job_dir,
    "started_at": remote_status.get("started_at"),
    "pid": remote_status.get("pid"),
    "output_dir": run_request.get("output_dir", ""),
    "effective_output_dir": run_request.get("effective_output_dir", run_request.get("output_dir", "")),
    "download_subdir": run_request.get("download_subdir", ""),
    "input_files": run_request.get("input_files") or ([run_request.get("input_file")] if run_request.get("input_file") else []),
    "run_request_summary": _make_run_request_summary(run_request),
})
```

Important:

- Preserve JSON-compatible values only.
- Use `_make_run_request_summary(run_request)` so behavior matches local and remote list job summaries.
- `run_request` already contains normalized preset `selected_tools` from `prepare_run_request`, so `stats_extraction` will be available immediately.

### 2. Ensure Frontend Merge Does Not Drop Existing Summary

In `tauri-app/src/pages/PipelinePage.tsx`, inspect the current `handleDialogClose` merge logic from the previous fixes.

If it inserts `normalized` before filtering existing jobs, make sure it does not replace a richer existing job with a poorer one.

Recommended merge behavior:

```ts
const existingJob = existing.find((j) => String(j.job_id || '') === newJobId) || {};
const mergedStartedJob = {...existingJob, ...normalized};
```

Then sort with the rest of the jobs. This protects against future partial payloads.

After backend fix, the started remote job should already include `run_request_summary`, but this defensive merge is still useful and small.

### 3. Keep The Current Selected Tools Merge Logic

Keep the latest `JobsPage.tsx` selected-tools logic that merges preset tools with job tools for named presets.

That logic is still correct, but it cannot help when the immediate remote start payload has neither `pipeline_mode` nor `run_request_summary`.

Once the complete payload includes `run_request_summary.pipeline_mode` and `run_request_summary.selected_tools`, stages 1, 3, and 9 should be scheduled immediately.

### 4. Optional Frontend Fallback

If there is a simple way to call remote job refresh after navigation without blanking the job list, it can be added, but do not rely on it as the primary fix.

The primary fix is the complete payload containing enough job metadata.

### 5. Tests

Add or update tests if the repo has relevant backend tests. Search for `RemoteJobService`, `stream_start_job`, or remote start stream tests.

Test expectation:

- Mock/stub a successful remote start with a `run_request` containing `pipeline_mode` and `selected_tools`.
- Assert the emitted `complete` event job includes:
  - `target: Server`
  - `remote_job_dir`
  - `run_request_summary.pipeline_mode`
  - `run_request_summary.selected_tools.stats_extraction`
  - `input_files` when present

If backend test setup is too heavy, at minimum run existing tests plus typecheck.

### 6. Verification

Run relevant tests:

```bash
cd tauri-app
npm run typecheck
npm run test -- jobs.test.ts
```

If backend tests are touched, also run the relevant Python tests from repo root.

Manual check:

- Start a new `FreeSurfer 8 + Volume` remote job.
- Click `View Jobs` immediately, without pressing Refresh.
- Stage 1 should be normal/running or success.
- Stage 3 should be normal/pending or running depending on timing.
- Stage 9 `Statistics & Atlas Mapping` should be normal/pending, not grey/skipped, before stats events start.
- Stages with empty selected tools should remain grey/skipped and hide metrics.

## Constraints

- Do not change backend run behavior.
- Do not infer scheduled stages from emitted events only.
- Do not print or commit SSH secrets.
- Keep the fix minimal: enrich job metadata at the remote start boundary.
