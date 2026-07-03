from __future__ import annotations

import logging
import os
import csv
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from .config import (
    BatchImageResult,
    EXPORT_OUTPUT_ITEMS,
    ExportConfig,
    STAT_VECTOR_DEFS,
    StatsVectorConfig,
    MetricsCallback,
    PipelineConfig,
    ProgressCallback,
    PROJECT_ROOT,
    STAGE_LABELS,
    STAGE_ORDER,
    StepResult,
    TOOL_DEFS,
    ToolContext,
    is_tool_enabled,
    tool_display_name,
)
from .docker_ops import _run_docker, ensure_image
from .utils import (
    _append_step_log,
    _check_output_workspace,
    _derive_subject_id,
    _describe_subject_files,
    _discover_mri_files,
    _duplicate_basenames,
    _find_existing_outputs,
    _find_output_file,
    _format_bytes,
    _load_pipeline_state,
    _new_pipeline_state,
    _organize_output,
    _repair_host_permissions,
    _resume_output_for_stage,
    _safe_container_name,
    _set_stage_state,
    _write_batch_benchmark_reports,
    _write_pipeline_metrics_log,
    _write_pipeline_state,
)


log = logging.getLogger(__name__)


def _volume_extension(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".nii.gz"):
        return ".nii.gz"
    return path.suffix.lower()


def _strip_volume_extension(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".nii.gz"):
        return name[:-7]
    return Path(name).stem


def _safe_export_stem(value: str, fallback: str) -> str:
    raw = (value or fallback).strip()
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in raw).strip("._-")
    return safe or fallback


def _export_item_id(stage: str, path: Path, index: int) -> str:
    name = path.name.lower()
    if stage == "brain_extraction" and ("mask" in name or name.endswith("_bet.nii.gz") or name.endswith("_bet.mgz")):
        return "brain_extraction.mask"
    if stage == "template_registration" and ("deformation" in name or "field" in name):
        return "template_registration.deformation"
    primary = f"{stage}.primary"
    return primary if index == 0 else f"{stage}.extra{index + 1}"


def _default_export_name(item_id: str, path: Path) -> str:
    item = EXPORT_OUTPUT_ITEMS.get(item_id)
    if item:
        return item["default_name"]
    return _strip_volume_extension(path.name)


def _copy_or_convert_export(src: Path, dst: Path, subject_dir: str) -> tuple[bool, str]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if _volume_extension(src) == _volume_extension(dst):
        shutil.copy2(src, dst)
        return True, ""

    ok, err, _build_time = ensure_image("mri_convert_fs7")
    if not ok:
        return False, f"mri_convert image not available: {err}"

    subject_path = Path(subject_dir).resolve()
    src_rel = src.resolve().relative_to(subject_path).as_posix()
    dst_rel = dst.resolve().relative_to(subject_path).as_posix()
    code, output, _peak_ram, _peak_cpu = _run_docker(
        image=TOOL_DEFS["mri_convert_fs7"]["image"],
        args=[],
        mounts=[(str(subject_path), "/subject")],
        command=["bash", "-c", f"mri_convert /subject/{src_rel} /subject/{dst_rel}"],
        container_name=_safe_container_name("mri", subject_path.name, "export"),
    )
    if code != 0:
        tail = " | ".join(output.strip().splitlines()[-3:]) if output.strip() else "no output"
        return False, f"mri_convert failed: {tail}"
    _repair_host_permissions(str(subject_path), TOOL_DEFS["mri_convert_fs7"]["image"])
    return True, ""


