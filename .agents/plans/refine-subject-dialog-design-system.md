# Refine Subject Progress Dialog Design System

## Goal

The new two-column layout is directionally correct, but the visual design does not match `DESIGN.md`. Refine the subject progress dialog in `tauri-app/src/pages/JobsPage.tsx` so it follows the documented Cursor-like design language:

- Warm cream canvas (`bg-cursor-canvas`) as the modal interior floor.
- White cards only as content surfaces over cream.
- Hairline-only depth; no heavy shadows.
- Restrained Sea Blue (`text-cursor-primary`) used sparingly.
- Editorial sans typography, with JetBrains Mono only for code/log/path surfaces and exact machine IDs.
- No boxed metric-grid look that makes the UI feel like a spreadsheet.
- Less green/blue full-card tinting; status should be visible but calm.

Preserve the current two-column information architecture:

- Left: Pipeline Stages.
- Right: Subject Details, Run Telemetry, Operator Console Log.

## Reference

Read `DESIGN.md` before editing. Relevant principles:

- Canvas: `#f7f7f4`, exposed generously.
- Card: white with 1px hairline border, no shadow.
- Typography: CursorGothic/Geist sans for normal UI; display/card titles use regular-to-semibold, not heavy/bold tech styling.
- JetBrains Mono only for code surfaces.
- Sea Blue is the single brand voltage and should be scarce.
- Timeline pastel palette may be used inside product timeline visualizations only, but do not turn the whole app into semantic neon blocks.

Existing Tailwind theme tokens are available in `tauri-app/src/styles.css`:

- `bg-cursor-canvas`
- `bg-cursor-canvas-soft`
- `bg-cursor-surface-card`
- `border-cursor-hairline`
- `border-cursor-hairline-soft`
- `text-cursor-ink`
- `text-cursor-body`
- `text-cursor-muted`
- `text-cursor-muted-soft`
- `text-cursor-primary`
- `text-cursor-semantic-success`
- `text-cursor-semantic-error`

## Current Problems To Fix

In `tauri-app/src/pages/JobsPage.tsx`, around the modal implementation:

- Dialog shell uses `bg-white` and `shadow-2xl`; this conflicts with hairline-only depth.
- Header is visually cramped and too system-modal-like.
- Left stage rows have large tinted blocks and four boxed metric chips per stage; this looks busy and industrial.
- Success rows are too green. Running row is too blue. The design should be quieter.
- Metric chips look like editable form fields/spreadsheet cells.
- Right column is cramped; Subject Details is a label/value table with awkward wrapping.
- Operator Console controls wrap badly and create visual clutter.
- Mono font appears in normal UI values where it should not.
- The log surface has horizontal scroll/clipping and should feel like a deliberate code pane.

## Implementation Plan

1. Refine modal shell and overlay.

   Replace the heavy modal look with hairline-only depth:

   - Overlay: `bg-cursor-ink/35 backdrop-blur-[2px]` is enough.
   - Shell: `bg-cursor-canvas border border-cursor-hairline rounded-xl shadow-none`.
   - Keep the existing width/max-height from the previous layout.
   - Remove `shadow-2xl`.

   Example direction:

   ```tsx
   className="relative bg-cursor-canvas border border-cursor-hairline rounded-xl max-w-[1180px] w-[min(1180px,calc(100vw-2rem))] max-h-[92vh] flex flex-col shadow-none overflow-hidden"
   ```

2. Redesign the modal header into an editorial title band.

   Keep it compact but more polished:

   - Background should be `bg-cursor-canvas`, not white/gray.
   - Use `px-6 py-5`, `border-b border-cursor-hairline`.
   - Subject index badge should be a small white hairline badge, not bright blue-heavy.
   - Subject title should be `text-[22px] font-medium leading-tight tracking-[-0.01em] text-cursor-ink` or similar.
   - Path should be a deliberate code/path surface: small rounded `bg-white border border-cursor-hairline-soft px-2 py-1 font-mono text-[11px] text-cursor-body` with truncation.
   - Stage completion summary should be a quiet pill, not plain text.
   - StatusPill can remain, but avoid adding extra blue emphasis.

