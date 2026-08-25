# Implementation Plan: Fix Stop Job Lifecycle, Subject Success Logic, and Pending Stage Display (Issue #17)

## 1. Overview & Scope

This plan addresses **Issue #17**: `[Job Lifecycle / Job Monitor] Sửa lỗi xử lý Stop Job: sai trạng thái Subject, crash SchedulerNotSafeToClose và hiển thị sai các bước Pending`.

When a user stops a running job (Local or Remote Server):
1. **Premature Subject Success**: In `pipeline/neuroflow_adapter.py`, when a job is interrupted mid-execution, a subject is incorrectly marked as `success=True` because it only checks `all(step.success for step in context.steps)` for steps that ran, ignoring that not all scheduled stages completed.
2. **Scheduler Crash on Stop**: In `pipeline/neuroflow_adapter.py`, stopping while tasks are in the queue causes `scheduler.close()` to throw `SchedulerNotSafeToClose: Workspace contains reserved or running work`, which crashes `job_worker.py` with `exit_code: 1` and marks the overall job as `Failed` instead of `Stopped`.
3. **Frontend Overriding Pending Steps to OK**: In `tauri-app/src/lib/jobs.ts`, receiving `image_done` with `success: true` automatically sets all pending steps to `success` (`OK`), displaying `Waiting` for Elapsed and `Not reported` for CPU/RAM.
4. **Job Terminal State**: Jobs stopped via `stop_requested` must consistently transition to `state: "stopped"` in the local registry, remote runner status, and Job Monitor overview.

---

## 2. Root Cause Analysis

| Component | File | Issue |
|---|---|---|
| **NeuroFLOW Adapter** | `pipeline/neuroflow_adapter.py` | `success = bool(context.steps) and all(step.success for step in context.steps)` evaluates `True` if only 1-2 stages ran and succeeded. Does not verify if all expected pipeline stages ran. |
| **NeuroFLOW Adapter & Worker** | `pipeline/neuroflow_adapter.py`, `pipeline/job_worker.py` | `scheduler.close()` raises unhandled `SchedulerNotSafeToClose` on abort, causing worker to exit with code 1 and record `state: "failed"`. |
| **Worker & Runner State** | `pipeline/job_worker.py`, `remote/remote_runner.py`, `app_backend/jobs.py` | If `stop_requested` exists, job state should be reconciled to `stopped` rather than `failed`. |
| **Frontend Stage History** | `tauri-app/src/lib/jobs.ts` | `deriveImageSteps` loops over `stepMap` on `image_done` and sets `s.status = 'success'` for all pending steps if `event.success === true`. |

---

## 3. Step-by-Step Implementation

### Task 1: Fix Subject Success Calculation in NeuroFLOW Adapter
* **Target File**: `pipeline/neuroflow_adapter.py`
* **Changes**:
  1. Determine total expected stages for each subject based on `selected_tools` / preset pipeline stages.
  2. In `run_neuroflow_batch`, evaluate subject success strictly:
     ```python
     expected_stages = [stage for stage, tool in selected_tools.items() if tool]
     for context in contexts.values():
         executed_stages = {step.stage for step in context.steps}
         all_stages_completed = all(stage in executed_stages for stage in expected_stages)
         all_steps_succeeded = bool(context.steps) and all(step.success for step in context.steps)
         success = all_stages_completed and all_steps_succeeded
         
         if should_stop and should_stop() and not success:
             error_msg = "Job stopped before all pipeline stages completed"
         elif not success:
             error_msg = "one or more NeuroFLOW scheduled steps failed"
         else:
             error_msg = ""
     ```
  3. Emit `image_done` with accurate `success` boolean and descriptive `error`.

---

