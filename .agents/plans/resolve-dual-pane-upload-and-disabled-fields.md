# Implementation Plan: WinSCP Dual-Pane File Transfer & Server Field Disabling

## 1. Overview & Requirements

Based on testing feedback for **TC-01 (Issue #3)** and **TC-02 (Issue #4)**:

1. **TC-01 (Disabled Server Fields)**:
   - When `Runtime target = Server` and `remoteConnected = false`:
     - In `Input & Output` section, both `Input location (server)` / `Input location (server path)` and `Output location (server)` / `Output location (server path)` fields must be disabled (inputs and browse buttons), with placeholder / hint *"Connect to server first"*.
2. **TC-02 (WinSCP-Style Dual-Pane Upload Modal & Layout Placement)**:
   - **Placement**: Move the **"Upload data to server"** button to be directly below the Source Input radio group, horizontally aligned on the same row with **"Configure batch"**.
   - **WinSCP Dual-Pane Popup**:
     - When clicking **"Upload data to server"**, open a 2-pane modal (Local on left, Remote Server on right).
     - **Left Pane (Local Computer)**:
       - Path input, "Up one level" (`..`), "Refresh", "Browse folder dialog".
       - File/folder list with icons, name, format badges (DICOM, NIfTI), size, modified date.
       - Multi-select checkboxes with "Select All" / "Clear Selection" / selection summary.
       - Double-click to navigate into directories.
     - **Center Column**:
       - Action button: **`Upload ->`** (transfers selected local items into current remote directory via SFTP).
       - Transfer progress and spinner.
     - **Right Pane (Remote Server - SSH)**:
       - Remote path input, "Up one level", "New Folder" modal, "Refresh".
       - File/folder list with icons, size, modified date.
       - Double-click to navigate into remote directories.
       - "Set as Input Location" button to apply current remote path to pipeline form.
     - **Footer Status Bar**:
       - Transfer summary (e.g. *"Successfully uploaded X item(s) to /home/catcd1/..."*).

---

## 2. Architecture & Design System (per `DESIGN.md`)

- **Modal styling**: `fixed inset-0 z-50 flex items-center justify-center bg-cursor-ink/40 backdrop-blur-xs p-4`
- **Dialog card**: `flex flex-col bg-cursor-surface-card border border-cursor-hairline rounded-xl shadow-2xl w-full max-w-5xl h-[85vh] overflow-hidden`
- **Dual Panes**: Left (`Local`) and Right (`Remote Server`) split by middle transfer action bar `grid grid-cols-[1fr_auto_1fr]`.
- **Colors**: Primary `#0077b6`, Canvas soft `#fafaf7`, Hairline `#e6e5e0`, Ink `#26251e`, Muted text `#807d72`.

---

## 3. Step-by-Step Implementation

### Step 1: Backend Local Shallow Browse & Remote Mkdir / Multi-Upload
* **Files**:
  - `app_backend/local_browse.py`
  - `app_backend/remote.py`
  - `app_backend/server.py`
* **Changes**:
  1. In `app_backend/local_browse.py`: When `purpose in ("browse", "file_manager")` or `recursive is False` or `max_depth == 0`:
     - Perform shallow directory listing of `scan_root` returning `{ok: true, path, parent, dirs, files, entries: dirs + files}`.
  2. In `app_backend/remote.py`:
     - Update `upload_stage`: Support `local_paths: list[str]` and `remote_path: str` / `remote_dir: str`.
     - Add `remote_mkdir`: Support creating directory on remote server (`ssh.mkdir_p`).
  3. In `app_backend/server.py`:
     - Route `POST /remote/mkdir` to `remote_jobs.remote_mkdir(payload)`.

### Step 2: Frontend API Client & Schema Updates
* **Files**:
  - `tauri-app/src/api/schemas.ts`
  - `tauri-app/src/api/client.ts`
* **Changes**:
  1. In `schemas.ts`: Add `dirs` and `files` to `remoteBrowseResponseSchema`.
  2. In `client.ts`: Add `remoteMkdir()` and support `local_paths` in `uploadStage()`.

### Step 3: Create DualPaneTransferModal Component
* **File**: `tauri-app/src/components/DualPaneTransferModal.tsx`
* **Features**:
  1. Left pane: Local shallow directory browser using `localBrowseMutation`.
     - Support path navigation (double click folder, click `..`, editable path input, Tauri folder picker fallback).
     - Multi-selection checkboxes, select all / deselect all.
  2. Right pane: Remote shallow directory browser using `remoteBrowseMutation`.
     - Support path navigation (double click folder, click `..`, editable path input).
     - New folder creation button with prompt modal.
     - "Set as Input Location" action button.
  3. Center transfer bar:
     - `Upload ->` button calling `uploadStageMutation` with selected local paths.
     - Loading state / spinner during transfer.
     - Automatically refreshes right pane when upload finishes.

### Step 4: PipelinePage UI Layout & Disabled Fields Updates
* **File**: `tauri-app/src/pages/PipelinePage.tsx`
* **Changes**:
  1. `PathField`: Add `disabled?: boolean` support with disabled styling on input and buttons.
  2. In `InputOutputSection`:
     - Pass `disabled={!remoteConnected}` to `Input location (server / server path)` and `Output location (server / server path)`.
     - Place the **"Upload data to server"** button directly under `Source Input` radio group, horizontally aligned with `Configure batch`.
     - Hook the button to open `<DualPaneTransferModal />`.

---

## 4. Verification & Testing

1. **Frontend Unit Tests**:
   - Add/update `test/DualPaneTransferModal.test.tsx` and `test/PipelinePage.test.tsx` (or `PipelineStepsSection.test.tsx`).
   - Run `cd tauri-app && npm test`.
2. **Backend Unit Tests**:
   - Run `.venv/bin/pytest tests/test_app_backend_local_browse.py tests/test_app_backend_remote.py`.
3. **Manual Verification**:
   - Verify TC-01: Server path fields are disabled when not connected.
   - Verify TC-02: Button is placed under Source Input and opens the WinSCP dual-pane file transfer modal with navigation and upload.
