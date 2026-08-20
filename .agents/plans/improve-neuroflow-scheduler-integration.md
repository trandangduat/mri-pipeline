# Improve NeuroFLOW Scheduler Integration (UI & Backend Controller)

## 1. Goal

Upgrade the NeuroFLOW Scheduler integration from a basic synchronous prototype to a robust, high-throughput scheduling system across both the Tauri/React UI and the Python backend adapter.

Key targets:
1. Fix the execution bottleneck in `pipeline/neuroflow_adapter.py` (replace batch barrier with a continuous event/tick loop).
2. Fix false-early-termination on empty polls (`empty_polls >= 3`).
3. Set sensible, high-performance UI defaults (`neuroflowEnabled = true`, `max_concurrent_tasks = 2` or auto-calculated).
4. Expose useful scheduler controls (e.g., Warm-up mode) and handle Custom mode gracefully.
5. Provide comprehensive unit & integration tests.

---

## 2. Problem Analysis & Current Limitations

### 2.1 Backend Adapter (`pipeline/neuroflow_adapter.py`)
* **Batching Barrier:** The current adapter submits a batch of tasks to `ThreadPoolExecutor` and uses `for future in as_completed(futures): future.result()`. It waits for **all** tasks in the batch to finish before asking NeuroFLOW for new launches. If one task takes 10 minutes and another takes 1 minute, the worker slot sits idle for 9 minutes.
* **Premature Termination:** If `response.launches` is empty for 3 polls (`max_empty_polls = 3`), the loop breaks—even if tasks are still running or waiting for dependency completion / retry backoff delays.
* **Coarse Lock per Image:** `context.lock` blocks all stage runs for a single subject, preventing independent stages of the same subject from running concurrently.
* **Custom Mode Crash:** If `pipeline_mode == "Custom"`, `_preset_id_from_request` raises an unhandled `ValueError`.
* **Hardcoded Disabled Warm-up:** `warmup` is hardcoded to `{"enabled": False}`.

### 2.2 Frontend UI (`tauri-app`)
* **Ineffective Defaults:** `neuroflowEnabled` defaults to `false`, and `neuroflowMaxConcurrentTasks` defaults to `1` (which disables parallel concurrency).
* **Locked / Incomplete Settings:** Machine profile is disabled with no explanation; useful options like Warm-up are missing.

---

## 3. Implementation Steps

### Step 1: Refactor `pipeline/neuroflow_adapter.py` into a Continuous Controller Loop
- Maintain an active task pool (`running_tasks: dict[str, Future]`).
- On each tick:
  1. Poll completed futures; report their `TaskResult` and write observations to disk.
  2. Compute available resource slots (`available_concurrency_slots = max_concurrent - len(running_tasks)`).
  3. If slots are available, capture `ResourceSnapshot` and call `scheduler.request_launches()`.
  4. Submit new `LaunchInstruction` tasks to `ThreadPoolExecutor` and track them in `running_tasks`.
  5. Check termination: Only stop when `scheduler.get_status().terminal` is True and `running_tasks` is empty.
  6. Sleep briefly (e.g. 100ms) between ticks to prevent busy waiting.

### Step 2: Fix Subject Tracking & State Locking
- Replace the coarse `context.lock` with thread-safe atomic updates on `context.steps` and `context.stage_outputs`.
- Ensure container names remain unique: `_safe_container_name("mri", subject_id, f"{local_stage}_{launch.attempt_id}")`.

### Step 3: Handle Custom Pipeline & Fallback
- If `pipeline_mode == "Custom"`:
  - Either gracefully fall back to `run_batch_pipeline` with a warning log, or resolve a dynamic pipeline config if stage mappings exist.
- Validate preset loading before entering the execution loop.

### Step 4: Expose Sane Defaults & Controls in UI (`tauri-app`)
- In `tauri-app/src/api/runConfig.ts`:
  - Change default `neuroflowEnabled` to `true`.
  - Change default `neuroflowMaxConcurrentTasks` to `2` (or calculate based on `Math.max(1, Math.min(4, Math.floor(logicalCores / 4)))`).
  - Add optional `neuroflowWarmupEnabled: boolean` (default `false`).
- In `tauri-app/src/pages/PipelinePage.tsx`:
  - Update `AdvancedSettingsSection` to include:
    - `Enable NeuroFLOW scheduler` (toggle/checkbox).
    - `Max concurrent tasks` (number input with helper text).
    - `Safe Warm-up mode` (checkbox with explanation).
    - Machine profile indicator with tooltip.

### Step 5: Testing & Verification
- Update `tests/test_neuroflow_adapter.py`:
  - Test continuous task replenishment (worker does not sit idle when one task finishes early).
  - Test graceful handling of empty launch responses while dependencies are pending.
  - Test multi-image batch execution with `max_concurrent_tasks = 2` and `max_concurrent_tasks = 4`.
  - Test Custom pipeline mode fallback without crashing.

---

## 4. Acceptance Criteria
- [ ] Concurrency: Multiple subjects/stages execute concurrently up to `max_concurrent_tasks`.
- [ ] No idle slots: When any task finishes, a new ready task is dispatched immediately on the next tick.
- [ ] No premature termination: Scheduler loop continues until all DAG nodes across all images reach terminal states.
- [ ] UI defaults: NeuroFLOW is enabled by default with `max_concurrent_tasks >= 2`.
- [ ] All unit and integration tests pass cleanly (`tests/test_neuroflow_adapter.py`).