3. Keep the two-column body but expose cream canvas.

   - Body container: `bg-cursor-canvas p-5`.
   - Cards: `bg-white border border-cursor-hairline rounded-xl p-5 shadow-none`.
   - Use `gap-4` or `gap-5`.
   - Right rail can be slightly wider if needed: `lg:grid-cols-[minmax(0,1.45fr)_minmax(360px,0.95fr)]`.

4. Rework the Pipeline Stages card header.

   Current header is too small. Use:

   - Eyebrow: `Pipeline` in uppercase caption style, muted.
   - Title: `Stage Timeline`, `text-[18px] font-semibold leading-[1.4]`.
   - Subtitle: `Live execution, tools, and resource usage for this subject`.
   - Completion pill on the right: white/hairline, uppercase caption.

   Avoid overusing Sea Blue icons. If keeping `ListOrdered`, use `text-cursor-muted` or place it in a muted 32px square.

5. Replace the current stage row treatment.

   The current row design is the main problem. Redesign `VerticalTimelineStepRow` to look like a calm timeline, not cards with form fields.

   Recommended structure:

   - Timeline gutter on the left with subtle hairline connector.
   - Dot only carries status color.
   - Main row is white or canvas-soft, with a thin border. Avoid full green/blue backgrounds.
   - Running row may have `border-cursor-primary/40 bg-cursor-canvas-soft` and a small running pill.
   - Success row may have `border-cursor-hairline bg-white`; use a green dot/check only.
   - Failed row may have subtle error border/background only.
   - Not scheduled row: muted text, `bg-cursor-canvas-soft`, no metrics.

   Suggested row layout:

   ```tsx
   <div className="relative grid grid-cols-[1.25rem_minmax(0,1fr)] gap-3">
     <div className="relative flex justify-center pt-4">
       {!isLast && <span className="absolute top-7 bottom-[-1rem] w-px bg-cursor-hairline" />}
       <span className={dotClass} />
     </div>
     <div className={rowClass}>
       <div className="flex min-w-0 items-start justify-between gap-4">
         <div className="min-w-0">
           <div className="flex flex-wrap items-center gap-2">
             <h4 className="m-0 text-[15px] font-semibold leading-[1.4] text-cursor-ink">...</h4>
             {statusBadge}
           </div>
           <p className="m-0 mt-1 text-[13px] leading-[1.4] text-cursor-body">...</p>
         </div>
         <div className="flex flex-wrap justify-end gap-x-4 gap-y-1 text-[12px] text-cursor-body">...</div>
       </div>
     </div>
   </div>
   ```

   Metrics should be inline text pairs, not four boxed chips:

   ```tsx
   <StageMetric label="Elapsed" value={formatElapsed(step.elapsed_sec)} />
   <StageMetric label="CPU" value={formatMetricValue(step.cpu_pct, '%', 1)} />
   <StageMetric label="RAM" value={formatMemory(step.ram_bytes)} />
   ```

   `StageMetric` should render like:

   ```tsx
   <span className="inline-flex items-baseline gap-1.5 whitespace-nowrap">
     <span className="text-cursor-muted">{label}</span>
     <span className="font-medium text-cursor-ink">{value}</span>
   </span>
   ```

   Only use `font-mono` for values if they are truly machine/code-like. For elapsed/CPU/RAM, prefer normal sans.

6. Improve status badges within stage rows.

   The global `Badge` component forces `font-mono`. For this dialog, use a local `StageStatusPill` instead of `Badge` for stage row statuses.

   Desired classes:

   - Base: `inline-flex rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.08em]`.
   - Success: `border-cursor-semantic-success/20 bg-cursor-semantic-success/5 text-cursor-semantic-success`.
   - Running: `border-cursor-primary/20 bg-cursor-primary/5 text-cursor-primary`.
   - Failed: `border-cursor-semantic-error/20 bg-cursor-semantic-error/5 text-cursor-semantic-error`.
   - Pending/not scheduled: `border-cursor-hairline bg-cursor-canvas-soft text-cursor-muted`.

7. Remove or repurpose `MetricChip`.

   The current `MetricChip` creates the worst visual issue. Replace it with inline `StageMetric`, or a much quieter compact stat line. Do not keep four boxed fields under every stage.

