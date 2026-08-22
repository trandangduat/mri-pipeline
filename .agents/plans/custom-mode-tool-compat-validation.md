# Custom Mode Tool Compatibility Validation

## Goal

In **Custom** pipeline mode, continuously validate the selected tool combination while the user edits stage selects. If an enabled stage's required input cannot be produced by the currently-enabled upstream tools, show a red error, highlight the affected stage rows, and block **Start** (client-side and server-side). Named presets remain exempt: their tool maps come from templates and are valid by construction.

## User-Visible Requirements

- Selecting a named preset never shows a compatibility error or row highlight, no matter how long the user waits.
- Any manual edit flips the preset selector to `Custom` (existing behavior, `handleStageToolChange`, `tauri-app/src/pages/PipelinePage.tsx:95-108`) and live validation kicks in.
- An invalid combination renders a **red error block** (not a warning) below the steps grid, listing each broken stage, why its input is missing, and which enabled upstream tool is responsible.
- Affected stage rows get a distinct red-tinted highlight (different from the muted "Not available" styling).
- The header **Start Pipeline** button is disabled with text such as "Invalid tool combination" while violations exist.
- Loading an arbitrary preset JSON file (which forces `Custom`) is validated like any other custom selection.
- Starting is also rejected server-side with a human-readable message surfaced through the existing start-stream "validate" step.

## Investigation Summary

### Where things live today (verified)

| Area | Location | Notes |
|---|---|---|
| Steps UI | `PipelineStepsSection`, `tauri-app/src/pages/PipelinePage.tsx:37-356` | Rows rendered 223-275; row styling ternary at 249 (`bg-cursor-canvas-soft/70 border-l-2 border-l-cursor-hairline-strong` when unavailable); empty option `Not available` at 260 |
| Preset→Custom flip | `handleStageToolChange`, `PipelinePage.tsx:95-108` | Skips flip only when new value equals the preset's own tool |
| Preset apply | `handlePipelineModeChange`, `PipelinePage.tsx:75-93` | Clears all `stage_*` fields then applies `preset.tools` — guarantees a named preset's exact tool map |
| Preset JSON load | `handlePresetFile`, `PipelinePage.tsx:110-135` | Sets `pipelineMode: 'Custom'` with arbitrary tools |
| Start gating | `AppHeader.tsx:224-235` (`startDisabled`, `startButtonText`), button at 283-291, `handleStartPipeline` 73-102 | Currently gates on starting / SSH-connected / license only |
| Metadata endpoint | `get_app_metadata()`, `app_backend/metadata.py:82-127` | Exposes presets/stages/stage_order/fs7_recon_style_stage_order/tools/tools_by_stage. `_tool_metadata` (45-58) already ships `output_files`/`output_globs` but **no requirements and no compatibility info** |
| Request validation | `validate_run_request_input`, `app_backend/run_request.py:162-212` | Checks inputs/target/runtime/license/neuroflow only. `_base_request` infers real mode from Custom+neuroflow at 223-226; `_selected_tools` (258-261) substitutes preset tools when mode ≠ Custom; `_license_error` (310-320) is the closest existing combo-ish check |
| Start-stream failure surfacing | `app_backend/jobs.py:86-95`, `app_backend/remote.py:198-206` | `prepare_run_request` errors already flow into `step_event("validate","failed")` + `complete_event(False, errors=...)` — **no changes needed there** if we reject inside `validate_run_request_input` |
| Input chaining | `pipeline/runner.py` — `run_pipeline` loop 532-541 skips unselected stages *without touching* `input_for_next_step`; success path resolves next input via `_find_output_file` at 616-624; missing-output failure at 620-624 | Bypass semantics are the *actual runtime*: a skipped stage lets the nearest preceding output flow to downstream |
| NeuroFLOW adapter | `NEUROFLOW_STAGE_TO_LOCAL_STAGE`, `pipeline/neuroflow_adapter.py:27-37`; `_ImageRunContext.input_for_stage` 73-83 (walks back `STAGE_ORDER` for nearest prior output) | Same bypass semantics |
| Reference propagation logic to port conceptually | `NeuroFLOW-private/src/neuroflow/graph.py:122-161` (`resolve_disabled_stages` — `active_ancestors` rewires deps around disabled stages); `NeuroFLOW-private/src/neuroflow/lifecycle.py:340-363` (`propagate_blocking` — cascades BLOCKED to descendants) | Pure functions; port the *algorithms*, not the imports |
| Stage-order switch | `STAGE_ORDER` `pipeline/registry.py:1575-1585`; `FS7_RECON_STYLE_STAGE_ORDER` 1587-1597; `stage_order_for_tools` 1600-1603 | When `template_registration == 'fs7_recon_style_template_registration'`, template_registration executes **before** brain_extraction |
| Tool definitions | `TOOL_DEFS`, `pipeline/registry.py:974-1549` | Per tool: `stage`, `image`, `command_builder`, `output_files`, `output_globs`, `needs_license`, optional `hidden_from_stage_select` (e.g. `fs8_reduced54_segmentation`, line 1190) |

