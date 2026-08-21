# Fix UI Pipeline Lifecycle, Workspace Sync, And Jobs Monitor Polish

## Goal

Resolve the UI issues across 3 sequential groups of tasks:

1. **Group 1: Pipeline Lifecycle & Workspace State Sync**
   - Fix Start button getting stuck in "Starting..." by ensuring backend SSE handlers close connections and frontend stream readers terminate cleanly.
   - Fix Workspace Load to override `inputPath`, `outputDir`, and normalize `inputMode` ('dir' -> 'batch_folder').
   - Include Batch Configuration (`batch_image_count`, `batch_scan_mode`, `selected_files`) in Workspace Save/Load.

2. **Group 2: Single Job Monitor UI & Real-time Action State**
   - Remove `<select>` dropdown from Single Job Monitor header; display clean title text.
   - Remove redundant `[SERVER]` badge when `[Server]` prefix is present.
   - Replace status badge pill with the standard status dot indicator.
   - Add `Pipeline Preset` entry to the Job Metadata table and remove the standalone preset badge.
   - Fix real-time reconciliation and polling so Stop Job disables and Download Outputs enables immediately upon job completion.

3. **Group 3: Batch Subjects Layout & Job List Status Animations**
   - Redesign Batch Subjects cards to be compact, space-efficient, and responsive.
   - Remove the faint outer ring on completed job cards in the job list.
   - Add expanding radar pulse wave animation (`animate-ping`) for running jobs.

---

## Detailed Task Groups

### Group 1: Pipeline Lifecycle & Workspace State Sync

#### 1. Backend SSE Stream Socket Termination (`app_backend/server.py`)
- In `_handle_remote_start_stream` and `_handle_local_start_stream`, wrap in `try ... finally:` with `self.close_connection = True`.
- In `tauri-app/src/api/client.ts`, inside `startPipelineStream`, when `currentEvent === 'complete'`, break and release reader lock so promise immediately resolves.
- In `tauri-app/src/components/AppHeader.tsx`, ensure `setStarting(false)` is reliably triggered when stream ends or dialog opens.

#### 2. Workspace Save & Load (`tauri-app/src/components/AppHeader.tsx` & `tauri-app/src/stores/pipelineFormStore.ts`)
- In `handleSaveWorkspace` in `AppHeader.tsx`:
  - Include `batch_image_count: fv.batchImageCount`, `batch_scan_mode: ...`, `selected_files: fv.additionalInputPaths ? fv.additionalInputPaths.split(',').map((s: string) => s.trim()).filter(Boolean) : []`.
  - Save `input_mode: fv.inputMode === 'batch_folder' ? 'batch_folder' : 'file'`.
- In `applyWorkspaceConfig` in `pipelineFormStore.ts`:
  - Override `inputPath`: `nextFormValues.inputPath = String(workspace.input_path || '')`.
  - Override `outputDir`: `nextFormValues.outputDir = String(workspace.output_dir || '')`.
  - Normalize `inputMode`: if `workspace.input_mode === 'dir'` or `workspace.input_mode === 'batch_folder'`, set `nextFormValues.inputMode = 'batch_folder'`.
  - Set `batchImageCount`: `(workspace.batch_image_count as number) ?? (Array.isArray(workspace.selected_files) ? workspace.selected_files.length : undefined)`.
  - Set `additionalInputPaths`: `Array.isArray(workspace.selected_files) ? workspace.selected_files.join(', ') : (workspace.selected_files as string) || ''`.

---

### Group 2: Single Job Monitor UI & Real-time Action State

#### 1. Job Header Cleanup (`tauri-app/src/pages/JobsPage.tsx`)
- Replace the `<select>` element with a clean `<h2>` heading:
  ```tsx
  <h2 className="m-0 text-base font-semibold tracking-tight text-cursor-ink truncate">
    {displayTitle}
  </h2>
  ```
- Remove `<Badge variant="default">{job?.target || 'Local'}</Badge>` when redundant.
- Remove `<StatusPill state={...}>` and replace with a clean status dot indicator + capitalized label:
  ```tsx
  <div className="flex items-center gap-1.5 font-medium text-xs text-cursor-ink">
    <span className={statusDotLargeClasses(normState)} />
    <span className="capitalize">{displayJobState(displayMeta.status_reconciled)}</span>
  </div>
  ```

#### 2. Preset Row in Metadata Table (`tauri-app/src/pages/JobsPage.tsx`)
- Add `['Preset', String(reqSummary.pipeline_mode || job?.pipeline_mode || 'Custom')]` to the Metadata table rows.
- Remove `<Badge variant="secondary">{reqSummary.pipeline_mode ...}</Badge>` from the top-right header pill group.

#### 3. Real-Time Action State Reconciliation (`tauri-app/src/lib/jobs.ts` & `tauri-app/src/pages/JobsPage.tsx`)
- In `deriveJobDisplayMetadata` (`tauri-app/src/lib/jobs.ts`):
  - Check if `events` contain a terminal event (`pipeline_completed`, `pipeline_failed`, `job_completed`, `complete`, etc.) or if all batch images are completed/failed.
  - If so, update `status_reconciled` to `'completed'` or `'failed'`.
- In `JobsPage.tsx`:
  - When `status_reconciled` becomes terminal or during running polling, periodically call `refreshJobs()` so the parent store updates `job.state`.
  - Enable `Download Outputs` button when `isTerminal` is true.
  - Disable `Stop Job` button when `!job || normState !== 'running' || isTerminal`.

---

### Group 3: Batch Subjects Layout & Job List Animations

#### 1. Compact Batch Subjects Cards (`tauri-app/src/pages/JobsPage.tsx`)
- Adjust grid columns to:
  `grid-cols-[repeat(auto-fill,minmax(14rem,1fr))]` with `gap-2`.
- Streamline card interior:
  - Compact padding (`p-2.5`).
  - Small icon (`h-5 w-5`), font sizes `text-xs` / `text-2xs`.
  - Compact 2-row layout with inline Stage and Status badges.

#### 2. Status Dot Animation Refinements (`tauri-app/src/pages/JobsPage.tsx` & `tauri-app/src/components/ui.tsx`)
- Update `statusDotLargeClasses`:
  - `completed`: Remove `ring-4 ring-cursor-semantic-success/20`. Use a clean solid dot: `h-3 w-3 rounded-full bg-cursor-semantic-success flex-none`.
  - `running`: Render an expanding radar pulse animation:
    ```tsx
    <span className="relative flex h-3 w-3 flex-none">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cursor-primary opacity-75" />
      <span className="relative inline-flex rounded-full h-3 w-3 bg-cursor-primary" />
    </span>
    ```

---

## Verification & Commit Strategy

Execute group by group and commit after each group:
1. **Commit 1**: `fix: resolve start stream socket hang and workspace settings sync`
2. **Commit 2**: `fix: polish single job monitor header, preset metadata, and action states`
3. **Commit 3**: `feat: streamline batch subject cards and add radar pulse animation to running jobs`

Run verification after all changes:
- `cd tauri-app && npm run typecheck`
- `.venv/bin/pytest tests/ -v`
