# Redesign Subject Progress Dialog

## Goal

Redesign the subject progress popup in `tauri-app/src/pages/JobsPage.tsx` so it has a clearer two-part layout:

- Left/main area: Pipeline Stage card focused on stage name, tool, status, elapsed time, and runtime metrics.
- Right/secondary area: separate cards for Run Telemetry, Operator Console Log, and compact subject/run metadata.

The current UI is too narrow, uses too much mono text, has small type, and hides key progress information inside cramped rows. Keep the existing live data behavior from the previous fix: polling should update content without closing or remounting the dialog.

## Current Code Location

All relevant UI is currently inline in `tauri-app/src/pages/JobsPage.tsx`:

- Modal overlay starts around line `709`.
- Modal content body starts around line `746`.
- `VerticalTimelineStepRow` helper starts around line `845`.
- `MetricSparkline` helper starts around line `912`.

The current helper and modal markup can be redesigned in place. Do not create a large component tree unless it clearly reduces complexity.

## Design Direction

Use a wider, dashboard-like dialog:

- Overlay remains centered with dark backdrop.
- Dialog should be wider: use something like `max-w-6xl` or `max-w-[1180px]`, `w-[min(1180px,calc(100vw-2rem))]`, `max-h-[92vh]`.
- Header should be cleaner and less mono-heavy:
  - Subject ID in normal sans font, `text-lg` or `text-xl`.
  - Input path as muted, readable text with truncation and `title`.
  - Keep subject number badge and status pill, but do not make the whole title mono.
  - Optionally include progress summary like completed stages over scheduled stages.
- Body should use a two-column layout on desktop:
  - `grid grid-cols-[minmax(0,1.55fr)_minmax(320px,0.9fr)] gap-4` or equivalent.
  - Left column: only Pipeline Stage card, scrollable if needed.
  - Right column: stacked cards for subject metadata/status summary, Run Telemetry, Operator Console Log.
  - On smaller screens, collapse to one column.
- Avoid tiny text. Use `text-sm` for primary information, `text-xs` for secondary labels, not `text-[10px]` except for small badges.
- Use mono font only where it helps: input path, log text, exact metric values. Stage labels and tools should use normal sans by default.

## Data Already Available

Inside `JobsPage`, the modal already has:

- `modalSubject`
- `modalImageSteps`
- `modalMetricsSeries`
- `filteredLog`
- `showRawLog`, `setShowRawLog`
- `jobLogSearch`, `setJobLogSearch`
- `clearJobLog`
- `displayMeta`
- `job`, `isServerJob`

`StageStepDetail` already includes:

- `stage`
- `label`
- `tool`
- `status`
- `elapsed_sec`
- `cpu_pct`
- `ram_bytes`
- `gpu_pct`
- `container_name`

No backend changes should be needed.

## Implementation Plan

1. Add small formatting helpers near `VerticalTimelineStepRow` or above the component return:

   ```ts
   function formatMetricValue(value: number | undefined, suffix: string, fractionDigits = 0) {
     if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return 'Not reported';
     return `${value.toFixed(fractionDigits)}${suffix}`;
   }

   function formatMemory(bytes: number | undefined) {
     if (typeof bytes !== 'number' || !Number.isFinite(bytes) || bytes <= 0) return 'Not reported';
     const mb = bytes / (1024 * 1024);
     if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
     return `${Math.round(mb)} MB`;
   }

   function formatElapsed(seconds: number | undefined) {
     if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds < 0) return 'Waiting';
     if (seconds >= 60) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
     return `${seconds.toFixed(1)}s`;
   }
   ```

   Exact names can vary. Keep helpers local and small.

2. Derive modal summary values before the return, near `modalImageSteps`:

   - `scheduledStageCount`: count stages whose status is not `not_scheduled`.
   - `completedStageCount`: count status `success`.
   - `runningStage`: first status `running`.
   - `failedStageCount`: count status `failed`.
   - `latestCpu`: last value in `modalMetricsSeries.cpuSeries`, if present.
   - `latestRam`: last value in `modalMetricsSeries.ramSeries`, if present.

   Example:

   ```ts
   const scheduledModalStages = modalImageSteps.filter((step) => step.status !== 'not_scheduled');
   const completedModalStages = scheduledModalStages.filter((step) => step.status === 'success').length;
   const runningModalStage = scheduledModalStages.find((step) => step.status === 'running');
   const failedModalStages = scheduledModalStages.filter((step) => step.status === 'failed').length;
   ```

3. Redesign modal shell:

   - Change dialog width from `max-w-4xl` to a wider max.
   - Header remains fixed at top of dialog.
   - Body uses grid and handles scrolling inside the body, not the whole window.
   - Use `min-h-0` and `overflow-auto` on columns/cards where needed.

   Suggested structure:

   ```tsx
   <div className="relative bg-white ... max-w-[1180px] w-[min(1180px,calc(100vw-2rem))] max-h-[92vh] flex flex-col overflow-hidden">
     <div className="... header ..." />
     <div className="grid flex-1 min-h-0 gap-4 overflow-hidden p-4 lg:grid-cols-[minmax(0,1.55fr)_minmax(320px,0.9fr)] max-[1024px]:overflow-auto max-[1024px]:grid-cols-1">
       <Card className="... pipeline card ..." />
       <div className="flex min-h-0 flex-col gap-4 overflow-auto">
         <Card>Subject Details / Current Status</Card>
         <Card>Run Telemetry</Card>
         <Card>Operator Console Log</Card>
       </div>
     </div>
   </div>
   ```

   Tailwind arbitrary grid classes are already used in the project; this is acceptable.

