# Fix “View all server jobs”

## Problem

Clicking `View all server jobs` in `tauri-app/src/AppSidebar.tsx` only calls `onSelectTab('jobs')`. If the user is already on `/jobs`, this produces no visible change. The hidden server jobs remain hidden because the sidebar always renders `group.jobs.slice(0, SIDEBAR_JOBS_PER_GROUP)`.

The Jobs page also does not render an all-jobs list; it only shows details for `selectedJobId` and tells users to select jobs from the sidebar. Therefore the smallest useful fix is to make the sidebar button expand the Server group in place so the hidden jobs become visible and selectable.

## Files To Change

- `tauri-app/src/AppSidebar.tsx`
- Add a focused component test, likely `tauri-app/test/AppSidebar.test.tsx`

## Implementation Steps

1. In `AppSidebar.tsx`, import `useState` from React.
2. Add local state tracking expanded job groups by group label, for example:
   - `const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});`
3. Inside `groupedJobs.map`, compute:
   - `const isExpanded = Boolean(expandedGroups[group.label]);`
   - `const visibleJobs = isExpanded ? group.jobs : group.jobs.slice(0, SIDEBAR_JOBS_PER_GROUP);`
   - `const hiddenCount = group.jobs.length - SIDEBAR_JOBS_PER_GROUP;`
4. Render the footer control whenever `hiddenCount > 0`.
5. Change that control’s click handler to:
   - Call `event.preventDefault()` because `SidebarMenuSubButton` renders an anchor by default.
   - Call `onSelectTab('jobs')` to preserve existing navigation behavior.
   - Toggle only the current group in `expandedGroups`.
6. Change the label based on state:
   - Collapsed: `View all server jobs (N more)`.
   - Expanded: `Show fewer server jobs`.
7. Keep local and server groups independent. Do not add global store state or URL parameters unless needed by tests.
8. Do not change job selection behavior for individual job rows.

## Test Plan

Add a React Testing Library test that renders `AppSidebar` with at least four Server jobs and one Local job.

Verify:

1. Initially only the first three Server jobs are visible.
2. The hidden Server job is not visible.
3. Clicking `View all server jobs (1 more)` reveals the hidden Server job.
4. The button changes to `Show fewer server jobs`.
5. Clicking `Show fewer server jobs` hides the extra Server job again.

Suggested test command:

```bash
npm run test -- AppSidebar
```

Then run broader verification if time allows:

```bash
npm run typecheck
npm run test
```

## Notes

- The current issue is not that the click handler fails to fire; the handler navigates to `/jobs`, which is already the active page in the common failure case and does not alter sidebar visibility.
- Avoid implementing a Jobs page-wide filter unless the product expectation is explicitly changed. The current UI copy says “View all server jobs” inside a sidebar group, and the actionable hidden items live in the sidebar.
