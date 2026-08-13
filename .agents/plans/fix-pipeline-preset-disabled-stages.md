# Fix Pipeline Preset Disabled Stages

## Goal

Fix the GUI behavior for pipeline presets so volume-only presets show unavailable stages clearly, and manual stage edits switch predefined presets to `Custom`.

## User-Visible Requirements

- In the GUI, selecting `FreeSurfer 8 + Volume` must not show tools for stages that the volume-only preset does not need.
- Disabled/unneeded stages should show `Not available` instead of `Disabled / Skip` or similar wording.
- Disabled/unneeded stages need clear visual separation from normal enabled stages.
- If the user selected one of the predefined presets and then changes a tool selection for any stage, the `Pipeline preset` select should change to `Custom`.

## Investigation Summary

- Main GUI code is in `tauri-app/src/pages/PipelinePage.tsx`.
- Preset metadata comes from `app_backend/metadata.py`, which exposes `PRESET_CONFIGS` from `pipeline/presets.py`.
- `pipeline/presets.py` currently has `FREESURFER_8_TOOLS = FREESURFER_8_SURFACE_TOOLS`, so `FreeSurfer 8 + Volume` gets the full FS8 surface-stage map.
- `FreeSurfer 7 + Volume` already has the desired pattern through `FREESURFER_7_VOLUME_TOOLS`, blanking volume-unneeded stages and using `fs7_recon_style_subcortical_stats`.
- `PipelineStepsSection.handlePipelineModeChange()` only writes entries present in the selected preset, so any stage not present in a new preset could keep stale form state unless all stage fields are cleared or the preset includes explicit empty strings for skipped stages.
- Stage rows currently always render the same normal row styling and the empty option label is `Disabled / Skip` at `PipelinePage.tsx` around line 192.
- Stage select `onChange` currently calls `setFormField()` directly, so it does not flip predefined presets to `Custom`.

## Implementation Plan

### 1. Fix `FreeSurfer 8 + Volume` Preset Data

Update `pipeline/presets.py`:

- Keep `FREESURFER_8_SURFACE_TOOLS` unchanged for cortical thickness and volume+thickness presets.
- Introduce a `FREESURFER_8_VOLUME_TOOLS` map, following the FS7 volume pattern.
- It should use the FS8 reduced54/synthseg early-stage tools required for FS8 volume output, but blank out the surface/thickness-only stages.
- Recommended map:

```python
FREESURFER_8_VOLUME_TOOLS = {
    **FREESURFER_8_SURFACE_TOOLS,
    **{stage: "" for stage in VOLUME_SKIPPED_STAGES},
}
```

- Then set `FREESURFER_8_TOOLS = FREESURFER_8_VOLUME_TOOLS` or point the preset directly to `FREESURFER_8_VOLUME_TOOLS`.
- This should make `FreeSurfer 8 + Volume` select only:
  - `reorientation`: `fs8_reduced54_reorientation`
  - `segmentation`: `synthseg_freesurfer_fs8`
  - `stats_extraction`: `fs8_reduced54_stats`
  - blank/disabled: `brain_extraction`, `template_registration`, `bias_correction`, `white_matter_segmentation`, `surface_reconstruction`, `surface_registration`
- Confirm whether `brain_extraction` and `template_registration` should be skipped by FS8 volume by following the existing `VOLUME_SKIPPED_STAGES` constant. The user explicitly says FS8 volume does not need all stages, and that constant already includes these stages.

### 2. Update Tests For FS8 Volume Preset

Update `tests/test_fs8_reduced54_preset.py`:

- Import the new `FREESURFER_8_VOLUME_TOOLS` if introduced.
- Change `test_freesurfer8_surface_presets_use_surface_tools()` so only cortical thickness and volume+thickness assert the full surface map.
- Add or adjust a test proving `FreeSurfer 8 + Volume` uses the new volume map with empty strings for skipped stages.
- Keep the existing tests that validate full surface tools cover all stages.
- Add an assertion that `PRESET_CONFIGS["FreeSurfer 8 + Volume"]["tools"] == FREESURFER_8_VOLUME_TOOLS`.

### 3. Clear All Stage Fields When Applying A Preset

Update `PipelineStepsSection.handlePipelineModeChange()` in `tauri-app/src/pages/PipelinePage.tsx`:

- When a predefined preset is selected, initialize `formFields` with `pipelineMode: mode` and a blank string for every stage in `metadata.stage_order` or `metadata.stages` before applying `preset.tools`.
- Then apply all entries from `preset.tools`.
- This prevents stale selected tools from remaining when switching between presets.