### Task 2: Handle Graceful Shutdown and `SchedulerNotSafeToClose`
* **Target File**: `pipeline/neuroflow_adapter.py`
* **Changes**:
  1. In `run_neuroflow_batch`, when `should_stop and should_stop()` triggers:
     - Log graceful shutdown request.
     - Call `scheduler.save()` before closing.
     - Catch `SchedulerNotSafeToClose` (or `PersistenceError` / `Exception`) during `scheduler.close()`, logging a graceful termination notice rather than letting the exception crash the process.
     ```python
     try:
         scheduler.save()
     except Exception as exc:
         _log(job_dir, f"NeuroFLOW save warning during shutdown: {exc}")
     try:
         scheduler.close()
     except Exception as exc:
         _log(job_dir, f"NeuroFLOW closed during active stop: {exc}")
     ```

---

### Task 3: Reconcile Job Terminal State to `stopped`
* **Target Files**:
  - `pipeline/job_worker.py`
  - `remote/remote_runner.py`
  - `app_backend/jobs.py`
* **Changes**:
  1. In `pipeline/job_worker.py`:
     - In `_run_job`, if `should_stop()` is true, return 0 (or a designated stopped indicator).
     - In `main()`, check `(job_dir / "stop_requested").exists()`. If true, set `state = "stopped"` and `exit_code = 0` in `_write_status` and `exit_code.txt`.
  2. In `remote/remote_runner.py`:
     - In `remote_status()` and `list_background_jobs()`, check if `stop_requested` file exists in the remote job directory.
     - If `stop_requested` exists and the process is no longer running, set `state = "stopped"` instead of `"failed"`.
  3. In `app_backend/jobs.py`:
     - In `_refresh_local_job()`, if `(job_dir / "stop_requested").exists()`, preserve or set `state = "stopped"`.

---

### Task 4: Fix Frontend Pending Stage Overriding in Stage Timeline
* **Target File**: `tauri-app/src/lib/jobs.ts`
* **Changes**:
  1. In `deriveImageSteps()`:
     - Remove the blind assignment of `s.status = 'success'` for pending steps on `image_done`.
     - Only mark a stage as `success` if it is present in `log_text` as `OK`, or has explicit completion/metrics event.
     - If `event.success === false` or the job is in a stopped/failed state, ensure pending stages retain their status or are marked appropriately (`pending` / `skipped`) without fabricating `OK`.
  2. In `deriveBatchImages()`:
     - When `job.state === 'stopped'`, reconcile non-completed subjects to `failed` or `stopped` instead of leaving them in limbo or marking as success.

---

### Task 5: Unit Tests & Verification
1. **Backend Tests**:
   - Add unit tests in `tests/test_neuroflow_adapter.py` verifying:
     - Subject success is `False` when `should_stop` triggers mid-run (partial stages completed).
     - `SchedulerNotSafeToClose` is handled gracefully and does not raise an unhandled exception.
   - Add unit tests in `tests/test_app_backend_jobs.py` verifying `stop_local_job` and `_refresh_local_job` produce `state: "stopped"`.
2. **Frontend Tests**:
   - Add unit tests in `tauri-app/test/jobs.test.ts` verifying:
     - `deriveImageSteps` does not mark pending stages as `success` when only initial stages complete in `image_done`.
     - `deriveBatchImages` properly reconciles image statuses when job state is `stopped`.
3. **Execution**:
   - Run `/home/trandangduat/mri-pipeline/.venv/bin/pytest tests/`
   - Run `npm test --prefix tauri-app`

---

## 4. Acceptance Criteria

- [ ] When a running NeuroFLOW batch job is stopped, subjects that did not complete all stages report `success: false`.
- [ ] Job worker does not crash with `SchedulerNotSafeToClose` and writes `state: "stopped"`.
- [ ] Job Monitor overview list displays `Stopped` for stopped jobs (not `Failed`).
- [ ] Subject Detail dialog only shows `OK` for stages that actually ran and completed. Unexecuted stages remain `Waiting` / `Pending` without false `OK` pills.
- [ ] All automated tests in Python and TypeScript pass.
