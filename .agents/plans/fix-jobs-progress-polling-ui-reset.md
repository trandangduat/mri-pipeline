# Fix Jobs Progress Polling UI Reset

## Problem

On the job progress monitor page, the Batch Subjects Workspace visibly resets every 2 seconds while a running job is polled. If a subject detail popup is open, it also disappears after the next polling tick.

## Root Cause

The affected code is in `tauri-app/src/pages/JobsPage.tsx`.

`loadJobDetails` is used for both initial/job-switch detail loading and background 2-second polling. At the start of every call it currently does all of the following:

- `setIsLoadingDetails(true)`
- `setJobEvents([])`
- `setOutputText('')`
- `setActiveModalSubjectFile(null)`
- `setDownloadNotice(null)`

The polling effect at lines around `264-277` calls `loadJobDetails(selectedJobId, targetJob)` every 2 seconds while the selected job is running. Because the same function clears UI state before fetching, each poll temporarily replaces the Batch Subjects Workspace with the skeleton and closes the modal.

There is a secondary issue in `refreshJobs`: after listing jobs it calls `loadJobDetails(...)`, which also resets the detail UI. Manual refresh may reasonably show loading, but automatic polling must not.

## Implementation Plan

Make `loadJobDetails` distinguish a full/reset load from a background poll.

1. In `tauri-app/src/pages/JobsPage.tsx`, add an options parameter to `loadJobDetails`, for example:

   ```ts
   type LoadJobDetailsOptions = {
     resetUi?: boolean;
   };
   ```

   This can be declared near the component or inline as the third parameter type.

2. Change the `loadJobDetails` signature from:

   ```ts
   async (jobId: string | null, targetJob?: Record<string, unknown> | null) => {
   ```

   to something equivalent to:

   ```ts
   async (jobId: string | null, targetJob?: Record<string, unknown> | null, options: LoadJobDetailsOptions = {}) => {
     const resetUi = options.resetUi ?? true;
   ```

3. Keep the existing clearing behavior only when `resetUi` is true.

   Current unconditional block near the top:

   ```ts
   setIsLoadingDetails(true);
   setJobEvents([]);
   setOutputText('');
   setActiveModalSubjectFile(null);
   setDownloadNotice(null);
   ```

   should become:

   ```ts
   if (resetUi) {
     setIsLoadingDetails(true);
     setJobEvents([]);
     setOutputText('');
     setActiveModalSubjectFile(null);
     setDownloadNotice(null);
   }
   ```

   Do not clear `activeModalSubjectFile` on background polling.

4. In the `finally` block, only set loading false when the call was allowed to set loading true:

   ```ts
   if (seq === reqSeqRef.current) {
     setJobEvents(events);
     setOutputText(logText || '');
     if (resetUi) {
       setIsLoadingDetails(false);
     }
   }
   ```

   This avoids background polling toggling the skeleton state.

5. Update the 2-second polling effect to use background mode:

   ```ts
   void loadJobDetails(selectedJobId, targetJob, {resetUi: false});
   ```

6. Keep job selection loads as reset/full loads. The existing calls in the selected job change effect can rely on the default `{resetUi: true}`.

7. For `refreshJobs`, choose the behavior intentionally:

   - If manual refresh should not interrupt the workspace/modal, call `loadJobDetails(..., {resetUi: false})` when the selected job remains the same.
   - If manual refresh selects a different job or no current job exists, use the default full load.

   Recommended minimal logic:

   ```ts
   const selectedChanged = nextSelected !== selectedJobId;
   await loadJobDetails(currentJob ? nextSelected : '', currentJob as Record<string, unknown>, {
     resetUi: selectedChanged || !currentJob,
   });
   ```

   This preserves UI for the current job during refresh, but still resets when the selected job changes.

8. Preserve the existing `!jobId` behavior. Clearing events/log/modal for no selected job is correct.

## Important Constraints

- Do not remount or rewrite the whole page.
- Do not move modal state out of `JobsPage` unless absolutely necessary. The minimal fix is to stop clearing it during polling.
- Do not disable polling. The live data should continue updating.
- Do not introduce backward-compatibility code.
- Keep changes limited to `tauri-app/src/pages/JobsPage.tsx` unless typecheck reveals a needed adjacent type/test fix.

## Expected Behavior After Fix

- While a running job is polled every 2 seconds, subject cards update statuses/current steps without the workspace flashing to skeleton.
- Search text and status filter remain stable during polling.
- An open subject detail popup remains open during polling.
- The popup contents can still update as new events arrive.
- Selecting a different job still resets details and closes stale modal state.
- If there is no selected job, the page still clears detail state as before.

## Verification

Run from `tauri-app/`:

```bash
npm run typecheck
```

If feasible, also run:

```bash
npm run test
```

Manual verification if running the app is feasible:

- Open a running batch job in the Jobs/progress page.
- Confirm the Batch Subjects Workspace does not flash/skeleton every 2 seconds.
- Open a subject detail modal and leave it open longer than one polling interval.
- Confirm the modal stays open and its timeline/metrics/log update as data changes.
- Switch to a different job and confirm stale modal/details are cleared.
