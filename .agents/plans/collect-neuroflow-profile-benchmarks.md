# Collect NeuroFLOW Profile Benchmark Data

## 1. Goal

Collect normal, non-NeuroFLOW benchmark runs so NeuroFLOW preset/profile YAML values can be calibrated from real measurements.

The target values are the cold-start scheduler priors in:

- `configs/neuroflow/profiles/*.yaml`

These values include:

- `runtime.point_ms`
- `runtime.upper_ms`
- `memory.peak_mib`
- `memory.reservation_mib`
- per-stage CPU configurations such as `cpu_1`, `cpu_2`, `cpu_4`, and optionally `cpu_5` if profiles support it
- GPU defaults for FastSurfer segmentation if GPU scheduling is supported later

The scheduler adapts during a NeuroFLOW job after observations are reported, but each new job currently starts from profile YAML unless resuming an existing `neuroflow_workspace.sqlite`. Therefore profile values must be safe cold-start estimates.

---

## 2. Benchmark Rules

Use normal pipeline runs only.

Required run settings:

- `neuroflow_enabled: false`
- same server for all runs
- same input MRI set for all runs
- use the server DICOM dataset at `/home/catcd1/ADNIDOD_T1`
- professor constraint: run benchmark jobs with `1-5` CPUs only
- do not start new `8` CPU benchmark jobs for primary calibration
- same `ram_percent`, preferably `90`
- same stats-vector selections intended for production use
- no resume, unless intentionally continuing a failed benchmark
- keep all output folders

If an executor has already started `8` CPU jobs from an older version of this plan:

- If the jobs just started, stop them and rerun with `threads: 5`.
- If the jobs are close to finishing, let them finish only if stopping would waste more time; mark the data as extra/non-primary.
- Do not use `8` CPU results as professor-compliant primary calibration data.
- Do not overwrite `cpu_8` profile values from these runs unless explicitly approved later.

Recommended sample size:

- Minimum: 3 subjects
- Better: 5-10 subjects
- Use the same subjects for every preset/thread run

Required artifacts per job:

- CLI command used for the run
- `<run-output-dir>/benchmark/batch_config.json`
- `<run-output-dir>/benchmark/benchmark_summary.json`
- `<run-output-dir>/benchmark/benchmark_steps.json`
- per-subject `<run-output-dir>/*/logs/pipeline_metrics.json` if deeper inspection is needed

Important CLI rule:

- Use a separate `--output-dir` for every preset/thread run.
- Do not reuse the same output directory across benchmark runs unless intentionally resuming that exact run.
- Recommended output path pattern:

```text
<benchmark-root>/<engine>_<feature-set>_threads-<n>
```

Example:

```text
/home/catcd1/neuroflow-profilebench/fs8_all_threads-4
```

Input dataset:

```text
/home/catcd1/ADNIDOD_T1
```

This dataset is nested, so keep `recursive: true` in worker job configs unless intentionally selecting a smaller explicit file list.

---

## 2.1 CLI Execution

Use the worker CLI with a generated `job_config.json`.

Do not use `python3 -m pipeline.cli` for this benchmark matrix. That CLI does not accept `pipeline_mode`, and its argparse choices cannot express preset-skipped stages as empty tool selections.

Run from the project root on the server:

```bash
python3 -m pipeline.job_worker --job-config "<job-dir>/job_config.json"
```

If the server uses a virtualenv, replace `python3` with the server virtualenv Python path.

Recommended directory layout:

```text
<benchmark-root>/
  jobs/
    <run-name>/job_config.json
  outputs/
    <run-name>/benchmark/benchmark_summary.json
    <run-name>/benchmark/benchmark_steps.json
```

Example run name:

```text
fs8_all_threads-4
```

### Job Config Template

Create one `job_config.json` per preset/thread run:

```json
{
  "mode": "folder",
  "input_dir": "/home/catcd1/ADNIDOD_T1",
  "output_dir": "<benchmark-root>/outputs/<run-name>",
  "effective_output_dir": "<benchmark-root>/outputs/<run-name>",
  "pipeline_mode": "FreeSurfer 8 + Volume + Cortical Thickness",
  "device": "cpu",
  "threads": 4,
  "ram_percent": 90,
  "recursive": true,
  "resume": false,
  "restart": false,
  "license_dir": "<license-dir-or-file>",
  "neuroflow_enabled": false,
  "stats_vector_config": {
    "atlases": {}
  },
  "export_config": {},
  "subject_id_map": {}
}
```

The worker will replace `selected_tools` from `PRESET_CONFIGS[pipeline_mode]`, so the config does not need explicit tool flags.

Use `recursive: false` only if the benchmark input directory contains MRI files directly and should not scan nested folders.