4. Redesign Pipeline Stage card:

   - Title should be `Pipeline Stages`, not `Pipeline Stage Execution Flow`.
   - Include a concise description/subtitle like `Live stage status and resource usage for this subject`.
   - Add a right header badge/summary: `{completedModalStages} / {scheduledModalStages.length} complete`.
   - Stage rows should be larger, readable, and structured as columns:
     - Left: status icon/dot and visual progression connector.
     - Middle: stage label and tool name.
     - Right: status badge and metrics chips.
   - Keep not scheduled rows visually quieter but readable; do not make them almost invisible.
   - For each stage display:
     - status
     - elapsed time
     - CPU
     - RAM
     - optional GPU if available

5. Replace or revise `VerticalTimelineStepRow`:

   Suggested props:

   ```ts
   function VerticalTimelineStepRow({step, isLast}: {step: StageStepDetail; isLast: boolean})
   ```

   Use `isLast` to stop the connector line after the last item.

   Use clearer visual treatment:

   - Success: green check-like dot, subtle green background.
   - Running: blue dot with small pulse and stronger left border/background.
   - Failed: red dot/background.
   - Pending: neutral dot/background.
   - Not scheduled: muted neutral background but readable text.

   Example row content:

   ```tsx
   <div className="relative grid grid-cols-[1.5rem_minmax(0,1fr)] gap-3">
     <div className="relative flex justify-center">
       {!isLast && <span className="absolute top-7 bottom-[-1rem] w-px bg-[#e6e5e0]" />}
       <span className={dotClass} />
     </div>
     <div className={rowClass}>
       <div className="min-w-0">
         <div className="flex flex-wrap items-center gap-2">
           <h4 className="m-0 text-sm font-semibold text-[#26251e]">{step.label || step.stage}</h4>
           {statusBadge}
         </div>
         <p className="m-0 mt-1 text-xs text-[#5a5852]">{toolLabel}</p>
       </div>
       <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
         <MetricChip label="Elapsed" value={formatElapsed(step.elapsed_sec)} />
         <MetricChip label="CPU" value={formatMetricValue(step.cpu_pct, '%', 1)} />
         <MetricChip label="RAM" value={formatMemory(step.ram_bytes)} />
         <MetricChip label="GPU" value={formatMetricValue(step.gpu_pct, '%', 1)} />
       </div>
     </div>
   </div>
   ```

   Add a tiny `MetricChip` helper if useful. Keep it local.

6. Redesign right-side Subject Details card:

   Include compact, useful info:

   - Current stage: `runningModalStage?.label || Completed/Failed/Waiting`.
   - Stage progress: completed over scheduled.
   - Failed stages count if nonzero.
   - Target: Local/Server.
   - Container: `modalMetricsSeries.latestContainer || 'None'`.
   - Input file path, truncated with `title`.

   This addresses the user's complaint about unupdated information by surfacing values derived from current `modalImageSteps` and `modalMetricsSeries`.

7. Redesign Run Telemetry card:

   - Keep CPU and RAM sparklines but make them bigger and clearer.
   - `MetricSparkline` should use `text-sm` label, readable current/peak values, and a taller SVG (`height` around 44 or 48).
   - Avoid mono font for all text; only metric values can be semibold/mono if desired.
   - If no points, show `No samples yet` instead of a flat baseline that looks broken.
   - GPU line can remain `Not reported` when no GPU data is available, but style it as a muted row.

8. Redesign Operator Console Log card:

   - Keep raw/sanitized toggle, search input, and clear action.
   - Make the header responsive: controls should wrap on narrow widths.
   - The log can stay mono, but use more comfortable sizing and a constrained height like `max-h-64` or `max-h-[22rem]`.
   - Use `aria-live="polite"` as existing.
   - Consider showing the current search state via placeholder only; no need for new features.

9. Update imports if needed:

   - Existing lucide imports include `LineChart`, `ListOrdered`, `Terminal`, etc.
   - If adding icons such as `Clock3`, `Cpu`, `HardDrive`, `CheckCircle2`, `Circle`, `XCircle`, import them from `lucide-react`.
   - Keep import additions minimal.

10. Preserve behavior:

   - Clicking the backdrop closes the modal.
   - Clicking inside the modal does not close it.
   - Close button and Escape still close it.
   - Polling updates should update modal contents in place.
   - Do not change the polling logic or data fetching logic for this UI redesign.

## Important Constraints

- Do not modify backend code.
- Do not change `deriveImageSteps` unless absolutely necessary for display correctness.
- Do not introduce a new route or modal library.
- Do not make the stage card and telemetry card visually identical; the stage card should be the primary focus.
- Keep the implementation within `JobsPage.tsx` unless extracting a small local component is clearly cleaner.
- Use the existing visual language: white cards, `#e6e5e0` borders, `#0077b6` blue, emerald/rose status colors.
- Avoid mono font for titles/stage names/tool names. Use mono only for paths/logs/exact metric values.

## Verification

Run from `tauri-app/`:

```bash
npm run typecheck
```

If feasible, run:

```bash
npm run test
```

Manual verification:

- Open the Jobs page and a subject progress dialog.
- Confirm desktop layout has Pipeline Stages on the left and metadata/telemetry/log cards stacked on the right.
- Confirm narrow/mobile width collapses to one column without clipped controls.
- Confirm stage rows show stage name, tool, status, elapsed time, CPU, RAM, and optional GPU clearly.
- Confirm Run Telemetry values update during polling without closing the dialog.
- Confirm log search/raw toggle/clear still work.
- Confirm Escape, close button, and backdrop click still close the dialog.