8. Redesign Subject Details card as summary blocks, not a label/value table.

   Current card feels cramped. Use 2-3 concise sections:

   - A prominent current stage block at top:
     - Label: `Current stage`.
     - Value: stage name, larger type.
     - Supporting text: progress like `4 of 5 scheduled stages complete`.
   - A compact two-column stat grid:
     - Target.
     - Container.
     - Failed stages, only if nonzero.
     - Input filename.
   - Path can stay a code surface if included, but keep it clipped and readable.

   Use cream-soft stat cells sparingly: `bg-cursor-canvas-soft border border-cursor-hairline-soft rounded-lg p-3`.

9. Redesign Run Telemetry card to feel like an IDE pane.

   The sparkline cards currently look generic. Make each telemetry panel closer to an IDE pane:

   - Container: `rounded-lg border border-cursor-hairline-soft bg-cursor-canvas-soft p-3`.
   - Label/value row at top, with sans label and mono value optional.
   - SVG in a calm code-pane-like area.
   - Stroke Sea Blue, but no excessive blue text.
   - For RAM, if unit is `MB`, display GB when large using a local formatter if easy; avoid `13507.0MB` in the UI.

   Update `MetricSparkline` to accept a formatter or infer by `unit`:

   - CPU current/peak: `100.5%`.
   - RAM current/peak: `174 MB`, `13.2 GB`.

   Keep implementation minimal; do not rewrite metric derivation.

10. Redesign Operator Console Log as a code pane.

   - Card header should not place controls in an awkward grid.
   - Use a header row with title/subtitle and a second small control row if needed.
   - Raw toggle and Clear should be quiet secondary buttons.
   - Search input should use `bg-white border-cursor-hairline h-8` and align naturally.
   - Log `pre` should be the strongest code surface:
     - `bg-cursor-canvas-soft`
     - `border border-cursor-hairline-soft`
     - `font-mono text-[12px] leading-relaxed`
     - `overflow-auto`
     - `whitespace-pre-wrap break-words`
   - Avoid horizontal scrollbar unless unavoidable.

11. Replace hard-coded hex classes in the modal area with design tokens where practical.

   In the modal-only block and helper components, prefer:

   - `text-cursor-ink` over `text-[#26251e]`
   - `text-cursor-body` over `text-[#5a5852]`
   - `text-cursor-muted` over `text-[#807d72]`
   - `border-cursor-hairline` over `border-[#e6e5e0]`
   - `bg-cursor-canvas` / `bg-cursor-canvas-soft` / `bg-white` appropriately

   Do not churn unrelated parts of `JobsPage.tsx` outside the modal and local helper functions.

12. Clean up imports.

   Current imports include `CheckCircle2`, `Clock3`, `Cpu`, `HardDrive`, `XCircle`, etc. Remove unused icons after the refinement. Add only minimal icons if needed.

## Acceptance Criteria

- The dialog still uses the implemented two-column layout.
- The dialog shell is cream, not a white shadowed box.
- No `shadow-2xl` or other heavy modal shadow remains in the subject dialog.
- Stage rows no longer show four boxed metric fields per row.
- Stage rows use a calm timeline: status dot/pill plus inline metrics.
- Success/running states are visible but not large tinted blocks.
- Right-side cards have cleaner hierarchy and no awkward table wrapping.
- Mono font is limited to the log pane, paths, and machine/container IDs.
- The log pane wraps text without the prominent horizontal scrollbar seen in the screenshot.
- Polling behavior, modal open/close behavior, log search, raw toggle, and clear still work.
- Changes stay focused in `tauri-app/src/pages/JobsPage.tsx` unless typecheck requires adjacent edits.

## Verification

Run from `tauri-app/`:

```bash
npm run typecheck
```

If feasible:

```bash
npm run test
```

Manual visual check:

- Open the subject dialog on a running batch job.
- Compare against `DESIGN.md`: cream canvas, white cards, hairline borders, no shadows, restrained blue.
- Confirm desktop shows Pipeline Stages left and other cards right.
- Confirm narrow widths collapse without clipped controls.
- Confirm stage metrics and telemetry update while the dialog remains open.
