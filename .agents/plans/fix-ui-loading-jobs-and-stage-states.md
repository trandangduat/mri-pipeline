# Fix UI Loading, Jobs Navigation, And Stage States

## Goal

Fix the four reported UI issues without changing backend behavior:

1. Tools image status loading should use skeleton loading instead of the empty dashed cards with icons/text.
2. Clicking `View Jobs` after successful preprocessing/start should keep jobs visible and navigate/select the job that was just started.
3. Skipped/not scheduled stages in the subject modal should be visually greyed out, should not show elapsed/CPU/RAM metrics, and text should say `Not available` instead of `Tool not reported yet` when no tool exists.
4. Batch Subjects should not replace the whole card with a skeleton when only details/status refresh. Remove count badges in Batch Subjects, make the body/header background consistent, and remove the wrapper card around search/filter controls.

## Relevant Files

- `tauri-app/src/pages/ToolsPage.tsx`
- `tauri-app/src/pages/PipelinePage.tsx`
- `tauri-app/src/components/StartPipelineDialog.tsx`
- `tauri-app/src/pages/JobsPage.tsx`
- `tauri-app/src/lib/jobs.ts`
- Optional tests in `tauri-app/test/jobs.test.ts` and/or `tauri-app/test/jobFormatters.test.ts`

## Investigation Notes

- `ToolsPage.tsx` currently shows dashed empty-state cards while `busy.refreshTools` is true and `latestImages` is empty. This is the source of Image 1's loading UI.
- `PipelinePage.tsx` handles the start dialog close in `handleDialogClose`. On success it currently does `navigate('/jobs')` and then `refreshJobs()`. It ignores `dialogJob`, so the newly started job is not selected or routed.
- `PipelinePage.tsx` also has a local-only `refreshJobs`, using `client.listLocalJobs()` only. For server starts this can overwrite the shared jobs store with only local jobs or an empty list, which explains the Jobs Monitor disappearing until manual refresh.
- `JobsPage.tsx` has the correct local + remote `refreshJobs` behavior, but it can briefly clear details through `loadJobDetails(..., resetUi: true)`, which causes the Batch Subjects whole-card skeleton at lines around 697-704.
- `VerticalTimelineStepRow` in `JobsPage.tsx` already hides metrics when `step.status === 'not_scheduled'`, but it still uses a weak not-scheduled visual and the default missing-tool text is `Tool not reported yet` for scheduled stages with no event tool.
- `deriveImageSteps` in `lib/jobs.ts` returns `not_scheduled` when a stage has no selected tool. There is also a `skipped` status type declared but not currently assigned by the derivation logic.
- `StartPipelineDialog` only exposes `onClose`; if the close behavior needs `dialogJob`, use closure in `PipelinePage` rather than changing the dialog API unless needed.

## Implementation Plan

### 1. Tools Image Status Skeleton Loading

In `tauri-app/src/pages/ToolsPage.tsx`:

- Import `Skeleton` from `@/components/ui/skeleton` or the existing relative path style used elsewhere (`components/ui/skeleton`). Follow repository import style in nearby files if lint prefers aliases.
- Add a small local component such as `ImageStatusSkeletonGrid` inside this file. Keep it simple.
- Only show skeletons when `busy.refreshTools && latestImages.length === 0`.
- For the `Available Images` section, replace the dashed empty state with skeleton cards during initial loading.
- For the `Not Available` section, replace the dashed empty state with skeleton cards during initial loading.
- Preserve existing cards during refresh when `latestImages.length > 0`, so manual refresh does not blank existing content.
- Keep the refresh button pending state unchanged.

Suggested shape:

```tsx
function ImageStatusSkeletonGrid({columns = 'available'}: {columns?: 'available' | 'missing'}) {
  const minWidth = columns === 'available' ? '24rem' : '20rem';
  return (
    <div className={`grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(${minWidth},1fr))]`}>
      {[0, 1, 2].map((i) => (
        <div key={i} className="rounded-xl border border-cursor-hairline bg-white p-4">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="mt-3 h-3 w-1/2" />
          <Skeleton className="mt-5 h-9 w-full" />
        </div>
      ))}
    </div>
  );
}
```

If Tailwind cannot handle dynamic arbitrary class strings, use two static class branches instead of interpolating `minmax(...)`.

