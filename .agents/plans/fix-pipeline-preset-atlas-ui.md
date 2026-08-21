# Fix Pipeline Preset And Atlas UI

## Goal

Fix preset and atlas behavior in the Tauri frontend so the selected pipeline preset, selected stage tools, and selected stats-vector atlases stay consistent.

The frontend must rely on backend metadata for preset atlas defaults:

- `metadata.presets[presetName].default_atlases`
- `metadata.presets[presetName].stats`
- `metadata.presets[presetName].tools`

Do not hard-code FreeSurfer or CAT12 atlas defaults in the frontend.

## Current Context

Relevant files:

- `tauri-app/src/api/runConfig.ts`
- `tauri-app/src/stores/pipelineFormStore.ts`
- `tauri-app/src/router/AppRouter.tsx`
- `tauri-app/src/pages/PipelinePage.tsx`
- `tauri-app/test/PipelineStepsSection.test.tsx`

Backend metadata already exposes preset atlas defaults through:

- `pipeline/presets.py`
- `app_backend/metadata.py`
- frontend schema: `tauri-app/src/api/schemas.ts`

Current frontend issues found:

- `DEFAULT_FORM_VALUES.pipelineMode` is `Custom`.
- `AppRouter.tsx` initializes atlas selections by taking the first atlas from each stats vector instead of using the selected preset's `default_atlases`.
- `PipelineStepsSection.handlePipelineModeChange()` applies preset tools but does not apply preset default atlases.
- `StatsAtlasSection` mutates atlases without checking whether this breaks the current preset.
- Custom mode has no warning when selected stats-vector atlases cannot be generated because the responsible stage is `Not available`.

## Product Behavior To Implement

1. First app open should use preset `FreeSurfer 8 + Volume + Cortical Thickness`, not `Custom`.

2. When a user chooses any preset:

- Apply the preset tools.
- Apply `preset.default_atlases` from backend metadata.
- Clear atlas selections for stats vectors absent from `preset.default_atlases`.
- Keep `Add Atlas` enabled for every stats vector.

3. When a user is currently in a preset:

- If they change a stage tool to a value different from the preset's tool for that stage, set `pipelineMode` to `Custom`.
- If they add an atlas to a stats vector not handled by the preset, set `pipelineMode` to `Custom`.
- If they add an atlas to a stats vector handled by the preset, keep the preset.
- If they remove a preset default atlas from a stats vector handled by the preset, set `pipelineMode` to `Custom`.

4. In `Custom` mode:

- If a stats vector has one or more selected atlases and the stage responsible for that stats vector is `Not available`, show a warning under that stats vector.

## Backend Default Atlas Note

The frontend must not decide that CAT12 uses FreeSurfer atlases.

Current backend defaults in `pipeline/presets.py` include:

- `CAT12 + Volume`
  - `subcortical_volume`: `cat12_neuromorphometrics`
  - `cortical_volume`: `cat12_schaefer2018_200parcels_17networks`
- `CAT12 + Cortical Thickness`
  - `cortical_thickness`: `aparc`
- `CAT12 + Volume + Cortical Thickness`
  - `subcortical_volume`: `cat12_neuromorphometrics`
  - `cortical_volume`: `cat12_schaefer2018_200parcels_17networks`
  - `cortical_thickness`: `aparc`

Before changing backend defaults, confirm whether `aparc` is acceptable as the CAT12 cortical-thickness default. There is no obvious `cat12_*` cortical-thickness atlas in current metadata. If product decides `aparc` is wrong for CAT12 thickness, update `pipeline/presets.py` and backend tests first, then the frontend will pick up the new default automatically.

## Detailed Implementation Steps

### 1. Add Frontend Helper Functions

Create small helper functions near `PipelineStepsSection` / `StatsAtlasSection`, or in a local module if preferred. Keep the change minimal.

Recommended helper behavior:

