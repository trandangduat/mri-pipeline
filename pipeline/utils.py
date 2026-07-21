from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import statistics
import csv
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .config import PipelineConfig, StepResult, BatchImageResult
from .registry import STAGE_LABELS, tool_display_name

VOLUME_FILE_EXTENSIONS = (".nii.gz", ".nii", ".mgz", ".mgh")
DICOM_FILE_EXTENSIONS = (".dcm", ".dicom", ".ima")
MRI_FILE_EXTENSIONS = (*VOLUME_FILE_EXTENSIONS, *DICOM_FILE_EXTENSIONS)

def _file_stem(filename: str) -> str:
    name = filename
    for ext in MRI_FILE_EXTENSIONS:
        if name.lower().endswith(ext):
            return name[: -len(ext)]
    return Path(filename).stem

_GENERIC_BASENAMES = frozenset({
    "001", "002", "003", "image", "images", "scan", "brain", "t1", "t1w", "t2", "flair", "data",
})

def _safe_container_name(*parts: str) -> str:
    raw = "-".join(part for part in parts if part)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-_.")
    if not safe:
        safe = "mri-pipeline"
    if not safe[0].isalnum():
        safe = f"mri-{safe}"
    return f"{safe[:80]}-{uuid4().hex[:8]}"

def _parse_docker_memory(value: str) -> int | None:
    first = value.split("/", 1)[0].strip()
    match = re.match(r"^([0-9.]+)\s*([A-Za-z]+)$", first)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2).lower()
    multipliers = {
        "b": 1, "kb": 1000, "mb": 1000 ** 2, "gb": 1000 ** 3, "tb": 1000 ** 4,
        "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "tib": 1024 ** 4,
    }
    multiplier = multipliers.get(unit)
    return int(number * multiplier) if multiplier is not None else None

def _parse_docker_stats_line(line: str) -> tuple[float | None, int | None]:
    parts = line.split("|", 1)
    cpu: float | None = None
    if parts:
        raw_cpu = parts[0].strip().rstrip("%").strip()
        try:
            cpu = float(raw_cpu)
        except ValueError:
            cpu = None
    ram = _parse_docker_memory(parts[1]) if len(parts) > 1 else None
    return cpu, ram

BENCHMARK_STEP_FIELDS = [
    "subject_id",
    "input_file",
    "subject_dir",
    "stage",
    "stage_label",
    "tool",
    "tool_label",
    "threads",
    "ram_percent",
    "device",
    "hostname",
    "cpu_vendor",
    "cpu_model",
    "logical_cores",
    "physical_cores",
    "total_ram_bytes",
    "status",
    "success",
    "run_sec",
    "build_pull_sec",
    "peak_ram_bytes",
    "peak_ram_mb",
    "avg_ram_bytes",
    "avg_ram_mb",
    "p95_ram_bytes",
    "p95_ram_mb",
    "peak_cpu_pct",
    "avg_cpu_pct",
    "p95_cpu_pct",
    "error",
]

def _number_values(rows: list[dict], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(key)
        if value is None or value == "":
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return values

def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None

def _median(values: list[float]) -> float | None:
    return round(float(statistics.median(values)), 3) if values else None

def _min(values: list[float]) -> float | None:
    return round(min(values), 3) if values else None

def _max(values: list[float]) -> float | None:
    return round(max(values), 3) if values else None

BENCHMARK_SUMMARY_FIELDS = [
    "stage",
    "stage_label",
    "tool",
    "tool_label",
    "threads",
    "ram_percent",
    "device",
    "hostname",
    "cpu_vendor",
    "cpu_model",
    "logical_cores",
    "physical_cores",
    "total_ram_bytes",
    "images",
    "success",
    "failed",
    "success_rate_pct",
    "avg_run_sec",
    "median_run_sec",
    "min_run_sec",
    "max_run_sec",
    "avg_build_pull_sec",
    "avg_peak_ram_mb",
    "max_peak_ram_mb",
    "avg_mean_ram_mb",
    "avg_p95_ram_mb",
    "max_p95_ram_mb",
    "avg_peak_cpu_pct",
    "max_peak_cpu_pct",
    "avg_mean_cpu_pct",
    "avg_p95_cpu_pct",
    "max_p95_cpu_pct",
    "errors",
]

