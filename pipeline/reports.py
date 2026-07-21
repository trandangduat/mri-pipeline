from __future__ import annotations

import os
import json
from datetime import datetime
from .config import StepResult
from .registry import STAGE_LABELS, tool_display_name
from .stats import _as_number
from .utils import _number_values, _avg, _median, _min, _max
from .hardware import _safe_batch_config, _host_info
from .config import PipelineConfig
import csv
from pathlib import Path
from dataclasses import dataclass

from .config import StatsVectorConfig, BatchImageResult
from .discovery import build_subject_id_map, _derive_subject_id
from .stats import _requested_vector_feature_map


BENCHMARK_STEP_FIELDS = ["subject_id", "mri_name", "dataset_root", "stage", "tool", "success", "duration_sec", "build_duration_sec", "peak_ram_bytes", "avg_ram_bytes", "p95_ram_bytes", "peak_cpu_pct", "avg_cpu_pct", "p95_cpu_pct", "error"]
BENCHMARK_SUMMARY_FIELDS = ["subject_id", "mri_name", "dataset_root", "success", "total_duration_sec", "total_build_duration_sec", "peak_ram_bytes", "peak_cpu_pct", "error"]

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
    path = Path(result.subject_dir) / "logs" / "pipeline_state.json"
    status = ""
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                status = str(data.get("status", "")).lower()
        except Exception:
            pass
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


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "n/a"
    if value < 1024:
        return f"{value} B"
    mib = value / (1024 ** 2)
    if mib < 1024:
        return f"{mib:.1f} MiB"
    return f"{mib / 1024:.2f} GiB"

def _append_step_log(logs_dir: str, tool_key: str, lines: list[str]) -> None:
    step_log = Path(logs_dir) / f"{tool_key}.log"
    try:
        with open(step_log, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))
            f.write("\n")
    except PermissionError:
        fallback = Path(logs_dir) / f"{tool_key}_pipeline.log"
        try:
            with open(fallback, "a", encoding="utf-8") as f:
                f.write(f"Could not append to {step_log}; file is not writable by the host user.\n")
                f.write("\n".join(lines))
                f.write("\n")
        except OSError as exc:
            print(f"WARNING: could not write step log for {tool_key}: {exc}", flush=True)
    except OSError as exc:
        print(f"WARNING: could not write step log for {tool_key}: {exc}", flush=True)

def _step_metrics_row(config: PipelineConfig, subject_dir: str, result: StepResult) -> dict:
    peak_ram_mb = (result.peak_ram_bytes / (1024 * 1024)) if result.peak_ram_bytes is not None else None
    avg_ram_mb = (result.avg_ram_bytes / (1024 * 1024)) if result.avg_ram_bytes is not None else None
    p95_ram_mb = (result.p95_ram_bytes / (1024 * 1024)) if result.p95_ram_bytes is not None else None
    return {
        "subject_id": config.subject_id,
        "input_file": os.path.abspath(config.input_file),
        "subject_dir": subject_dir,
        "stage": result.stage,
        "stage_label": STAGE_LABELS.get(result.stage, result.stage),
        "tool": result.tool,
        "tool_label": tool_display_name(result.tool) or result.tool,
        "threads": config.threads,
        "ram_percent": config.ram_percent,
        "device": config.device,
        "status": "OK" if result.success else "FAILED",
        "success": result.success,
        "run_sec": round(result.duration_sec, 3),
        "build_pull_sec": round(result.build_duration_sec, 3),
        "peak_ram_bytes": result.peak_ram_bytes,
        "peak_ram_mb": round(peak_ram_mb, 3) if peak_ram_mb is not None else None,
        "avg_ram_bytes": result.avg_ram_bytes,
        "avg_ram_mb": round(avg_ram_mb, 3) if avg_ram_mb is not None else None,
        "p95_ram_bytes": result.p95_ram_bytes,
        "p95_ram_mb": round(p95_ram_mb, 3) if p95_ram_mb is not None else None,
        "peak_cpu_pct": round(result.peak_cpu_pct, 3) if result.peak_cpu_pct is not None else None,
        "avg_cpu_pct": round(result.avg_cpu_pct, 3) if result.avg_cpu_pct is not None else None,
        "p95_cpu_pct": round(result.p95_cpu_pct, 3) if result.p95_cpu_pct is not None else None,
        "error": result.error,
    }

def _write_rows_tsv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

