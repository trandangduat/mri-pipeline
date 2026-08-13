# Redesign Job Progress Page

## Goal

Redesign the Jobs Monitor / Job progress page to follow the provided mock UI layout while using the actual visual system from `DESIGN.md`.

The mock is layout direction only. Do not copy its strong blue/red/green dashboard styling, heavy shadows, or spacing exactly. Use the repository's Cursor-inspired tokens: warm cream canvas, white card surfaces, hairline borders, restrained Sea Blue, semantic success/error only for status, no drop shadows.

## Non-Goals

- Do not change job fetching, polling, event parsing, detail loading, filtering logic, or modal behavior.
- Do not remove the subject detail modal or its stage timeline/log/telemetry content.
- Do not create new persisted state or alter stores.
- Do not redesign the sidebar except for any necessary interaction compatibility.
- Do not add broad backwards-compatibility shims.

## Files To Inspect/Edit

Primary file:

- `tauri-app/src/pages/JobsPage.tsx`

Reference files:

- `DESIGN.md`
- `tauri-app/src/styles.css` for available `cursor-*` Tailwind theme tokens.
- `tauri-app/src/components/ui.tsx` and `tauri-app/src/lib/uiTokens.ts` for `StatusPill` and button/status conventions.
- `tauri-app/src/AppSidebar.tsx` only for understanding how the job list appears in the left sidebar.

Expected implementation should likely touch only `JobsPage.tsx`. If imports need cleanup, do that in the same file.

## Current State Summary

`JobsPage.tsx` already derives all required data:

- `job`, `displayMeta`, `normState`, `isTerminal`, `isServerJob`.
- `batchImages`, `batchSummary`, `filteredBatchImages`, `subjectFilterCounts`.
- `getSubjectCurrentStepLabel(img)` and per-subject `deriveImageSteps(...)` data in the subject card map.
- `refreshJobs`, `handleDownloadClick`, subject filtering/search, subject detail modal state.

The current page structure around the main return is:

- Top grid with Job Overview card and Batch Summary card.
- `Batch Subjects` panel with header, search/filter toolbar, summary strip, and subject cards.
- Subject detail modal overlay.

This is close functionally but should be re-laid out to match the mock's page composition:

- Top left large job-detail card.
- Top right batch summary/action card.
- Wide lower `Batch Subjects` card with simple card grid/list controls.
- More compact, direct subject cards showing subject number, subject name, stage, and status.

## Design Requirements From DESIGN.md

Use tokens/classes instead of inline hex whenever possible:

- Page canvas: `bg-cursor-canvas` (`#f7f7f4`).
- Card surface: `bg-white` / `bg-cursor-surface-card`.
- Hairlines: `border-cursor-hairline`, `border-cursor-hairline-soft`, `border-cursor-hairline-strong`.
- Ink/body/muted text: `text-cursor-ink`, `text-cursor-body`, `text-cursor-muted`, `text-cursor-muted-soft`.
- Primary action only: `bg-cursor-primary`, hover/active `bg-cursor-primary-active`.
- Semantic status: `text-cursor-semantic-success`, `text-cursor-semantic-error` and matching borders/backgrounds where needed.
- Running status should use Sea Blue (`cursor-primary`) rather than timeline pastel unless using existing `StatusPill` behavior. Avoid introducing new color palettes.
- Cards should be rounded `rounded-xl`/`rounded-lg`, hairline-only depth, `shadow-none`.
- Use normal sans for labels/content; use `font-mono` only for paths, logs, IDs where helpful.
- Keep touch targets around `h-10`/`h-11` for buttons and inputs.

## Implementation Plan

### 1. Update Imports

In `JobsPage.tsx`, adjust lucide imports to support the mock-inspired controls if useful.

Recommended icons:

- Keep `Download`, `FileCheck`, `Layers`, `Loader2`, `RefreshCw`, `Search`, `Square`, `X`, `Eye`, `EyeOff`, `Eraser`, `ImageIcon` if still used.
- Consider adding `ArrowLeft`, `BrainCircuit`, `CalendarDays`, `CheckCircle2`, `CircleDot`, `LayoutGrid`, `List`, and/or `PanelTop` if they improve readability.
- Remove unused imports after the redesign. Run typecheck/lint to catch this.

Do not spend time creating a custom icon component. Lucide icons are sufficient.

### 2. Add Small Local View Helpers

Keep helpers in `JobsPage.tsx` near existing helper functions or above return. Avoid new files.

Add local status helper functions if needed:

```ts
function subjectAccentClasses(status: string) {
  if (status === 'success') return 'text-cursor-semantic-success border-cursor-semantic-success/25 bg-cursor-semantic-success/5';
  if (status === 'failed') return 'text-cursor-semantic-error border-cursor-semantic-error/25 bg-cursor-semantic-error/5';
  if (status === 'running') return 'text-cursor-primary border-cursor-primary/25 bg-cursor-primary/5';
  return 'text-cursor-muted border-cursor-hairline bg-cursor-canvas-soft';
}
```

