# Sidebar Jobs Grouping And SSH Refresh

## Goal

Improve Jobs Monitor sidebar UX so it does not dump every local and server job into one flat list.

Required behavior:

- Under `Jobs Monitor`, group jobs by target: `Local` and `Server`.
- Within each group, sort jobs by `started_at` descending so the most current jobs appear first.
- Cap visible sidebar jobs per group, recommended `3` per group.
- If a group has more jobs than the cap, show a `View all ... jobs` row that navigates to `/jobs`.
- Every time a new SSH connection is successfully established, refresh the server jobs list immediately and update the sidebar/store.

## Context

Relevant files:

- `tauri-app/src/AppSidebar.tsx`
- `tauri-app/src/components/RuntimeSection.tsx`
- `tauri-app/src/pages/JobsPage.tsx`
- `tauri-app/src/pages/PipelinePage.tsx`
- `tauri-app/src/jobFormatters.ts`
- `tauri-app/src/api/schemas.ts`
- `tauri-app/src/stores/jobsStore.ts`
- `tauri-app/src/stores/remoteStore.ts`

Jobs Monitor currently loads jobs in `JobsPage.refreshJobs()`:

- Local: `client.listLocalJobs()` / `GET /jobs/local`
- Remote: `listRemoteJobsMutation.mutateAsync(buildRemotePayload(formValues))` / `POST /remote/jobs`, only when `remoteResult.connected` is true
- The merged result is saved in `useJobsStore().latestJobs`

The sidebar receives `latestJobs` from `AppRouter.tsx` and renders the nested list in `AppSidebar.tsx`.

Remote SSH connection is handled in `RuntimeSection.connectRemote()`:

- Calls `validateRemoteMutation.mutateAsync(remotePayload())`
- On success, sets `useRemoteStore().connected = true`
- It currently does not necessarily update `useJobsStore().latestJobs` immediately with remote jobs after connect.

## Implementation Plan

1. Add or reuse a job sort helper.

Implement a small helper in `tauri-app/src/jobFormatters.ts`, or keep local to the sidebar if preferred:

```ts
export function jobStartedAtValue(job: Record<string, unknown>): number {
  const startedAt = Number(job.started_at || job.created_at || 0);
  if (Number.isFinite(startedAt) && startedAt > 0) return startedAt;
  const updatedAt = Number(job.updated_at || 0);
  return Number.isFinite(updatedAt) ? updatedAt : 0;
}

export function sortJobsByStartedAtDesc<T extends Record<string, unknown>>(jobs: T[]): T[] {
  return [...jobs].sort((a, b) => jobStartedAtValue(b) - jobStartedAtValue(a));
}
```

Use it where jobs are merged for display/store consistency.

2. Preserve remote job metadata from API parsing.

Check `tauri-app/src/api/schemas.ts`. `remoteJobSummarySchema` may currently only preserve a minimal subset. Ensure remote job responses retain `started_at`, `updated_at`, `job_id`, `job_dir`, `output_dir`, `effective_output_dir`, `download_subdir`, `input_files`, and `run_request_summary`.

This matters because `/remote/jobs` backend returns richer data from `app_backend/remote.py`, and sorting by `started_at` for server jobs depends on the frontend schema not stripping/rejecting it.

Use `.passthrough()` if needed to avoid dropping future remote summary fields.

3. Update `AppSidebar.tsx` rendering.

Replace the flat `jobs.map(...)` under `Jobs Monitor` with grouped rendering:

- Convert `jobs` to `Record<string, unknown>[]`.
- Sort by `started_at` descending.
- Build groups:
  - Local: `String(job.target || 'Local') !== 'Server'`
  - Server: `String(job.target || 'Local') === 'Server'`
- Skip empty groups.
- Show group header text: `Local`, `Server`.
- Render only first `SIDEBAR_JOBS_PER_GROUP` jobs per group.
- If hidden count exists, render a button row: `View all local jobs (N more)` or `View all server jobs (N more)`.
- Clicking a visible job should keep existing behavior: navigate/select Jobs Monitor and selected job.
- Clicking view-all should navigate/select Jobs Monitor only.

Recommended cap:

```ts
const SIDEBAR_JOBS_PER_GROUP = 3;
```

4. Sort Jobs Monitor merged jobs newest-first.

In `JobsPage.refreshJobs()`, after normalizing local and remote jobs, sort the merged array by `started_at` descending before `setLatestJobs(...)`.

This ensures the first auto-selected job is the most recent job and the sidebar receives stable sorted input.

Also check `PipelinePage.refreshJobs()` for local-only refresh after starting a local job. Sort those jobs too so navigation after start selects the newest local job.

5. Refresh server jobs after successful SSH connect.

In `RuntimeSection.connectRemote()`:

- After `validateRemoteMutation` succeeds with `result.connected === true`, immediately call `listRemoteJobsMutation.mutateAsync(remotePayload())`.
- Update `remoteStore.jobs` via existing `renderRemoteResult(...)` or equivalent.
- Replace the Server entries in `useJobsStore().latestJobs` with the newly fetched remote jobs.
- Preserve Local entries in `latestJobs`.
- Sort the combined list by `started_at` descending before saving.
- If the server job list fetch fails after SSH validation succeeds, keep the SSH connection state successful, but clear/replace stored Server entries to avoid showing stale jobs from a previous server connection. Also print/log a remote jobs failure.

Suggested merge logic:

```ts
const currentJobs = useJobsStore.getState().latestJobs || [];
const localJobs = currentJobs.filter((job) => String(job.target || 'Local') !== 'Server');
const serverJobs = remoteJobs.map((job) => normalizeJob(job as Record<string, unknown>, 'Server'));
setLatestJobs(sortJobsByStartedAtDesc([...localJobs, ...serverJobs]));
```

Important nuance:

- A new SSH connection may point to a different server/workspace, so do not append remote jobs to existing Server jobs. Replace existing Server jobs.
- Do not remove Local jobs when refreshing after SSH connect.

6. Manual remote job listing should also update sidebar/store.

In `RuntimeSection.listRemoteJobs()`, after successful list, use the same replace-Server-jobs merge helper so clicking the manual list button updates sidebar data too.

7. Verification.

Run from `tauri-app/`:

```bash
npm run typecheck
npm run test -- jobFormatters api jobs runtime
```

If touching formatting-sensitive files, consider:

```bash
npm run lint
```

## Acceptance Criteria

- Sidebar no longer shows a single flat list of all jobs.
- Sidebar shows `Local` and/or `Server` headings only when those groups have jobs.
- Each group shows at most 3 jobs.
- Jobs within each group are newest-first by `started_at`.
- Hidden jobs are represented by a `View all ... jobs` row.
- Connecting to SSH successfully immediately refreshes remote server jobs in the sidebar without requiring the user to click Jobs Monitor or manual refresh.
- Connecting to a different SSH server/workspace replaces old Server jobs in the sidebar/store.
- Local jobs remain visible after SSH connect.
- Typecheck and focused tests pass.

## Note For Executor

The planner accidentally made implementation edits before this handoff. Inspect the working tree before editing. You may keep, adjust, or replace those changes, but verify they match this plan and do not blindly assume they are complete.
