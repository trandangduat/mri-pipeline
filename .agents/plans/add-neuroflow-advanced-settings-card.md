# Add NeuroFLOW Advanced Settings Card

## Goal

Add an `Advanced Settings` card directly under the `Stats & Atlas Mapping` card on the pipeline configuration page. The first purpose of this card is to expose the existing NeuroFLOW scheduler integration safely.

NeuroFLOW is off by default. When enabled, the user can set the scheduler controls that are already supported by the current backend request contract.

## Research Summary

Relevant files inspected:

- `tauri-app/src/pages/PipelinePage.tsx`
- `tauri-app/src/api/runConfig.ts`
- `tauri-app/src/stores/pipelineFormStore.ts`
- `app_backend/run_request.py`
- `pipeline/neuroflow_adapter.py`
- `pipeline/job_worker.py`
- `remote/remote_runner.py`
- `configs/neuroflow/presets/*.yaml`
- `configs/neuroflow/profiles/*.yaml`
- `tests/test_neuroflow_adapter.py`

Current supported request fields:

- `neuroflow_enabled`: boolean, default `false`
- `neuroflow_max_concurrent_tasks`: integer, min `1`, default `1`
- `neuroflow_machine_profile_id`: string, currently passed as `application_default`

Current backend behavior:

- `app_backend/run_request.py` already validates and forwards `neuroflow_enabled` and `neuroflow_max_concurrent_tasks`.
- NeuroFLOW currently requires a supported preset pipeline mode from `PIPELINE_MODE_TO_PRESET`.
- NeuroFLOW is not supported for lazy-watch jobs.
- `pipeline/neuroflow_adapter.py` hardcodes scheduler policy as `{"name": "neuroflow", "algorithm_version": "1"}`.
- No queue-order field such as FIFO/LIFO is currently consumed by the adapter.
- `NeuroFLOW-private` is referenced by code but is not present in this checkout, and `neuroflow` is not installed in the current Python environment. Because of that, do not add an active FIFO/LIFO setting in this slice.

## Proposed Card Contents

Add these controls to `Advanced Settings`:

1. `Enable NeuroFLOW scheduler`
   - Type: checkbox or switch-like checkbox.
   - Form field: `neuroflowEnabled`.
   - Default: `false`.
   - Helper text: `Use NeuroFLOW to schedule supported preset pipeline runs across images and stages.`

2. `Max concurrent tasks`
   - Type: number input.
   - Form field: `neuroflowMaxConcurrentTasks`.
   - Default: `1`.
   - Minimum: `1`.
   - Visible only when NeuroFLOW is enabled.
   - Helper text: `Maximum scheduler launches to execute at the same time.`

3. `Machine profile`
   - Type: text input or disabled/read-only row.
   - Form field: `neuroflowMachineProfileId`.
   - Default: `application_default`.
   - Visible only when NeuroFLOW is enabled.
   - If implementing as editable, pass it through the request and workspace JSON. If keeping minimal, render it as a read-only value and keep backend behavior unchanged.
   - Recommended first slice: read-only, because the current UI has no metadata endpoint listing alternate machine profiles.

4. NeuroFLOW constraints notice
   - Visible only when NeuroFLOW is enabled.
   - Text should explain:
     - NeuroFLOW currently works only with supported FreeSurfer/FastSurfer preset modes.
     - Custom pipeline mode is not supported by the existing backend validation.
     - Lazy-watch jobs are not supported.

Do not add `Run type`, `FIFO`, `LIFO`, or similar scheduling-policy controls yet unless executor finds the private NeuroFLOW scheduler API and confirms the exact request/config field that controls this. If confirmed, add it as a separate supported field with backend parsing, validation, tests, and adapter wiring. Do not create UI-only controls that do nothing.

## Implementation Plan

### 1. Add Frontend Form Fields

Update `tauri-app/src/api/runConfig.ts`:

- Extend `PipelineFormValues` with:
  - `neuroflowEnabled?: boolean`
  - `neuroflowMaxConcurrentTasks?: number`
  - `neuroflowMachineProfileId?: string`
- Extend `DEFAULT_FORM_VALUES` with:
  - `neuroflowEnabled: false`
  - `neuroflowMaxConcurrentTasks: 1`
  - `neuroflowMachineProfileId: 'application_default'`

Update `buildRunConfig()` to include:

- `neuroflow_enabled: Boolean(formValues.neuroflowEnabled)`
- `neuroflow_max_concurrent_tasks: Math.max(1, Number(formValues.neuroflowMaxConcurrentTasks || 1))`
- `neuroflow_machine_profile_id: String(formValues.neuroflowMachineProfileId || 'application_default')`

