# Fix NeuroFLOW DAG and Stats Vector Robustness

## 1. Goal

Fix the remaining issues found after `.agents/plans/complete-neuroflow-scheduler-integration.md` was implemented.

The confirmed issues are:

1. `configs/neuroflow/presets/freesurfer7_volumetrics.yaml` skips `template_registration`, but the normal `FreeSurfer 7 + Volume` preset runs it before `brain_extraction`.
2. `configs/neuroflow/profiles/freesurfer7_volumetrics_default.yaml` has no profile entries for `template_registration`, because the preset currently omits that stage.
3. `freesurfer7_all.yaml` and `freesurfer7_cortical_thickness.yaml` have metadata `active_pipeline_stages` in non-FS7 order, even though their actual stage list and dependencies are correct.
4. Stats-vector generation can still fail if a raw worker/job config reaches the worker with atlas selections but no `stats_vector_config.enabled_stats`.

Do not redesign the NeuroFLOW scheduler. This plan is only for preset correctness and stats-vector robustness.

---

## 2. Evidence

### FS7 Volume Normal Preset

`pipeline/presets.py` defines `FreeSurfer 7 + Volume` with active stages:

```text
reorientation -> template_registration -> brain_extraction -> segmentation -> stats_extraction
```

The preset skips:

```text
bias_correction
white_matter_segmentation
surface_reconstruction
surface_registration
```

It does not skip `template_registration`.

### FS7 Volume NeuroFLOW Preset

`configs/neuroflow/presets/freesurfer7_volumetrics.yaml` currently has:

```text
reorientation -> brain_extraction -> segmentation -> stats_extraction
```

and lists `template_registration` in `skipped_pipeline_stages`.

This conflicts with the command behavior in `pipeline/registry.py`:

- `fs7_recon_style_template_registration` creates `transforms/talairach.xfm`.
- `fs7_recon_style_brain_extraction` uses `transforms/talairach.xfm`.

### Stats Vector Issue

Observed remote job `job_20260820_124243` had:

```json
"stats_vector_config": {
  "atlases": {...}
}
```

but no `enabled_stats`.

`StatsVectorConfig.from_dict()` defaults missing `enabled_stats` to all false. Result: `stats_vectors_summary.csv` contained only:

```csv
mri_name,file_path,run_status
```

The raw stats and atlas mapping files existed, so the DAG did not cause that missing-vector issue.

---

## 3. Implementation Steps

### Step 1: Fix `freesurfer7_volumetrics.yaml`

File:

- `configs/neuroflow/presets/freesurfer7_volumetrics.yaml`

Required changes:

- Add `template_registration` to `metadata.active_pipeline_stages` after `reorientation`.
- Remove `template_registration` from `metadata.skipped_pipeline_stages`.
- Insert a new DAG stage after `reorient_resize`:

```yaml
- id: template_registration
  display_name: Template Registration
  operation: template_registration
  implementation: fs7_recon_style_template_registration
  implementation_version: 7.4.1
  enabled: true
  depends_on:
  - reorient_resize
  execution_configurations:
  - id: cpu_1
    mode: cpu
    cpu_threads: 1
    profile_ref: freesurfer7_volumetrics_default_template_registration_cpu_1
    metadata:
      executor: cpu
      pipeline_stage: template_registration
      pipeline_tool_key: fs7_recon_style_template_registration
      docker_image: mkdayyyy/mri-fs7-all:latest
      provisional: true
  - id: cpu_2
    mode: cpu
    cpu_threads: 2
    profile_ref: freesurfer7_volumetrics_default_template_registration_cpu_2
    metadata:
      executor: cpu
      pipeline_stage: template_registration
      pipeline_tool_key: fs7_recon_style_template_registration
      docker_image: mkdayyyy/mri-fs7-all:latest
      provisional: true
  - id: cpu_4
    mode: cpu
    cpu_threads: 4
    profile_ref: freesurfer7_volumetrics_default_template_registration_cpu_4
    metadata:
      executor: cpu
      pipeline_stage: template_registration
      pipeline_tool_key: fs7_recon_style_template_registration
      docker_image: mkdayyyy/mri-fs7-all:latest
      provisional: true
  metadata:
    pipeline_stage: template_registration
    pipeline_tool_key: fs7_recon_style_template_registration
    pipeline_stage_order: 2
    docker_image: mkdayyyy/mri-fs7-all:latest
    needs_license: true
    output_files: []
    output_globs:
    - freesurfer/*/mri/transforms/talairach.xfm
    - freesurfer/*/mri/transforms/talairach.xfm.lta
    - freesurfer/*/mri/orig_nu.mgz
```

- Change `brain_extraction.depends_on` from:

```yaml
depends_on:
- reorient_resize
```

to:

```yaml
depends_on:
- template_registration
```

- Update `pipeline_stage_order` metadata so the stage order is:

```text
reorient_resize: 1
template_registration: 2
brain_extraction: 3
subcortical_segmentation: 4
statistics_atlas_mapping: 5
```

Keep the same image and provisional metadata style as existing FS7 configs.

---

### Step 2: Add FS7 Volume Template Registration Profiles

File:

- `configs/neuroflow/profiles/freesurfer7_volumetrics_default.yaml`

Add profile entries for:

```text
freesurfer7_volumetrics_default_template_registration_cpu_1
freesurfer7_volumetrics_default_template_registration_cpu_2
freesurfer7_volumetrics_default_template_registration_cpu_4
```

Use the corresponding values from `configs/neuroflow/profiles/freesurfer7_all_default.yaml` or `configs/neuroflow/profiles/freesurfer7_cortical_thickness_default.yaml` for the same stage/configuration if available.

Required profile fields:

```yaml
pipeline_id: freesurfer7_volumetrics
implementation: fs7_recon_style_template_registration
implementation_version: 7.4.1
stage: template_registration
configuration_id: cpu_1/cpu_2/cpu_4
mode: cpu
cpu_threads: 1/2/4
```

Keep `source`, `status`, `sample_count`, `runtime`, and `memory` consistent with the copied FS7 profile style.

---

### Step 3: Clean FS7 Metadata Active Stage Order

Files:

- `configs/neuroflow/presets/freesurfer7_all.yaml`
- `configs/neuroflow/presets/freesurfer7_cortical_thickness.yaml`

Their actual YAML stage list and dependencies are already correct.

Only update `metadata.active_pipeline_stages` to match the normal FS7 order:

```text
reorientation
template_registration
brain_extraction
segmentation
bias_correction
white_matter_segmentation
surface_reconstruction
surface_registration
stats_extraction
```

This is a metadata cleanup. It should not change runtime scheduling if NeuroFLOW uses the `stages:` section as the real DAG.

---

### Step 4: Add Defensive Stats Vector Normalization

Current request preparation in `app_backend/run_request.py` already normalizes preset stats vectors when the request passes through `prepare_run_request()`.

However, workers can still receive raw `job_config.json`-style payloads. Add a defensive normalization helper so missing `enabled_stats` cannot silently produce empty vector CSVs for preset runs.

Preferred implementation:

1. Add a small helper in `app_backend/run_request.py` or a shared backend module:

```python
def normalize_stats_vector_config_for_pipeline_mode(pipeline_mode: str, stats_vector_config: dict[str, object]) -> dict[str, JsonValue]:
    ...
```

2. Reuse the existing `_stats_vector_config()` logic instead of duplicating it if possible.

3. Use it anywhere a worker consumes raw job config before creating `StatsVectorConfig`:

- `pipeline/job_worker.py`
- `pipeline/neuroflow_adapter.py` if it can be called independently with raw `req`

Expected behavior:

- If `pipeline_mode` is a known preset and `stats_vector_config.enabled_stats` is missing, infer it from `PRESET_CONFIGS[pipeline_mode]["stats"]`.
- Preserve user-selected atlas lists.
- Filter invalid atlas names the same way current request prep does.
- If an enabled stat has no selected atlas, use preset default atlases.
- For `Custom`, do not infer preset stats. Preserve existing custom config.

Important:

- Do not make `StatsVectorConfig.from_dict()` infer preset stats. It does not know `pipeline_mode`.
- Keep inference at request/job-config normalization boundaries.

Tests to add:

- A unit test where a raw preset request has only:

```json
"stats_vector_config": {"atlases": {...}}
```

and normalization adds correct `enabled_stats`.

- A NeuroFLOW adapter or job-worker test where raw `req` with missing `enabled_stats` still results in `StatsGenerator` receiving enabled preset stats.

---

### Step 5: Add DAG Regression Tests

File:

- `tests/test_neuroflow_adapter.py`

Add tests that parse NeuroFLOW preset YAMLs and compare them to normal preset definitions.

Recommended tests:

1. `test_neuroflow_presets_match_normal_active_stages()`

- For every NeuroFLOW YAML preset, read `metadata.pipeline_mode`.
- Get normal tools from `PRESET_CONFIGS[pipeline_mode]["tools"]`.
- Get normal stage order from `stage_order_for_tools(tools)`.
- Compute active normal stages where `tools[stage]` is truthy.
- Map NeuroFLOW stage IDs back to local stage IDs.
- Assert the YAML `stages:` list matches active normal stages.
- Assert `metadata.skipped_pipeline_stages` matches skipped normal stages.

2. `test_freesurfer7_volume_neuroflow_runs_template_registration_before_brain_extraction()`

- Read `freesurfer7_volumetrics.yaml`.
- Assert `template_registration` exists.
- Assert `brain_extraction.depends_on == ["template_registration"]` or at least includes it.
- Assert `template_registration.depends_on` includes `reorient_resize`.

3. `test_neuroflow_profiles_cover_every_preset_stage()`

- For each preset, read `metadata.default_profile_set`.
- Load the profile file.
- Assert every preset stage has at least one profile entry with matching `stage`.

Optional:

- Add a semantic reachability test for key edges by engine/feature set.
- Keep it simple enough to avoid false positives.

---

## 4. Verification Commands

Use the project virtualenv for Python:

```bash
./.venv/bin/python -m pytest tests/test_neuroflow_adapter.py tests/test_app_backend_run_request.py
```

If touching worker stats normalization:

```bash
./.venv/bin/python -m pytest tests/test_neuroflow_adapter.py tests/test_app_backend_run_request.py tests/test_runner_executor_integration.py
```

If no frontend code is touched, frontend tests are not required for this plan.

---

## 5. Acceptance Criteria

- `freesurfer7_volumetrics.yaml` includes `template_registration`.
- FS7 volume NeuroFLOW DAG has `reorient_resize -> template_registration -> brain_extraction -> subcortical_segmentation -> statistics_atlas_mapping`.
- `freesurfer7_volumetrics_default.yaml` has profile entries for `template_registration`.
- FS7 all/cortical metadata active stage order matches normal FS7 order.
- Every NeuroFLOW preset stage has profile coverage.
- Raw preset job configs missing `stats_vector_config.enabled_stats` are normalized before `StatsVectorConfig.from_dict()` is used.
- A raw preset config with only atlas selections can still generate requested vector columns.
- Targeted tests pass.

---

## 6. Non-Goals

- Do not change NeuroFLOW scheduling policy.
- Do not change FS8 or FastSurfer DAGs unless tests reveal a concrete issue.
- Do not modify CAT12 behavior.
- Do not make `Custom` mode use NeuroFLOW.
- Do not rewrite stats vector generation internals.
