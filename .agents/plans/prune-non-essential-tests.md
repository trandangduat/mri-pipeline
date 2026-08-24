# Prune Non-Essential Tests

## Goal

Remove low-value, fragile, and static-assert test files and test cases in `tauri-app/test/` to streamline the test suite, decrease maintenance overhead, and eliminate brittle CSS-class assertions while preserving 100% of critical workflow, validation, state management, and persistence tests.

## Target Files to Remove / Modify

### 1. Files to Delete

- `tauri-app/test/alert.test.tsx` (6 tests): Pure Tailwind CSS class string assertions (`border-none`, `bg-amber-500/10`, icon presence). Fragile to design token tweaks.
- `tauri-app/test/theme.test.tsx` (3 tests): Dark/light class toggle on document root and localStorage check.
- `tauri-app/test/format.test.ts` (4 tests): Basic string helpers.
- `tauri-app/test/uiClasses.test.ts` (9 tests): Basic classname joining helpers.

### 2. Files to Prune / Refactor

- `tauri-app/test/AppHeader.test.tsx`:
  - **Remove** `test('renders brand title and theme toggle switch')`: Checks static "NeuroFlow" brand text.
  - **Remove** `test('renders AppFooter with system status, version, and links')`: Checks static copyright text, version string, and github link.
  - **Keep** `test('renders all 3 horizontal tabs with jobs count badge')`
  - **Keep** `test('triggers onSelectTab callback when clicking tabs')`
  - **Keep** `test('renders workspace and pipeline action buttons')`
  - **Keep** `test('save workspace persists all NeuroFLOW settings')` (Critical workspace persistence test)

- `tauri-app/test/DownloadOutputsDialog.test.tsx`:
  - **Remove** `test('select phase shows web browse hint when webBrowseHint is true')`: Static hint text.
  - **Keep** all 10 remaining tests for download path validation, progress counts, button locking, error handling, and completion.

### 3. Verification

- Run `npm test` in `tauri-app/` to verify that all remaining 15 test files pass cleanly.
- Run `npm run check:all` or `cargo test` to verify no broken imports or knip/typecheck issues.
