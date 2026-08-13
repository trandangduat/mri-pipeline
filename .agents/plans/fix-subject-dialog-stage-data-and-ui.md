# Fix Subject Dialog Stage Data And UI

## Goal

Improve the subject progress dialog after the previous design pass. The layout/design is better, but several correctness and usability issues remain:

- Popup is too narrow.
- Stage tools show `Default pipeline tool` instead of actual tool names like `FreeSurfer 8 SynthSeg` or `FreeSurfer 8 Brain Extraction`.
- Progress summaries like `4/5 complete` are wrong; there are 9 canonical stages.
- UI can show stale running stage, e.g. log says `RUNNING surface_reconstruction` but dialog still shows `Image standardization` running.
- Telemetry graphs are too small/weak.
- Log card layout is bugged and has bad scrolling/clipping.
- Elapsed/CPU/RAM need clearer visual separation per stage.
- Remove the Subject Details card.

Keep this focused. Do not rewrite unrelated Jobs page sections.

## Files

Primary:

- `tauri-app/src/pages/JobsPage.tsx`
- `tauri-app/src/lib/jobs.ts`

Likely no backend edits are required. Use existing metadata from `useMetadata()`.

## Findings

1. `JobsPage.tsx` currently computes:

   ```ts
   const scheduledModalStages = modalImageSteps.filter((step) => step.status !== 'not_scheduled');
   const completedModalStages = scheduledModalStages.filter((step) => step.status === 'success').length;
   ```

   This makes the denominator 5 for a partially selected/scheduled subset. User expects the dialog to reflect all 9 stages in the stage order.

2. `deriveImageSteps` initializes tools from `selectedTools[stage]`, but the UI renders `step.tool` directly. `step.tool` is a tool key, not a display label, and when empty the UI shows `Default pipeline tool`. Actual display labels are in `metadata.tools[toolKey].display_name`.

3. `deriveImageSteps` marks a stage `running` when it sees a running progress event, but it does not mark previously running stages successful when a later stage starts. If an earlier `success` event was missed/truncated, stale running status remains.

4. Events are read with default `limit=500` unless overridden. Long jobs may exceed 500 events, causing stale UI state if newer progress events are beyond the returned window while the log text shows newer lines. The local backend accepts up to `limit=5000`; remote passes `limit` through.

5. `Subject Details` card is not needed and takes right-column space away from telemetry/log.

## Implementation Plan

### 1. Make Event Reads Less Likely To Truncate

In `JobsPage.tsx`, when reading local and remote events inside `loadJobDetails`, request the maximum supported limit.

Local current code:

```ts
readEventsMutation.mutateAsync(jobId).catch(() => ({events: []}))
```

Change to use the query hook mutation type if necessary so it can accept options, or call the client through existing mutation by updating `useReadLocalEventsMutation`.

Recommended minimal change:

- In `tauri-app/src/query/useJobs.ts`, change `useReadLocalEventsMutation` to accept either a string or an object:

  ```ts
  mutationFn: (input: string | {jobId: string; offset?: number; limit?: number}) => {
    if (typeof input === 'string') return client.readLocalEvents(input);
    return client.readLocalEvents(input.jobId, input.offset, input.limit);
  }
  ```

- Then in `JobsPage.tsx`, call:

  ```ts
  readEventsMutation.mutateAsync({jobId, offset: 0, limit: 5000})
  ```

Remote current code:

```ts
readRemoteEventsMutation.mutateAsync({...remotePayload, remote_job_dir: remoteJobDir, job_id: jobId})
```

Change to:

```ts
readRemoteEventsMutation.mutateAsync({...remotePayload, remote_job_dir: remoteJobDir, job_id: jobId, offset: 0, limit: 5000})
```

This is important for the stale-running-stage symptom.

### 2. Fix Stage Reconciliation In `deriveImageSteps`

Update `tauri-app/src/lib/jobs.ts`.

Add a small helper inside/near `deriveImageSteps` to resolve stage keys as it already does via exact match or `STAGE_KEYWORD_MAP`. Keep it local/minimal if possible.

When processing events in order:

- Track the latest/current stage index for this image.
- When a stage receives `running/start/started`, mark any earlier scheduled stage that is still `running` or `pending` as `success`.
- Then mark the current stage `running`.
- When a stage receives `success/done/completed/ok` or `pct === 100`, mark it success.
- When a later `metrics` event arrives for a stage, also treat that stage as current/running and reconcile earlier scheduled stages. Metrics events include `stage` and `tool`, and are reliable proof the stage is active.
- When setting `step.tool` from an event, use `event.tool` if present. This is a tool key; display conversion happens in `JobsPage`.

