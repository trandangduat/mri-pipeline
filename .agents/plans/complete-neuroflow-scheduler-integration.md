# Complete NeuroFLOW Scheduler Integration

## 1. Goal

Finish the NeuroFLOW scheduler integration that was started in `.agents/plans/improve-neuroflow-scheduler-integration.md`.

The current implementation already has a continuous backend loop, UI controls, and passing tests. It still has several behavior and UX gaps:

1. Backend can still stop after bounded empty polls.
2. UI defaults to `Custom` pipeline mode with NeuroFLOW enabled, but backend rejects that combination.
3. NeuroFLOW-launched Docker containers are not attempt-unique.
4. Workspace save does not persist all NeuroFLOW settings.
5. Advanced scheduler UI is too dense and exposes expert details too early.

This plan should be implemented as small focused changes. Do not rewrite the scheduler adapter.

---

## 2. Current State Summary

### Backend

Relevant files:

- `pipeline/neuroflow_adapter.py`
- `pipeline/job_worker.py`
- `pipeline/runner.py`
- `pipeline/config.py`
- `app_backend/run_request.py`
- `tests/test_neuroflow_adapter.py`
- `tests/test_app_backend_run_request.py`

Current behavior:

- `run_neuroflow_batch()` uses a continuous loop and tracks running futures.
- It reports completed task results back to NeuroFLOW.
- It requests launches when slots are available.
- It still has `max_empty_polls = 60` and can break even if scheduler is not terminal.
- `Custom` mode is rejected by request validation when NeuroFLOW is enabled.
- `job_worker.py` contains a fallback to standard execution for unsupported modes, but this is mostly unreachable from normal prepared UI/API requests.
- `run_pipeline_stage()` creates Docker container names from subject and tool only.

### Frontend

Relevant files:

- `tauri-app/src/api/runConfig.ts`
- `tauri-app/src/pages/PipelinePage.tsx`
- `tauri-app/src/stores/pipelineFormStore.ts`
- `tauri-app/src/components/AppHeader.tsx`
- `tauri-app/test/api.test.ts`
- `tauri-app/test/AppHeader.test.tsx`

Current behavior:

- `DEFAULT_FORM_VALUES` has `pipelineMode: 'Custom'` and `neuroflowEnabled: true`.
- Advanced settings show many NeuroFLOW fields.
- Workspace save stores only `neuroflow_enabled`, `neuroflow_max_concurrent_tasks`, and `neuroflow_machine_profile_id`.
- Saved workspace max concurrency fallback uses `1`, not `2`.

---

## 3. Implementation Steps

### Step 1: Fix Backend Scheduler Termination

File: `pipeline/neuroflow_adapter.py`

Change the loop termination logic so empty launch responses do not stop the run by poll count.

Required behavior:

- Do not use `max_empty_polls` as a terminal condition.
- Continue polling when there are no launches and scheduler is not terminal.
- Stop only when scheduler terminal state is true and no futures are running.
- Keep a short sleep between ticks to avoid busy waiting.
- If `scheduler.request_launches()` response has `terminal == true`, treat that as terminal only when there are no running futures.
- If available, prefer `scheduler.get_status().terminal` for the final terminal check.

Suggested shape:

```python
def _scheduler_is_terminal() -> bool:
    if hasattr(scheduler, "get_status"):
        status = scheduler.get_status()
        return bool(getattr(status, "terminal", False))
    return bool(last_response_terminal)
```

Keep it simple. It can also be inline if clearer.

Acceptance:

- Empty launches with pending dependencies must not end the run.
- Empty launches with retry backoff must not end the run.
- Terminal scheduler plus no running futures must end the run.

Tests to add or update:

- In `tests/test_neuroflow_adapter.py`, add a test where scheduler returns more than 60 empty launch responses before becoming ready again.
- The test should fail on the current `max_empty_polls` behavior and pass after the fix.
- Keep the fake scheduler fast. Do not sleep 60 ticks in real time if avoidable. Monkeypatch `neuroflow_adapter.time.sleep` to a no-op if needed.

---

### Step 2: Decide and Implement `Custom` Mode Behavior

Use this product decision:

- NeuroFLOW is supported only for built-in FreeSurfer/FastSurfer preset modes for now.
- `Custom` mode should run with the standard runner.
- The UI should make this clear before submit.
- Backend should not silently crash.

Recommended backend behavior:

- Keep `is_neuroflow_supported()` returning false for `Custom` without explicit `neuroflow_preset`.
- Keep `job_worker.py` fallback to standard execution as a safety net.
- Adjust request preparation so normal UI requests do not fail just because `Custom` mode has `neuroflow_enabled: true`.

File: `app_backend/run_request.py`

Preferred implementation:

- In `_base_request()`, set `neuroflow_enabled` to false if pipeline mode is unsupported.
- Add a request field such as `neuroflow_disabled_reason` only if useful for logs/UI. Keep it out if not used.
- Or adjust `_neuroflow_error()` so unsupported modes do not hard-fail. It should only return errors for invalid NeuroFLOW numeric settings, not unsupported mode.

Avoid this behavior:

- Do not raise a validation error for `Custom` plus `neuroflow_enabled: true`.
- Do not try to generate a dynamic NeuroFLOW DAG for Custom mode in this task.

Tests to add:

- `tests/test_app_backend_run_request.py`
- Add a test for `Custom` mode with `neuroflow_enabled=True`.
- Expected result: prepared request is ok and has `neuroflow_enabled is False`.
- Add a test for a supported preset with `neuroflow_enabled=True`.
- Expected result: prepared request is ok and keeps `neuroflow_enabled is True`.

---

### Step 3: Make NeuroFLOW Container Names Attempt-Unique

Problem:

- `run_pipeline_stage()` currently creates container names from subject and tool.
- NeuroFLOW may retry attempts or run independent stages for the same subject.
- Docker container names can collide.

Preferred minimal implementation:

1. Add an optional field to `PipelineConfig` in `pipeline/config.py`:

```python
container_name_suffix: str = ""
```

2. In `pipeline/runner.py`, where container names are created, append this suffix when present.

Current pattern to look for:

```python
container_name=_safe_container_name("mri", config.subject_id, tool_key)
```

New behavior:

```python
container_parts = ["mri", config.subject_id, tool_key]
if config.container_name_suffix:
    container_parts.append(config.container_name_suffix)
container_name = _safe_container_name(*container_parts)
```

3. In `pipeline/neuroflow_adapter.py`, set the suffix when building `stage_config` in `_run_launch_stage()`:

```python
container_name_suffix=f"{local_stage}_{launch.attempt_id}"
```

If `PipelineConfig` is used in many places, make the new field optional with a default so existing code does not change.

Tests to add:

- Add or update a runner test to assert suffix is included in container names when config has `container_name_suffix`.
- Add a NeuroFLOW adapter test that monkeypatches `run_pipeline_stage()` and asserts `config.container_name_suffix` contains the local stage and attempt id.

Acceptance:

- Standard non-NeuroFLOW runs keep existing container names.
- NeuroFLOW runs have attempt-specific names.

---

### Step 4: Persist All NeuroFLOW Workspace Settings

File: `tauri-app/src/components/AppHeader.tsx`

Current save stores only:

- `neuroflow_enabled`
- `neuroflow_max_concurrent_tasks`
- `neuroflow_machine_profile_id`

Update workspace save to include:

- `neuroflow_enabled`
- `neuroflow_max_concurrent_tasks`
- `neuroflow_max_retries`
- `neuroflow_warmup_enabled`
- `neuroflow_warmup_initial_concurrency`
- `neuroflow_warmup_safe_successes`
- `neuroflow_preserve_oom_bounds`
- `neuroflow_estimation_mode`
- `neuroflow_max_io_heavy_tasks`
- `neuroflow_machine_profile_id`

Also change max-concurrent fallback during save:

```ts
Math.max(1, Number(fv.neuroflowMaxConcurrentTasks || 2))
```

Do not use fallback `1`.

Tests to add:

- Update `tauri-app/test/AppHeader.test.tsx` or add a focused test.
- Save a workspace with non-default NeuroFLOW settings.
- Assert all fields are sent to `client.saveWorkspace()`.

---

### Step 5: Simplify and Make UI Mode-Aware

File: `tauri-app/src/pages/PipelinePage.tsx`

Goal:

- Keep the UI useful but less dense.
- Make unsupported `Custom` mode clear.
- Avoid exposing all expert fields by default.

Required UX behavior:

- If `pipelineMode === 'Custom'`, show an inline notice in Advanced Settings:
  - `NeuroFLOW is available for built-in FreeSurfer/FastSurfer presets. Custom mode uses the standard runner.`
