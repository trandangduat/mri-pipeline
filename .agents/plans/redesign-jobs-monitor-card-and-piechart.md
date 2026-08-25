# Plan: Redesign Jobs Monitor Card and Pie Chart

## 1. Goal

Redesign the Job Cards in the Jobs Monitor page (`tauri-app/src/pages/JobsPage.tsx`) to improve readability, visual balance, and space efficiency while adhering strictly to all user constraints:
1. **Strictly NO monospace font**: Remove `font-mono` completely from Job Cards (Job Name, timestamp, etc.). Use the standard UI sans-serif font.
2. **Mandatory full job name**: Display the entire job name without shortening, truncation, ellipsis, or awkward multi-line word splitting.
3. **Mandatory Pie Chart with hover tooltips**: Maintain the Pie Chart in each card and add interactive hover tooltips to each slice (e.g., `Finished: 8`, `Running: 4`, `Pending: 3`, `Failed: 1`) along with smooth slice hover feedback.
4. **Strictly existing data only**: Do not introduce new data fields. Retain only:
   - Full Job ID / Name
   - Status Badge (`FINISHED`, `FAILED`, `RUNNING`) + Lagging badge if applicable
   - Preset Tag (`FreeSurfer 8 + Volume`, `Custom`, etc.)
   - Pie Chart (with status segment counts)
   - Timestamp (with Clock icon)
   - Action buttons (Delete icon `🗑️` and Detail chevron `>`)
5. **Right-aligned metadata & actions**: Position the Preset tag, Timestamp, and Action buttons in the space to the right of the Pie Chart.
6. **Responsive Grid**: Expand card minimum width in the grid layout (`minmax(22rem, 1fr)`) so cards have sufficient horizontal space for long job names and metadata.

---

## 2. Target Design & Layout Specification

### 2.1. Card Structure
```text
┌──────────────────────────────────────────────────────────────┐
│ job_20260825_120137                               [FINISHED] │
├──────────────────┬───────────────────────────────────────────┤
│                  │  🏷️ [ FreeSurfer 8 + Volume ]             │
│    (  Pie  )     │                                           │
│    ( Chart )     │  🕒 08/25/2026, 12:02:23 PM               │
│       ┌───────────────┐                                      │
│       │ 🟢 Finished:8 │                    [ 🗑️ ]    [ > ]    │
│       └───────────────┘                                      │
└──────────────────┴───────────────────────────────────────────┘
```

### 2.2. Visual & Interaction Details
- **Header Row**:
  - Full Job Name on the left (`text-xs font-semibold text-cursor-ink group-hover:text-cursor-primary transition-colors whitespace-nowrap`).
  - Status Badge + Lagging Badge on the right.
- **Divider**: Subtle hairline border (`border-t border-cursor-hairline-soft pt-2`).
- **Body Row (2-column layout)**:
  - **Left column**: `BatchPieChart` (size ~64px) inside a soft canvas container (`bg-cursor-canvas-soft border border-cursor-hairline-soft rounded-md p-1`).
  - **Right column**:
    - Preset tag pill (`text-2xs font-medium text-cursor-body bg-cursor-canvas border border-cursor-hairline px-2 py-0.5 rounded`).
    - Timestamp with Clock icon (`text-2xs text-cursor-muted font-sans` — strictly sans-serif).
    - Bottom action row with Delete button (`h-6.5 w-6.5 rounded hover:bg-cursor-semantic-error/10 hover:text-cursor-semantic-error`) and Detail navigation chevron (`>`).
- **Pie Chart Slice Tooltips**:
  - Slices have SVG `<title>` or Tooltip wrappers describing the segment (`Finished: X`, `Failed: Y`, `Running: Z`, `Pending: W`).
  - Slices have interactive hover styling (`hover:opacity-85 transition-opacity cursor-pointer`).

---

## 3. Files To Modify

### 3.1. `tauri-app/src/pages/JobsPage.tsx`
- **`BatchPieChart` component**:
  - Add interactive tooltips for multi-segment SVG paths and single solid circles.
  - Slices mapped with specific label tokens:
    - Success: `Finished: ${success}` (color `#1f8a65`)
    - Failed: `Failed: ${failed}` (color `#cf2d56`)
    - Running: `Running: ${running}` (color `#0077b6`)
    - Pending: `Pending: ${pending}` (color `#cfcdc4`)
  - Add `<title>{label}</title>` inside each `<path>` and `<circle>` SVG element for native instant tooltips.
  - Add slice hover transitions (`transition-all duration-200 hover:opacity-85 cursor-pointer`).
- **`JobCard` component**:
  - Change root container from side-by-side grid to vertical stack with top header and lower 2-column split.
  - Header: Job title (full name, sans-serif font, `whitespace-nowrap`) and Status badge.
  - Body: Left Pie Chart (64px) and Right metadata column (Preset tag, Timestamp without mono font, Delete & Chevron buttons).
  - Ensure all typography strictly uses sans-serif (no `font-mono`).
- **`JobsListView` component**:
  - Update grid columns from `[grid-template-columns:repeat(auto-fill,minmax(16rem,1fr))]` to `[grid-template-columns:repeat(auto-fill,minmax(22rem,1fr))]` for both Local Jobs and Server Jobs.

### 3.2. `tauri-app/test/JobsPage.test.tsx`
- Verify existing tests and update selector queries if necessary to ensure 100% test pass rate.

---

## 4. Verification & Testing

1. Run TypeScript check:
   ```bash
   cd tauri-app && npm run typecheck
   ```
2. Run test suite:
   ```bash
   cd tauri-app && npm test
   ```
3. Verify build:
   ```bash
   cd tauri-app && npm run build
   ```

---

## 5. Acceptance Criteria

- [ ] Job Cards display full job names without truncation or line-breaking glitches.
- [ ] No monospace font (`font-mono`) is used anywhere on the Job Cards.
- [ ] Pie Chart is preserved and displays accurate status slices.
- [ ] Hovering over Pie Chart slices displays tooltips indicating status and counts (`Running: X`, `Pending: Y`, etc.).
- [ ] Preset tag, Timestamp, and Action buttons are cleanly positioned on the right side of the Pie Chart.
- [ ] Only existing fields are used; no extra extraneous information is added.
- [ ] Grid layout maintains comfortable card widths across screen sizes.
- [ ] All unit tests pass with zero regressions.
