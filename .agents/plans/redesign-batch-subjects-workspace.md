# Redesign Batch Subjects Workspace

## Goal

Redesign the `Batch Subjects Workspace` card in `tauri-app/src/pages/JobsPage.tsx` to match `DESIGN.md` and the improved subject dialog. The current workspace card is functional but visually weak: plain card, small controls, tiny subject tile, poor progress information, and no clear hierarchy.

Do not change polling/data fetching behavior. The workspace must keep updating in place and opening the subject dialog must keep working.

## Current Code

Relevant section in `tauri-app/src/pages/JobsPage.tsx`:

- Batch workspace starts around line `590`.
- Header and controls around `600-648`.
- Subject grid and subject card around `651-697`.
- It uses `batchImages`, `filteredBatchImages`, `subjectSearchQuery`, `subjectStatusFilter`, `getSubjectCurrentStepLabel`, `deriveImageSteps`, `selectedTools`, `stageOrder`, `stageLabels`, and `toolDisplayNames`.

## Design Direction

Follow `DESIGN.md`:

- Warm cream canvas (`bg-cursor-canvas`) should be visible inside the workspace.
- White cards over cream with hairline borders only.
- No shadows or heavy depth. Current `shadow-sm` on subject cards should go.
- Sea Blue should be restrained and reserved for active/running/interactive emphasis.
- Use normal sans for subject titles and stage names. Use mono only for filenames/paths/IDs if needed.
- Prefer calm editorial hierarchy over dashboard clutter.

The workspace should feel like a batch command board:

- Strong title/header area with subtitle.
- Compact status summary strip for All/Success/Running/Failed/Pending counts.
- Search and filters integrated cleanly.
- Subject cards show stage progress clearly, not just `Current: Surface Registration`.

## Implementation Plan

### 1. Add Per-Subject Derived View Data

In `JobsPage.tsx`, near `filteredBatchImages` or before return, build a helper or inline map for subject card display.

For each subject card, derive:

- `steps = deriveImageSteps(safeEvents, img, selectedTools, stageOrder, stageLabels)`
- `totalStages = steps.length`
- `completedStages = steps.filter((s) => s.status === 'success').length`
- `runningStep = steps.find((s) => s.status === 'running')`
- `failedSteps = steps.filter((s) => s.status === 'failed').length`
- `currentStepText` using existing `getSubjectCurrentStepLabel(img)` or direct running/completed/failed logic
- `runningToolLabel = runningStep?.tool ? toolDisplayNames[runningStep.tool] || runningStep.tool : ''`
- `progressPercent = totalStages ? Math.round((completedStages / totalStages) * 100) : 0`

Keep this local in the `.map()` if simplest. Do not introduce global state.

### 2. Add Batch Status Counts For Filters

Create small derived counts for filter tabs:

```ts
const subjectFilterCounts = {
  all: batchImages.length,
  success: batchSummary.success,
  running: batchSummary.running,
  failed: batchSummary.failed,
  pending: batchSummary.pending,
};
```

Use these counts in the filter buttons.

### 3. Redesign The Workspace Shell

Replace the current workspace card classes around line `600`:

Current:

```tsx
<Card className="p-4 bg-white border-[#e6e5e0] flex-1 flex flex-col overflow-hidden">
```

Recommended:

```tsx
<Card className="flex-1 overflow-hidden border-cursor-hairline bg-white p-0 shadow-none flex flex-col">
```

Inside it, create a cream interior after the header:

```tsx
<div className="border-b border-cursor-hairline bg-white px-5 py-4">...</div>
<div className="flex min-h-0 flex-1 flex-col bg-cursor-canvas p-4">...</div>
```

This gives the card a designed shell rather than a flat white container.

### 4. Redesign Header

Use a two-row header or a responsive flex layout:

Left:

- Small uppercase eyebrow: `Batch monitor`.
- Title: `Batch Subjects` or `Subject Workspace` with `text-[18px] font-semibold leading-[1.4] text-cursor-ink`.
- Subtitle: e.g. `{batchImages.length} subjects tracked from events.jsonl`.

Right:

- A quiet count pill: `{filteredBatchImages.length}/{batchImages.length} shown`.
- Optional active count pill if running/pending > 0.

Use design tokens:

- `text-cursor-ink`, `text-cursor-body`, `text-cursor-muted`.
- `border-cursor-hairline`, `bg-cursor-canvas-soft`, `bg-white`.

### 5. Redesign Search And Filters

Move controls into a clean toolbar on the cream canvas:

```tsx
<div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-cursor-hairline bg-white p-3">
```

Search:

- Wider: `max-w-sm` or `w-[min(24rem,100%)]`.
- Use `h-10`, `text-sm`, `bg-cursor-canvas-soft` or `bg-white`.
- Avoid tiny `text-xs h-8.5`.

Filters:

- Use pill buttons with counts.
- Active: white/primary text with hairline border or `bg-cursor-primary text-white` only if it does not over-dominate.
- Inactive: `text-cursor-body hover:text-cursor-ink`.
- Include counts as muted small spans.
- Preserve `subjectStatusFilter` values exactly: `all`, `success`, `running`, `failed`, `pending`.

Example button content:

```tsx
<span>{label}</span>
<span className="rounded-full bg-cursor-canvas-soft px-1.5 text-[11px]">{count}</span>
```

### 6. Add A Compact Summary Strip

Above the subject grid, add a status strip using `batchSummary`:

- Total
- Running/Pending
- Success
- Failed

Use 4 small cells on desktop, 2 columns on mobile:

```tsx
<div className="mb-4 grid grid-cols-4 gap-3 max-[900px]:grid-cols-2 max-[520px]:grid-cols-1">
```

Cell style:

```tsx
rounded-xl border border-cursor-hairline bg-white p-3
```

Make it calm, not color-heavy. Use tiny colored dot/icon only.

This improves the workspace card itself and reduces dependence on the separate Batch Summary card.

### 7. Redesign Subject Cards

Replace the existing tiny 128px-tall cards.

Use larger, more useful cards:

```tsx
className="group flex min-h-[11rem] cursor-pointer flex-col rounded-xl border border-cursor-hairline bg-white p-4 text-left transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft focus:outline-none focus:ring-2 focus:ring-cursor-primary/30"
```

Use `<button type="button">` instead of clickable `<div>` if feasible for accessibility. If converting is too much, keep `<div>` but add `role="button"`, `tabIndex={0}`, `onKeyDown` for Enter/Space. Recommended: use `button`.

Card structure:

- Top row:
  - `#idx` quiet pill.
  - Subject ID title, readable and truncated.
  - Status pill aligned right.
- Filename/path:
  - mono code surface, one line, muted.
- Progress section:
  - Label: `Stage progress`.
  - Count: `{completedStages}/{totalStages}`.
  - Progress bar with calm color based on status.
- Current stage section:
  - Label: `Current stage`.
  - Value: current stage name.
  - If running tool label exists, show it as secondary line: e.g. `FreeSurfer 8 Surface Reconstruction`.
- Footer:
  - Duration if available.
  - Maybe `Open details` hint on hover.

Do not overuse badges. One status pill per card is enough.

### 8. Card Status Styling

Implement local helper functions near existing helpers:

```ts
function subjectCardAccentClass(status: string) { ... }
function subjectProgressClass(status: string) { ... }
```

Suggested:

- success: `bg-cursor-semantic-success`
- failed: `bg-cursor-semantic-error`
- running: `bg-cursor-primary`
- pending: `bg-cursor-hairline-strong`

Use colors primarily in thin progress bar/dot, not full-card backgrounds.

### 9. Subject Grid Layout

Current grid is `grid-cols-3`, which leaves large empty space for small batches and cramped cards for bigger names.

Use responsive auto-fit:

```tsx
<div className="grid flex-1 auto-rows-fr grid-cols-[repeat(auto-fill,minmax(20rem,1fr))] gap-4 overflow-y-auto p-1 min-h-0">
```

If Tailwind arbitrary repeat syntax is problematic, use:

```tsx
grid grid-cols-3 gap-4 max-[1400px]:grid-cols-2 max-[900px]:grid-cols-1
```

Prefer cards wide enough for long subject IDs. The screenshot currently has one narrow card on a huge empty area.

### 10. Empty State

Replace the dashed tiny empty state with a designed empty panel:

```tsx
<div className="col-span-full flex min-h-[14rem] flex-col items-center justify-center rounded-xl border border-dashed border-cursor-hairline bg-white p-8 text-center">
```

Text:

- Title: `No subjects match these filters`.
- Body: `Try a different status filter or search term.`

If `batchImages.length === 0`, use `No subject events yet`.

### 11. Preserve Behavior

- Search and status filters must keep working.
- Clicking a subject must still set `activeModalSubjectFile` and open the dialog.
- The card must update every polling tick without remounting the whole workspace or clearing filter/search state.
- Do not alter `loadJobDetails`, polling, modal state, or backend endpoints unless typecheck forces a small adjacent change.

### 12. Imports

Current imports include `ImageIcon`, `Filter`, `Search`, etc. Add icons only if useful and minimal. Avoid adding many decorative icons.

Potential useful existing/additional icons:

- `ImageIcon` already exists.
- `Filter`, `Search` already exist.
- If adding, `CheckCircle2`, `Clock3`, or `ArrowRight` are acceptable but not required.

Clean up unused imports after editing.

## Acceptance Criteria

- Workspace card visibly follows `DESIGN.md`: white shell, cream workspace floor, hairline borders, no shadows, restrained blue.
- Header has clear title/subtitle and shown/total count.
- Search/filter toolbar is polished and readable.
- Filter buttons show counts.
- Summary strip shows batch counts.
- Subject cards are larger, more useful, and show subject ID, filename, status, current stage, tool if available, and stage progress.
- Long subject names truncate cleanly without making the card unusable.
- Single-subject batch does not look like a tiny orphan tile in a huge blank panel.
- Opening subject dialog still works.
- Polling updates statuses/current stages/progress in place.

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

- Open Jobs Monitor on a running batch job.
- Confirm Batch Subjects Workspace uses the new design.
- Use search and all status filters.
- Click a subject card and confirm the subject progress dialog opens.
- Leave the page polling and confirm cards update without flicker/reset.
