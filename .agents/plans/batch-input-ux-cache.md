# Batch Input UX, Selection Controls, And Scan Cache

## Goal

Improve the batch input UX in `tauri-app/src/pages/PipelinePage.tsx` based on the user's screenshots and requested changes:

- Reduce repeated image-count copy in the batch configuration modal.
- Add an explicit `Unselect all` action next to `Select all`.
- Make truncated `Subject` and `Relative path` values easier to inspect with tooltips.
- Widen the important table columns so subject and relative path are more readable.
- Add a `Re-scan` button.
- Cache the last scan so opening `Configure batch settings` does not scan again unless the input path, connection context, scan mode, or user-triggered `Re-scan` requires it.
- Reposition `Upload data to server` and `Configure batch settings` so they are contextually attached to the controls they affect.

## Files To Inspect/Edit

- Main file: `tauri-app/src/pages/PipelinePage.tsx`
- Existing tooltip component: `tauri-app/components/ui/tooltip.tsx`
- Package scripts for verification: `tauri-app/package.json`

## Current Relevant Code

In `PipelinePage.tsx`:

- `BatchConfigModal` starts around line 722.
- It currently owns scan state locally:
  - `serverEntries`
  - `selectedPaths`
  - `scanStatus`
  - `scanMode`
  - `scanned`
  - `hasConflict`
- It auto-runs `doServerScan(scanMode)` on mount via an empty-dependency `useEffect` when server is connected.
- It displays repeated counts:
  - `Found ${candidates.length} image file(s) across ${labelCounts.size} subject(s).`
  - `${selectedPaths.size} of ${serverEntries.length} selected.`
  - `Save (${finalCount} image...)`
- Table grid currently uses `gridTemplateColumns: '1.5rem 1fr 1fr minmax(0,2fr) 4rem'` for both header and rows.
- Row cells currently use native `title` attributes for subject, filename, and relative path.
- `InputOutputSection` starts around line 1071.
- `Upload data to server` currently appears below the server path fields.
- `Configure batch settings` currently appears below both server path fields as a separate bottom action.

## Implementation Guidance

Keep the change as small as possible. Prefer staying within `PipelinePage.tsx` unless the tooltip import path requires a tiny adjustment. Do not introduce global store changes unless absolutely necessary.

### 1. Add Parent-Owned Batch Scan Cache

Move the server scan result state out of `BatchConfigModal` and into `InputOutputSection`, or otherwise persist it in parent state so closing/reopening the modal reuses the prior scan.

Suggested local types in `PipelinePage.tsx` near `ScanMode`:

```ts
type BatchScanCache = {
  inputPath: string;
  scanMode: ScanMode;
  entries: RemoteBrowseEntry[];
  selectedPaths: string[];
  status: string;
  hasConflict: boolean;
  subjectCount: number;
  scanned: boolean;
};
```

Add parent state in `InputOutputSection`:

```ts
const [batchScanCache, setBatchScanCache] = React.useState<BatchScanCache | null>(null);
```

Pass `batchScanCache` and `setBatchScanCache` into `BatchConfigModal`.

Invalidate stale cache when it would be misleading:

- If `formValues.inputPath` changes, cached results for the old path should not be reused.
- If source switches away from `Server`, do not use the server scan cache.
- If remote connection payload changes in a way that points to a different server, stale cache should not be reused. If comparing `remotePayload` is awkward, a pragmatic minimal approach is to include a stable `cacheKey` string prop based on `inputSource`, `inputPath`, and `JSON.stringify(remotePayload)` and store it in the cache.

Avoid repeated automatic scanning:

- On modal open, if cache matches the current input path/cache key and has `scanned: true`, hydrate modal state from cache and do not call `doServerScan`.
- If no matching cache exists and server is connected, scan once on first open.
- When the user changes scan mode, it is acceptable to scan immediately for that new mode and replace the cache.
- `Re-scan` must always force a fresh scan for the current mode and replace the cache.

Important selection behavior:

- Preserve user selections in the cache when the modal closes and when they confirm.
- If a cached scan is reopened, selected rows should remain selected.
- On a fresh scan, keep current auto-select behavior: auto-select labels with exactly one image.

### 2. Add `Re-scan`

Place `Re-scan` in the server scan controls row, aligned to the right of the scan mode buttons when space allows.

Suggested structure:

- Label row: `Scan mode` on the left, `Re-scan` ghost/small button on the right.
- Or controls row: scan mode buttons left, `Re-scan` right.

Disable `Re-scan` while `browseMutation` is pending if the mutation exposes a pending state such as `browseMutation.isPending`.

Use copy:

- Button: `Re-scan`
- Pending/status remains `Scanning...`

### 3. Reduce Count Copy In The Modal

Use one concise discovery status and one concise selection status.

Recommended copy:

- Scan status after success: `5 images found across 5 subjects.`
- Empty status: `No image files found in this directory.`
- Selection footer/status: `2 selected`
- Save button: `Save selection`

Do not keep all three count variants visible at once. The footer already communicates the selected count, so the Save button should not repeat it.

