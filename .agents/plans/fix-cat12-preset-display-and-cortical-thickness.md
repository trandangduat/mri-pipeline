# Fix CAT12 Preset Display And Cortical Thickness Preset

## 1. Goal

Make CAT12 presets clearer and consistent with the other preset families.

Changes needed:

- Add missing `CAT12 + Cortical Thickness` preset.
- For CAT12 presets, show only real CAT12 stages in the UI.
- Stop showing many `Not available` rows for CAT12 presets.
- Avoid pretending CAT12 maps to FreeSurfer-style internal stages.

This should be a small backend metadata + frontend display change. It should not change CAT12 command execution beyond adding the new preset option.

---

## 2. Current Behavior

`pipeline/presets.py` currently defines these CAT12 modes:

- `CAT12 + Volume`
- `CAT12 + Volume + Cortical Thickness`

It does not define:

- `CAT12 + Cortical Thickness`

The UI in `tauri-app/src/pages/PipelinePage.tsx` renders every global pipeline stage from `metadata.stages` when tools are visible.

For each stage, it reads:

```ts
const selectedToolKey = ((formValues as Record<string, unknown>)[`stage_${stage.id}`] as string) || '';
```

If `selectedToolKey` is empty, it renders `Not available`.

CAT12 presets only have real tools for:

- `segmentation`
- `stats_extraction`

Therefore the UI currently shows `Not available` for most non-CAT12 stages.

This is technically consistent with the generic UI, but misleading for CAT12.

---

## 3. Desired CAT12 UI

For CAT12 built-in presets, show only the CAT12 stages that exist.

Recommended labels:

| Internal stage | UI label for CAT12 |
| --- | --- |
| `segmentation` | `CAT12 Processing` |
| `stats_extraction` | `CAT12 Statistics` |

Do not show these rows for CAT12 presets:

- Reorientation, resize
- Brain Extraction
- Template Registration
- Image standardization
- WM Segmentation
- Surface Reconstruction
- Surface Registration

Do not show disabled `Not available` rows for CAT12 built-in presets.

Keep the normal full stage table for:

- FreeSurfer 7 presets
- FreeSurfer 8 presets
- FastSurfer presets
- Custom mode
- loaded custom preset files

---

## 4. Desired CAT12 Presets

Add this preset:

```text
CAT12 + Cortical Thickness
```

It should follow the same pattern used by FreeSurfer/FastSurfer cortical-thickness-only presets:

- same processing tools as the full `Volume + Cortical Thickness` preset
- only cortical thickness stats enabled
- no volume stats vectors enabled by default

Expected backend configuration:

```python
"CAT12 + Cortical Thickness": {
    "tools": CAT12_FULL_TOOLS,
    "stats": THICKNESS_STATS,
    "default_atlases": {
        "cortical_thickness": ["aparc"],
    },
}
```

Rationale:

- `CAT12 + Volume + Cortical Thickness` already uses `CAT12_FULL_TOOLS`.
- `CAT12_FULL_TOOLS` already uses `cat12_full_segmentation` and `cat12_full_stats_extraction`.
- `THICKNESS_STATS` already exists and is used by other cortical-thickness-only presets.

Important caveat:

- Confirm that `cat12_full_stats_extraction` writes or exposes cortical thickness data compatible with existing `cortical_thickness` stats-vector generation.
- The existing full CAT12 preset strongly suggests this is intended, but tests should cover it.

---

## 5. Backend Implementation Steps

Edit `pipeline/presets.py`.

1. Add `CAT12 + Cortical Thickness` to `PIPELINE_MODES` near other CAT12 presets.

Recommended order:

```python
PIPELINE_MODES = (
    "CAT12 + Volume",
    "CAT12 + Cortical Thickness",
    "CAT12 + Volume + Cortical Thickness",
    ...
)
```

2. Add a `PRESET_CONFIGS` entry:

```python
"CAT12 + Cortical Thickness": {
    "tools": CAT12_FULL_TOOLS,
    "stats": THICKNESS_STATS,
    "default_atlases": {
        "cortical_thickness": ["aparc"],
    },
},
```

3. Do not add new command builders unless tests prove the existing CAT12 full tools cannot produce thickness-only outputs.

4. Do not add NeuroFLOW support for CAT12 unless separately requested. NeuroFLOW currently maps only FreeSurfer/FastSurfer presets in `pipeline/neuroflow_adapter.py`.

---

## 6. Frontend Implementation Steps

Edit `tauri-app/src/pages/PipelinePage.tsx`.

Add a small helper or inline constants near the component render logic.

Suggested logic:

```ts
const isCat12Preset = formValues.pipelineMode.startsWith('CAT12 +');
```

When `showTools` is true and the selected mode is a built-in CAT12 preset:

- filter rendered stages to only stages with selected tools
- relabel the two rows for CAT12

