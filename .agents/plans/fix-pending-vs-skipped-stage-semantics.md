# Fix Pending Vs Skipped Stage Semantics

## Goal

Correct the stage timeline semantics after the first UI fix:

- `pending` means the stage is scheduled by the selected preset/custom tools but has not run yet.
- `skipped` / `not_scheduled` means the stage has no selected tool for this job/preset.
- CAT12 Full presets should not grey out stages just because an event did not report a tool name.
- FreeSurfer 8 Volume should grey out only stages with no selected tool, such as stages outside 1, 3, and 9.

## Current Bug

The recent implementation made `VerticalTimelineStepRow` show `Not available` when `step.tool` is empty. That confuses two cases:

- A scheduled stage whose event did not report `event.tool` yet.
- An unscheduled stage with no selected tool.

Also, `deriveImageSteps` can promote no-tool stages to `success`/`failed` from placeholder progress/log events. This is why stages with no selected tool may show `OK` instead of grey skipped.

## Relevant Files

- `tauri-app/src/pages/JobsPage.tsx`
- `tauri-app/src/lib/jobs.ts`
- `tauri-app/test/jobs.test.ts`

## Required Semantics

### Scheduled Stage

A stage is scheduled if it has a selected tool from the job request or preset metadata:

```ts
selectedTools[stage] !== ''
```

Scheduled stage display rules:

- Status starts as `pending`.
- It may become `running`, `success`, or `failed` based on events.
- It should show the selected tool display name even if individual events do not include `event.tool`.
- It may show elapsed/CPU/RAM metrics.

### Skipped / Not Scheduled Stage

A stage is skipped/not scheduled if it has no selected tool for this job/preset.

Skipped stage display rules:

- Status should remain `not_scheduled` or `skipped`.
- It should be greyed out.
- It should show `Not available`.
- It should not show elapsed/CPU/RAM metrics.
- Placeholder events without a tool must not promote it to `OK`, `RUNNING`, or `FAIL`.

## Implementation Plan

### 1. Build Effective Selected Tools In `JobsPage.tsx`

In `JobsPage.tsx`, replace the current direct `selectedTools` calculation:

```ts
const selectedTools = (reqSummary.selected_tools as Record<string, string>) || {};
```

with an effective selected tools calculation that falls back to preset metadata when the job summary has no selected tools:

```tsx
const selectedTools = React.useMemo(() => {
  const fromJob = (reqSummary.selected_tools as Record<string, string>) || {};
  if (Object.values(fromJob).some(Boolean)) return fromJob;

  const mode = String(reqSummary.pipeline_mode || job?.pipeline_mode || '');
  const presetTools = ((metadata?.presets || {}) as Record<string, {tools?: Record<string, string>}>)[mode]?.tools || {};
  return presetTools;
}, [job?.pipeline_mode, metadata?.presets, reqSummary.pipeline_mode, reqSummary.selected_tools]);
```

Notes:

- This is necessary because older or remote job summaries may not always include `run_request_summary.selected_tools` even though `pipeline_mode` exists.
- This is what lets CAT12 Full initialize every preset stage as scheduled.
- This is what lets FreeSurfer 8 Volume initialize only stages 1, 3, and 9 as scheduled.
- If TypeScript complains about dependencies/object types, keep the logic equivalent but simpler; do not change backend schemas.

### 2. Preserve No-Tool Stages In `deriveImageSteps`

In `tauri-app/src/lib/jobs.ts`, update event processing so no-tool stages are not promoted by placeholder events.

Add a small local helper inside `deriveImageSteps`:

```ts
const isUnscheduledStep = (step: StageStepDetail) => !step.tool && (step.status === 'not_scheduled' || step.status === 'skipped');
```

Then adjust each event branch:

#### Progress/Step/Stage Events

- Read `event.tool` before applying status.
- If `event.tool` exists, assign it to `step.tool` and allow the event to schedule/update the stage.
- If `isUnscheduledStep(step)` and the event has no tool, ignore status updates and keep the stage not scheduled/skipped.

Pseudo:

```ts
const eventTool = event.tool ? String(event.tool) : '';
if (eventTool) step.tool = eventTool;
if (isUnscheduledStep(step) && !eventTool) continue;
```

Then apply `running`, `success`, `failed`, `skipped` status mapping as before.

#### Metrics Events

- Same rule: if an unscheduled step receives metrics without a tool, ignore those metrics and keep it skipped.
- If metrics include a tool, assign it and allow the stage to become running.

Important: avoid setting CPU/RAM/elapsed on skipped/no-tool stages from placeholder metrics.

#### Image Done Log Parsing