Keep manual fallback count behavior for local or unscanned server cases, because this is existing behavior.

### 4. Add `Unselect all` Next To `Select all`

In the server scanned selection summary, show actions together.

Recommended layout:

```tsx
<p>2 selected</p>
<div>
  <button>Select all</button>
  <button>Unselect all</button>
</div>
```

Behavior:

- `Select all`: selects every `serverEntries.map((e) => e.path)`.
- `Unselect all`: clears `selectedPaths`.
- Both actions can be shown all the time after a scan, or disabled/hidden when redundant. Simpler: show both all the time and use current text-button styling.

Confirm behavior currently uses all images when `selectedPaths.size === 0` because `paths` becomes `undefined` and `finalCount` falls back to `count`. This conflicts with an explicit `Unselect all` action.

Fix this by distinguishing scanned server mode from manual fallback:

- For scanned server entries, `finalCount` should be exactly `selectedPaths.size`, including `0`.
- On confirm for scanned server entries, pass `Array.from(selectedPaths)` even if empty, so the store can represent zero selected or the modal can prevent saving zero.
- Prefer disabling `Save selection` when server scan is active and `selectedPaths.size === 0`; this avoids downstream ambiguity and is better UX. If disabling, keep the count text as `0 selected`.

### 5. Improve Table Widths And Tooltips

Update the table grid to allocate more room to `Subject` and `Relative path`, less to filename.

Suggested grid for desktop/tablet:

```ts
'1.5rem minmax(10rem,1.8fr) minmax(4.5rem,0.7fr) minmax(14rem,3fr) 4.5rem'
```

The exact values can be tuned visually, but subject and relative path should receive materially more space than filename.

Keep mobile behavior sane:

- Relative path is currently hidden below `sm`; that can remain.
- Ensure the grid does not overflow badly in the modal.

Tooltips:

- Use `Tooltip`, `TooltipTrigger`, and `TooltipContent` from `tauri-app/components/ui/tooltip.tsx` if the import path works cleanly from `src/pages/PipelinePage.tsx`.
- If path aliasing is awkward, use a relative import such as `../../components/ui/tooltip` from `src/pages/PipelinePage.tsx`.
- Wrap at least `Subject` and `Relative path` cells so hovering/focusing shows the full value.
- Native `title` is acceptable as a fallback only if the Base UI tooltip creates layout/event issues inside the clickable row.

Avoid breaking checkbox row click behavior:

- Current row is a `<label>` wrapping all cells. If wrapping cells in tooltip triggers causes invalid/nested interactive behavior, switch the row to a non-label container and wire checkbox + row click manually, or keep native `title` rather than a risky refactor.
- Prioritize safe behavior over a large semantic rewrite.

### 6. Reposition Input/Output Actions

Rework the `InputOutputSection` layout so actions feel attached to their context.

Recommended minimal UX:

- Move `Configure batch settings` into the `Input Mode` column, directly below the `RadioGroup`, only when `isBatch` is true.
- Keep its selected count next to it, but use cleaner copy: `${count} selected` instead of `${count} image(s) selected`.
- Move `Upload data to server` into the `Source Input` column, directly below the source `RadioGroup`, only when source/server context makes sense.

Specific copy:

- Button: `Upload data to server`
- Notice: `Not wired yet - upload feature coming soon.` can remain.
- Batch button: `Configure batch`
- Selected label: `3 selected`

Remove the old bottom action blocks below the path fields so the buttons are not duplicated.

If `Upload data to server` should only appear for `Local` source, that is arguably better UX, but the current behavior shows it for server source. To keep behavior conservative, move it near `Source Input` and keep the same condition it currently uses unless the UI becomes confusing. If changing condition, choose `!isLocal` or `inputSource === 'Local' && !isLocal` only after checking surrounding runtime semantics.

### 7. Preserve Current Data Contract

When confirming the batch modal, keep writing existing form fields in the same place where `BatchConfigModal` is rendered near the bottom of `InputOutputSection`. Inspect lines after 1320 to find the current `BatchConfigModal` render and `onConfirm` handler.

Ensure selected paths still flow to whatever field is currently used for selected batch paths.

Do not change backend API payload shape unless needed.

## Verification

Run from `tauri-app/`:

```bash
npm run typecheck
```

If typecheck passes and the change is not too slow, also run:

```bash
npm run test
```

Manual smoke checks:

- Open `Configure batch`; first open scans if no cache exists.
- Close and reopen `Configure batch`; it should show cached rows without flashing `Scanning...` or calling browse again.
- Click `Re-scan`; it should fetch fresh rows.
- Change scan mode; it should fetch for that mode.
- Click `Select all`; all rows become checked.
- Click `Unselect all`; no rows are checked and save is disabled or otherwise prevented.
- Hover/focus truncated `Subject` and `Relative path`; full values are visible.
- Main `Input & Output` panel shows `Configure batch` near `Batch input` and upload near source selection, not as orphan buttons below the path fields.

## Notes

- Keep changes focused and local.
- Avoid a broader component extraction unless needed to make TypeScript happy.
- Do not make an implementation plan beyond this file; implement directly from this handoff.