### Feasibility verdict: contracts are PARTIALLY auto-derivable — curated table + drift-guard tests

**Produces: derivable.** `output_files` / `output_globs` are already structured per tool (and already shipped via metadata). E.g. `fastsurfer_reorientation → freesurfer/*/mri/orig.mgz` (registry.py:1056), `fs7_recon_style_brain_extraction → freesurfer/*/mri/brainmask.mgz` (1282), `fastsurfer_segmentation → freesurfer/*/mri/aseg.auto.mgz` (1066).

**Requires: NOT reliably derivable.** Required inputs exist only as `test -s …` guards and path references *inside shell command builders* (e.g. `_fastsurfer_stage4` tests `orig.mgz`, `aparc.DKTatlas+aseg.deep.mgz`, `aseg.auto.mgz` at 723; `_fs8r_stage4` consumes `synthstrip.mgz` at 276; `_fs7r_stage2` consumes `transforms/talairach.xfm` at 492; `_fs7r_stage9` consumes `../surf/lh.white.preaparc` and `../label/lh.aparc.annot` at 614-617). Scraping these is fragile because:

- guards sit behind conditionals and self-healing fallbacks (`if [ ! -s "$MDIR/orig_nu.mgz" ]; then …regenerate…; fi`, registry.py:729);
- some tools are dual-mode (`_fs8_synthseg` runs in-subject-dir when `$SD/mri/orig.mgz` exists, else standalone NIfTI, registry.py:259-269);
- file-glob equality does not imply semantic compatibility — the whole reason the user rejected stage-level `depends_on`: FastSurfer vs FS7 vs SynthSeg segmentations differ in label space; fs7 vs fs8 surface/sphere products differ; stats tools of one family read the other family's files only by accident of shared `$SUBJECTS_DIR`.

**Decision:** a hand-curated contract table keyed by `tool_id` (`requires` / `produces` artifact tokens), made drift-proof by unit tests that (a) force every enabled, visible tool in `TOOL_DEFS` to have an entry, and (b) assert every preset tool map validates clean. Adding a tool without a contract fails CI.

### Cross-family hazards observed (drives the exception list)

- `fs8_reduced54_template_registration` consumes `synthstrip.mgz` (brain-extraction product) — breaks if `brain_extraction` disabled (registry.py:276).
- `fs7_recon_style_brain_extraction` consumes `transforms/talairach.xfm` — only satisfied when `fs7_recon_style_template_registration` is enabled AND the fs7-style order puts template_registration first (registry.py:492, 1587-1597). With the default order this pair is invalid.
- `fs7_recon_style_stats` needs fs7-only intermediates (`lh.white.preaparc`, `lh.aparc.annot`, autodet gw stats) — FastSurfer/FS8 chains do not satisfy it.
- `fastsurfer_stats_extraction` needs FastSurfer mapped annots + `sphere.reg` from `fastsurfer_surface_registration`.
- `surface_stats_fs7` (registered under stage `surface_registration`, registry.py:1491-1503) needs any FS-family `lh/rh.thickness` **and** `lh/rh.sphere.reg`.
- `freesurfer_stats_fs7` is a pure checker: requires `subcortical_volume.tsv`/`cortical_volume.tsv` already in `/output/stats` (registry.py:1509).
- Known-good mixes: `fastsurfer_reorientation → synthseg_freesurfer_fs8` (dual-mode reads `$SD/mri/orig.mgz`); `mri_convert_fs7|nibabel → synthstrip_fs7|hdbet|synthseg_standalone|ants_n4 → recon_all_fs7` (NIfTI chain, recon_all falls back `01_reoriented.nii.gz → 05_standardized.nii.gz → raw input`, registry.py:1476-1478); `sugar` consumes any FS-family white/pial under `/output/freesurfer`.