For `/home/catcd1/ADNIDOD_T1`, keep `recursive: true`.

### Stats Vector Config

For calibration, use the same stats-vector selections intended for production.

If only atlas selections are provided, current worker code normalizes preset `enabled_stats` from `pipeline_mode`.

Minimal preset-default config:

```json
{
  "atlases": {}
}
```

Explicit production-like example:

```json
{
  "atlases": {
    "cortical_thickness": ["aparc", "aparc_a2009s", "schaefer2018_400parcels_17networks"],
    "cortical_volume": ["freesurfer_aseg", "harvard_oxford_cortical", "brainnetome246"],
    "subcortical_volume": ["freesurfer_aseg", "harvard_oxford_subcortical"]
  }
}
```

### Generate Configs From CLI

Optional helper pattern for one run:

```bash
mkdir -p "<benchmark-root>/jobs/fs8_all_threads-4"
python3 - <<'PY'
import json
from pathlib import Path

benchmark_root = Path("<benchmark-root>")
run_name = "fs8_all_threads-4"
job_dir = benchmark_root / "jobs" / run_name
output_dir = benchmark_root / "outputs" / run_name
job_dir.mkdir(parents=True, exist_ok=True)
output_dir.mkdir(parents=True, exist_ok=True)

config = {
    "mode": "folder",
    "input_dir": "/home/catcd1/ADNIDOD_T1",
    "output_dir": str(output_dir),
    "effective_output_dir": str(output_dir),
    "pipeline_mode": "FreeSurfer 8 + Volume + Cortical Thickness",
    "device": "cpu",
    "threads": 4,
    "ram_percent": 90,
    "recursive": True,
    "resume": False,
    "restart": False,
    "license_dir": "<license-dir-or-file>",
    "neuroflow_enabled": False,
    "stats_vector_config": {"atlases": {}},
    "export_config": {},
    "subject_id_map": {},
}
(job_dir / "job_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
PY
python3 -m pipeline.job_worker --job-config "<benchmark-root>/jobs/fs8_all_threads-4/job_config.json"
```

---

## 3. Minimum Useful Matrix

Run these first if time/server capacity is limited.

| Preset | Threads |
| --- | --- |
| `FreeSurfer 7 + Volume + Cortical Thickness` | `1`, `2`, `4`, `5` |
| `FreeSurfer 8 + Volume + Cortical Thickness` | `1`, `2`, `4`, `5` |
| `FastSurfer + Volume + Cortical Thickness` | `1`, `2`, `4`, `5` |
| `FreeSurfer 7 + Volume` | `1`, `2`, `4`, `5` |
| `FreeSurfer 8 + Volume` | `1`, `2`, `4`, `5` |
| `FastSurfer + Volume` | `1`, `2`, `4`, `5` |

This matrix calibrates most active stages used by all and volume presets.

Cortical-only presets can initially reuse matching all-preset stage values if the same stage implementations are used. Run cortical-only jobs later to confirm stats and surface stages are not materially different.

---

## 3.1 Time-Saving Safe-Enough Strategy

Do not rerun the full matrix first. Existing server jobs already provide useful normal-run measurements for most engine/preset/thread combinations.

Known server resources from `server196`:

- 28 physical cores / 56 logical cores
- 251 GiB RAM
- about 156 GiB available RAM during inspection
- no GPU detected by `nvidia-smi`
- about 429 GiB free under `/home`

Existing useful benchmark workspaces:

- `/home/catcd1/mri-remote-jobs`
- `/home/catcd1/duat-jobs2`
- `/home/catcd1/pipeline-test-19082026`

Measured per-subject runtimes from existing jobs. `8` thread values are historical reference only and should not drive professor-compliant calibration:

| Preset | 1 thread | 2 threads | 4 threads | 8 threads |
| --- | ---: | ---: | ---: | ---: |
| `FreeSurfer 7 + Volume` | `4.27h` | `3.40h` | `2.86h` | `2.71h` |
| `FreeSurfer 7 + Volume + Cortical Thickness` | `6.14h` | `5.20h` | `4.64h` | `~4.50h` interpolated |
| `FreeSurfer 8 + Volume` | `0.53h` | `0.28h` | `0.17h` | `0.13h` |
| `FreeSurfer 8 + Volume + Cortical Thickness` | `3.30h` | `2.48h` | `2.03h` | `1.72h` |
| `FastSurfer + Volume` | `0.66h` | `0.39h` | `0.23h` | not needed |
| `FastSurfer + Volume + Cortical Thickness` | `3.17h` | `2.82h` | `2.20h` | `1.79h` |

Recommended approach:

1. First, aggregate existing measurements and update profiles where data is already adequate.
2. Run only the missing or high-value validation jobs.
3. Use limited parallelism to save time while keeping measurements safe enough for cold-start scheduler profiles.