```ts
function presetDefaultAtlases(metadata, pipelineMode) {
  const next: Record<string, string[]> = {};

  for (const statKey of Object.keys(metadata?.stats_vectors || {})) {
    next[statKey] = [];
  }

  const defaults = metadata?.presets?.[pipelineMode]?.default_atlases || {};
  for (const [statKey, atlases] of Object.entries(defaults)) {
    next[statKey] = Array.isArray(atlases) ? [...atlases] : [];
  }

  return next;
}
```

Also add helpers for preset drift checks:

```ts
function isPresetMode(metadata, pipelineMode) {
  return pipelineMode !== 'Custom' && Boolean(metadata?.presets?.[pipelineMode]);
}

function presetHandlesStat(metadata, pipelineMode, statKey) {
  return Boolean(metadata?.presets?.[pipelineMode]?.stats?.includes(statKey));
}

function isPresetDefaultAtlas(metadata, pipelineMode, statKey, atlasKey) {
  return Boolean(metadata?.presets?.[pipelineMode]?.default_atlases?.[statKey]?.includes(atlasKey));
}
```

Use concrete project types if easy. Otherwise keep the helper local and typed with existing metadata shape.

### 2. Change Default Pipeline Mode

Edit `tauri-app/src/api/runConfig.ts`:

- Change `DEFAULT_FORM_VALUES.pipelineMode` from `Custom` to `FreeSurfer 8 + Volume + Cortical Thickness`.

Confirm effects:

- `usePipelineFormStore.resetForm()` already copies `DEFAULT_FORM_VALUES`, so reset behavior will follow the new default.
- `showTools` initial state remains hidden because the new mode is not `Custom`.

### 3. Fix Startup Atlas Initialization

Edit `tauri-app/src/router/AppRouter.tsx`.

Current startup code builds atlas selection from `meta.stats_vectors` by selecting first atlas entries. Replace this with preset-driven initialization.

Startup should:

- Wait for backend health.
- Fetch metadata.
- Read the current `pipelineMode` from `usePipelineFormStore.getState().formValues.pipelineMode`.
- If that mode exists in `meta.presets`, apply:
  - stage fields from `preset.tools`
  - selected stats atlases from `preset.default_atlases`
- If the current mode is missing from metadata, avoid crashing. A safe fallback is to leave form fields unchanged and set selected atlases to `{}` or all stats keys as `[]`.

Implementation option:

- Add store action `applyPresetConfig` support for `default_atlases`, then call it from startup.
- Or keep startup local and call `setFormFields()` plus `setSelectedStatsAtlases()`.

Prefer local minimal changes unless the store helper becomes cleaner.

Important: do not reintroduce generic first-atlas selection.

### 4. Fix Preset Selection In `PipelineStepsSection`

Edit `handlePipelineModeChange()` in `tauri-app/src/pages/PipelinePage.tsx`.

When `mode` is a preset:

- Build form fields with `pipelineMode: mode`.
- Clear all stage fields using `metadata.stage_order`.
- Apply `preset.tools`.
- Set form fields.
- Set selected atlases using `presetDefaultAtlases(metadata, mode)`.

Needed store selector:

- Add `const setSelectedStatsAtlases = usePipelineFormStore((s) => s.setSelectedStatsAtlases);`

When `mode` is `Custom`:

- Keep existing behavior of showing tools.
- Only set `pipelineMode` to `Custom`.
- Do not clear stage tools or atlases.

This preserves the user's current configuration when explicitly switching into custom mode.

### 5. Fix Stage-Tool Drift Behavior

Edit `handleStageToolChange()` in `PipelineStepsSection`.

Behavior:

- Always set the selected stage value.
- If current mode is `Custom`, stay custom.
- If current mode is a preset:
  - Compare `toolKey` with `metadata.presets[currentMode].tools[stageId] || ''`.
  - If equal, keep the preset.
  - If different, set `pipelineMode` to `Custom`.

Important nuance:

- If the user changes a stage and somehow picks the same value as the preset, do not switch to `Custom`.
- Existing UI likely fires only on changed values, but the comparison makes behavior correct.

Suggested implementation:

```ts
const presetTool = metadata?.presets?.[formValues.pipelineMode]?.tools?.[stageId] || '';
const nextMode = formValues.pipelineMode !== 'Custom' && toolKey !== presetTool ? 'Custom' : formValues.pipelineMode;
setFormFields({pipelineMode: nextMode, [`stage_${stageId}`]: toolKey});
```

### 6. Fix Atlas Drift Behavior In `StatsAtlasSection`

Do not change `Add Atlas` button disabled state. It should remain enabled.

Add selectors:

- `formValues`
- `setFormField` or `setFormFields`

Replace direct calls to `toggleAtlas()` and `removeAtlas()` with local handlers:

```ts
function markCustomIfAtlasChangeBreaksPreset(statKey, atlasKey, action) {
  if (formValues.pipelineMode === 'Custom') return;

  const preset = metadata?.presets?.[formValues.pipelineMode];
  if (!preset) return;

  const handled = preset.stats?.includes(statKey);
  if (!handled) {
    setFormField('pipelineMode', 'Custom');
    return;
  }

  if (action === 'remove' && preset.default_atlases?.[statKey]?.includes(atlasKey)) {
    setFormField('pipelineMode', 'Custom');
  }
}
```

For add/toggle behavior:

- In the picker, `toggleAtlas(statKey, atlasKey)` can either add or remove.
- Determine `isSelected` before calling the store.
- If `isSelected` is false, action is `add`.
- If `isSelected` is true, action is `remove`.

Rules:

- Add to handled stat: keep preset.
- Add to unhandled stat: switch to `Custom`.
- Remove default atlas from handled stat: switch to `Custom`.
- Remove non-default atlas from handled stat: keep preset.
- Remove atlas from unhandled stat while still in a preset should normally be impossible, because adding it would have switched to `Custom`; still handle safely by switching to `Custom` if it happens.

Order of operations:

- It is acceptable to set `pipelineMode` to `Custom` before or after toggling atlas, as long as the final state is correct.
- Prefer calling drift handler first, then mutate atlas selection.

### 7. Add Custom Warning Under Stats Vector

Add warning rendering inside each stats-vector block in `StatsAtlasSection`.

Initial mapping:

- `subcortical_volume` -> `stats_extraction`
- `cortical_volume` -> `stats_extraction`
- `cortical_thickness` -> `stats_extraction`

Reason: current frontend stage metadata does not expose per-stat producer stages. All stats-vector outputs are represented by the `stats_extraction` stage in the UI.

Warning condition:

```ts
const isCustomMode = formValues.pipelineMode === 'Custom';
const hasSelectedAtlases = selectedAtlases.length > 0;
const statsStageUnavailable = !formValues.stage_stats_extraction;
const showUnavailableWarning = isCustomMode && hasSelectedAtlases && statsStageUnavailable;
```

Render under the atlas chips / empty state:

```tsx
{showUnavailableWarning ? (
  <div className="col-span-2 ml-3 rounded-md border border-cursor-semantic-warning/30 bg-cursor-semantic-warning/5 px-2.5 py-1.5 text-xs text-cursor-semantic-warning">
    This stats vector has selected atlases, but Statistics & Atlas mapping is set to Not available.
  </div>
) : null}
```

Check available design tokens before final class names. If no warning semantic token exists, use existing warning/error styles already present in the project.

### 8. Update Tests

Add or update frontend tests.

Preferred files:

- Existing: `tauri-app/test/PipelineStepsSection.test.tsx`
- New if needed: `tauri-app/test/StatsAtlasSection.test.tsx`

Test metadata should include realistic `stats_vectors`, `atlases`, and `default_atlases`.

Test cases:

1. Default mode:
   - After `resetForm()`, `formValues.pipelineMode` is `FreeSurfer 8 + Volume + Cortical Thickness`.

2. Selecting a preset applies default atlases:
   - Select `CAT12 + Volume`.
   - Assert selected atlases are:
     - `subcortical_volume`: `cat12_neuromorphometrics`
     - `cortical_volume`: `cat12_schaefer2018_200parcels_17networks`
     - `cortical_thickness`: `[]`