If using colored subject icons, keep them semantic/restrained:

- Success: `text-cursor-semantic-success`.
- Failed: `text-cursor-semantic-error`.
- Running: `text-cursor-primary`.
- Pending: `text-cursor-muted`.

Do not use large saturated blocks for statuses except status pills/buttons. The mock's color-blocked summary should be translated into quieter DESIGN.md styling.

### 3. Replace The Top Page Layout

Rewrite the top part of the return from the outer wrapper through the top grid.

Recommended outer wrapper:

```tsx
<div className="flex h-full min-h-0 flex-1 flex-col gap-4 overflow-hidden text-cursor-ink">
```

Recommended top grid:

```tsx
<div className="grid flex-none grid-cols-[minmax(0,1fr)_minmax(20rem,28rem)] gap-4 max-[1180px]:grid-cols-1">
```

Left card should become a mock-like job detail block:

- White card, `rounded-xl`, `border-cursor-hairline`, `shadow-none`, `p-5`.
- Header row with a small circular back/return button, large job title, and status/target/mode pills on the right.
- The back button can be non-routing and simply call `setActiveModalSubjectFile(null)` or be decorative disabled if there is no obvious job-list route. Prefer not to change navigation semantics. If implementing, `window.history.back()` is acceptable only if it does not break direct `/jobs/:jobId` use; otherwise keep it as a quiet icon button that does nothing only if marked `aria-label` and disabled. Simpler: omit the back button if it would be fake. The sidebar already handles job selection.
- Job title: `(job?.display_name as string) || (job?.job_id as string) || 'No Job Selected'`.
- Pills: `StatusPill`, target badge, pipeline mode badge.

Metadata table should match the mock's two-column key/value rows:

- Use a bordered rounded `div`, not necessarily a `<table>` if a CSS grid is cleaner.
- Rows: `Started`, `Process PID`, `Model / Review` or `Mode / Device`, `Threads`, `RAM Alloc`, `Container`, `Input Path`, `Output Path`.
- Keep `NeuroFlow` only if it is still valuable, but the mock does not show it. Prefer the mock list and omit `NeuroFlow` from this compact page unless removing it would lose important information. If uncertain, place `NeuroFlow` as a small pill in the header instead of an extra table row.
- Use `text-[14px]`/`text-[15px]`, row dividers `border-cursor-hairline-soft`, labels `font-semibold text-cursor-ink`, values `text-cursor-body` or `font-mono` for paths.
- Paths should truncate but expose `title={...}`.

Preserve loading/no-job behavior. If `job` is null, this top left card can still show `No Job Selected` and `N/A` rows.

### 4. Redesign Top Right Batch Summary / Actions Card

Move the primary actions out of the job info card and into the right summary card, as in the mock.

Card content:

- Header: icon + `Batch Summary` title.
- Segmented horizontal count bar with four segments: Success, Failed, Running, Pending.
- Legend row or compact two-column legend with colored dots and counts.
- Action buttons stacked vertically: Refresh Jobs, Stop Job, Download Outputs.
- `downloadNotice` should render below buttons as a quiet notice box.

Segment calculation:

- Current code computes `successPct`, `failedPct`, and `activePct`, merging running/pending. Change this to separate `runningPct` and `pendingPct` for the four-segment mock layout.
- Avoid `Math.round` sums causing >100 width. Use raw ratio widths:
  - `const successWidth = batchSummary.total ? (batchSummary.success / batchSummary.total) * 100 : 0;`
  - same for failed/running/pending.
- If total is 0, show an empty rounded bar with muted text like `No subjects yet`.

Segment style mapping:

- Success: `bg-cursor-semantic-success`.
- Failed: `bg-cursor-semantic-error`.
- Running: `bg-cursor-primary`.
- Pending: `bg-cursor-muted` or `bg-cursor-hairline-strong` with dark text if using light background.

Button styles:

- Refresh: full width Sea Blue, pending state exactly per `DESIGN.md`: disabled, spinning `Loader2`, text `Refreshing...`.
- Stop Job: full width white/outline danger, not filled unless you keep shadcn destructive disabled semantics. Recommended class: `border-cursor-semantic-error text-cursor-semantic-error bg-white hover:bg-cursor-semantic-error/5`.
- Download Outputs: full width white/outline ink/body, disabled unless terminal.
- Keep the existing handlers and disabled conditions.

### 5. Simplify Batch Subjects Section To Match The Mock

Replace the current lower panel shell with a mock-like wide card:

- `Card className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border-cursor-hairline bg-white p-0 shadow-none"`
- Header row: left icon + `Batch Subjects` + pill `{batchImages.length} subjects`.
- Right controls: segmented icon buttons for grid/list view visual only or functional if easy.