High-value new runs:

| Run | Why | Expected time for 3 subjects |
| --- | --- | ---: |
| `FreeSurfer 7 + Volume + Cortical Thickness`, threads `5` | Highest allowed CPU count; validates FS7 surface-heavy behavior without using 8 CPUs | `~14h` |
| `FreeSurfer 8 + Volume + Cortical Thickness`, threads `5` | Highest allowed CPU count; reconfirm current code/data and profile mismatches | `~5.5-6h` |
| `FastSurfer + Volume + Cortical Thickness`, threads `5` | Highest allowed CPU count; reconfirm current code/data and profile mismatches | `~6-6.5h` |

These three jobs run serially in about `26h`. With safe-enough parallelism, they should finish in about `14-16h`, dominated by FS7.

### Parallelism Rules

Parallel runs are acceptable for safe/conservative cold-start profiles, but they are not ideal for clean isolated calibration. The measured runtime may include realistic contention.

Use these limits:

- Never set a single benchmark job above `threads: 5`.
- Keep total requested `threads` around `15-20`.
- Run at most `3-4` jobs at once.
- Run at most one `FreeSurfer 7 + Volume + Cortical Thickness` job at once.
- Prefer only one heavy all-preset `5` thread job at once if exact clean timing matters.
- Always use separate job dirs and output dirs.
- Do not run unrelated production jobs on the server during calibration if possible.

Safe-enough high-value parallel batch:

| Slot | Job |
| --- | --- |
| A | `FreeSurfer 7 + Volume + Cortical Thickness`, threads `5`, 3 subjects |
| B | `FreeSurfer 8 + Volume + Cortical Thickness`, threads `5`, 3 subjects |
| C | `FastSurfer + Volume + Cortical Thickness`, threads `5`, 3 subjects |

Total requested threads: `15`.

Expected wall time: `14-16h`.

This is safe enough on the inspected server because the machine has 28 physical cores and over 150 GiB available RAM. It also respects the `1-5` CPU benchmark constraint. It will not produce perfectly isolated runtimes, but it should produce conservative cold-start values, which is acceptable for NeuroFLOW scheduler priors.

If the server load rises above about `20` before starting, run only two jobs at once:

| Wave | Jobs |
| --- | --- |
| 1 | FS7 all `threads=5` + FS8 all `threads=5` |
| 2 | FastSurfer all `threads=5` |

Expected wall time: `20-22h`.

### When To Run More

After the high-value batch, only run additional jobs if one of these is true:

- A profile has no matching measured data for its exact thread count.
- Existing measurements are from failed/partial jobs.
- Existing measurements are from old code paths that no longer match current tool behavior.
- A stage has high outlier variance and profile bounds need stronger confidence.
- Cortical-only presets must be independently validated rather than inheriting all-preset surface-stage values.

Avoid rerunning volume-only FS8/FastSurfer configs initially; existing measurements are already sufficient and those stages are short.

---

## 4. Full Matrix

Run this when possible for complete calibration.

| Preset | Threads |
| --- | --- |
| `FreeSurfer 7 + Volume` | `1`, `2`, `4`, `5` |
| `FreeSurfer 7 + Cortical Thickness` | `1`, `2`, `4`, `5` |
| `FreeSurfer 7 + Volume + Cortical Thickness` | `1`, `2`, `4`, `5` |
| `FreeSurfer 8 + Volume` | `1`, `2`, `4`, `5` |
| `FreeSurfer 8 + Cortical Thickness` | `1`, `2`, `4`, `5` |
| `FreeSurfer 8 + Volume + Cortical Thickness` | `1`, `2`, `4`, `5` |
| `FastSurfer + Volume` | `1`, `2`, `4`, `5` |
| `FastSurfer + Cortical Thickness` | `1`, `2`, `4`, `5` |
| `FastSurfer + Volume + Cortical Thickness` | `1`, `2`, `4`, `5` |

Notes:

- Do not run `8` CPU jobs for primary calibration.
- If profile YAMLs only expose `cpu_1`, `cpu_2`, `cpu_4`, and `cpu_8`, update only `cpu_1`, `cpu_2`, and `cpu_4` from compliant benchmark data.
- Add or update `cpu_5` profile entries only if the profile schema and NeuroFLOW scheduler config support `cpu_5` for that stage.
- Leave `cpu_8` values unchanged/provisional unless there is explicit approval to use historical non-primary data.
- CAT12 is excluded because there is currently no CAT12 NeuroFLOW preset.

---

## 5. Job Naming

Use clear job/workspace labels if the UI supports labels.

Recommended convention:

```text
nf-profilebench_<engine>_<feature-set>_threads-<n>_<date>
```

