# Integrate DICOM And Batch DICOM Series Support

## Goal

Add complete DICOM series recognition and batch scanning support to both the backend scanner APIs and frontend UI:

1. Enable the local scanner (`app_backend/local_browse.py`) and remote SFTP scanner (`app_backend/remote.py`) to recognize DICOM series directories (folders containing `.dcm` / `.dicom` / `.ima` / DICOM magic files) as single volume candidates rather than breaking them down into hundreds of individual slice files.
2. Provide DICOM series metadata (`is_dicom_series: true`, `slice_count: N`, total aggregated size) in browse responses.
3. Update the frontend Zod schemas (`tauri-app/src/api/schemas.ts`) and TypeScript definitions (`tauri-app/src/types/backend.ts`).
4. Update `BatchConfigModal` in `tauri-app/src/pages/PipelinePage.tsx` to render clear format badges (`NII` vs `DCM Series (N slices)`) and handle DICOM folder selections cleanly.
5. Update Single Input controls on `PipelinePage.tsx` to provide both "Browse File" (NIfTI/DICOM file) and "Browse DICOM Folder" options.
6. Add unit and integration tests covering single DICOM files, DICOM series directories, and multi-subject batch DICOM datasets in `tests/`.

---

## Files To Modify

- `app_backend/local_browse.py`: Scan and group DICOM series directories as single candidates.
- `app_backend/remote.py`: Scan and group remote SFTP DICOM series directories as single candidates.
- `tauri-app/src/api/schemas.ts`: Add `is_dicom_series` and `slice_count` to `remoteBrowseEntrySchema`.
- `tauri-app/src/types/backend.ts`: Update TypeScript types if necessary (inferred from schemas).
- `tauri-app/src/pages/PipelinePage.tsx`:
  - Update `BatchConfigModal` candidate table to display DICOM format badge and slice count.
  - Update `InputOutputSection` single input controls with dual browse (Browse File & Browse DICOM Folder).
- `tests/test_app_backend_local_browse.py`: Add unit tests for local DICOM series scanning and batch datasets.
- `tests/test_app_backend_remote.py`: Add unit tests for remote DICOM series detection.

---

## Detailed Implementation Steps

### 1. Update Local Scanner (`app_backend/local_browse.py`)

1. Import DICOM helper functions from `pipeline.discovery`:
   - `_is_dicom_file`
   - `_is_dicom_series_dir`
   - `_dicom_files_in_series`
2. In `browse_local_path`:
   - If `scan_root` itself is a DICOM series directory (`_is_dicom_series_dir(Path(scan_root))`):
     - Compute total size and slice count across all DICOM files in `scan_root`.
     - Emit 1 candidate representing `scan_root`.
   - In `_recurse(current_dir, depth, subject_hint)`:
     - When inspecting a directory entry `entry`:
       - Check `_is_dicom_series_dir(Path(entry.path))`.
       - If it IS a DICOM series directory:
         - List all DICOM files in that folder.
         - Compute total byte size: `sum(f.stat().st_size for f in dicom_files)`.
         - Compute slice count: `len(dicom_files)`.
         - Determine `label`:
           - If `depth == 0`: `entry.name`
           - If `depth > 0`: `subject_hint or os.path.basename(current_dir)`
         - Append single candidate:
           ```python
           candidates.append({
               "name": entry.name,
               "path": entry.path,
               "kind": "file",
               "size": total_size,
               "modified_at": latest_mtime,
               "selectable": True,
               "relative_path": rel,
               "subject_label": label,
               "depth": depth,
               "parent": current_dir,
               "is_dicom_series": True,
               "slice_count": len(dicom_files),
           })
           ```
         - **Do NOT recurse further into `entry.path`**.
       - If it is NOT a DICOM series directory:
         - Recurse into `entry.path` if `depth < max_depth` with `subject_hint`.
     - When inspecting a file entry `entry`:
       - If `_is_image_file(entry.name)` and not part of an already-processed series:
         - If `entry.name` is `.dcm` / `.dicom`, check if `_is_dicom_series_dir(Path(current_dir))`. If `current_dir` is a DICOM series, parent should have captured it; if standing alone at root or flat, allow single file candidate.
         - For NIfTI (`.nii`, `.nii.gz`, `.mgz`, `.mgh`), emit candidate as usual with `is_dicom_series: False`.

### 2. Update Remote SFTP Scanner (`app_backend/remote.py`)

1. In `_scan_batch_via_sftp`:
   - When inspecting a remote directory `entry_path`:
     - Inspect child attributes using `client.sftp.listdir_attr(entry_path)`.
     - Check if children contain files with extensions `(".dcm", ".dicom", ".ima")` (case-insensitive).
     - If yes:
       - Treat `entry_path` as a remote DICOM series directory!
       - Sum file sizes: `sum(int(c.st_size or 0) for c in dicom_children)`.
       - Count slices: `len(dicom_children)`.
       - Append candidate with `is_dicom_series: True` and `slice_count`.
       - Do not recurse into `entry_path`.
     - If no:
       - Recurse if `depth < max_depth`.
   - In `_browse_via_sftp`:
     - Check if directory entries are DICOM series folders; if so, mark them with `is_dicom_series: True` and `selectable: True`.

### 3. Update Frontend API Schemas & Types (`tauri-app/src/api/schemas.ts`)

1. Update `remoteBrowseEntrySchema`:
   ```ts
   export const remoteBrowseEntrySchema = z.object({
     name: z.string(),
     path: z.string(),
     kind: z.enum(['directory', 'file']),
     size: z.number().nullable().optional(),
     modified_at: z.number().nullable().optional(),
     selectable: z.boolean(),
     subject_label: z.string().optional(),
     relative_path: z.string().optional(),
     depth: z.number().optional(),
     parent: z.string().optional(),
     is_dicom_series: z.boolean().optional(),
     slice_count: z.number().optional(),
   });
   ```

### 4. Update PipelinePage UI (`tauri-app/src/pages/PipelinePage.tsx`)

1. In `BatchConfigModal`:
   - In the candidate list table:
     - Update table header/row layout to display format badge:
       - If `entry.is_dicom_series`:
         - Show badge: `DCM (${entry.slice_count ?? '?'} sl)` in subtle primary/cyan style.
         - Tooltip: `DICOM Series (${entry.slice_count} slices)`.
       - If NIfTI/Volume (`.nii`, `.nii.gz`, `.mgz`):
         - Show badge: `NII` or `IMG`.
2. In `InputOutputSection` (Single Input mode):
   - For Local input:
     - In addition to browsing for a file (`.nii.gz`, `.dcm`), provide a secondary action/button **"Folder (DICOM)"** or dropdown picker that opens Tauri's directory dialog (`open({directory: true, multiple: false})`).
     - Update placeholder to: `/data/sub-001_T1w.nii.gz or /data/dicom_series_folder`.
     - Update hint copy to: `Process one NIfTI file or DICOM series folder.`

### 5. Verification & Tests

1. Create/Update Python tests in `tests/test_app_backend_local_browse.py`:
   - Test scanning a dataset containing mixed NIfTI files and multi-slice DICOM series directories.
   - Assert each DICOM series folder is treated as a single candidate with correct `slice_count` and `size`.
   - Assert `has_multi_subject_conflict` is `False` when each subject folder has 1 DICOM series.
2. Run backend pytest suite:
   ```bash
   pytest tests/test_app_backend_local_browse.py tests/test_app_backend_run_request.py -v
   ```
3. Run frontend checks:
   ```bash
   cd tauri-app && npm run typecheck
   ```