Minimal example shape:

```ts
const formFields: Record<string, string> = {pipelineMode: mode};
for (const stageKey of metadata?.stage_order || []) {
  formFields[`stage_${stageKey}`] = '';
}
for (const [stageKey, toolKey] of Object.entries(preset.tools || {})) {
  formFields[`stage_${stageKey}`] = toolKey;
}
```

### 4. Switch Predefined Presets To `Custom` On Manual Tool Edit

Update `PipelineStepsSection` in `PipelinePage.tsx`:

- Add a small local handler for stage select changes.
- If `formValues.pipelineMode !== 'Custom'`, set both the changed stage and `pipelineMode: 'Custom'` in one `setFormFields()` call.
- If already custom, only update that stage.
- Do not switch to `Custom` when `handlePipelineModeChange()` itself is applying preset fields.

Example shape:

```ts
const handleStageToolChange = (stageId: string, toolKey: string) => {
  if (formValues.pipelineMode === 'Custom') {
    setFormField(`stage_${stageId}`, toolKey);
    return;
  }
  setFormFields({pipelineMode: 'Custom', [`stage_${stageId}`]: toolKey});
};
```

- Replace the stage select `onChange={(e) => setFormField(...)}` with this handler.

### 5. Change Empty Stage Label To `Not available`

Update the empty select option label in `PipelinePage.tsx`:

- Replace `Disabled / Skip` with `Not available`.
- Keep the option value as `""` so backend/run config behavior remains unchanged.

### 6. Add Visual Separation For Unavailable Stages

Update stage-row rendering in `PipelineStepsSection`:

- Determine whether the current selected value is blank:

```ts
const selectedToolKey = ((formValues as Record<string, unknown>)[`stage_${stage.id}`] as string) || '';
const isUnavailable = selectedToolKey === '';
```

- Apply different row styling when unavailable. Keep it subtle but obvious:
  - muted background such as `bg-cursor-canvas-soft/70` or current design-system equivalent
  - left accent/border such as `border-l-2 border-l-cursor-hairline-strong`
  - muted stage label text
  - maybe reduced opacity on the select, but keep it readable
- Preserve normal row styling for selected-tool stages.
- Avoid disabling the select itself. The user may intentionally pick a tool, which should switch preset to `Custom`.
- Because the table container already has borders and each row has a bottom border, prefer a minimal class-name conditional rather than adding a new component.

Example shape:

```tsx
const rowClassName = isUnavailable
  ? '... bg-cursor-canvas-soft/70 border-l-2 border-l-cursor-hairline-strong'
  : '... bg-white';
```

### 7. Check Related Behavior In Tools Page

Inspect `tauri-app/src/pages/ToolsPage.tsx` after the preset changes:

- It currently uses `metadata?.presets?.[formValues.pipelineMode]?.tools || {}` for image refresh.
- When pipeline mode is `Custom`, this may not include current selected custom stage fields. This is pre-existing, but the new automatic switch to `Custom` can make it more visible.
- If necessary and small, update `ToolsPage.refreshTools()` to derive selected tools from current `formValues.stage_*` when `pipelineMode === 'Custom'`, using `metadata.stage_order`. Filter out empty strings.
- If this becomes non-trivial, leave it unchanged and mention it in the final executor summary as a follow-up risk. Do not over-expand the task.

## Verification

Run targeted backend tests:

```bash
pytest tests/test_fs8_reduced54_preset.py tests/test_fs7_recon_style_preset.py
```

Run frontend typecheck:

```bash
npm run typecheck
```

with working directory `tauri-app/`.

If time allows, run:

```bash
npm run test
```

with working directory `tauri-app/`.

Manual GUI smoke checks if feasible:

- Select `FreeSurfer 8 + Volume`; verify unneeded stages display `Not available` with muted/separated styling.
- Select `FreeSurfer 7 + Volume`; verify existing skipped stages also display `Not available` with the same styling.
- Select a predefined preset, change a stage tool, and verify `Pipeline preset` changes to `Custom`.
- Switch between presets and verify stale tools do not remain in stages that the newly selected preset leaves unavailable.

## Notes

- Do not change the empty string sentinel for skipped stages unless a backend contract explicitly requires it.
- Do not disable unavailable stage selects, because users must be able to pick a tool and create a custom configuration.
- Keep the UI change localized to `PipelineStepsSection` unless tests or typecheck show a broader type issue.
