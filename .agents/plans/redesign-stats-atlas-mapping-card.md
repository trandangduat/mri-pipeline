# Redesign Stats & Atlas Mapping Card

## Goal

Update the `Stats & Atlas Mapping` card to match the requested UI changes:

- Show vector names in uppercase: `SUBCORTICAL VOLUME`, `CORTICAL VOLUME`, `CORTICAL THICKNESS`.
- Make selected atlas tags bigger.
- Replace the `+ Add Atlas` `<select>` with a normal button using a larger font.
- On button click, open a popup dialog for that vector.
- The dialog must include a search bar and all atlases available for that vector.
- The atlas list must clearly show which atlases are already selected.

## Files To Change

- `tauri-app/src/pages/PipelinePage.tsx`

No new dependency is needed. The file already uses local modal overlay patterns and React state.

## Current Location

The target component is `StatsAtlasSection` in `tauri-app/src/pages/PipelinePage.tsx`, around lines 289-379.

Current behavior:

- It renders vector groups from `order = ['subcortical_volume', 'cortical_volume', 'cortical_thickness']`.
- It renders `stat?.label || statKey` as the vector name.
- It uses a small `<select>` to add atlases.
- It renders selected atlas tags as compact `span` pills.
- It uses `addAtlas(statKey, atlasKey)` and `removeAtlasStore(statKey, atlasKey, metadata)`.

## Implementation Plan

1. Add local dialog state inside `StatsAtlasSection`:

```ts
const [atlasPickerStatKey, setAtlasPickerStatKey] = React.useState<string | null>(null);
const [atlasSearch, setAtlasSearch] = React.useState('');
```

Reset `atlasSearch` to `''` when opening or closing the picker.

2. Replace vector label rendering with uppercase display text:

```tsx
{(stat?.label || statKey).toUpperCase()}
```

Also update the label class to include uppercase-friendly tracking, for example:

```tsx
text-[12px] font-semibold uppercase tracking-[0.08em]
```

3. Replace the `<select>` with a normal button:

```tsx
<button
  type="button"
  onClick={() => {
    setAtlasPickerStatKey(statKey);
    setAtlasSearch('');
  }}
  className="inline-flex h-10 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-cursor-hairline bg-white px-4 text-sm font-semibold text-cursor-ink transition-colors hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft"
>
  + Add Atlas
</button>
```

The exact Tailwind classes can be adjusted to fit the local style, but the button should be visibly larger than the current select text.

4. Increase selected atlas tag size.

Current tag class is:

```tsx
inline-flex items-center gap-1 rounded-md border border-cursor-hairline bg-white pl-2.5 pr-1.5 py-1 text-[12px] font-medium text-cursor-ink
```

Use a larger pill, for example:

```tsx
inline-flex items-center gap-2 rounded-lg border border-cursor-hairline bg-white py-1.5 pl-3 pr-2 text-sm font-medium text-cursor-ink
```

Increase the remove button target too, for example `h-5 w-5 text-[11px]`.

5. Add an atlas picker popup inside `StatsAtlasSection`, after the group list.

Use the existing local modal styling pattern from `ModalOverlay` or inline the same pattern if hoisting/reusing is awkward. Since `ModalOverlay` is declared later in the same file, it is safe to use it from `StatsAtlasSection` at runtime, but keeping a small inline modal is also acceptable.

Suggested structure:

```tsx
{atlasPickerStatKey && (() => {
  const pickerStat = metadata?.stats_vectors?.[atlasPickerStatKey];
  const pickerAtlasKeys = Array.isArray(pickerStat?.atlases) ? pickerStat.atlases : [];
  const pickerSelectedAtlases = selectedStatsAtlases[atlasPickerStatKey] || [];
  const filteredAtlasKeys = pickerAtlasKeys.filter((atlasKey) => {
    const atlas = metadata?.atlases?.[atlasKey] || {key: atlasKey, label: atlasKey};
    const query = atlasSearch.trim().toLowerCase();
    if (!query) return true;
    return `${atlas.label || ''} ${atlas.key || atlasKey}`.toLowerCase().includes(query);
  });

  return (
    <ModalOverlay onClose={() => { setAtlasPickerStatKey(null); setAtlasSearch(''); }}>
      ...dialog content...
    </ModalOverlay>
  );
})()}
```

6. Dialog content requirements:

- Title: `Add Atlas to ${uppercase vector label}` or similar.
- Search input uses the existing `inputCls` imported from `../components/ui`.
- List all atlases for that vector, filtered by search.
- Each atlas row should show label and key if useful.
- Each row should show selected state clearly, for example a `Selected` pill and/or disabled-looking row.
- Clicking an unselected atlas should call `addAtlas(atlasPickerStatKey, atlasKey)`.
- Clicking a selected atlas should not duplicate it. It may be disabled, or it may remove the atlas if explicitly designed that way. Prefer simple disabled selected rows because the user only asked to show selected state.
- Include a `Close` button.
- If search has no results, show `No atlases match this search.`

Example row behavior:

```tsx
<button
  type="button"
  disabled={isSelected}
  onClick={() => addAtlas(atlasPickerStatKey, atlasKey)}
  className={`flex w-full items-center justify-between gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors ${
    isSelected
      ? 'cursor-default border-cursor-hairline bg-cursor-canvas-soft text-cursor-muted'
      : 'cursor-pointer border-cursor-hairline bg-white text-cursor-ink hover:border-cursor-hairline-strong hover:bg-cursor-canvas-soft'
  }`}
>
  <span className="min-w-0">
    <span className="block truncate text-sm font-semibold">{atlas.label || atlas.key}</span>
    <span className="block truncate text-[12px] text-cursor-muted">{atlas.key}</span>
  </span>
  {isSelected ? <span className="rounded-full bg-cursor-hairline px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-cursor-body">Selected</span> : null}
</button>
```

7. Accessibility and interaction details:

- Add `role="dialog"` and `aria-modal="true"` to the modal panel or overlay if not already present.
- Give the dialog heading an `id` and use `aria-labelledby`.
- Make the search input `autoFocus` if TypeScript/React accepts it cleanly.
- Add Escape-to-close only if it is simple and local. Existing modal patterns mostly rely on overlay click and close buttons, so this is optional.
- Ensure the dialog remains usable on mobile with `max-h-[min(34rem,calc(100vh-6rem))]` or similar and an overflow-y list.

8. Keep the change minimal:

- Do not introduce a general dialog component unless needed.
- Do not change store behavior.
- Do not change metadata shape.
- Do not modify unrelated sections in `PipelinePage.tsx`.

## Verification

Run from `tauri-app`:

```sh
npm run typecheck
```

If time permits, also run:

```sh
npm run test
```

Manual UI checks:

- The three vector labels are uppercase.
- Selected atlas tags are visibly bigger.
- `+ Add Atlas` is a normal button, not a select.
- Clicking `+ Add Atlas` opens a popup for that vector.
- Search filters atlas rows by label/key.
- Already-selected atlases are marked `Selected` and cannot be added twice.
- Unselected atlases can be added and then appear as selected tags in the card.
- The dialog can be closed.