3. Selecting FreeSurfer volume clears thickness:
   - Start with thickness atlas selected.
   - Select `FreeSurfer 8 + Volume`.
   - Assert `cortical_thickness` is `[]`.

4. Covered stat atlas add keeps preset:
   - Current mode: `FreeSurfer 8 + Volume`.
   - Add another atlas to `subcortical_volume`.
   - Assert mode remains `FreeSurfer 8 + Volume`.

5. Uncovered stat atlas add switches to custom:
   - Current mode: `FreeSurfer 8 + Volume`.
   - Add atlas to `cortical_thickness`.
   - Assert mode becomes `Custom`.

6. Removing preset default atlas switches to custom:
   - Current mode: `FreeSurfer 8 + Volume`.
   - Remove `freesurfer_aseg` from `subcortical_volume`.
   - Assert mode becomes `Custom`.

7. Stage tool mismatch switches to custom:
   - Current mode: any built-in preset.
   - Change one stage select to a different tool or `Not available`.
   - Assert mode becomes `Custom`.

8. Stage tool equal to preset does not switch to custom:
   - If easy to simulate, call handler via UI with same option is hard.
   - This can be skipped if it requires awkward test setup.

9. Custom warning:
   - Set mode to `Custom`.
   - Set `stage_stats_extraction` to `''`.
   - Select an atlas in one stats vector.
   - Render `StatsAtlasSection`.
   - Assert warning text is visible under that stats vector.

10. Add Atlas stays enabled:
   - In a volume-only preset, assert the cortical-thickness `Add Atlas` button can still be opened.

Backend tests only needed if changing CAT12 defaults:

- Update `tests/test_cat12_volume_preset.py`.
- Update any metadata tests that assert default atlas values.

### 9. Verification Commands

Run from repository root or `tauri-app` depending on package scripts.

Suggested frontend verification:

```bash
npm test -- PipelineStepsSection
```

If a new stats atlas test file is added:

```bash
npm test -- StatsAtlasSection
```

If package scripts use Vitest directly:

```bash
npm run test -- PipelineStepsSection
```

Run typecheck/build if available:

```bash
npm run typecheck
npm run build
```

If backend defaults are changed:

```bash
pytest tests/test_cat12_volume_preset.py tests/test_app_backend_metadata.py
```

Use the actual commands available in `tauri-app/package.json`.

## Acceptance Criteria

- New sessions and form resets default to `FreeSurfer 8 + Volume + Cortical Thickness`.
- Initial selected atlases come from that preset's backend `default_atlases`.
- Choosing any preset replaces stats-vector atlas selections with that preset's backend defaults and clears vectors not listed by that preset.
- CAT12 volume presets use CAT12 default atlases from backend metadata, not FreeSurfer defaults.
- `Add Atlas` remains available for stats vectors not covered by the current preset.
- Adding atlases to covered stats vectors does not switch out of the preset.
- Adding atlases to uncovered stats vectors switches to `Custom`.
- Changing a preset stage tool switches to `Custom` when the selected tool differs from the preset tool.
- Removing a default atlas from a preset switches to `Custom`.
- Custom mode shows a warning when selected stats-vector atlases cannot be generated because `stage_stats_extraction` is `Not available`.
- Relevant frontend tests pass.

## Risks And Notes

- The default mode string must exactly match backend `PIPELINE_MODES`: `FreeSurfer 8 + Volume + Cortical Thickness`.
- Do not use label matching such as `FreeSurfer Aseg Atlas` in frontend logic. Use atlas keys from backend metadata only.
- Be careful not to erase custom atlas choices when the user switches explicitly to `Custom`.
- `AppRouter.tsx` currently performs startup initialization once. Avoid effects that repeatedly overwrite user changes after metadata is loaded.
- Zustand updates can be split across `setFormFields` and `setSelectedStatsAtlases`; React should settle correctly, but tests should assert final store state.
- If warning color tokens do not include a warning semantic token, reuse existing app tokens instead of inventing unsupported classes.