Important: The current page has search/filter controls. The mock does not show them. Do not remove useful functionality completely. Use one of these minimal approaches:

- Preferred: Keep search/filter controls in a compact secondary toolbar under the header, but visually quiet and collapsible-looking.
- Acceptable: Keep status filter chips and search in the header area if it fits.

Do not add real list/grid state unless it is cheap and fully works. If adding a view toggle:

- `const [subjectViewMode, setSubjectViewMode] = useState<'grid' | 'list'>('grid');`
- Grid mode matches mock cards.
- List mode can be a simple one-column compact row version using the same data.
- If not implementing real toggling, do not render fake clickable controls. Use a static grid icon only or omit controls.

### 6. Redesign Subject Cards

Subject cards should match the mock's information density:

- Left colored outline brain/status icon.
- Top small label: `Subject #007` using padded `img.idx` if desired: `String(img.idx).padStart(3, '0')`.
- Main title: `img.subject_id` or filename-derived label.
- Two detail rows:
  - `Stage:` `{currentStepText}`.
  - `Status:` semantic uppercase status.
- Use small calendar/check/circle icons for detail rows if imported, otherwise text labels are enough.

Keep subject cards clickable to open modal:

```tsx
onClick={() => setActiveModalSubjectFile(img.input_file)}
```

Card classes:

- `rounded-xl border border-cursor-hairline bg-white p-4 text-left shadow-none transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft`.
- Grid: `grid grid-cols-3 gap-4 max-[1400px]:grid-cols-2 max-[900px]:grid-cols-1 overflow-y-auto`.
- Do not include the previous progress bar unless it can fit without clutter. The mock does not show it. If keeping it, make it a 1px/2px subtle footer, not the main visual.

Stage text should reuse current derivation:

- `const currentStepText = getSubjectCurrentStepLabel(img);`
- For failed subjects, if `deriveImageSteps` finds a failed step, stage should show that failed step label where possible instead of generic `Failed`.
- For pending, `Waiting in queue` or `Queued` is acceptable.

Status label mapping:

- Success: `SUCCESS` in semantic success.
- Failed: `FAILED` in semantic error.
- Running: `RUNNING` in primary.
- Pending: `PENDING` in muted/ink.

### 7. Preserve Empty And Loading States

Keep the existing loading skeleton block, but restyle it consistently if needed.

For no subjects or no filter match:

- Keep the empty state inside the lower card grid area.
- Use `ImageIcon`, title, and explanatory body text.
- Maintain current messages or equivalent.

For no selected job:

- Keep the existing `No Job Selected` card and refresh button behavior.
- Restyle with token classes if touched.

### 8. Keep Subject Detail Modal Working

Do not restructure modal logic unless a class conflict is introduced.

Verify after changes:

- Clicking a subject still sets `activeModalSubjectFile` and opens the modal.
- Escape closes modal.
- Modal close button closes modal.
- Log search/raw/clear controls still work.

### 9. Remove Obsolete Calculations

After splitting running/pending in the summary, remove unused variables:

- `activeCount` if no longer used.
- `activePct` if no longer used.
- Any imports only needed by the old page.

Do not remove data variables that are still used by the modal.

## Acceptance Criteria

- Job progress page visually follows the mock composition: top job details + right batch summary/actions + lower batch subjects card grid.
- Styling follows `DESIGN.md`: cream canvas, white cards, hairline borders, no shadows, Sea Blue restrained, semantic colors only for statuses.
- Refresh, stop, download, search/filter, subject modal, log controls, and polling behavior still work.
- Subject cards show subject number, subject label/name, current stage, and status in the simplified mock style.
- Batch summary shows separate Success / Failed / Running / Pending counts, not merged running/pending.
- Responsive behavior remains usable at desktop/tablet/mobile widths. Top grid collapses to one column below ~1180px; subject grid collapses 3 -> 2 -> 1 columns.
- No TypeScript or lint errors.

## Verification Commands

Run from `tauri-app/`:

```bash
npm run typecheck
npm run lint
```

If time permits, also run:

```bash
npm run test
```

If a verification command fails because of pre-existing unrelated issues, report the exact failure and whether it appears related to the redesign.

## Notes For Executor

- Make the smallest correct change. This should be a focused JSX/class rewrite in `JobsPage.tsx`, not a component architecture refactor.
- Prefer existing shadcn `Card`, `Badge`, `Button`, `Skeleton` imports if they still work with custom classes.
- Avoid fake controls. If you render view-toggle buttons, make them functional or omit them.
- Preserve all state updates and async handlers exactly unless there is a direct UI reason to move them.
- The supplied image shows a left job list, but this app already has `AppSidebar.tsx`; do not duplicate the job list inside `JobsPage.tsx`.