- Disable the NeuroFLOW toggle in `Custom` mode, or leave it enabled visually but clearly say it will be ignored. Prefer disabling it.
- When mode is `Custom`, effective request should send `neuroflow_enabled: false` after Step 2.
- Main visible NeuroFLOW fields should be only:
  - `Use NeuroFLOW scheduler`
  - `Max parallel tasks`
  - `Start safely, then scale up`
- Move these to expert/tuning details:
  - max retries
  - warm-up initial concurrency
  - warm-up safe successes
  - estimation risk profile
  - max I/O-heavy tasks
  - machine profile identifier
  - preserve OOM memory bounds

Suggested label changes:

- `Enable NeuroFLOW Dynamic Scheduler` -> `Use NeuroFLOW scheduler`
- `Max Concurrent Tasks` -> `Max parallel tasks`
- `Safe Warm-up Mode (Adaptive Scaling)` -> `Start safely, then scale up`
- `Successes to Scale Up` -> `Successful tasks before scaling`
- `Estimation Risk Profile` -> `Scheduling risk`
- `Preserve OOM Memory Bounds` -> `Remember memory failures`

Default display behavior:

- `Max parallel tasks` should show `2` for a fresh form.
- If loaded workspace value is `1`, keep it but show helper text:
  - `Loaded from workspace. Use 2 or more for parallel scheduling.`

Important:

- Do not redesign the whole page.
- Keep the existing card/panel style.
- Avoid adding a modal.
- Keep mobile layout readable. Replace rigid `grid-cols-2` with responsive classes if needed, for example `grid-cols-1 sm:grid-cols-2`.

Tests to add:

- Add a frontend test if there is existing coverage around `AdvancedSettingsSection`.
- If not, add a small test that renders the section with `pipelineMode: 'Custom'` and checks the unsupported-mode text.
- Add an API test in `tauri-app/test/api.test.ts` for `buildRunConfig()` if you choose to force `neuroflow_enabled: false` there for `Custom` mode. If backend handles it instead, do not duplicate the logic in frontend unless needed for UX consistency.

---

### Step 6: Keep UI and Backend Consistent

After implementing Step 2 and Step 5, confirm these flows:

1. Fresh UI load:
   - Pipeline mode: `Custom`
   - NeuroFLOW toggle disabled or explained as unavailable
   - Prepared request: `neuroflow_enabled: false`

2. User selects built-in preset:
   - NeuroFLOW toggle available
   - Default max parallel tasks: `2`
   - Prepared request: `neuroflow_enabled: true`

3. User loads old workspace with `neuroflow_max_concurrent_tasks: 1`:
   - Value remains `1`
   - Helper text recommends `2+`
   - Saving workspace should not silently change it unless user changes it

4. User saves workspace with advanced settings:
   - All NeuroFLOW fields are included
   - Loading workspace restores them

---

## 4. Verification Commands

Use the virtualenv for Python commands.

Run:

```bash
./.venv/bin/python -m pytest tests/test_neuroflow_adapter.py tests/test_app_backend_run_request.py
```

Run frontend tests:

```bash
npm test
```

from `tauri-app/`.

Run frontend typecheck:

```bash
npm run typecheck
```

from `tauri-app/`.

If touching shared backend config or runner behavior, also run:

```bash
./.venv/bin/python -m pytest tests/test_runner_executor_integration.py tests/test_executor.py tests/test_utils.py
```

---

## 5. Acceptance Criteria

- NeuroFLOW loop no longer stops because of a fixed empty-poll count.
- Scheduler stops only when terminal and no futures are running.
- `Custom` mode plus NeuroFLOW default no longer blocks starting a run.
- Built-in preset modes can still use NeuroFLOW by default.
- NeuroFLOW container names include a stage/attempt-specific suffix.
- Workspace save/load preserves all NeuroFLOW settings.
- Advanced settings UI is simpler and explains why NeuroFLOW is unavailable in `Custom` mode.
- Targeted Python tests pass using `./.venv/bin/python`.
- Frontend tests and typecheck pass.

---

## 6. Non-Goals

- Do not generate dynamic NeuroFLOW DAGs for Custom mode.
- Do not rewrite `run_neuroflow_batch()`.
- Do not change NeuroFLOW config YAML schema unless tests prove it is required.
- Do not remove existing standard-runner fallback in `job_worker.py`.
- Do not redesign unrelated pipeline UI sections.
