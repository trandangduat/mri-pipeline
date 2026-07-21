from __future__ import annotations

import csv
from pathlib import Path
from dataclasses import dataclass

from .config import StatsVectorConfig, BatchImageResult
from .discovery import build_subject_id_map, _derive_subject_id
from .stats import _requested_vector_feature_map

@dataclass
class BatchReportContext:
    output_dir: str
    input_files: list[str]
    batch_results: list[BatchImageResult]
    subject_id_map: dict[str, str] | None
    dataset_root: str
    stats_vector_config: StatsVectorConfig
    running_input_file: str = ""

def result_run_status(result: BatchImageResult | None) -> str:
    if result is None:
        return "not_started"
    state = _load_pipeline_state(str(Path(result.subject_dir) / "logs"))
    status = str(state.get("status", "")).lower()
    if status == "success":
        return "completed"
    if status in {"failed", "paused", "running"}:
        return status
    return "completed" if result.success else "failed"

def _read_subject_vector_cells(subject_dir: str | Path) -> dict[str, str]:
    path = Path(subject_dir) / "stats" / "vectors" / "stats_vectors.csv"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            row = next(csv.DictReader(f), None)
    except (OSError, StopIteration):
        return {}
    if not row:
        return {}
    return {key: (value if value not in (None, "") else "NA") for key, value in row.items() if key != "subject"}

def _read_subject_feature_values(subject_dir: str | Path, vector_column: str, expected_count: int) -> list[str | float]:
    values: list[str | float] = ["NA"] * expected_count
    path = Path(subject_dir) / "stats" / "vectors" / f"{vector_column}_features.tsv"
    if not path.exists():
        return values
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                try:
                    idx = int(row.get("index", "0")) - 1
                except ValueError:
                    continue
                if 0 <= idx < expected_count:
                    values[idx] = _as_number(row.get("value"))
    except OSError:
        return values
    return values

def write_batch_reports(ctx: BatchReportContext) -> None:
    output_path = Path(ctx.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    result_by_input = {result.input_file: result for result in ctx.batch_results}
    derived_subject_ids = build_subject_id_map(ctx.input_files, ctx.dataset_root) if ctx.input_files else {}
    vector_features = _requested_vector_feature_map(ctx.stats_vector_config)

    for result in ctx.batch_results:
        for column in _read_subject_vector_cells(result.subject_dir):
            vector_features.setdefault(column, [])

    vector_columns = list(vector_features.keys())
    wide_columns = [f"{column}_{feature}" for column, features in vector_features.items() for feature in features]
    base_fields = ["mri_name", "file_path", "run_status"]
    vector_rows: list[dict[str, object]] = []
    wide_rows: list[dict[str, object]] = []

    for input_file in ctx.input_files:
        result = result_by_input.get(input_file)
        subject_id = result.subject_id if result else (
            (ctx.subject_id_map or {}).get(input_file)
            or (ctx.subject_id_map or {}).get(str(Path(input_file).resolve()))
            or derived_subject_ids.get(input_file)
            or _derive_subject_id(input_file, ctx.dataset_root)
        )
        subject_dir = result.subject_dir if result else str(output_path / subject_id)
        status = "running" if input_file == ctx.running_input_file else result_run_status(result)
        base = {
            "mri_name": Path(input_file).name,
            "file_path": input_file,
            "run_status": status,
        }

        vector_cells = _read_subject_vector_cells(subject_dir)
        vector_row = dict(base)
        wide_row = dict(base)
        for column in vector_columns:
            features = vector_features.get(column, [])
            vector_row[column] = vector_cells.get(column) or "NA"
            feature_values = _read_subject_feature_values(subject_dir, column, len(features)) if features else []
            for feature, value in zip(features, feature_values):
                wide_row[f"{column}_{feature}"] = value
        for column in wide_columns:
            wide_row.setdefault(column, "NA")
        vector_rows.append(vector_row)
        wide_rows.append(wide_row)

    with open(output_path / "stats_vectors_summary.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[*base_fields, *vector_columns], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(vector_rows)

    with open(output_path / "stats_vectors_wide.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[*base_fields, *wide_columns], extrasaction="ignore")
        writer.writeheader()
        writer.writerows(wide_rows)