def _export_stage_outputs(subject_dir: str, stage: str, outputs_found: list[str], export_config: ExportConfig) -> tuple[list[str], str]:
    if not export_config.enabled:
        return [], ""
    fmt_default = export_config.default_format if export_config.default_format in ("same", ".nii.gz", ".mgz") else ".nii.gz"
    export_folder = _safe_export_stem(export_config.folder, "exports")
    export_dir = Path(subject_dir) / export_folder
    exported: list[str] = []
    errors: list[str] = []
    used_names: set[str] = set()

    volume_exts = (".nii", ".nii.gz", ".mgz", ".mgh")
    volume_outputs = [Path(p) for p in outputs_found if Path(p).name.lower().endswith(volume_exts)]
    for idx, src in enumerate(volume_outputs):
        if not src.exists():
            continue
        item_id = _export_item_id(stage, src, idx)
        default_name = _default_export_name(item_id, src)
        configured_name = _strip_volume_extension(export_config.names.get(item_id, default_name))
        stem = _safe_export_stem(configured_name, default_name)
        target_format = export_config.formats.get(item_id, fmt_default)
        if target_format not in ("same", ".nii.gz", ".mgz"):
            target_format = fmt_default
        ext = _volume_extension(src) if target_format == "same" else target_format
        filename = f"{stem}{ext}"
        if filename in used_names:
            filename = f"{stem}_{idx + 1}{ext}"
        used_names.add(filename)
        dst = export_dir / filename
        ok, err = _copy_or_convert_export(src, dst, subject_dir)
        if ok:
            exported.append(str(dst))
        else:
            errors.append(f"{src.name} -> {filename}: {err}")
    return exported, "; ".join(errors)