Keep field names consistent with existing backend snake_case request keys.

### 2. Add Advanced Settings Section Component

Update `tauri-app/src/pages/PipelinePage.tsx`:

- Add a new exported component near `StatsAtlasSection`, for example `AdvancedSettingsSection`.
- Use the existing `Panel`, `inputCls`, and `labelCls` patterns.
- Use an appropriate icon already imported from `lucide-react`, such as `SlidersHorizontal`. It is already imported in this file.
- Read `formValues`, `setFormField`, and optionally `setFormFields` from `usePipelineFormStore`.

UI structure:

- `Panel` title: `Advanced Settings`
- Top row: checkbox/switch-style control for `Enable NeuroFLOW scheduler`
- When disabled: show only a short muted line, e.g. `NeuroFLOW is off. Runs use the standard pipeline executor.`
- When enabled:
  - Number input for `Max concurrent tasks`
  - Read-only row or disabled text input for machine profile `application_default`
  - Constraint notice in a subdued bordered box

Place the card under `StatsAtlasSection` in the left pane:

```tsx
<PipelineStepsSection />
<StatsAtlasSection />
<AdvancedSettingsSection />
```

### 3. Workspace Save/Load Persistence

Update workspace save logic in `PipelinePage.tsx` around the `Save Workspace` handler:

- Add these fields to saved workspace JSON:
  - `neuroflow_enabled`
  - `neuroflow_max_concurrent_tasks`
  - `neuroflow_machine_profile_id`

Update `tauri-app/src/stores/pipelineFormStore.ts` in `applyWorkspaceConfig()`:

- Load `workspace.neuroflow_enabled` into `nextFormValues.neuroflowEnabled`.
- Load `workspace.neuroflow_max_concurrent_tasks` into `nextFormValues.neuroflowMaxConcurrentTasks`, clamped to at least `1`.
- Load `workspace.neuroflow_machine_profile_id` into `nextFormValues.neuroflowMachineProfileId`, defaulting to `application_default`.

### 4. Backend Machine Profile Pass-Through

The current backend always emits `neuroflow_machine_profile_id: 'application_default'`, but `remote/remote_runner.py` already has a config field for it.

Update `app_backend/run_request.py` minimally:

- Add `neuroflow_machine_profile_id: str = 'application_default'` to `RunRequestInput`.
- Parse it in `from_dict()` with default `application_default`.
- Emit it in `_base_request()` instead of hardcoding `application_default`.

No validation beyond non-empty fallback is needed for this slice.

### 5. Do Not Implement Queue Policy Yet

Do not add these in this slice:

- `neuroflow_run_type`
- `FIFO` / `LIFO` select
- scheduler policy name changes
- scheduler algorithm changes

Reason: this checkout does not include the private scheduler source, and the current adapter has no corresponding field. Adding a UI control now would be misleading because it would not change execution behavior.

If the executor can access `NeuroFLOW-private` in another environment, they may research and add a follow-up plan or implementation only if they find the exact supported config key and legal values.

### 6. Tests and Verification

Run frontend checks:

```bash
npm run typecheck
```

from `tauri-app/`.

Run backend tests related to run request and NeuroFLOW if available:

```bash
pytest tests/test_neuroflow_adapter.py
```

Also run or add a backend test for `app_backend/run_request.py` if there is an existing run-request test file. Verify:

- Default request has `neuroflow_enabled: false`.
- Enabling NeuroFLOW passes `neuroflow_enabled: true`.
- `neuroflow_max_concurrent_tasks` clamps to at least `1`.
- `neuroflow_machine_profile_id` passes through or defaults to `application_default`.

Manual UI verification:

- The new `Advanced Settings` card appears directly under `Stats & Atlas Mapping`.
- NeuroFLOW fields are hidden when disabled.
- Enabling the switch reveals max concurrent tasks and the constraints notice.
- Starting a local run includes `neuroflow_enabled` and `neuroflow_max_concurrent_tasks` in the request payload.
- Saving and loading a workspace preserves NeuroFLOW fields.

## Acceptance Criteria

- `Advanced Settings` card is visible under `Stats & Atlas Mapping`.
- NeuroFLOW is off by default.
- NeuroFLOW-specific settings are conditionally visible only when enabled.
- `Max concurrent tasks` is sent as `neuroflow_max_concurrent_tasks` and cannot be less than `1`.
- Machine profile remains `application_default` and is passed through if implemented as a form field.
- No FIFO/LIFO UI appears unless the actual NeuroFLOW scheduler API is confirmed and wired end-to-end.
- Existing pipeline behavior is unchanged when NeuroFLOW is off.
- Typecheck and relevant backend tests pass.