## Implementation Plan

> **Dependency:** the red error block and error row-highlight reuse the shared `<Alert severity="error">` component and `cursor-semantic-error` tokens delivered by `.agents/plans/unify-warning-alert-components.md` (steps 1, 3, 4: `ALERT` map in `src/lib/uiTokens.ts`, `Alert` in `src/components/ui.tsx`). Do not duplicate that work here; if it hasn't landed, implement this plan's frontend steps behind the same component API assuming it exists.

### 1. Backend module `pipeline/tool_compat.py` (source of truth)

Artifact-token vocabulary (semantic classes, family-scoped where mixing matters):

```python
INPUT_RAW = "input_raw"                    # implicit, available at chain start
NIFTI_VOLUME = "nifti_volume"
ORIG_CONFORMED = "orig_conformed"          # freesurfer/*/mri/orig.mgz (any recon family)
BE_SYNTHSTRIP_MGZ = "be_synthstrip_mgz"    # fs8_reduced54_brain_extraction
BE_FASTSURFER_MASK = "be_fastsurfer_mask"  # mask.mgz, produced by fastsurfer_segmentation
BE_FS7_BRAINMASK = "be_fs7_brainmask"
BE_NIFTI = "be_nifti"                      # synthstrip_fs7 / hdbet
SEG_FASTSURFER = "seg_fastsurfer"          # aparc.DKTatlas+aseg.deep(+CC).mgz + aseg.auto.mgz
SEG_SYNTHSEG_RCA = "seg_synthseg_rca"      # synthseg.rca.mgz + vol.csv (+ aseg.auto aliases)
SEG_FS7 = "seg_fs7"                        # aseg.presurf.mgz via mri_ca_label
SEG_NIFTI = "seg_nifti"                    # standalone synthseg / fastsurfervinn
SEG_CAT12 = "seg_cat12"                    # cat_*.xml + mwp1*/p0*
TALAIRACH_XFM = "talairach_xfm"            # transforms/talairach.xfm(.lta)
NU_TALAIRACH = "nu_talairach"              # nu.mgz (+ talairach.lta) post fastsurfer_template_registration
BIAS_NORM_FS = "bias_norm_fs"              # norm.mgz / T1.mgz / brainmask.mgz / brain.finalsurfs.mgz
WM_FILLED = "wm_filled"                    # wm.mgz + filled.mgz
SURFACES_PREAPARC_FS7 = "surfaces_preaparc_fs7"
SURFACES_FINAL = "surfaces_final"          # lh/rh.white, lh/rh.pial, lh/rh.thickness
SPHERE_REG = "sphere_reg"                  # lh/rh.sphere.reg
DKT_ANNOTS = "dkt_annots"                  # aparc.DKTatlas.mapped.annot (FastSurfer)
STATS_TSVS = "stats_tsvs"                  # subcortical_volume.tsv + cortical_volume.tsv
```

Contract shape:

```python
@dataclass(frozen=True)
class ToolContract:
    requires: frozenset[str]          # ALL of these must be available
    produces: frozenset[str]

TOOL_CONTRACTS: dict[str, ToolContract] = {
    "fastsurfer_reorientation":        ToolContract(frozenset({INPUT_RAW}), frozenset({ORIG_CONFORMED})),
    "fs8_reduced54_reorientation":     ToolContract(frozenset({INPUT_RAW}), frozenset({ORIG_CONFORMED})),
    "fs7_recon_style_reorientation":   ToolContract(frozenset({INPUT_RAW}), frozenset({ORIG_CONFORMED})),
    "mri_convert_fs7":                 ToolContract(frozenset({INPUT_RAW}), frozenset({NIFTI_VOLUME})),
    "nibabel":                         ToolContract(frozenset({INPUT_RAW}), frozenset({NIFTI_VOLUME})),
    "synthseg_freesurfer_fs8":         ToolContract(frozenset({ORIG_CONFORMED}), frozenset({SEG_SYNTHSEG_RCA})),
    # ... one entry per tool in TOOL_DEFS; fill remaining during implementation
}

def effective_stage_order(selected_tools: dict[str, str]) -> list[str]:
    # mirror registry.stage_order_for_tools (fs7 recon-style reorder)

def validate_tool_combo(selected_tools: dict[str, str]) -> list[dict]:
    """Pure function → [{"stage": ..., "tool": ..., "reason": ..., "blocked_by": ...}].
    1. Drop empty selections; if nothing remains → single violation 'no stages selected'.
    2. Walk effective_stage_order; maintain `available = {INPUT_RAW}` ∪ produces of validated tools.
    3. For each enabled stage whose tool's `requires` ⊄ `available` → violation
       (do NOT add its produces — mirror lifecycle.propagate_blocking cascading so
       downstream stages that depended on it are also reported).
    4. Return [] when the normalized non-empty map equals any PRESET_CONFIGS['tools']
       (defense: named presets are valid by construction).
    """
```

Curated cross-family exceptions (kept small, encoded as extra `produces` entries or an `EXCEPTIONS: dict[tuple[str, str], list[str]]` granting specific consumer↔producer token allowances):

- `fastsurfer_reorientation` additionally produces `orig_conformed` usable by `synthseg_freesurfer_fs8` and fs8/fs7 chains (all write/read the same `orig.mgz` path) — i.e. treat `orig_conformed` as family-agnostic by design.
- NIfTI chain: `synthstrip_fs7`, `hdbet`, `synthseg_standalone`, `ants_n4`, `corticalflow` accept `NIFTI_VOLUME` from any NIfTI producer; `recon_all_fs7` requires `NIFTI_VOLUME` (its own builder falls back to raw input, so `requires={}` + soft preference — encode as `requires=frozenset()` with a doc comment).
- `sugar` requires `SURFACES_FINAL` from any family (shared `$SUBJECTS_DIR`).
- Everything else stays family-scoped (the hazards listed in the Investigation Summary stay hard errors).

### 2. Expose contracts via `/metadata` (extend `get_app_metadata`)

Extend `app_backend/metadata.py:get_app_metadata()` (82-127):

```python
"tool_contracts": {
    tool_key: {"requires": sorted(c.requires), "produces": sorted(c.produces)}
    for tool_key, c in TOOL_CONTRACTS.items()
},
```

Justification: the frontend already fetches metadata once via `useMetadata()` and caches it; adding one key avoids a new endpoint, new IPC wiring, and a second round-trip, and keeps `version`-keyed cache invalidation intact. A dedicated endpoint is unjustified for ~40 small static dicts.

**Ship contracts, compute client-side** (rather than a precomputed pairwise matrix) because validity is a property of the *ordered enabled set* (bypass rewiring, fs7 order switch, cascading blocks), not of isolated pairs; a 40×40 boolean matrix could not express those semantics and would go stale with every tool addition. The TS evaluator is a ~60-line mirror of `validate_tool_combo`.

### 3. Frontend lib `tauri-app/src/lib/stageValidation.ts`

```ts
export interface StageViolation {
  stageId: string;
  toolKey: string;
  reason: string;      // human-readable, e.g. "needs brain-extraction output (synthstrip.mgz) but Brain Extraction is off"
  blockedBy?: string;  // display name of the offending/mismatched upstream tool
}

export function validateStageTools(
  metadata: AppMetadata,
  formValues: Record<string, unknown>,
): StageViolation[] {
  // 0. Named preset short-circuit: pipelineMode !== 'Custom' → [].
  //    Additionally, if the collected stage_* map deep-equals any preset.tools
  //    (covers Load-Preset-file which sets Custom), return [].
  // 1. Collect tools from stage_* keys (mirror api/runConfig.ts:122-124 trimming).
  // 2. Order: metadata.fs7_recon_style_stage_order when
  //    stage_template_registration === 'fs7_recon_style_template_registration',
  //    else metadata.stage_order (both already shipped, metadata.py:98-99).
  // 3. Union-of-enabled-upstream producers (bypass semantics, see Edge Cases);
  //    cascade-block descendants of violated stages.
  // 4. Empty selection → [{stageId: '*', reason: 'No pipeline steps selected'}].
}
export const EMPTY_STAGE_VIOLATIONS: StageViolation[] = [];
```