def _sanitize_vector_feature(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe.strip("_") or "feature"


def _stats_source_candidates(stats_dir: Path, stat: str, atlas: str = "") -> list[Path]:
    if stat == "subcortical_volume":
        return [stats_dir / "subcortical_volume.tsv"]
    if stat == "cortical_volume" and not atlas:
        return [stats_dir / "cortical_volume.tsv"]
    if not atlas:
        return []
    if stat == "cortical_volume":
        return [
            stats_dir / f"{atlas}_cortical_volume.tsv",
            stats_dir / f"cortical_volume_{atlas}.tsv",
            stats_dir / f"{atlas}_volume.tsv",
        ]
    if stat == "cortical_thickness":
        return [
            stats_dir / f"{atlas}_cortical_thickness.tsv",
            stats_dir / f"cortical_thickness_{atlas}.tsv",
            stats_dir / f"{atlas}_thickness.tsv",
        ]
    return []


VECTOR_SPECS = {
    "subcortical_volume": {
        "column": "subcortical_volume",
        "features": "subcortical_volume_feats.txt",
        "value": "volume_mm3",
    },
    "cortical_volume": {
        "column": "cortical_volume",
        "features": "cortical_volume_feats.txt",
        "value": "volume_mm3",
    },
    "aparc": {
        "column": "aparc_cortical_thickness",
        "features": "aparc_cortical_thickness_feats.txt",
        "value": "thickness_mm",
        "stats_stem": "aparc",
    },
    "aparc_a2009s": {
        "column": "aparc_a2009s_cortical_thickness",
        "features": "aparc_a2009s_cortical_thickness_feats.txt",
        "value": "thickness_mm",
        "stats_stem": "aparc.a2009s",
    },
    "schaefer2018": {
        "column": "schaefer200_7network",
        "features": "schaefer200_7network_feats.txt",
        "value": "thickness_mm",
        "stats_stem": "schaefer200_7network",
    },
    "kong": {
        "column": "200Parcels_Kong2022_17Networks",
        "features": "200Parcels_Kong2022_17Networks_feats.txt",
        "value": "thickness_mm",
        "stats_stem": "200Parcels_Kong2022_17Networks",
    },
    "yale": {
        "column": "YBA_696parcels",
        "features": "YBA_696parcels_feats.txt",
        "value": "thickness_mm",
        "stats_stem": "YBA_696parcels",
    },
}


def _norm_feature(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _load_vector_features(filename: str) -> list[str]:
    path = PROJECT_ROOT / "info" / filename
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines() if line.strip()]


def _as_number(value: str | float | int | None) -> float | str:
    if value is None:
        return "NA"
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().strip("'").strip('"')
    if not text or text.upper() in {"NA", "NAN", "NONE"}:
        return "NA"
    try:
        return float(text)
    except ValueError:
        return "NA"


def _vector_list_string(values: list[str | float | int | None]) -> str:
    return repr([_as_number(value) for value in values])


def _parse_freesurfer_stats_table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    headers: list[str] = []
    rows: list[dict[str, str]] = []
    if not path.exists():
        return headers, rows
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# ColHeaders"):
            headers = line.split()[2:]
            continue
        if line.startswith("#") or not headers:
            continue
        parts = line.split()
        if len(parts) >= len(headers):
            rows.append(dict(zip(headers, parts[: len(headers)])))
    return headers, rows


def _parse_freesurfer_measures(path: Path) -> dict[str, str]:
    measures: dict[str, str] = {}
    if not path.exists():
        return measures
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line.startswith("# Measure "):
            continue
        parts = [part.strip() for part in line[len("# Measure "):].split(",")]
        if len(parts) < 2:
            continue
        numeric = next((part for part in reversed(parts) if re.fullmatch(r"[-+]?\d+(\.\d+)?([eE][-+]?\d+)?", part)), "")
        if not numeric:
            continue
        for key in parts[:2]:
            if key:
                measures[key] = numeric
                measures[_norm_feature(key)] = numeric
    return measures


def _put_value(values: dict[str, str], key: str, value: str) -> None:
    if not key:
        return
    values[key] = value
    values[_norm_feature(key)] = value


def _read_subcortical_values(stats_dir: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in [stats_dir / "aseg.stats", stats_dir / "aparc.DKTatlas+aseg.deep.stats", stats_dir / "aseg+DKT.stats"]:
        _headers, rows = _parse_freesurfer_stats_table(path)
        for row in rows:
            name = row.get("StructName", "")
            volume = row.get("Volume_mm3") or row.get("Volume") or row.get("NVoxels")
            if name and volume:
                _put_value(values, name, volume)
        for key, value in _parse_freesurfer_measures(path).items():
            _put_value(values, key, value)

    tsv = stats_dir / "subcortical_volume.tsv"
    if tsv.exists():
        with open(tsv, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                _put_value(values, row.get("structure", ""), row.get("volume_mm3", ""))
    return values


def _read_cortical_volume_values(stats_dir: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for hemi in ("lh", "rh"):
        for path in [stats_dir / f"{hemi}.aparc.stats", stats_dir / f"{hemi}.aparc.DKTatlas.stats"]:
            _headers, rows = _parse_freesurfer_stats_table(path)
            for row in rows:
                name = row.get("StructName", "")
                volume = row.get("GrayVol") or row.get("Volume_mm3") or row.get("Volume")
                if name and volume:
                    _put_value(values, f"{hemi}_{name}", volume)

    tsv = stats_dir / "cortical_volume.tsv"
    if tsv.exists():
        with open(tsv, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                hemi = row.get("hemisphere", "")
                region = row.get("region", "")
                if hemi and region:
                    _put_value(values, f"{hemi}_{region}", row.get("volume_mm3", ""))
    return values


def _atlas_stats_candidates(stats_dir: Path, atlas: str, hemi: str) -> list[Path]:
    stem = str(VECTOR_SPECS[atlas].get("stats_stem", atlas))
    return [
        stats_dir / f"{hemi}.{stem}.stats",
        stats_dir / f"{hemi}_{stem}.stats",
        stats_dir / f"{hemi}.{stem.lower()}.stats",
        stats_dir / f"{hemi}_{stem.lower()}.stats",
    ]


def _read_atlas_thickness_values(stats_dir: Path, atlas: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for hemi in ("lh", "rh"):
        hemi_upper = hemi.upper()
        for path in _atlas_stats_candidates(stats_dir, atlas, hemi):
            _headers, rows = _parse_freesurfer_stats_table(path)
            for row in rows:
                name = row.get("StructName", "")
                thick = row.get("ThickAvg") or row.get("MeanThickness") or row.get("thickness_mm")
                if not name or not thick:
                    continue
                for key in (name, f"{hemi}_{name}", f"{hemi_upper}_{name}"):
                    _put_value(values, key, thick)
    return values


def _values_for_vector(stats_dir: Path, stat: str, atlas: str = "") -> dict[str, str]:
    if stat == "subcortical_volume":
        return _read_subcortical_values(stats_dir)
    if stat == "cortical_volume":
        return _read_cortical_volume_values(stats_dir)
    if stat == "cortical_thickness" and atlas:
        return _read_atlas_thickness_values(stats_dir, atlas)
    return {}


def _lookup_feature(values: dict[str, str], feature: str) -> str:
    if feature in values:
        return values[feature]
    norm = _norm_feature(feature)
    if norm in values:
        return values[norm]
    return "NA"


def _write_standard_vector(
    vectors_dir: Path,
    subject_id: str,
    column: str,
    features: list[str],
    values_by_feature: dict[str, str],
) -> tuple[list[str], str, int]:
    vector_values = [_lookup_feature(values_by_feature, feature) for feature in features]
    missing = sum(1 for value in vector_values if _as_number(value) == "NA")
    list_text = _vector_list_string(vector_values)
    vectors_dir.mkdir(parents=True, exist_ok=True)
    txt_path = vectors_dir / f"{column}.txt"
    txt_path.write_text(list_text + "\n", encoding="utf-8")
    feature_path = vectors_dir / f"{column}_features.tsv"
    with open(feature_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["index", "feature", "value"])
        for idx, (feature, value) in enumerate(zip(features, vector_values), start=1):
            writer.writerow([idx, feature, _as_number(value)])
    return [str(txt_path), str(feature_path)], list_text, missing


def _write_vector_from_long_tsv(src: Path, dst: Path, subject_id: str, value_column: str) -> tuple[bool, str]:
    delimiter = "\t" if src.suffix.lower() == ".tsv" else ","
    with open(src, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter=delimiter))
    if not rows:
        return False, f"empty stats file: {src.name}"

    columns = rows[0].keys()
    value_candidates = [value_column, "value", "mean", "thickness", "volume", "volume_mm3"]
    value_key = next((col for col in value_candidates if col in columns), "")
    if not value_key:
        return False, f"missing value column in {src.name}; expected one of {', '.join(value_candidates)}"

    feature_keys = [col for col in columns if col not in {"subject", "tool", value_key}]
    if not feature_keys:
        return False, f"missing feature columns in {src.name}"

    vector: dict[str, str] = {}
    for row in rows:
        parts = [row.get(key, "") for key in feature_keys if row.get(key, "")]
        feature = _sanitize_vector_feature("__".join(parts))
        if feature in vector:
            suffix = 2
            base = feature
            while f"{base}_{suffix}" in vector:
                suffix += 1
            feature = f"{base}_{suffix}"
        vector[feature] = row.get(value_key, "")

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["subject", *vector.keys()])
        writer.writerow([subject_id, *vector.values()])
    return True, ""


def _generate_stats_vectors(subject_dir: str, subject_id: str, config: StatsVectorConfig) -> tuple[list[str], list[str]]:
    generated: list[str] = []
    warnings: list[str] = []
    stats_dir = Path(subject_dir) / "stats"
    vectors_dir = stats_dir / "vectors"
    vector_columns: dict[str, str] = {}

    requested: list[tuple[str, str, str]] = []
    if config.enabled_stats.get("subcortical_volume"):
        requested.append(("subcortical_volume", "", "subcortical_volume"))
    if config.enabled_stats.get("cortical_volume"):
        requested.append(("cortical_volume", "", "cortical_volume"))
    if config.enabled_stats.get("cortical_thickness"):
        atlases = list(config.atlases.get("cortical_thickness", []))
        if not atlases:
            warnings.append("cortical_thickness: no atlas selected")
        for atlas in atlases:
            requested.append(("cortical_thickness", atlas, atlas))

    for stat, atlas, spec_key in requested:
        spec = VECTOR_SPECS.get(spec_key)
        if not spec:
            warnings.append(f"{stat}:{atlas or 'default'}: no vector spec")
            continue
        column = str(spec["column"])
        features = _load_vector_features(str(spec["features"]))
        if not features:
            warnings.append(f"{column}: missing feature list info/{spec['features']}")
            continue
        values = _values_for_vector(stats_dir, stat, atlas)
        paths, list_text, missing = _write_standard_vector(vectors_dir, subject_id, column, features, values)
        generated.extend(paths)
        vector_columns[column] = list_text
        if missing:
            warnings.append(f"{column}: {missing}/{len(features)} features missing; filled with NA")

    if vector_columns:
        csv_path = vectors_dir / "stats_vectors.csv"
        columns = ["subject", *vector_columns.keys()]
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerow([subject_id, *[vector_columns[col] for col in vector_columns]])
        generated.append(str(csv_path))
        manifest_path = vectors_dir / "stats_vectors_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            import json
            json.dump(
                {
                    "subject": subject_id,
                    "columns": list(vector_columns.keys()),
                    "feature_files": {key: str(value["features"]) for key, value in VECTOR_SPECS.items()},
                    "format": "CSV cells contain Python-list-style vectors aligned 1:1 with the corresponding *_feats.txt file.",
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        generated.append(str(manifest_path))
    return generated, warnings


def run_pipeline(
    config: PipelineConfig,
    on_progress: ProgressCallback | None = None,
    on_build_log: Callable[[str], None] | None = None,
    on_metrics: MetricsCallback | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[StepResult]:
    started_at = time.time()

    def progress(stage: str, status: str, pct: float, msg: str) -> None:
        if on_progress:
            on_progress(stage, status, pct, msg)
        log.info("[%s] %s (%.0f%%) %s", stage, status, pct * 100, msg)

    subject_dir = os.path.join(os.path.abspath(config.output_dir), config.subject_id)
    mri_dir = os.path.join(subject_dir, "mri")
    stats_dir = os.path.join(subject_dir, "stats")
    logs_dir = os.path.join(subject_dir, "logs")
    for d in (mri_dir, stats_dir, logs_dir):
        Path(d).mkdir(parents=True, exist_ok=True)

    workspace_ok, workspace_msg = _check_output_workspace(subject_dir, config.input_file)
    if not workspace_ok:
        progress("preflight", "failed", 0, workspace_msg)
        result = StepResult(stage="preflight", tool="output_workspace", success=False, duration_sec=0.0, error=workspace_msg)
        _write_pipeline_metrics_log(logs_dir, config, subject_dir, [result], started_at, time.time())
        return [result]
    log.info(workspace_msg)

    state = _load_pipeline_state(logs_dir) if config.resume else {}
    if not state:
        state = _new_pipeline_state(config, subject_dir)
    state["status"] = "running"
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    state["selected_tools"] = config.selected_tools
    _write_pipeline_state(logs_dir, state)

    license_mount: list[tuple[str, str]] = []
    if config.license_dir:
        lic_path = Path(config.license_dir).absolute()
        license_mount.append((str(lic_path), "/license/license.txt" if lic_path.is_file() else "/license"))

    results: list[StepResult] = []
    input_for_next_step: str | None = None
    total_stages = len(STAGE_ORDER)
    paused = False

    for stage_idx, stage in enumerate(STAGE_ORDER):
        tool_key = config.selected_tools.get(stage)
        if not tool_key:
            progress(stage, "success", (stage_idx + 1) / total_stages, f"Skipped {STAGE_LABELS[stage]}: no tool selected")
            continue
        if tool_key not in TOOL_DEFS:
            continue
        if not is_tool_enabled(tool_key):
            progress(stage, "success", (stage_idx + 1) / total_stages, f"Skipping disabled tool: {tool_display_name(tool_key)}")
            continue

        tool = TOOL_DEFS[tool_key]
        stage_pct = stage_idx / total_stages

        if config.resume:
            resumed_output, resumed_outputs = _resume_output_for_stage(
                subject_dir,
                state,
                stage,
                tool_key,
                tool["output_files"],
                tool.get("output_globs", []),
            )
            if resumed_output:
                input_for_next_step = resumed_output
                _set_stage_state(
                    logs_dir,
                    state,
                    stage,
                    tool_key,
                    "completed",
                    output_file=resumed_output,
                    output_files_found=resumed_outputs,
                    duration_sec=0.0,
                )
                results.append(StepResult(stage=stage, tool=tool_key, success=True, duration_sec=0.0, output_files=tool["output_files"], log_text="resumed from verified output files"))
                progress(stage, "success", (stage_idx + 1) / total_stages, f"Resume: verified outputs and skipped {STAGE_LABELS[stage]} with {tool_display_name(tool_key)}")
                continue

        progress(stage, "running", stage_pct, f"Starting {STAGE_LABELS[stage]} with {tool_display_name(tool_key)}")
        _set_stage_state(logs_dir, state, stage, tool_key, "running")

        ok, err, build_time = ensure_image(tool_key, on_progress=on_progress, on_build_log=on_build_log)
        if not ok:
            error = f"Image not available: {err}"
            _set_stage_state(logs_dir, state, stage, tool_key, "failed", error=error)
            results.append(StepResult(stage=stage, tool=tool_key, success=False, duration_sec=0, build_duration_sec=build_time, error=error))
            progress(stage, "failed", (stage_idx + 1) / total_stages, f"{STAGE_LABELS[stage]} FAILED: {err}")
            break

        if input_for_next_step is None:
            host_input_dir = os.path.dirname(os.path.abspath(config.input_file))
            input_path = f"/input/{os.path.basename(config.input_file)}"
            mounts: list[tuple[str, str]] = [(host_input_dir, "/input")]
        else:
            rel = os.path.relpath(input_for_next_step, subject_dir)
            input_path = f"/work/{rel}"
            mounts = []

        mounts.append((subject_dir, "/output"))
        mounts.append((subject_dir, "/work"))
        if tool["needs_license"] and license_mount:
            mounts.extend(license_mount)
        for rel, container in tool.get("extra_mounts", {}).items():
            host = os.path.join(subject_dir, "mri", rel)
            Path(host).mkdir(parents=True, exist_ok=True)
            mounts.append((host, container))
        norm_vol = Path(__file__).resolve().parent.parent / "normalize_volumes.py"
        if norm_vol.exists():
            mounts.append((str(norm_vol), "/app/normalize_volumes.py"))

        args = ["--input", input_path, "--output-dir", "/output", "--work-dir", "/work", "--subject-id", config.subject_id, "--threads", str(config.threads), "--device", config.device]
        command = tool.get("command")

        if "command_builder" in tool:
            ctx = ToolContext(
                input_path=input_path,
                subject_id=config.subject_id,
                threads=config.threads,
                device=config.device
            )
            actual_cmd = tool["command_builder"](ctx)
            command = [tool.get("shell", "bash"), "-c", actual_cmd]
            args = []

        t0 = time.time()
        container_name = _safe_container_name("mri", config.subject_id, tool_key)

        def _metrics_relay(cpu_pct, ram_bytes, elapsed, _cn=container_name, _stage=stage, _tool=tool_key):
            if on_metrics:
                on_metrics(_stage, _tool, cpu_pct, ram_bytes, elapsed, _cn)

        code, output, peak_ram, peak_cpu = _run_docker(
            image=tool["image"],
            args=args,
            mounts=mounts,
            gpus=(config.device == "gpu" or config.device == "cuda"),
            container_name=container_name,
            command=command,
            entrypoint=tool.get("entrypoint"),
            on_metrics=_metrics_relay if on_metrics else None,
        )
        duration = time.time() - t0
        _repair_host_permissions(subject_dir, tool["image"])
        _organize_output(subject_dir, preserve_dirs={_safe_export_stem(config.export_config.folder, "exports")})

        success = code == 0
        error = ""
        if not success:
            if not output.strip():
                try:
                    logs = [p for p in Path(logs_dir).glob("*.log") if p.name not in ("pipeline_metrics.log", "pipeline_state.json")]
                    if logs:
                        output = max(logs, key=lambda p: p.stat().st_mtime).read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
            tail = " | ".join(output.strip().splitlines()[-3:]) if output.strip() else "No output"
            error = f"exit code {code} ({tail})"
            lower_output = output.lower()
            if "error writing data" in lower_output or "no space left on device" in lower_output:
                try:
                    disk_hint = f"free disk at output: {_format_bytes(shutil.disk_usage(subject_dir).free)}"
                except OSError:
                    disk_hint = "could not check free disk at output"
                error += f". Write failure hint: check remote disk space and output permissions ({disk_hint})"
            if output.strip():
                print(f"\n--- DOCKER ERROR LOG ({tool_key}) ---", flush=True)
                for line in output.strip().splitlines()[-20:]:
                    print(line, flush=True)
                print("-" * 40, flush=True)

        if success:
            found = _find_output_file(subject_dir, tool["output_files"], tool.get("output_globs", []))
            if found:
                input_for_next_step = found
            else:
                success = False
                expected = ", ".join(tool["output_files"] + tool.get("output_globs", []))
                output_tail = " | ".join(output.strip().splitlines()[-8:]) if output.strip() else "no docker output captured"
                error = f"missing expected output files/patterns: {expected}. Files found: {_describe_subject_files(subject_dir)}. Docker output tail: {output_tail}"

        outputs_found = _find_existing_outputs(subject_dir, tool["output_files"], tool.get("output_globs", [])) if success else []
        exported_outputs: list[str] = []
        export_error = ""
        if success:
            exported_outputs, export_error = _export_stage_outputs(subject_dir, stage, outputs_found, config.export_config)
            if export_error:
                progress(stage, "running", (stage_idx + 1) / total_stages, f"Export warning: {export_error}")
        _set_stage_state(logs_dir, state, stage, tool_key, "completed" if success else "failed", output_file=input_for_next_step if success and input_for_next_step else "", output_files_found=outputs_found, error=error, duration_sec=duration)
        if success and (exported_outputs or export_error):
            state.setdefault("stages", {}).setdefault(stage, {})["exported_outputs"] = exported_outputs
            if export_error:
                state["stages"][stage]["export_error"] = export_error
            _write_pipeline_state(logs_dir, state)

        step_log_lines = [
            f"Stage: {stage}",
            f"Tool: {tool_display_name(tool_key)}",
            f"Duration: {duration:.1f}s",
            f"Build: {build_time:.1f}s",
            f"Peak RAM: {_format_bytes(peak_ram)}",
            f"Peak CPU: {peak_cpu:.0f}%" if peak_cpu is not None else "Peak CPU: n/a",
            f"Exit code: {code}",
        ]
        if exported_outputs:
            step_log_lines.append("Exported outputs: " + "; ".join(exported_outputs))
        if export_error:
            step_log_lines.append("Export warning: " + export_error)
        if output.strip():
            step_log_lines.append(f"\n--- Output ---\n{output[-3000:]}")
        _append_step_log(logs_dir, tool_key, step_log_lines)

        results.append(StepResult(stage=stage, tool=tool_key, success=success, duration_sec=duration, build_duration_sec=build_time, peak_ram_bytes=peak_ram, peak_cpu_pct=peak_cpu, log_text=output[-2000:] if output else "", output_files=tool["output_files"], error=error))

        if success:
            msg = f"{STAGE_LABELS[stage]} done in {duration:.0f}s"
            if build_time > 0:
                msg += f" (build: {build_time:.0f}s)"
            progress(stage, "success", (stage_idx + 1) / total_stages, msg)
            if should_stop and should_stop():
                paused = True
                state["status"] = "PAUSED"
                state["paused_after_stage"] = stage
                state["updated_at"] = datetime.now().isoformat(timespec="seconds")
                _write_pipeline_state(logs_dir, state)
                progress("pipeline", "paused", (stage_idx + 1) / total_stages, f"Paused after {STAGE_LABELS[stage]}. Resume will verify outputs and continue from the next incomplete stage.")
                break
        else:
            progress(stage, "failed", (stage_idx + 1) / total_stages, f"{STAGE_LABELS[stage]} FAILED: {error}")
            break

    if paused:
        state["status"] = "PAUSED"
    else:
        state["status"] = "SUCCESS" if results and all(r.success for r in results) else "FAILED"
    generated_vectors, vector_warnings = _generate_stats_vectors(subject_dir, config.subject_id, config.stats_vector_config)
    if generated_vectors or vector_warnings:
        state["stats_vectors"] = {
            "generated": generated_vectors,
            "warnings": vector_warnings,
        }
        if vector_warnings:
            _append_step_log(logs_dir, "stats_vectors", ["Stats vector warnings:", *vector_warnings])
        if generated_vectors:
            _append_step_log(logs_dir, "stats_vectors", ["Generated stats vectors:", *generated_vectors])
    state["finished_at"] = datetime.now().isoformat(timespec="seconds")
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_pipeline_state(logs_dir, state)
    _write_pipeline_metrics_log(logs_dir, config, subject_dir, results, started_at, time.time())
    return results


def _unique_subject_id(input_file: str, used_subject_ids: set[str], dataset_root: str = "", duplicate_basenames: set[str] | None = None) -> str:
    base = _derive_subject_id(input_file, dataset_root, duplicate_basenames)
    subject_id = base
    counter = 2
    while subject_id in used_subject_ids:
        subject_id = f"{base}_{counter}"
        counter += 1
    used_subject_ids.add(subject_id)
    return subject_id


def run_batch_pipeline(
    input_dir: str,
    output_dir: str,
    license_dir: str = "",
    device: str = "cpu",
    threads: int = 4,
    selected_tools: dict[str, str] | None = None,
    resume: bool = False,
    recursive: bool = True,
    input_files: list[str] | None = None,
    export_config: ExportConfig | None = None,
    stats_vector_config: StatsVectorConfig | None = None,
    subject_id_map: dict[str, str] | None = None,
    on_progress: ProgressCallback | None = None,
    on_build_log: Callable[[str], None] | None = None,
    on_image_done: Callable[[BatchImageResult, int, int], None] | None = None,
    on_image_start: Callable[[str, int, int], None] | None = None,
    on_metrics: MetricsCallback | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[BatchImageResult]:
    if input_files is None:
        input_files = _discover_mri_files(input_dir, recursive=recursive)
    used_subject_ids: set[str] = set()
    batch_results: list[BatchImageResult] = []
    total = len(input_files)
    dup_basenames = _duplicate_basenames(input_files)
    dataset_root = str(Path(input_dir).expanduser().resolve())

    for idx, input_file in enumerate(input_files, start=1):
        if should_stop and should_stop():
            break
        subject_id = (subject_id_map or {}).get(input_file) or (subject_id_map or {}).get(str(Path(input_file).resolve()))
        if subject_id:
            used_subject_ids.add(subject_id)
        else:
            subject_id = _unique_subject_id(input_file, used_subject_ids, dataset_root, dup_basenames)
        subject_dir = os.path.join(os.path.abspath(output_dir), subject_id)
        started_at = time.time()
        if on_image_start:
            on_image_start(input_file, idx, total)
        if on_progress:
            on_progress("batch", "running", (idx - 1) / total if total else 0, f"Starting image {idx}/{total}: {input_file}")

        try:
            config = PipelineConfig(input_file=input_file, output_dir=output_dir, subject_id=subject_id, license_dir=license_dir, device=device, threads=threads, resume=resume, export_config=export_config or ExportConfig(), stats_vector_config=stats_vector_config or StatsVectorConfig(), selected_tools=selected_tools or PipelineConfig(input_file, output_dir, subject_id).selected_tools)
            steps = run_pipeline(config, on_progress=on_progress, on_build_log=on_build_log, on_metrics=on_metrics, should_stop=should_stop)
            success = bool(steps) and all(step.success for step in steps)
            error = "" if success else "one or more pipeline steps failed"
        except Exception as exc:
            failed_duration = time.time() - started_at
            success = False
            error = str(exc)
            steps = [StepResult(stage="pipeline", tool="pipeline", success=False, duration_sec=failed_duration, error=error)]
            logs_dir = Path(subject_dir) / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            with open(logs_dir / "pipeline_metrics.log", "w", encoding="utf-8") as f:
                f.write("MRI Pipeline Metrics\n")
                f.write(f"Input file: {os.path.abspath(input_file)}\n")
                f.write(f"Subject ID: {subject_id}\n")
                f.write(f"Subject output: {subject_dir}\n")
                f.write(f"Started: {datetime.fromtimestamp(started_at).isoformat(timespec='seconds')}\n")
                f.write(f"Finished: {datetime.now().isoformat(timespec='seconds')}\n")
                f.write("Status: FAILED\n")
                f.write(f"Error: {error}\n")
            _write_pipeline_metrics_log(str(logs_dir), PipelineConfig(input_file=input_file, output_dir=output_dir, subject_id=subject_id, license_dir=license_dir, device=device, threads=threads, selected_tools=selected_tools or PipelineConfig(input_file, output_dir, subject_id).selected_tools), subject_dir, steps, started_at, time.time())

        image_result = BatchImageResult(input_file=input_file, subject_id=subject_id, subject_dir=subject_dir, success=success, duration_sec=time.time() - started_at, steps=steps, error=error)
        batch_results.append(image_result)
        if on_image_done:
            on_image_done(image_result, idx, total)
    if batch_results:
        _write_batch_benchmark_reports(output_dir, batch_results)
    return batch_results