Current log parsing can set status to `success` or `failed` even when `toolName` is empty and the step has no selected tool.

Change it so:

- If the matched `toolName` is non-empty, assign `step.tool = toolName` and allow status update.
- If `step` is unscheduled and `toolName` is empty, do not set `success`/`failed`; keep it skipped/not scheduled.
- Scheduled stages with preset `step.tool` may still be marked success/failed even if `toolName` is empty.

Pseudo:

```ts
const toolName = (match[2] || '').trim();
if (toolName) step.tool = toolName;
if (isUnscheduledStep(step) && !toolName) continue;
step.status = res.toUpperCase() === 'OK' ? 'success' : 'failed';
```

#### Completion Reconciliation

Keep the existing logic that marks only stages with `s.tool` as success when an image completes successfully:

```ts
if (s.status === 'running' || (s.tool && s.status === 'pending')) {
  s.status = 'success';
}
```

Do not mark no-tool stages successful.

### 3. Fix Tool Label Logic In `VerticalTimelineStepRow`

In `JobsPage.tsx`, keep `isSkipped` for `not_scheduled`/`skipped`.

Change tool label logic to make `Not available` specific to skipped stages:

```tsx
const displayTool = step?.tool ? (toolDisplayNames[step.tool] || step.tool) : '';
const toolLabel = isSkipped ? 'Not available' : displayTool || 'Not available';
```

If effective selected tools are computed correctly, scheduled stages should usually have `displayTool` from the preset. The fallback `Not available` is only an edge case for malformed job data.

Keep metrics hidden only when `isSkipped`.

### 4. Add/Update Tests

In `tauri-app/test/jobs.test.ts`, add tests for the distinction:

1. Scheduled but pending stages remain pending, not skipped:

```ts
test('deriveImageSteps keeps scheduled stages pending until events run them', () => {
  const steps = deriveImageSteps([], {input_file: 'a.nii', subject_id: 'a', idx: 1, total: 1, status: 'running'}, {preproc: 'cat_preproc', seg: 'cat_seg'}, ['preproc', 'seg'], {});
  expect(steps[0].status).toBe('pending');
  expect(steps[0].tool).toBe('cat_preproc');
  expect(steps[1].status).toBe('pending');
  expect(steps[1].tool).toBe('cat_seg');
});
```

2. Unscheduled stages stay not scheduled even when placeholder progress/log says OK without a tool:

```ts
test('deriveImageSteps does not promote no-tool stages from placeholder events', () => {
  const stageOrder = ['stage1', 'stage2', 'stage3'];
  const selectedTools = {stage1: 'tool1', stage3: 'tool3'};
  const image = {input_file: 'a.nii', subject_id: 'a', idx: 1, total: 1, status: 'failed' as const};
  const events = [
    {kind: 'image_start', input_file: 'a.nii'},
    {kind: 'progress', stage: 'stage2', status: 'ok'},
    {kind: 'image_done', input_file: 'a.nii', success: false, log_text: '[stage2]  - OK'},
  ];
  const steps = deriveImageSteps(events, image, selectedTools, stageOrder, {});
  expect(steps[1].status).toBe('not_scheduled');
  expect(steps[1].tool).toBe('');
});
```

3. Optional: event tool can recover scheduling when selected tools are missing:

```ts
test('deriveImageSteps accepts event tool for stages missing selected tool metadata', () => {
  const image = {input_file: 'a.nii', subject_id: 'a', idx: 1, total: 1, status: 'running' as const};
  const events = [{kind: 'image_start', input_file: 'a.nii'}, {kind: 'progress', stage: 'seg', status: 'running', tool: 'cat_seg'}];
  const steps = deriveImageSteps(events, image, {}, ['seg'], {});
  expect(steps[0].status).toBe('running');
  expect(steps[0].tool).toBe('cat_seg');
});
```

### 5. Verification

Run from `tauri-app/`:

```bash
npm run typecheck
npm run test -- jobs.test.ts
```

If the targeted Vitest command is not accepted, run:

```bash
npm run test
```

Manual UI checks:

- CAT12 Full preset: all preset stages should be scheduled. Future stages should be `PENDING`/normal, not grey skipped, and should show the preset tool display name when available.
- FreeSurfer 8 Volume: only stages with selected tools should be normal. Stages without selected tools should be grey, say `SKIPPED`/`Not available`, and not show metrics.
- A scheduled stage waiting for execution should still show metrics as `Waiting` / `Not reported` until data exists, not be greyed out.

## Constraints

- Do not change backend behavior.
- Do not treat lack of `event.tool` as lack of selected tool.
- Only no-selected-tool stages should be skipped/greyed.