Pseudo-implementation:

```ts
const displayedStages = (metadata?.stages || []).filter((stage) => {
  if (!isCat12Preset) return true;
  return ['segmentation', 'stats_extraction'].includes(stage.id);
});

const stageLabel = isCat12Preset
  ? stage.id === 'segmentation'
    ? 'CAT12 Processing'
    : stage.id === 'stats_extraction'
      ? 'CAT12 Statistics'
      : stage.label
  : stage.label;
```

Use `displayedStages` instead of `(metadata?.stages || [])` for rendering.

Use `stageLabel` instead of `stage.label` for the row label.

Keep the select controls enabled so a user can still change tools and switch to `Custom` via existing `handleStageToolChange()` behavior.

If a CAT12 preset somehow has an empty tool for either displayed stage, it is acceptable to show `Not available` for that row because that would indicate a real metadata problem.

---

## 7. Tests

Run existing tests first to understand current baseline.

Backend tests:

```bash
./.venv/bin/python -m pytest tests/test_cat12_volume_preset.py tests/test_app_backend_run_request.py tests/test_job_worker.py
```

Add or update tests as needed.

Recommended backend assertions:

- `CAT12 + Cortical Thickness` exists in `PIPELINE_MODES`.
- `PRESET_CONFIGS["CAT12 + Cortical Thickness"]["tools"]` uses:
  - `segmentation == "cat12_full_segmentation"`
  - `stats_extraction == "cat12_full_stats_extraction"`
- enabled stats are only `cortical_thickness` after normalization.
- default atlas for `cortical_thickness` is `aparc`.
- volume stats are not enabled for this preset.

Frontend tests:

```bash
cd tauri-app && npm test
```

Add or update a test if a suitable `PipelinePage` test exists. If no focused `PipelinePage` test harness exists, keep frontend change minimal and rely on typecheck plus manual inspection.

Recommended frontend assertions if practical:

- Selecting `CAT12 + Volume` shows `CAT12 Processing` and `CAT12 Statistics`.
- CAT12 display does not show `Brain Extraction` or `Not available` rows for skipped global stages.
- Selecting `FreeSurfer 8 + Volume` still shows the normal global stage table including unavailable rows.

Frontend verification:

```bash
cd tauri-app && npm run typecheck
cd tauri-app && npm test
```

Known existing note:

- `npm test` may print existing React `act(...)` warnings. Do not treat those warnings as new failures unless the test result fails.

---

## 8. Manual UI Verification

Start the app/backend as usual.

Check these presets in Pipeline Steps with tools visible:

- `CAT12 + Volume`
- `CAT12 + Cortical Thickness`
- `CAT12 + Volume + Cortical Thickness`
- `FreeSurfer 8 + Volume`
- `FreeSurfer 8 + Volume + Cortical Thickness`

Expected CAT12 display:

| Preset | Rows shown |
| --- | --- |
| `CAT12 + Volume` | `CAT12 Processing`, `CAT12 Statistics` |
| `CAT12 + Cortical Thickness` | `CAT12 Processing`, `CAT12 Statistics` |
| `CAT12 + Volume + Cortical Thickness` | `CAT12 Processing`, `CAT12 Statistics` |

Expected non-CAT12 display:

- unchanged full pipeline stage table
- unavailable stages still shown as `Not available` for volume-only FreeSurfer/FastSurfer presets

---

## 9. Non-Goals

Do not do these in this change:

- Do not redesign backend stage taxonomy.
- Do not remap CAT12 internals into FreeSurfer stages.
- Do not add CAT12 NeuroFLOW preset YAMLs.
- Do not change CAT12 command builders unless tests reveal a real bug.
- Do not remove `Not available` rows globally; this change is CAT12-only.

---

## 10. Risk

Risk is low.

Main risks:

- `cat12_full_stats_extraction` may not generate thickness TSVs for the selected `aparc` atlas in some outputs.
- UI filtering might accidentally apply to `Custom` mode if CAT12 detection is too broad.
- Adding a new pipeline mode may require updating tests that assert exact preset counts or order.

Risk controls:

- Keep CAT12 detection strict: `pipelineMode.startsWith('CAT12 +')` and not Custom.
- Add backend tests for preset stats normalization.
- Keep frontend changes local to `PipelinePage.tsx`.

---

## 11. Acceptance Criteria

The work is complete when:

- `CAT12 + Cortical Thickness` appears in the pipeline preset dropdown.
- Its backend preset uses CAT12 full processing tools.
- It enables only `cortical_thickness` stats by default.
- CAT12 built-in presets show only two rows in Pipeline Steps.
- FreeSurfer/FastSurfer preset display remains unchanged.
- Backend tests pass.
- Frontend typecheck passes.
- Frontend tests pass or any failures are confirmed unrelated/existing.