Examples:

```text
nf-profilebench_fs8_all_threads-4_20260820
nf-profilebench_fastsurfer_volume_threads-2_20260820
nf-profilebench_fs7_all_threads-5_20260820
```

If labels are not supported, record the generated `job_YYYYMMDD_HHMMSS` IDs in a notes file.

---

## 6. Data Extraction

After jobs complete, collect a table from each `benchmark_summary.json` with these fields:

- job ID
- pipeline mode
- device
- threads
- stage
- tool
- images
- success
- failed
- `avg_run_sec`
- `max_run_sec`
- `median_run_sec`
- `avg_peak_ram_mb`
- `max_peak_ram_mb`
- `avg_peak_cpu_pct`
- `max_peak_cpu_pct`

Use `benchmark_steps.json` when per-subject outliers need inspection.

---

## 7. Calibration Method

For each preset/profile/stage/configuration:

1. Match normal pipeline stage names to NeuroFLOW stage IDs.

| Normal stage | NeuroFLOW stage ID |
| --- | --- |
| `reorientation` | `reorient_resize` |
| `brain_extraction` | `brain_extraction` |
| `segmentation` | `subcortical_segmentation` |
| `template_registration` | `template_registration` |
| `bias_correction` | `image_standardization` |
| `white_matter_segmentation` | `wm_segmentation` |
| `surface_reconstruction` | `surface_reconstruction` |
| `surface_registration` | `surface_registration` |
| `stats_extraction` | `statistics_atlas_mapping` |

2. Match thread count to profile `configuration_id`:

| Threads | Profile config |
| --- | --- |
| `1` | `cpu_1` |
| `2` | `cpu_2` |
| `4` | `cpu_4` |
| `5` | `cpu_5` only if supported; otherwise keep as external benchmark evidence and do not map to `cpu_8` |

3. Set runtime values conservatively:

- `point_ms`: use median or mean successful runtime for the matching stage/configuration
- `upper_ms`: use observed max runtime with safety margin
- recommended margin: `max_run_sec * 1000 * 1.20`, rounded up

4. Set memory values conservatively:

- `peak_mib`: use observed max peak RAM, rounded up
- `reservation_mib`: use observed max peak RAM with safety margin
- recommended margin: `max_peak_ram_mb * 1.25`, rounded up

5. Keep `sample_count` equal to number of successful stage observations used.

6. Set profile metadata from provisional to measured when enough data exists:

- `source`: `normal_pipeline_benchmark_<date>`
- `status`: `measured` or equivalent if accepted by schema
- top-level `metadata.validated`: `true` only after all required presets/configs are covered

---

## 8. Known Priorities

Existing remote normal-run checks already showed these areas need attention:

- FreeSurfer 8 volume/all `statistics_atlas_mapping`
- FreeSurfer 8 all `surface_reconstruction`
- FreeSurfer 8 all `wm_segmentation`
- FastSurfer all `statistics_atlas_mapping`
- FastSurfer all `surface_reconstruction`
- FastSurfer all `wm_segmentation`
- RAM reservations for FastSurfer `reorient_resize` and `template_registration`

FS7 still needs measurement from the other server workspace before FS7 profiles should be trusted.

---

## 9. Handoff Format

When benchmark jobs are done, provide:

```text
server: <host/user/port or workspace name>
workspace path: <remote workspace path>
input subject count: <n>
ram_percent: <n>
jobs:
- <job_id>: <pipeline mode>, threads=<n>
- <job_id>: <pipeline mode>, threads=<n>
```

The calibration agent should then inspect those jobs and update:

- `configs/neuroflow/profiles/freesurfer7_*_default.yaml`
- `configs/neuroflow/profiles/freesurfer8_*_default.yaml`
- `configs/neuroflow/profiles/fastsurfer_*_default.yaml`

Only update profiles with matching observed jobs. Do not invent measured values for unmeasured configurations.

---

## 10. Acceptance Criteria

- Every measured NeuroFLOW CPU profile has matching normal-run data for the same engine, feature set, stage, and thread count.
- `runtime.upper_ms` is at least the observed max runtime plus margin.
- `memory.reservation_mib` is at least the observed max peak RAM plus margin.
- `sample_count` reflects actual successful observations.
- Profile refs still validate across all NeuroFLOW presets.
- Targeted tests pass:

```bash
./.venv/bin/python -m pytest tests/test_neuroflow_adapter.py
```

---

## 11. Non-Goals

- Do not change NeuroFLOW scheduling policy.
- Do not add cross-job learning in this benchmark plan.
- Do not calibrate CAT12 until a CAT12 NeuroFLOW preset exists.
- Do not use NeuroFLOW runs as the primary calibration source for cold-start profiles.
