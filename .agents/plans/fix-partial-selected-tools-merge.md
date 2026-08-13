# Fix Partial Selected Tools Merge

## Goal

Fix the remaining stage timeline bug where FreeSurfer 8 + Volume shows only stage 1 as scheduled while stages 3 and 9 are greyed/skipped, even though the preset includes tools for those stages.

The user also reports that pending stages generally become `Not available` / `SKIPPED`.

## Root Cause

The current `JobsPage.tsx` effective selected tools logic does this:

```ts
const fromJob = (reqSummary.selected_tools as Record<string, string>) || {};
if (Object.values(fromJob).some(Boolean)) return fromJob;
```

This is too coarse. If `fromJob` is partial and contains only one truthy tool, the UI returns that partial map and never falls back to preset tools for the remaining scheduled stages.

For FreeSurfer 8 + Volume, this can make stage 1 scheduled while preset-scheduled stages 3 (`segmentation`) and 9 (`stats_extraction`) are missing from `selectedTools`, so `deriveImageSteps` initializes them as `not_scheduled`.

## Required Behavior

- For named presets, preset tools are the baseline source of scheduled stages.
- Job `run_request_summary.selected_tools` should override preset values per stage, but a partial job map must not discard missing preset stages.
- Empty-string values are meaningful because presets use `""` to mark skipped stages.
- For `Custom`, use job `selected_tools` only because there is no preset baseline.
- Pending scheduled stages must remain `pending`, not `skipped`, even before event metrics/progress report a tool.

## Files

- `tauri-app/src/pages/JobsPage.tsx`
- `tauri-app/test/jobs.test.ts` if adding pure tests is possible, otherwise component-level tests can be skipped.

## Implementation Plan

### 1. Replace Choose-One Selected Tools Logic With Merge Logic

In `JobsPage.tsx`, replace the current `selectedTools` `useMemo` around lines 314-321.

Current behavior:

```tsx
const selectedTools = React.useMemo(() => {
  const fromJob = (reqSummary.selected_tools as Record<string, string>) || {};
  if (Object.values(fromJob).some(Boolean)) return fromJob;

  const mode = String(reqSummary.pipeline_mode || job?.pipeline_mode || '');
  const presetTools = ((metadata?.presets || {}) as Record<string, {tools?: Record<string, string>}>)[mode]?.tools || {};
  return presetTools;
}, [job?.pipeline_mode, metadata?.presets, reqSummary.pipeline_mode, reqSummary.selected_tools]);
```

Replace with logic equivalent to:

```tsx
const selectedTools = React.useMemo(() => {
  const fromJob = (reqSummary.selected_tools as Record<string, string>) || {};
  const mode = String(reqSummary.pipeline_mode || job?.pipeline_mode || '');
  const presets = (metadata?.presets || {}) as Record<string, {tools?: Record<string, string>}>;
  const presetTools = presets[mode]?.tools || {};

  if (mode && mode !== 'Custom' && Object.keys(presetTools).length > 0) {
    return {...presetTools, ...fromJob};
  }

  return fromJob;
}, [job?.pipeline_mode, metadata?.presets, reqSummary.pipeline_mode, reqSummary.selected_tools]);
```

Important details:

- Use preset baseline first, then `fromJob` overrides.
- Do not filter out empty strings; empty strings must remain explicit skipped stages.
- If `fromJob` is `{reorientation: 'fs8_reduced54_reorientation'}` and preset has `segmentation` and `stats_extraction`, the result must include all three.

### 2. Resolve Preset Aliases If Needed

If `mode` is sometimes an alias rather than exact metadata preset key, add a small inline resolver in `JobsPage.tsx`.

Use `metadata.pipeline_modes`, which includes `id` and `aliases`.

Equivalent logic:

```tsx
const presetMode = presets[mode]
  ? mode
  : (metadata?.pipeline_modes || []).find((m) => m.id === mode || m.aliases?.includes(mode))?.id || mode;
const presetTools = presets[presetMode]?.tools || {};
```

This handles modes such as `FS8`, `FreeSurfer8`, or other aliases listed by backend metadata.

Keep this minimal and type-safe.

### 3. Optional Helper For Readability

If the `useMemo` gets too dense, add a small local helper above `JobsPage`:

```ts
function resolvePresetTools(metadata: unknown, mode: string): Record<string, string> { ... }
```

But prefer keeping it inside `useMemo` if it stays readable.

### 4. Do Not Change `deriveImageSteps` Again Unless Needed

The latest `deriveImageSteps` guards are directionally correct:

- Scheduled stages start as `pending` when `selectedTools[stage]` exists.
- No-tool stages stay `not_scheduled` when placeholder events lack a tool.

The remaining issue is upstream: `selectedTools` is partial.

Only adjust `deriveImageSteps` if tests reveal a clear issue.

### 5. Add A Regression Test If Practical

There is no existing exported helper for `JobsPage` selected-tool resolution. If adding a component test is too much, skip it and rely on typecheck.

If you add a helper, test this pure case:

```ts
const presetTools = {
  reorientation: 'fs8_reduced54_reorientation',
  brain_extraction: '',
  segmentation: 'synthseg_freesurfer_fs8',
  stats_extraction: 'fs8_reduced54_stats',
};
const fromJob = {reorientation: 'fs8_reduced54_reorientation'};
expect(resolveEffectiveSelectedTools(presetTools, fromJob)).toEqual({
  reorientation: 'fs8_reduced54_reorientation',
  brain_extraction: '',
  segmentation: 'synthseg_freesurfer_fs8',
  stats_extraction: 'fs8_reduced54_stats',
});
```

Do not overbuild tests if this requires exporting UI internals awkwardly.

### 6. Verification

Run from `tauri-app/`:

```bash
npm run typecheck
npm run test -- jobs.test.ts
```

Manual UI checks:

- FreeSurfer 8 + Volume should show stage 1, stage 3, and stage 9 as scheduled/non-grey.
- Pending scheduled stages should show `PENDING`/normal row styling and their preset tool name if available.
- Skipped preset stages should remain grey, show `SKIPPED`, show `Not available`, and hide metrics.
- CAT12 Full should not grey out future pending stages just because event tools have not arrived yet.

## Constraints

- Do not change backend behavior.
- Do not treat partial job `selected_tools` as the complete source of truth for named presets.
- Preserve empty string preset values as explicit skipped stages.
