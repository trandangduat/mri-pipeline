# Plan: Clean Initial Loading States & Synchronize Refresh Button Typography

## Background
- Currently, when Jobs Monitor opens for the first time before jobs have loaded, it displays empty text messages "No server jobs found..." and "No local jobs found...".
- In Tools Configuration, loading image status renders an `ImageStatusSkeletonGrid`.
- The Refresh button in Jobs Monitor uses `text-xs font-medium` while Tools Configuration uses `text-sm font-medium`.

## User Request
1. Jobs Monitor: on first load, replace empty text messages with a simple loading row (icon + `Loading...`). Once loaded, if no jobs are present, show nothing under the headers. If jobs exist, show the cards as usual.
2. Tools Configuration: remove skeleton loading and replace with a simple `Loading...` row with icon.
3. Synchronize Refresh button font size in Jobs Monitor with Tools Configuration (`text-sm font-medium`).

## Proposed Changes
1. `tauri-app/src/pages/JobsPage.tsx`:
   - Add initial load tracking (`hasLoadedOnce`).
   - While loading initially, render a simple `Loading...` row.
   - Remove "No server jobs found..." and "No local jobs found..." empty text messages.
   - Update `refreshButton` font size to `text-sm font-medium`.
2. `tauri-app/src/pages/ToolsPage.tsx`:
   - Remove `ImageStatusSkeletonGrid`.
   - Replace skeleton loading in Available / Not Available sections with a simple `Loading...` indicator.

## Verification
- Run `npm test -- --run` in `tauri-app`.