Wire-up:

- `PipelineStepsSection` (`PipelinePage.tsx`): `const violations = React.useMemo(() => metadata ? validateStageTools(metadata, formValues) : [], [metadata, formValues]);` — recomputes on every form change automatically (formValues is the zustand store object).
- Red error block **after the steps-grid closing `})}` at line 275**, rendered only when `violations.length > 0 && formValues.pipelineMode === 'Custom'`, using `<Alert severity="error">` with one `<li>` per violation (`{stageLabel}: {violation.reason}`).
- Row highlight: extend the ternary at line 249 to three states — normal / unavailable (current muted classes) / **invalid**: `border-l-2 border-l-cursor-semantic-error bg-cursor-semantic-error/10` with stage label `text-cursor-semantic-error`. Compute membership via a `Set` of `violations.map(v => v.stageId)`.
- `AppHeader.tsx`: `const violations = React.useMemo(...same validator...)`; extend `startDisabled` (224-227) with `|| violations.length > 0` and prepend a `startButtonText` branch (229-235) `'Fix tool combination'`. No prop drilling — the header already subscribes to `formValues` + `useMetadata`.

### 4. Server-side mirror (defense in depth)

Add to `app_backend/run_request.py`:

```python
def _tool_combo_error(config: RunRequestInput) -> str:
    from pipeline.tool_compat import validate_tool_combo
    violations = validate_tool_combo(_selected_tools(config))  # 258-261: preset modes resolve to preset tools
    return "; ".join(f"{v['stage']}: {v['reason']}" for v in violations[:3]) if violations else ""
```

Call it inside `validate_run_request_input` (162-212) right after `_license_error`, before the remote/local file checks. Because `_base_request`'s neuroflow inference (223-226) happens *after* validation, replicate its intent inside the check: if `config.pipeline_mode == "Custom"` and `infer_pipeline_mode_from_tools(selected) != "Custom"`, skip (the request will execute as a named preset). Errors flow into the existing `step_event("validate", "failed", …)` in `jobs.py:87-94` and `remote.py:199-204` unchanged.

### 5. Edge cases (decisions)

1. **Disabled intermediate stages → bypass ALLOWED.** This matches real runtime behavior: `run_pipeline` leaves `input_for_next_step` untouched when skipping (runner.py:534-541), and the NeuroFLOW adapter's `input_for_stage` walks back to the nearest prior output (neuroflow_adapter.py:73-83) — the same ancestor-rewiring idea as `resolve_disabled_stages` (graph.py:122-161). Validation therefore satisfies a requirement from the **union of all enabled upstream producers**, not strict adjacency. Caveat documented in the module: family side-channels (e.g. fs7 stats reading `$SD/surf/*`) are covered because their tokens are only produced by the correct family's stages, not by chain position.
2. **fs7 recon-style order.** Always evaluate against `stage_order_for_tools(selected_tools)` semantics. Concrete consequence: `fs7_recon_style_brain_extraction` without `fs7_recon_style_template_registration` is INVALID (no `talairach_xfm` producer upstream in either order).
3. **Empty selection.** All stages off → one violation ("No pipeline steps selected"), Start blocked. Running zero stages is meaningless.
4. **NeuroFLOW-supported Custom combos.** A Custom map identical to a preset's tools is inferred to that preset at request time (run_request.py:223-226) and becomes NeuroFLOW-eligible; both client and server validators short-circuit to valid in that case, so the two layers agree.
5. **CAT12 preset display filter** (`PipelinePage.tsx:224-228` hides all but 2 stages): validation always runs over the full stage order, so hidden-stage violations are still reported in the error block.
6. **Hidden tools** (`hidden_from_stage_select`, e.g. `fs8_reduced54_segmentation`, registry.py:1190) still get contract entries — presets and workspaces can reference them.

## Tests

### Backend — new `tests/test_tool_compat.py`