### 2. Fix `View Jobs` Navigation And Jobs Disappearing

In `tauri-app/src/pages/PipelinePage.tsx`:

- Remove or avoid using the current local-only `refreshJobs` after a successful dialog close. It is not safe for server jobs because it calls only `client.listLocalJobs()`.
- Use `dialogJob` from `useStartPipelineStream()` when `dialogSuccess` is true.
- Normalize the started job with `normalizeJob(dialogJob, isRemote ? 'Server' : 'Local')`, where target can be read from `dialogJob.target` first and then `formValues.runtimeTarget`.
- Merge the normalized started job into the existing jobs store instead of replacing the entire list:
  - Read existing jobs from `useJobsStore.getState().latestJobs` inside the handler to avoid stale closure issues.
  - Replace any existing job with the same `job_id`; otherwise prepend/add it.
  - Sort with `sortJobsByStartedAtDesc`.
  - Call `setLatestJobs(mergedJobs)`.
- Set the selected job ID to the new job ID before navigating.
- Navigate directly to `/jobs/${encodeURIComponent(newJobId)}`.
- Do not call the local-only `refreshJobs()` from `handleDialogClose`.
- If `dialogJob` is missing or does not produce a usable job ID, fall back to `navigate('/jobs')` and do not clear the existing jobs store.

Suggested handler outline:

```tsx
const handleDialogClose = () => {
  closeDialog();
  if (!dialogSuccess) return;

  if (dialogJob) {
    const target = String(dialogJob.target || formValues.runtimeTarget || 'Local');
    const normalized = normalizeJob(dialogJob, target === 'Server' ? 'Server' : 'Local');
    const newJobId = String(normalized.job_id || '');
    if (newJobId) {
      const existing = useJobsStore.getState().latestJobs || [];
      const merged = sortJobsByStartedAtDesc([
        normalized,
        ...existing.filter((j) => String(j.job_id || '') !== newJobId),
      ] as Record<string, unknown>[]);
      setLatestJobs(merged);
      setSelectedJobId(newJobId);
      navigate(`/jobs/${encodeURIComponent(newJobId)}`);
      return;
    }
  }

  navigate('/jobs');
};
```

- After this change, consider whether `PipelinePage.refreshJobs` and `PipelinePage.loadJobDetails` are still needed. If they become unused, remove them to satisfy lint/knip. Be careful not to remove `print` if it is still used elsewhere in the component.
- If `dialogJob` for remote starts contains `remote_job_dir` but no `job_id`, `normalizeJob` can derive a stable job ID from the basename of `remote_job_dir`. That is acceptable and aligns with existing formatter behavior.

### 3. Grey Out Skipped/Not Scheduled Stages And Hide Metrics

In `tauri-app/src/pages/JobsPage.tsx`:

- Treat both `not_scheduled` and `skipped` as skipped-like statuses in `StageStatusPill` and `VerticalTimelineStepRow`.
- Add a helper boolean inside `VerticalTimelineStepRow`:

```tsx
const isSkipped = step?.status === 'not_scheduled' || step?.status === 'skipped';
```

- Use `isSkipped` to:
  - Grey out the whole row with lower opacity and muted text.
  - Use a muted dot and muted border/background.
  - Hide the metrics pill entirely.
  - Set the tool label to `Not available`.
- For non-skipped stages with no tool, change `Tool not reported yet` to `Not available` per user request. The screenshot text says `Tools Not reported yet`, but the current code uses singular `Tool`; replace that displayed fallback.
- Ensure success/running/failed stages with a real tool still display the friendly tool name.

Suggested adjustments:

```tsx
const isSkipped = step?.status === 'not_scheduled' || step?.status === 'skipped';
const displayTool = step?.tool ? (toolDisplayNames[step.tool] || step.tool) : '';
const toolLabel = isSkipped || !displayTool ? 'Not available' : displayTool;
```

- Update title and paragraph classes when `isSkipped`, for example `text-cursor-muted` for title and `text-cursor-muted-soft` for tool label.
- Update `StageStatusPill` label for both skipped statuses to a concise grey label. Prefer `SKIPPED` for both `not_scheduled` and `skipped` unless product language requires `NOT SCHED.`. The user says stages are skipped, so `SKIPPED` is clearer.

In `tauri-app/src/lib/jobs.ts`:

- Do not introduce backend changes.
- If events can report skipped states, update `deriveImageSteps` so raw statuses like `skipped`, `skip`, `not_scheduled`, or `not scheduled` set `step.status` to `skipped` or `not_scheduled` consistently. Keep no-selected-tool stages as `not_scheduled`.
- Existing unit test `deriveImageSteps distinguishes pending vs not_scheduled stages` should still pass unless you update expectations for event-reported skipped statuses only.

### 4. Batch Subjects Card Loading And Styling

In `tauri-app/src/pages/JobsPage.tsx`:

- Remove the top-level conditional that replaces the whole Batch Subjects card when `isLoadingDetails` is true.
- Render the card whenever `job` exists, even while details are loading.
- Keep existing subjects visible while details reload. If there are no `batchImages` yet and `isLoadingDetails` is true, show a small inline skeleton inside the subject grid/list area only.
- Do not show the skeleton over the header/search/filter toolbar.
- Remove count badges in the Batch Subjects header:
  - Remove `{batchImages.length} subjects` badge.
  - Remove `{running + pending} active` badge.
- Remove count numbers from status filter pills:
  - Keep labels `all`, `OK`, `running`, `failed`, `pending`.
  - Remove the `<span>{count}</span>` count badge and remove unused `count` variable.
  - If `subjectFilterCounts` becomes unused, remove it.
- Make the Batch Subjects card background the same color as its header:
  - Current card/header are `bg-white`; body is `bg-cursor-canvas` at line around 753. Change body to `bg-white`, or use `bg-cursor-canvas` for both header/card if that better matches design. The request says same as card header, so minimal change is body `bg-white`.
  - If inner subject cards remain white on white, keep their border; optionally use `bg-cursor-canvas-soft` for subject cards only if needed for contrast, but prefer minimal change.
- Remove the wrapper around search bar and filter pills:
  - Current toolbar has `rounded-lg border border-cursor-hairline bg-white p-2.5`.
  - Replace with a plain flex row: `mb-4 flex flex-wrap items-center justify-between gap-3 flex-none`.
  - Keep the input itself styled with border/background.
- Add an inline subject skeleton component or JSX in grid/list area:
  - For grid mode, render 3-6 subject card-shaped skeletons when `isLoadingDetails && batchImages.length === 0`.
  - For list mode, render 4-6 list-row skeletons when `isLoadingDetails && batchImages.length === 0`.
  - If `batchImages.length > 0`, do not show skeleton; keep existing cards and let them update.
- For the no-job branch, keep the existing no-job empty state.

### 5. JobsPage Refresh Detail Flicker

Still in `JobsPage.tsx`:

- `refreshJobs()` currently calls `loadJobDetails(..., {resetUi: selectedChanged || !currentJob})`.
- This is reasonable for full job changes, but it causes large card replacement because the render uses `isLoadingDetails`. After removing the top-level Batch Subjects skeleton, this should no longer blank the card.
- Keep `isLoadingDetails` to control only inline placeholders or subtle pending indicators.

### 6. Tests And Verification

Run from `tauri-app/`:

```bash
npm run typecheck
npm run test -- jobs.test.ts jobFormatters.test.ts
```

If the targeted `npm run test -- ...` syntax does not work with this Vitest setup, run:

```bash
npm run test
```

Also run a quick full build/type verification if time permits:

```bash
npm run build
```

Manual checks in the UI:

- Open Tools Configuration with no cached images and trigger refresh. Both sections should show skeleton cards, not dashed icon empty states.
- Start a local pipeline, click `View Jobs`. It should navigate to `#/jobs/<jobId>`, the sidebar should keep/show jobs, and the new job should be selected.
- Start a server pipeline, click `View Jobs`. It should not wipe the sidebar because the local-only refresh is no longer called.
- Open a subject detail modal with skipped/unselected stages. Skipped rows should be muted/grey, say `Not available`, and omit elapsed/CPU/RAM metrics.
- Refresh a selected running job. Batch Subjects header and filters should remain visible; existing subject cards should not be replaced by a whole-card skeleton.
- Confirm Batch Subjects header/filter count badges are gone.

## Constraints

- Keep changes minimal and UI-only where possible.
- Do not change backend APIs.
- Do not remove unrelated user changes.
- Follow existing Tailwind token classes and no-shadow card style.
