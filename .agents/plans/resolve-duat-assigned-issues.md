# Implementation Plan: Resolve Duat's Assigned Issues (#3, #4, #5, #8, #9, #10)

## 1. Overview & Scope

This plan covers the implementation and bug fixes for the 6 issues assigned to **Duật (`@trandangduat` / `kusssso`)** on the `trandangduat/mri-pipeline` repository:

1. **Issue #3**: `[Pipeline Page] Sửa logic disabled của Source input khi chọn Runtime target = Server chưa Connect`
2. **Issue #4**: `[Pipeline Page] Thêm nút "Upload data to server" khi Runtime target = Server và Source input = Local`
3. **Issue #5**: `[Pipeline Page] Hiển thị cảnh báo khi máy đích (Local/Server) đang có job khác đang chạy`
4. **Issue #8**: `[Job Monitor] Sửa lỗi tràn viền chữ trong khung download`
5. **Issue #9**: `[Pipeline Page] Sửa lỗi cấu hình Output location không có tác dụng khi chạy trên Server`
6. **Issue #10**: `[Lazy Upload / Job Monitor] Sửa lỗi nhảy số lượng subjects trong batch khi bật Lazy Upload`

---

## 2. Design System & UI Principles (per `DESIGN.md`)

- **Palette**: Surface background `#ffffff`, Canvas soft `#fafaf7`, Hairline `#e6e5e0`, Ink `#26251e`, Muted text `#807d72`, Primary `#0077b6`, Primary active `#005f8f`, Warn `#b45309`, Error `#cf2d56`, Success `#1f8a65`.
- **Modals & Dialogs**: Backdrop `bg-cursor-ink/30`, Modal card `bg-cursor-surface-card border border-cursor-hairline rounded-lg p-4 max-w-[28rem]`.
- **Buttons**: Secondary/Ghost buttons with icon and text `h-8 px-2.5 text-xs font-medium`.
- **Typography**: Display/Body in CursorGothic, code/paths in JetBrains Mono (`font-mono text-2xs` or `text-xs`).

---

## 3. Step-by-Step Implementation

### Task 1 (Issue #3): Sửa logic disabled của Source input khi chưa Connect Server
* **Target File**: `tauri-app/src/pages/PipelinePage.tsx`
* **Changes**:
  1. In `sourceOptions`:
     ```tsx
     const sourceOptions = [
       {
         label: 'Local',
         value: 'Local',
         hint: 'Files on this machine.',
         disabled: false,
       },
       {
         label: 'Server',
         value: 'Server',
         hint: isLocal
           ? 'Available when Runtime target is Server.'
           : !remoteConnected
             ? 'Connect to server first.'
             : 'Files on the remote server.',
         disabled: isLocal || !remoteConnected,
       },
     ];
     ```
  2. If `inputSource === 'Server'` and `!remoteConnected`, or when disconnecting, automatically revert `inputSource` to `'Local'` if Server is no longer reachable.
  3. Ensure `RadioGroup` correctly passes `disabled` down to the individual radio items.

---

### Task 2 (Issue #4): Thêm nút "Upload data to server"
* **Target File**: `tauri-app/src/pages/PipelinePage.tsx`
* **Changes**:
  1. In `InputOutputSection`, under the `inputSource === 'Local' && !isLocal` branch:
     - Next to / below `Input location (server)`, add a dedicated action row with:
       ```tsx
       <Button
         variant="secondary"
         icon={<UploadCloud className="h-3.5 w-3.5" />}
         onClick={handleManualUploadToServer}
         disabled={!remoteConnected || !formValues.inputPath || !formValues.inputServerDir || uploadingStaging}
       >
         {uploadingStaging ? 'Uploading...' : 'Upload data to server'}
       </Button>
       ```
     - Provide feedback toast or inline status badge when manual upload is started or completed.
     - Use the existing backend staging/upload endpoint `/remote/jobs/upload/stage` or SSH file copy to push input data to `inputServerDir`.

---

### Task 3 (Issue #5): Cảnh báo khi máy đích đang có job đang chạy
* **Target File**: `tauri-app/src/components/AppHeader.tsx`
* **Changes**:
  1. In `handleStartPipeline()`:
     - Check if there are active running jobs on the target:
       ```ts
       const activeJobs = (latestJobs || []).filter((j) => {
         const target = normalizeJobTarget(j.target);
         const isTargetMatch = target === (formValues.runtimeTarget || 'Local');
         const state = normalizeJobState(j.state);
         return isTargetMatch && state === 'running';
       });
       ```
     - If `activeJobs.length > 0`:
       - Open a stateful `activeJobWarningModal` with job ID and warning message.
       - Allow user to click **"Cancel"** or **"Run Anyway"**.
       - If user clicks **"Run Anyway"**, proceed with `executeStartPipeline()`.