- **Preset sweep (parametrized):** every `PRESET_CONFIGS[mode]["tools"]` validates clean via `validate_tool_combo` — locks in "named presets valid by construction".
- **Known-good pairs:** `fastsurfer_reorientation + synthseg_freesurfer_fs8`; `mri_convert_fs7 + hdbet + synthseg_standalone`; `nibabel + ants_n4 + recon_all_fs7`; full fs8/fs7/fastsurfer surface chains.
- **Known-bad pairs (assert stage id in result + non-empty reason):**
  - `fs7_recon_style_stats` with only `fs7_recon_style_reorientation` upstream (cross-family stats hazard);
  - `fs8_reduced54_stats` atop a CAT12/FastSurfer-only selection;
  - `fastsurfer_stats_extraction` without `fastsurfer_surface_registration` (no `sphere_reg`);
  - `fs7_recon_style_brain_extraction` without `fs7_recon_style_template_registration`;
  - `fs8_reduced54_template_registration` without any `be_synthstrip_mgz` producer;
  - empty selection.
- **Cascade:** enabling `fastsurfer_surface_registration` but disabling `fastsurfer_wm_segmentation` reports violations on both the WM stage and every downstream stage that needed `WM_FILLED`.
- **Drift guards:** (a) every key of `enabled_tools_for_stage(stage)` for all stages appears in `TOOL_CONTRACTS`; (b) every `produces` token maps to ≥1 declared `output_files`/`output_globs` substring for that tool (spot-checked mapping table in the test) so contracts can't silently rot when builders change.
- **Request-validation tests** appended to `tests/test_app_backend_run_request.py` following existing patterns (tmp_path fake image/license as at lines ~55 and ~77, mode-inference case as at ~300): invalid Custom combo → `ok is False`, `errors` mentions the stage; same combo with `pipeline_mode="FreeSurfer 8 + Volume"` preset tools → passes; Custom tools exactly equal to a preset + `neuroflow_enabled=True` → passes (inference path).

### Frontend (`cd tauri-app && npm run test`, vitest + @testing-library/react)

- New `test/stageValidation.test.ts`: pure-function cases mirroring the backend ones against a fixture `AppMetadata` containing `tool_contracts` (reuse the `mockMetadata` shape from `test/PipelineStepsSection.test.tsx`); preset-map short-circuit; fs7-order case; empty-selection case.
- Extend `test/PipelineStepsSection.test.tsx`: pick two incompatible tools → red `Alert` (role="alert") visible with both stage labels, affected rows carry the `border-l-cursor-semantic-error` class; switch back to a named preset → alert disappears and highlights clear.
- Extend `test/AppHeader.test.tsx`: with a violating `formValues`, the start button (`#headerStartButton`) is disabled and labeled `Fix tool combination`.

### Verification commands

```bash
pytest tests/test_tool_compat.py tests/test_app_backend_run_request.py
cd tauri-app && npm run typecheck && npm run lint && npm run test
```

## Risks & Open Questions

- **Curation accuracy:** contracts encode what command builders *require*, but builders evolve; the drift-guard tests reduce (not eliminate) rot. Reviewer for the initial ~40-entry table should spot-check each `requires` claim against the builder source.
- **False positives on resume:** static validation ignores files already on disk from prior runs; a technically runnable resume could be blocked until the user fixes the combo. Accepted for now (message explains the missing producer); a "resume-aware" relaxation is future work.
- **Soft preferences vs hard requirements:** `recon_all_fs7` prefers pipeline intermediates but tolerates raw input; modeling it as `requires={}` may mask suboptimal-but-valid combos. Kept permissive intentionally.
- **Token granularity:** `TALAIRACH_XFM` treated as family-agnostic (standard LTA format); if FS8-vs-FS7 transform quirks surface at runtime, split the token rather than loosening the checker.
- **Alert dependency sequencing:** the red banner/highlight styling depends on `.agents/plans/unify-warning-alert-components.md` landing; coordinate ordering or vendor a minimal local error style if executed first (do not duplicate the shared component).
- **Resolved decision:** the error block DOES appear whenever `pipelineMode === 'Custom'`, including when StatsAtlasSection edits flip mode to Custom mid-session — any Custom-state map is validated uniformly. Named-preset short-circuits still apply via exact tool-map equality (step 3.0), so a user who flips to Custom without changing tools sees no error.
