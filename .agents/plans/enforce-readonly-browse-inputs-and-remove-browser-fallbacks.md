# Enforce Read-Only Browse Inputs & Remove Legacy Browser Fallbacks

Make all browse path input fields across the application read-only by default so users must click the Browse button or modal to select files and folders. Remove legacy browser-only fallback handlers and hidden file input elements.

## User Review Required

> [!NOTE]
> All browse inputs (`inputPath`, `outputDir`, `inputServerDir`, `serverOutputDir`, `licensePath`, `neuroflowPresetFile`, `neuroflowProfileFile`, `key_path`, `localDir` in Download dialog) will now have the `readOnly` attribute enabled. Users will not be able to type custom text directly into these inputs, ensuring all selected paths originate from valid system dialogs or server browsers.
> Direct address bars inside modal file browsers (`ServerBrowserModal` and `DualPaneTransferModal`) remain editable for directory navigation.

---

## Proposed Changes

### Component 1: Pipeline Page

#### [MODIFY] [PipelinePage.tsx](file:///c:/Users/ADMIN/Desktop/mri-pipeline/tauri-app/src/pages/PipelinePage.tsx)
- Remove `hasTauriInternals()` helper function.
- In `License Path`:
  - Set `readOnly={true}` on `#licensePath` input and apply read-only styling (`bg-cursor-canvas-soft text-cursor-muted`).
  - Remove hidden `<input ref={licenseFileInput} type="file" ... />`.
  - Remove `handleBrowserLicenseFile` and `uploadingLicense` state.
  - Simplify `onClick` on Browse button to directly call Tauri `open()`.
- In `NeuroFLOW Custom Config`:
  - Set `readOnly={true}` on `neuroflowPresetFile` and `neuroflowProfileFile` inputs.
  - Remove `presetConfigInput` and `profileConfigInput` refs and hidden `<input type="file" ... />` elements.
  - Remove `handleConfigFile`.
  - Simplify `browseNeuroflowConfig` to directly invoke Tauri `open()`.
- In `PathField` and `InputOutputSection`:
  - Default `readOnly = true` on `PathField` so all main input/output path fields are read-only.
  - Remove `localFileInput`, `localFolderInput`, and `localOutputDirInput` refs and hidden `<input type="file" ... />` elements.
  - Remove `handleLocalFileChange` and `localFileListLen`.
  - Simplify `handleLocalBrowseFile`, `handleLocalBrowseFolder`, and `handleLocalBrowseOutputDir` to call Tauri `open()` directly.

---

### Component 2: SSH Runtime Configuration

#### [MODIFY] [RuntimeSection.tsx](file:///c:/Users/ADMIN/Desktop/mri-pipeline/tauri-app/src/components/RuntimeSection.tsx)
- Set `readOnly={true}` and add `bg-cursor-canvas-soft text-cursor-muted` styling to `key_path` `<input>`.

---

### Component 3: Download Outputs & Jobs

#### [MODIFY] [JobsPage.tsx](file:///c:/Users/ADMIN/Desktop/mri-pipeline/tauri-app/src/pages/JobsPage.tsx)
- Remove `hasTauriInternals()` helper function.
- Remove `webBrowseHint` state, setter, and props.
- Simplify `handleBrowseDownloadDir` to call `@tauri-apps/plugin-dialog` `open()` directly.

#### [MODIFY] [DownloadOutputsDialog.tsx](file:///c:/Users/ADMIN/Desktop/mri-pipeline/tauri-app/src/components/DownloadOutputsDialog.tsx)
- Remove `webBrowseHint` prop and hint banner.
- Set `readOnly={true}` on `localDir` `<input>` with placeholder `"Select a destination folder with Browse..."` and read-only styling `bg-cursor-canvas-soft text-cursor-muted`.

---

### Component 4: Dual Pane Transfer Modal

#### [MODIFY] [DualPaneTransferModal.tsx](file:///c:/Users/ADMIN/Desktop/mri-pipeline/tauri-app/src/components/DualPaneTransferModal.tsx)
- Remove `hasTauriInternals()` helper function.
- Simplify `handleLocalBrowseDialog` to invoke `openDialog()` directly without fallback alerts.
- Keep manual path navigation input at the top of left/right explorer panes editable for typing directory paths.

---

## Verification Plan

### Automated Tests
- Run the full vitest suite:
  ```bash
  npm test -- --run
  ```
- Verify and update test cases in:
  - `tauri-app/test/PipelineInputOutput.test.tsx`
  - `tauri-app/test/AdvancedSettingsSection.test.tsx`
  - `tauri-app/test/DownloadOutputsDialog.test.tsx`