---

### Task 4 (Issue #8): Sửa lỗi tràn viền chữ trong khung download
* **Target File**: `tauri-app/src/components/DownloadOutputsDialog.tsx`
* **Changes**:
  1. Around lines 188–195:
     ```tsx
     {logs.length > 0 && (
       <div className="max-h-28 overflow-x-hidden overflow-y-auto rounded-md border border-cursor-hairline bg-cursor-canvas-soft p-2">
         {logs.slice(-10).map((line, i) => (
           <p key={i} className="m-0 font-mono text-2xs text-cursor-body leading-relaxed break-all whitespace-pre-wrap">
             {line}
           </p>
         ))}
       </div>
     )}
     ```
  2. Ensure the dialog container has `max-w-[32rem]` and `w-full` with `break-all` on path displays.

---

### Task 5 (Issue #9): Sửa lỗi Output location không có tác dụng trên Server
* **Target Files**:
  - `tauri-app/src/api/runConfig.ts`
  - `app_backend/run_request.py`
  - `remote/remote_runner.py`
* **Changes**:
  1. In `tauri-app/src/api/runConfig.ts` (`buildRunConfig`):
     - Forward `server_output_dir`:
       ```ts
       server_output_dir: formValues.runtimeTarget === 'Server'
         ? (formValues.serverOutputDir || formValues.outputDir || '')
         : '',
       ```
  2. In `app_backend/run_request.py`:
     - Ensure `server_output_dir` in `prepare_run_request` is preserved and passed to `RemoteRunConfig`.
  3. In `remote/remote_runner.py`:
     - In `_setup_remote_workspace()`: When `self.config.server_output_dir` is provided, set `self.remote_output_dir` to `self._remote_path(ssh, self.config.server_output_dir)` and create the directory on the remote machine if missing.
  4. In `tauri-app/src/components/DownloadOutputsDialog.tsx`:
     - Default the remote download path to `job.server_output_dir || job.remote_output_dir || (workspace/job_id/outputs)`.

---

### Task 6 (Issue #10): Sửa lỗi nhảy số lượng subjects khi bật Lazy Upload
* **Target File**: `tauri-app/src/lib/jobs.ts`
* **Changes**:
  1. In `deriveBatchImages(events, job)`:
     - Currently, `imagesMap` uses `file` path as the exact Map key.
     - When lazy upload runs, initial files are local paths (e.g. `/home/trandangduat/mri-pipeline/data/001.nii.gz`), while SSE events have server remote paths (e.g. `/home/catcd1/duat-jobs/001.nii.gz`).
     - Update the matching heuristic:
       ```ts
       function findMatchingImage(file: string, idx: number): BatchImageItem | undefined {
         if (imagesMap.has(file)) return imagesMap.get(file);
         const {subject_id} = deriveSubjectLabel(file, idx);
         for (const item of imagesMap.values()) {
           if (item.subject_id === subject_id || item.idx === idx) {
             return item;
           }
         }
         return undefined;
       }
       ```
     - When updating with server event, update the existing entry in `imagesMap` rather than appending a new key/item.
     - This guarantees the batch count remains exact (e.g. 2 subjects) throughout the entire lazy upload lifecycle.

---

## 4. Verification & Testing

1. **Frontend Tests**:
   - Update and run `npm test` in `tauri-app`:
     - `test/jobs.test.ts`: Test `deriveBatchImages` with local initial files and remote SSE events (Lazy upload scenario).
     - `test/workspaceRunConfig.test.ts`: Verify `server_output_dir` is correctly serialized in `buildRunConfig`.
     - `test/DownloadOutputsDialog.test.tsx`: Test log wrapping with long file paths.
     - `test/AppHeader.test.tsx`: Test active running job warning modal before start.
     - `test/StatsAtlasSection.test.tsx`: Fix count text query to match rendered DOM.
2. **Backend Tests**:
   - Run `.venv/bin/pytest tests/test_app_backend_run_request.py tests/test_remote_runner.py tests/test_lazy_upload.py`.
   - Ensure all 346+ tests pass with zero regressions.

---

## 5. Execution Handoff

Implement the plan at `.agents/plans/resolve-duat-assigned-issues.md`.