Be careful:

- Do not mark `not_scheduled` stages success just because they are earlier.
- Do not mark earlier failed stages success.
- For `image_done`, keep existing terminal reconciliation.

Pseudo-helper inside `deriveImageSteps`:

```ts
const markPriorActiveStagesSuccess = (currentStage: string) => {
  const currentIndex = stageOrder.indexOf(currentStage);
  if (currentIndex < 0) return;
  for (let i = 0; i < currentIndex; i += 1) {
    const prior = stepMap.get(stageOrder[i] || '');
    if (!prior || prior.status === 'not_scheduled' || prior.status === 'failed') continue;
    if (prior.status === 'running' || prior.status === 'pending') {
      prior.status = 'success';
    }
  }
};
```

Use this when a progress/metrics event maps to a concrete stage and is active for the modal image.

### 3. Resolve Actual Tool Display Names In `JobsPage.tsx`

In `JobsPage.tsx`, build a display-name map from metadata:

```ts
const toolDisplayNames = React.useMemo(() => {
  const tools = metadata?.tools || {};
  return Object.fromEntries(Object.entries(tools).map(([key, tool]) => [key, tool.display_name || key]));
}, [metadata?.tools]);
```

If TypeScript complains about metadata typing, use a narrow local type or safe record access:

```ts
const tools = (metadata?.tools || {}) as Record<string, {display_name?: string}>;
```

Pass this to `VerticalTimelineStepRow`:

```tsx
<VerticalTimelineStepRow ... toolDisplayNames={toolDisplayNames} />
```

Update `VerticalTimelineStepRow` props and compute:

```ts
const displayTool = step?.tool ? toolDisplayNames[step.tool] || step.tool : '';
const toolLabel = step?.status === 'not_scheduled' ? 'No tool selected for this stage' : displayTool || 'Tool not reported yet';
```

Do not show `Default pipeline tool` anywhere in the dialog.

Expected examples:

- `FreeSurfer 8 Brain Extraction`
- `FreeSurfer 8 SynthSeg`
- `FreeSurfer 8 Surface Reconstruction`

### 4. Fix Stage Counts And Progress Summary

Use all stage rows as the denominator, not only scheduled stages.

In `JobsPage.tsx`, replace/augment current summary variables:

```ts
const totalModalStages = modalImageSteps.length;
const completedModalStages = modalImageSteps.filter((step) => step.status === 'success').length;
const activeModalStage = modalImageSteps.find((step) => step.status === 'running');
const failedModalStages = modalImageSteps.filter((step) => step.status === 'failed').length;
const scheduledModalStages = modalImageSteps.filter((step) => step.status !== 'not_scheduled');
```

Use `totalModalStages` for all header/card pills:

- `{completedModalStages}/{totalModalStages} stages`
- `{completedModalStages}/{totalModalStages} complete`

If the UI wants to mention scheduled separately, it can say `5 scheduled`, but the primary denominator should be 9.

Also update `getSubjectCurrentStepLabel` to use the reconciled active stage after `deriveImageSteps` fixes.

### 5. Remove Subject Details Card

Remove the `Subject Details` card from the right column entirely.

Keep only:

- Run Telemetry
- Operator Console Log

If target/container/input still needs to be available, move only a compact subset into the header or under the Stage Timeline subtitle. But the user explicitly says Subject Details card is not needed, so do not replace it with another details card.

### 6. Make Popup Wider

In the modal shell:

Current:

```tsx
max-w-[1180px] w-[min(1180px,calc(100vw-2rem))]
```

Change to something wider:

```tsx
max-w-[min(1560px,calc(100vw-1.5rem))] w-[min(1560px,calc(100vw-1.5rem))]
```

or:

```tsx
w-[min(1540px,calc(100vw-1.5rem))]
```

Keep `max-h-[92vh]` or increase slightly to `max-h-[94vh]` if useful.

Update body grid after removing Subject Details:

```tsx
lg:grid-cols-[minmax(0,1.65fr)_minmax(420px,0.85fr)]
```

The left stage area should benefit most from the added width.

### 7. Improve Stage Metric Separation

Keep the refined calm row style, but make Elapsed/CPU/RAM visually separated.

Do not revert to boxed metric chips. Instead use separated inline groups:

```tsx
<div className="flex flex-wrap justify-end overflow-hidden rounded-md border border-cursor-hairline-soft bg-cursor-canvas-soft px-2 py-1 text-[12px]">
  <StageMetric ... />
  <span className="h-4 w-px bg-cursor-hairline" />
  <StageMetric ... />
  <span className="h-4 w-px bg-cursor-hairline" />
  <StageMetric ... />
</div>
```

Or use CSS borders between metric cells:

```tsx
<div className="grid grid-cols-3 overflow-hidden rounded-md border border-cursor-hairline-soft bg-cursor-canvas-soft">
  <StageMetric className="px-2 py-1" ... />
  <StageMetric className="border-l border-cursor-hairline-soft px-2 py-1" ... />
  <StageMetric className="border-l border-cursor-hairline-soft px-2 py-1" ... />
</div>
```

This provides separation without the previous spreadsheet look.

### 8. Improve Telemetry Graphs

Replace tiny 200px sparklines with a larger responsive SVG.

Update `MetricSparkline`:

- Use `viewBox="0 0 320 104"` or similar.
- Use `preserveAspectRatio="none"` so it fills width.
- Render a soft filled area under the line.
- Render 2-3 horizontal gridlines using `stroke-cursor-hairline-soft`.
- Render latest point marker.
- Use a larger chart area: `h-28` or `h-32`.
- Reduce labels clutter: no duplicate peak label at both top and bottom.
- For RAM, format values as MB/GB properly.
- Use min/max scaling from safe points with a small padding. Current baseline always includes 100, which compresses RAM/CPU if values are far away.

Suggested shape:

```tsx
const width = 320;
const height = 104;
const minPoint = Math.min(...safePoints);
const maxPoint = Math.max(...safePoints);
const padding = Math.max((maxPoint - minPoint) * 0.12, maxPoint === minPoint ? Math.max(maxPoint * 0.1, 1) : 1);
const yMin = Math.max(0, minPoint - padding);
const yMax = maxPoint + padding;
```

Build both `polylinePoints` and an `areaPoints` polygon:

```tsx
const baselineY = height - 8;
const areaPoints = `0,${baselineY} ${polylinePoints} ${width},${baselineY}`;
```

Note: If first point x is not 0 due to point mapping, build the area with first/last coordinates explicitly. Keep it simple but correct.

Visual classes:

```tsx
<polygon className="fill-cursor-primary/10" points={areaPoints} />
<polyline className="fill-none stroke-cursor-primary stroke-2" points={polylinePoints} />
<circle className="fill-white stroke-cursor-primary stroke-2" ... />
```

Make each telemetry card taller and clearer:

```tsx
className="rounded-xl border border-cursor-hairline-soft bg-cursor-canvas-soft p-4"
```

### 9. Fix Log Card Layout Bug

After removing Subject Details, give log more vertical room.

In the right column, make telemetry flex-none and log flex-1:

```tsx
<div className="flex min-h-0 flex-col gap-4 overflow-hidden ...">
  <div className="... flex-none">Run Telemetry</div>
  <div className="... flex-1 min-h-0 flex flex-col">Operator Console Log</div>
</div>
```

For the log card:

- Put controls in a clean row.
- Ensure `CardContent`/wrapper has `flex-1 min-h-0`.
- Make `pre` fill available height and wrap instead of causing horizontal scroll:

```tsx
className="h-full min-h-0 w-full overflow-auto whitespace-pre-wrap break-words rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft p-3 font-mono text-[12px] leading-relaxed text-cursor-ink"
```

If a fixed minimum is needed, use `min-h-[18rem]`, but avoid nested scrollbars in both the right column and log `pre` when possible.

### 10. Verification

Run from `tauri-app/`:

```bash
npm run typecheck
```

If feasible:

```bash
npm run test
```

Manual checks:

- Open dialog on a running batch job.
- Popup is visibly wider and uses available screen width.
- Header/stage cards show `x/9 stages`, not `x/5`.
- Stage rows show actual tool display names, not `Default pipeline tool`.
- If log shows `RUNNING surface_reconstruction`, stage timeline highlights `Surface Reconstruction` as running, and earlier scheduled stages are no longer stuck running.
- Telemetry graphs are larger, clearer, and not tiny flat sparklines.
- Log card no longer has broken/clipped layout or prominent horizontal scrollbar.
- Elapsed/CPU/RAM are visually separated per stage.
- Subject Details card is gone.
- Modal still stays open during polling and updates in place.