def _write_pipeline_metrics_log(logs_dir: str, config: PipelineConfig, subject_dir: str, results: list[StepResult], started_at: float, ended_at: float) -> str:
    metrics_log = Path(logs_dir) / "pipeline_metrics.log"
    total_run = sum(r.duration_sec for r in results)
    total_build = sum(r.build_duration_sec for r in results)
    status = "SUCCESS" if results and all(r.success for r in results) else "FAILED"
    rows = [_step_metrics_row(config, subject_dir, r) for r in results]
    with open(metrics_log, "w", encoding="utf-8") as f:
        f.write("MRI Pipeline Metrics\n")
        f.write(f"Input file: {os.path.abspath(config.input_file)}\n")
        f.write(f"Subject ID: {config.subject_id}\n")
        f.write(f"Subject output: {subject_dir}\n")
        f.write(f"Started: {datetime.fromtimestamp(started_at).isoformat(timespec='seconds')}\n")
        f.write(f"Finished: {datetime.fromtimestamp(ended_at).isoformat(timespec='seconds')}\n")
        f.write(f"Status: {status}\n")
        f.write(f"RAM percent: {config.ram_percent}%\n")
        f.write(f"Total wall time: {ended_at - started_at:.1f}s\n")
        f.write(f"Total run time: {total_run:.1f}s\n")
        f.write(f"Total build/pull time: {total_build:.1f}s\n\n")
        f.write("Stage\tTool\tStatus\tRun(s)\tBuild/Pull(s)\tPeak RAM\tMean RAM\tP95 RAM\tPeak CPU\tMean CPU\tP95 CPU\tError\n")
        for r in results:
            peak_cpu = f"{r.peak_cpu_pct:.0f}%" if r.peak_cpu_pct is not None else "n/a"
            avg_cpu = f"{r.avg_cpu_pct:.1f}%" if r.avg_cpu_pct is not None else "n/a"
            p95_cpu = f"{r.p95_cpu_pct:.1f}%" if r.p95_cpu_pct is not None else "n/a"
            f.write(f"{r.stage}\t{r.tool}\t{'OK' if r.success else 'FAILED'}\t{r.duration_sec:.1f}\t{r.build_duration_sec:.1f}\t{_format_bytes(r.peak_ram_bytes)}\t{_format_bytes(r.avg_ram_bytes)}\t{_format_bytes(r.p95_ram_bytes)}\t{peak_cpu}\t{avg_cpu}\t{p95_cpu}\t{r.error}\n")
    metrics_json = Path(logs_dir) / "pipeline_metrics.json"
    with open(metrics_json, "w", encoding="utf-8") as f:
        json.dump(
            {
                "input_file": os.path.abspath(config.input_file),
                "subject_id": config.subject_id,
                "subject_dir": subject_dir,
                "started_at": datetime.fromtimestamp(started_at).isoformat(timespec="seconds"),
                "finished_at": datetime.fromtimestamp(ended_at).isoformat(timespec="seconds"),
                "status": status,
                "total_wall_sec": round(ended_at - started_at, 3),
                "total_run_sec": round(total_run, 3),
                "total_build_pull_sec": round(total_build, 3),
                "steps": rows,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    _write_rows_tsv(Path(logs_dir) / "pipeline_steps.tsv", rows, BENCHMARK_STEP_FIELDS)
    return str(metrics_log)

def _write_batch_benchmark_reports(output_dir: str, batch_results: list[BatchImageResult], batch_config: dict | None = None) -> str:
    benchmark_dir = Path(output_dir) / "benchmark"
    safe_config = _safe_batch_config(batch_config)
    host_info = _host_info()
    threads = safe_config.get("threads")
    ram_percent = safe_config.get("ram_percent")
    device = safe_config.get("device")
    context = {
        "threads": threads,
        "ram_percent": ram_percent,
        "device": device,
        "hostname": host_info.get("hostname"),
        "cpu_vendor": host_info.get("cpu_vendor"),
        "cpu_model": host_info.get("cpu_model"),
        "logical_cores": host_info.get("logical_cores"),
        "physical_cores": host_info.get("physical_cores"),
        "total_ram_bytes": host_info.get("total_ram_bytes"),
    }
    rows: list[dict] = []
    for image_result in batch_results:
        if image_result.steps:
            config = PipelineConfig(
                input_file=image_result.input_file,
                output_dir=str(Path(image_result.subject_dir).parent),
                subject_id=image_result.subject_id,
                device=str(device or "cpu"),
                threads=int(threads or 4),
                ram_percent=int(ram_percent or 100),
            )
            for step in image_result.steps:
                row = _step_metrics_row(config, image_result.subject_dir, step)
                row.update(context)
                rows.append(row)
        else:
            row = {
                "subject_id": image_result.subject_id,
                "input_file": os.path.abspath(image_result.input_file),
                "subject_dir": image_result.subject_dir,
                "stage": "pipeline",
                "stage_label": "Pipeline",
                "tool": "pipeline",
                "tool_label": "Pipeline",
                "threads": threads,
                "ram_percent": ram_percent,
                "device": device,
                "status": "FAILED" if not image_result.success else "OK",
                "success": image_result.success,
                "run_sec": round(image_result.duration_sec, 3),
                "build_pull_sec": 0.0,
                "peak_ram_bytes": None,
                "peak_ram_mb": None,
                "avg_ram_bytes": None,
                "avg_ram_mb": None,
                "p95_ram_bytes": None,
                "p95_ram_mb": None,
                "peak_cpu_pct": None,
                "avg_cpu_pct": None,
                "p95_cpu_pct": None,
                "error": image_result.error,
            }
            row.update(context)
            rows.append(row)

    groups: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        groups.setdefault((str(row.get("stage", "")), str(row.get("tool", ""))), []).append(row)

    summary: list[dict] = []
    for (stage, tool), group in sorted(groups.items()):
        total = len(group)
        successes = sum(1 for row in group if bool(row.get("success")))
        run_values = _number_values(group, "run_sec")
        build_values = _number_values(group, "build_pull_sec")
        ram_values = _number_values(group, "peak_ram_mb")
        avg_ram_values = _number_values(group, "avg_ram_mb")
        p95_ram_values = _number_values(group, "p95_ram_mb")
        cpu_values = _number_values(group, "peak_cpu_pct")
        avg_cpu_values = _number_values(group, "avg_cpu_pct")
        p95_cpu_values = _number_values(group, "p95_cpu_pct")
        errors = sorted({str(row.get("error", "")) for row in group if row.get("error")})
        first = group[0]
        summary.append({
            "stage": stage,
            "stage_label": first.get("stage_label", stage),
            "tool": tool,
            "tool_label": first.get("tool_label", tool),
            "threads": first.get("threads"),
            "ram_percent": first.get("ram_percent"),
            "device": first.get("device"),
            "hostname": first.get("hostname"),
            "cpu_vendor": first.get("cpu_vendor"),
            "cpu_model": first.get("cpu_model"),
            "logical_cores": first.get("logical_cores"),
            "physical_cores": first.get("physical_cores"),
            "total_ram_bytes": first.get("total_ram_bytes"),
            "images": total,
            "success": successes,
            "failed": total - successes,
            "success_rate_pct": round((successes / total) * 100, 1) if total else 0.0,
            "avg_run_sec": _avg(run_values),
            "median_run_sec": _median(run_values),
            "min_run_sec": _min(run_values),
            "max_run_sec": _max(run_values),
            "avg_build_pull_sec": _avg(build_values),
            "avg_peak_ram_mb": _avg(ram_values),
            "max_peak_ram_mb": _max(ram_values),
            "avg_mean_ram_mb": _avg(avg_ram_values),
            "avg_p95_ram_mb": _avg(p95_ram_values),
            "max_p95_ram_mb": _max(p95_ram_values),
            "avg_peak_cpu_pct": _avg(cpu_values),
            "max_peak_cpu_pct": _max(cpu_values),
            "avg_mean_cpu_pct": _avg(avg_cpu_values),
            "avg_p95_cpu_pct": _avg(p95_cpu_values),
            "max_p95_cpu_pct": _max(p95_cpu_values),
            "errors": " | ".join(errors[:5]),
        })

    benchmark_dir.mkdir(parents=True, exist_ok=True)
    with open(benchmark_dir / "batch_config.json", "w", encoding="utf-8") as f:
        json.dump(safe_config, f, indent=2, ensure_ascii=False)
    with open(benchmark_dir / "host_info.json", "w", encoding="utf-8") as f:
        json.dump(host_info, f, indent=2, ensure_ascii=False)
    _write_rows_tsv(benchmark_dir / "benchmark_steps.tsv", rows, BENCHMARK_STEP_FIELDS)
    _write_rows_tsv(benchmark_dir / "benchmark_summary.tsv", summary, BENCHMARK_SUMMARY_FIELDS)
    with open(benchmark_dir / "benchmark_steps.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    with open(benchmark_dir / "benchmark_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return str(benchmark_dir)
