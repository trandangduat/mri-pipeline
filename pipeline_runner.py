"""Real MRI pipeline runner — executes Docker containers in sequence.

Output structure per subject:
    outputs/<subject_id>/
        mri/        — NIfTI/MGZ volumes
        stats/      — TSV/CSV statistics
        logs/       — tool logs + timing

Pipeline stages:
  1. Reorientation:      mri-mri-convert OR mri-nibabel-utils
  2. Brain Extraction:   mri-synthstrip OR mri-hdbet
  3. Segmentation:       mri-synthseg-freesurfer OR mri-synthseg-standalone OR mri-fastsurfervinn
  4. Bias Correction:    mri-ants
  5. Template Registration: mri-synthmorph
  6. White Matter Segmentation: mri-wm-seg
  7. Stats Extraction:   mri-freesurfer-stats (from FastSurfer/SynthSeg outputs)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOL_DEFS: dict[str, dict] = {
    "mri_convert_fs8": {
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "reorientation",
        "needs_license": True,
        "command": ["python3", "/app/run_convert.py"],
        "output_files": ["01_reoriented.nii.gz"],
    },
    "mri_convert_fs7": {
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "reorientation",
        "needs_license": True,
        "command": ["python3", "/app/run_convert.py"],
        "output_files": ["01_reoriented.nii.gz"],
    },
    "nibabel": {
        "image": "duattran05/mri-nibabel-utils:latest",
        "dockerfile": "docker/nibabel-utils",
        "stage": "reorientation",
        "needs_license": False,
        "output_files": ["01_nibabel_reoriented.nii.gz"],
    },
    "synthstrip_fs8": {
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "brain_extraction",
        "needs_license": True,
        "command": ["python3", "/app/run_synthstrip.py"],
        "output_files": ["02_synthstrip_brain.nii.gz", "02_synthstrip_brain_mask.nii.gz"],
    },
    "synthstrip_fs7": {
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "brain_extraction",
        "needs_license": True,
        "command": ["python3", "/app/run_synthstrip.py"],
        "output_files": ["02_synthstrip_brain.nii.gz", "02_synthstrip_brain_mask.nii.gz"],
    },
    "hdbet": {
        "image": "duattran05/mri-hdbet:latest",
        "dockerfile": "docker/hdbet",
        "stage": "brain_extraction",
        "needs_license": False,
        "output_files": ["02_hdbet_brain.nii.gz", "02_hdbet_brain_bet.nii.gz"],
        "extra_mounts": {"hdbet_weights": "/root/.cache/torch/hub/checkpoints"},
    },
    "synthseg_freesurfer_fs8": {
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "segmentation",
        "needs_license": True,
        "command": ["python3", "/app/run_synthseg.py"],
        "output_files": ["03_freesurfer_synthseg_segmentation.nii.gz"],
    },
    "synthseg_freesurfer_fs7": {
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "segmentation",
        "needs_license": True,
        "command": ["python3", "/app/run_synthseg.py"],
        "output_files": ["03_freesurfer_synthseg_segmentation.nii.gz"],
    },
    "synthseg_standalone": {
        "image": "duattran05/mri-synthseg-standalone:latest",
        "dockerfile": "docker/synthseg-standalone",
        "stage": "segmentation",
        "needs_license": False,
        "output_files": ["03_synthseg_standalone_segmentation.nii.gz"],
    },
    "fastsurfervinn": {
        "image": "duattran05/mri-fastsurfervinn:latest",
        "dockerfile": "docker/fastsurfervinn",
        "stage": "segmentation",
        "needs_license": True,
        "output_files": ["03_fastsurfervinn_segmentation.nii.gz", "aparc.DKTatlas+aseg.deep.mgz"],
    },
    "ants_n4": {
        "image": "duattran05/mri-ants:latest",
        "dockerfile": "docker/ants",
        "stage": "bias_correction",
        "needs_license": False,
        "output_files": ["05_standardized.nii.gz"],
    },
    "synthmorph_fs8": {
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "template_registration",
        "needs_license": True,
        "command": ["python3", "/app/run_synthmorph.py"],
        "output_files": ["04_warped.nii.gz", "04_deformation_field.nii.gz"],
    },
    "wm_seg": {
        "image": "magicianfrog/mri-wm-seg:latest",
        "dockerfile": "docker/wm-segmentation",
        "stage": "white_matter_segmentation",
        "needs_license": True,
        "output_files": ["06_wm_mask.nii.gz"],
    },
    "freesurfer_stats_fs8": {
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "stats_extraction",
        "needs_license": True,
        "output_files": [
            "subcortical_volume.tsv",
            "lh_aparc_volume.tsv",
            "rh_aparc_volume.tsv",
            "lh_aparc.DKTatlas_volume.tsv",
            "rh_aparc.DKTatlas_volume.tsv",
        ],
    },
}

STAGE_ORDER = [
    "reorientation",
    "brain_extraction",
    "segmentation",
    "bias_correction",
    "template_registration",
    "white_matter_segmentation",
    "stats_extraction",
]

STAGE_LABELS = {
    "reorientation": "Reorientation & Resampling",
    "brain_extraction": "Brain Extraction",
    "segmentation": "Subcortical Segmentation",
    "bias_correction": "Bias Field Correction (N4)",
    "template_registration": "Template Registration (SynthMorph)",
    "white_matter_segmentation": "White Matter Segmentation",
    "stats_extraction": "FreeSurfer Stats Extraction",
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class PipelineConfig:
    input_file: str
    output_dir: str          # base dir, e.g. "outputs"
    subject_id: str          # e.g. "sub-002"
    license_dir: str = ""
    device: str = "cpu"
    threads: int = 4
    resume: bool = False
    selected_tools: dict[str, str] = field(default_factory=lambda: {
        "reorientation": "mri_convert_fs7",
        "brain_extraction": "synthstrip_fs7",
        "segmentation": "synthseg_freesurfer_fs7",
        "bias_correction": "ants_n4",
        "template_registration": "synthmorph_fs8",
        "white_matter_segmentation": "wm_seg",
        "stats_extraction": "freesurfer_stats_fs8",
    })


@dataclass
class StepResult:
    stage: str
    tool: str
    success: bool
    duration_sec: float
    build_duration_sec: float = 0.0
    peak_ram_bytes: int | None = None
    peak_cpu_pct: float | None = None
    log_text: str = ""
    output_files: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class BatchImageResult:
    input_file: str
    subject_id: str
    subject_dir: str
    success: bool
    duration_sec: float
    steps: list[StepResult] = field(default_factory=list)
    error: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[str, str, float, str], None]
BuildLogCallback = Callable[[str], None]
# (stage, tool, cpu_pct, ram_bytes, elapsed_sec, container_name)
MetricsCallback = Callable[[str, str, "float | None", "int | None", float, str], None]

PROJECT_ROOT = Path(__file__).parent


def _file_stem(filename: str) -> str:
    name = filename
    for ext in (".nii.gz", ".nii", ".mgz", ".mgh", ".dcm"):
        if name.lower().endswith(ext):
            return name[: -len(ext)]
    return Path(filename).stem


def _default_subject_id(input_file: str) -> str:
    """Derive subject_id from input filename: sub-002_T1w.nii -> sub-002_T1w"""
    return _file_stem(Path(input_file).name)


_GENERIC_BASENAMES = frozenset({
    "001", "002", "003", "image", "images", "scan", "brain", "t1", "t1w", "t2", "flair", "data",
})


def _is_generic_basename(filename: str) -> bool:
    """True for ADNI-style names like 001.mgz where parent folder holds identity."""
    stem = _file_stem(filename).lower()
    if stem in _GENERIC_BASENAMES:
        return True
    return bool(re.fullmatch(r"\d{1,6}", stem))


def _sanitize_subject_id(raw: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    if not safe:
        safe = "subject"
    if not safe[0].isalnum():
        safe = f"mri_{safe}"
    return safe[:200]


def _duplicate_basenames(files: list[str]) -> set[str]:
    counts: dict[str, int] = {}
    for f in files:
        name = Path(f).name
        counts[name] = counts.get(name, 0) + 1
    return {name for name, n in counts.items() if n > 1}


def _derive_subject_id(
    input_file: str,
    dataset_root: str = "",
    duplicate_basenames: set[str] | None = None,
) -> str:
    """Unique output folder name; uses path/parent when filenames collide (e.g. ADNI_orig/001.mgz)."""
    path = Path(input_file).expanduser().resolve()
    dup_names = duplicate_basenames or set()
    use_path = path.name in dup_names or _is_generic_basename(path.name)

    if use_path and path.parent.name:
        if dataset_root:
            try:
                rel = path.relative_to(Path(dataset_root).expanduser().resolve())
                if len(rel.parts) >= 2:
                    slug = "__".join(rel.with_suffix("").parts)
                    return _sanitize_subject_id(slug)
            except ValueError:
                pass
        return _sanitize_subject_id(path.parent.name)

    if dataset_root:
        try:
            rel = path.relative_to(Path(dataset_root).expanduser().resolve())
            if len(rel.parts) > 1:
                slug = "__".join(rel.with_suffix("").parts)
                return _sanitize_subject_id(slug)
        except ValueError:
            pass

    return _sanitize_subject_id(_default_subject_id(str(path)))


def build_subject_id_map(files: list[str], dataset_root: str) -> dict[str, str]:
    """Map each input path to a unique subject_id for outputs/."""
    dup_names = _duplicate_basenames(files)
    used: set[str] = set()
    out: dict[str, str] = {}
    for f in sorted(files):
        base = _derive_subject_id(f, dataset_root, dup_names)
        sid = base
        counter = 2
        while sid in used:
            sid = f"{base}_{counter}"
            counter += 1
        used.add(sid)
        out[f] = sid
    return out


def _is_supported_mri_file(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith((".nii.gz", ".nii", ".mgz", ".mgh", ".dcm"))


def _discover_mri_files(input_dir: str, recursive: bool = True) -> list[str]:
    root = Path(input_dir).expanduser()
    if not root.exists() or not root.is_dir():
        return []

    iterator = root.rglob("*") if recursive else root.glob("*")
    return [str(p) for p in sorted(iterator) if p.is_file() and _is_supported_mri_file(p)]


def _safe_container_name(*parts: str) -> str:
    raw = "-".join(part for part in parts if part)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-_.")
    if not safe:
        safe = "mri-pipeline"
    if not safe[0].isalnum():
        safe = f"mri-{safe}"
    return f"{safe[:80]}-{uuid4().hex[:8]}"


def _parse_docker_memory(value: str) -> int | None:
    """Parse docker stats MemUsage values such as '742.6MiB / 15.5GiB'."""
    first = value.split("/", 1)[0].strip()
    match = re.match(r"^([0-9.]+)\s*([A-Za-z]+)$", first)
    if not match:
        return None

    number = float(match.group(1))
    unit = match.group(2).lower()
    multipliers = {
        "b": 1,
        "kb": 1000,
        "mb": 1000 ** 2,
        "gb": 1000 ** 3,
        "tb": 1000 ** 4,
        "kib": 1024,
        "mib": 1024 ** 2,
        "gib": 1024 ** 3,
        "tib": 1024 ** 4,
    }
    multiplier = multipliers.get(unit)
    if multiplier is None:
        return None
    return int(number * multiplier)


def _parse_docker_stats_line(line: str) -> tuple[float | None, int | None]:
    """Parse 'CPUPerc|MemUsage' such as '12.34%|742.6MiB / 15.5GiB'."""
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


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "n/a"
    if value < 1024:
        return f"{value} B"
    mib = value / (1024 ** 2)
    if mib < 1024:
        return f"{mib:.1f} MiB"
    return f"{mib / 1024:.2f} GiB"


def _organize_output(subject_dir: str) -> None:
    """Move files from scattered Docker output locations into mri/, stats/, logs/."""
    sd = Path(subject_dir)
    mri_dir = sd / "mri"
    stats_dir = sd / "stats"
    logs_dir = sd / "logs"

    mri_dir.mkdir(parents=True, exist_ok=True)
    stats_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # --- Move volume files (.nii.gz, .mgz, .mgh) ---
    volume_exts = {".nii", ".nii.gz", ".mgz", ".mgh"}
    for f in sd.rglob("*"):
        if f.is_file() and f.parent not in (mri_dir, stats_dir, logs_dir):
            fname_lower = f.name.lower()
            if any(fname_lower.endswith(ext) for ext in volume_exts):
                dest = mri_dir / f.name
                if not dest.exists():
                    shutil.move(str(f), str(dest))

    # --- Move stats files (.tsv, .csv, .stats) ---
    for f in sd.rglob("*"):
        if f.is_file() and f.parent not in (mri_dir, stats_dir, logs_dir):
            if f.suffix.lower() in (".tsv", ".csv", ".stats"):
                dest = stats_dir / f.name
                if not dest.exists():
                    shutil.move(str(f), str(dest))

    # --- Move log files (.log) ---
    for f in sd.rglob("*"):
        if f.is_file() and f.parent not in (mri_dir, stats_dir, logs_dir):
            if f.suffix.lower() == ".log":
                dest = logs_dir / f.name
                if not dest.exists():
                    shutil.move(str(f), str(dest))

    # --- Clean up empty dirs ---
    for d in sorted(sd.rglob("*"), reverse=True):
        if d.is_dir() and d not in (mri_dir, stats_dir, logs_dir):
            try:
                d.rmdir()  # only removes if empty
            except OSError:
                pass


def _find_output_file(subject_dir: str, possible_names: list[str]) -> str | None:
    """Find an output file anywhere under subject_dir."""
    sd = Path(subject_dir)
    for name in possible_names:
        # Check in mri/ first, then root, then any subfolder
        for candidate in [sd / "mri" / name, sd / name]:
            if candidate.exists():
                return str(candidate)
        # Fallback: glob
        matches = list(sd.rglob(name))
        if matches:
            return str(matches[0])
    return None


def _write_pipeline_metrics_log(
    logs_dir: str,
    config: PipelineConfig,
    subject_dir: str,
    results: list[StepResult],
    started_at: float,
    ended_at: float,
) -> str:
    metrics_log = Path(logs_dir) / "pipeline_metrics.log"
    total_run = sum(r.duration_sec for r in results)
    total_build = sum(r.build_duration_sec for r in results)
    status = "SUCCESS" if results and all(r.success for r in results) else "FAILED"

    with open(metrics_log, "w", encoding="utf-8") as f:
        f.write("MRI Pipeline Metrics\n")
        f.write(f"Input file: {os.path.abspath(config.input_file)}\n")
        f.write(f"Subject ID: {config.subject_id}\n")
        f.write(f"Subject output: {subject_dir}\n")
        f.write(f"Started: {datetime.fromtimestamp(started_at).isoformat(timespec='seconds')}\n")
        f.write(f"Finished: {datetime.fromtimestamp(ended_at).isoformat(timespec='seconds')}\n")
        f.write(f"Status: {status}\n")
        f.write(f"Total wall time: {ended_at - started_at:.1f}s\n")
        f.write(f"Total run time: {total_run:.1f}s\n")
        f.write(f"Total build/pull time: {total_build:.1f}s\n\n")
        f.write("Stage\tTool\tStatus\tRun(s)\tBuild/Pull(s)\tPeak RAM\tError\n")
        for r in results:
            f.write(
                f"{r.stage}\t{r.tool}\t{'OK' if r.success else 'FAILED'}\t"
                f"{r.duration_sec:.1f}\t{r.build_duration_sec:.1f}\t"
                f"{_format_bytes(r.peak_ram_bytes)}\t{r.error}\n"
            )

    return str(metrics_log)


def _pipeline_state_path(logs_dir: str) -> Path:
    return Path(logs_dir) / "pipeline_state.json"


def _load_pipeline_state(logs_dir: str) -> dict:
    path = _pipeline_state_path(logs_dir)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_pipeline_state(logs_dir: str, state: dict) -> None:
    path = _pipeline_state_path(logs_dir)
    Path(logs_dir).mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _new_pipeline_state(config: PipelineConfig, subject_dir: str) -> dict:
    return {
        "version": 1,
        "input_file": os.path.abspath(config.input_file),
        "subject_id": config.subject_id,
        "subject_dir": subject_dir,
        "status": "running",
        "current_stage": "",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "selected_tools": config.selected_tools,
        "stages": {},
    }


def _set_stage_state(
    logs_dir: str,
    state: dict,
    stage: str,
    tool: str,
    status: str,
    output_file: str = "",
    output_files_found: list[str] | None = None,
    error: str = "",
    duration_sec: float = 0.0,
) -> None:
    state.setdefault("stages", {})[stage] = {
        "tool": tool,
        "status": status,
        "output_file": output_file,
        "output_files_found": output_files_found or ([output_file] if output_file else []),
        "error": error,
        "duration_sec": duration_sec,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    state["current_stage"] = stage
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    if status == "failed":
        state["status"] = "failed"
    elif status == "running":
        state["status"] = "running"
    _write_pipeline_state(logs_dir, state)


def _find_existing_outputs(subject_dir: str, possible_names: list[str]) -> list[str]:
    found: list[str] = []
    sd = Path(subject_dir)
    for name in possible_names:
        match = None
        for candidate in [sd / "mri" / name, sd / "stats" / name, sd / name]:
            if candidate.exists():
                match = str(candidate)
                break
        if match is None:
            matches = list(sd.rglob(name))
            if matches:
                match = str(matches[0])
        if match:
            found.append(match)
    return found


def _resume_output_for_stage(subject_dir: str, state: dict, stage: str, tool_key: str, output_files: list[str]) -> str | None:
    stage_state = state.get("stages", {}).get(stage, {})
    if stage_state.get("status") != "completed" or stage_state.get("tool") != tool_key:
        return None

    recorded_outputs = [p for p in stage_state.get("output_files_found", []) if p]
    if recorded_outputs and not all(Path(p).exists() for p in recorded_outputs):
        return None

    saved_output = stage_state.get("output_file")
    if saved_output and Path(saved_output).exists():
        return saved_output

    found_outputs = _find_existing_outputs(subject_dir, output_files)
    return found_outputs[0] if found_outputs else None


# ---------------------------------------------------------------------------
# Docker operations
# ---------------------------------------------------------------------------

def image_exists(image: str) -> bool:
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True, text=True, timeout=10,
        )
        return proc.returncode == 0
    except Exception:
        return False


def build_image(
    image: str,
    context_dir: str,
    on_progress: ProgressCallback | None = None,
    on_build_log: BuildLogCallback | None = None,
) -> bool:
    ctx = PROJECT_ROOT / context_dir
    if not ctx.exists():
        if on_progress:
            on_progress("build", "failed", 0, f"Dockerfile context not found: {ctx}")
        return False

    if on_progress:
        on_progress("build", "running", 0, f"Building {image}...")
    if on_build_log:
        on_build_log(f">>> docker build -t {image} {ctx}")

    t0 = time.time()
    try:
        proc = subprocess.Popen(
            ["docker", "build", "-t", image, str(ctx)],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        last_progress: dict[str, str] = {}
        raw = ""

        def flush_progress():
            for v in last_progress.values():
                if on_build_log:
                    on_build_log(v)
            last_progress.clear()

        for chunk in proc.stdout:
            raw += chunk
            while "\n" in raw or "\r" in raw:
                idx_n = raw.find("\n")
                idx_r = raw.find("\r")
                idx = min(i for i in (idx_n, idx_r) if i >= 0)
                line = raw[:idx].strip()
                raw = raw[idx + 1:]
                if not line:
                    continue
                if ("MB/s" in line or "GB/s" in line or "kB/s" in line) and "%" in line:
                    parts = line.split()
                    lid = parts[0] if parts and parts[0].startswith("#") else line[:20]
                    last_progress[lid] = line
                else:
                    flush_progress()
                    if on_build_log:
                        on_build_log(line)

        flush_progress()
        if raw.strip() and on_build_log:
            on_build_log(raw.strip())
        proc.wait()
        build_time = time.time() - t0

        if proc.returncode == 0:
            if on_progress:
                on_progress("build", "success", 0, f"Built {image} in {build_time:.0f}s")
            return True
        else:
            if on_progress:
                on_progress("build", "failed", 0, f"Build failed (exit {proc.returncode})")
            return False
    except Exception as e:
        if on_progress:
            on_progress("build", "failed", 0, f"Build error: {e}")
        return False


def _try_pull(image: str, on_progress: ProgressCallback | None = None,
              on_build_log: BuildLogCallback | None = None) -> bool:
    if on_progress:
        on_progress("build", "running", 0, f"Pulling {image}...")
    if on_build_log:
        on_build_log(f">>> docker pull {image}")
    try:
        proc = subprocess.Popen(
            ["docker", "pull", image],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        last_progress: dict[str, str] = {}
        raw = ""
        for chunk in proc.stdout:
            raw += chunk
            while "\n" in raw or "\r" in raw:
                idx_n = raw.find("\n")
                idx_r = raw.find("\r")
                idx = min(i for i in (idx_n, idx_r) if i >= 0)
                line = raw[:idx].strip()
                raw = raw[idx + 1:]
                if not line:
                    continue
                if ("MB/s" in line or "GB/s" in line or "kB/s" in line) and "%" in line:
                    parts = line.split()
                    lid = parts[0] if parts and parts[0].startswith("#") else line[:20]
                    last_progress[lid] = line
                else:
                    for v in last_progress.values():
                        if on_build_log:
                            on_build_log(v)
                    last_progress.clear()
                    if on_build_log:
                        on_build_log(line)
        for v in last_progress.values():
            if on_build_log:
                on_build_log(v)
        if raw.strip() and on_build_log:
            on_build_log(raw.strip())
        proc.wait()
        return proc.returncode == 0
    except Exception:
        return False


def ensure_image(
    tool_key: str,
    on_progress: ProgressCallback | None = None,
    on_build_log: BuildLogCallback | None = None,
) -> tuple[bool, str, float]:
    tool = TOOL_DEFS.get(tool_key)
    if not tool:
        return False, f"Unknown tool: {tool_key}", 0.0

    image = tool["image"]
    total_build = 0.0

    base_image = tool.get("base_image")
    base_dockerfile = tool.get("base_dockerfile")
    if base_image and not image_exists(base_image):
        if on_progress:
            on_progress("build", "running", 0, f"Pulling base {base_image}...")
        t0 = time.time()
        pulled = _try_pull(base_image, on_progress, on_build_log)
        total_build += time.time() - t0
        if not pulled:
            if base_dockerfile:
                if on_progress:
                    on_progress("build", "running", 0, f"Pull failed, building {base_image}...")
                t0 = time.time()
                if not build_image(base_image, base_dockerfile, on_progress, on_build_log):
                    return False, f"Failed to get base image {base_image}", total_build
                total_build += time.time() - t0
            else:
                return False, f"Base image {base_image} not available", total_build

    if not image_exists(image):
        if on_progress:
            on_progress("build", "running", 0, f"Pulling {image}...")
        t0 = time.time()
        pulled = _try_pull(image, on_progress, on_build_log)
        total_build += time.time() - t0
        if not pulled:
            dockerfile = tool.get("dockerfile")
            if dockerfile:
                if on_progress:
                    on_progress("build", "running", 0, f"Pull failed, building {image}...")
                t0 = time.time()
                if not build_image(image, dockerfile, on_progress, on_build_log):
                    return False, f"Failed to build {image}", total_build
                total_build += time.time() - t0
            else:
                return False, f"Image {image} not available", total_build

    return True, "", total_build


def _run_docker(
    image: str,
    args: list[str],
    mounts: list[tuple[str, str]] | dict[str, str],
    env: dict[str, str] | None = None,
    gpus: bool = False,
    timeout: int = 7200,
    container_name: str | None = None,
    on_metrics: Callable[[float | None, int | None, float, str], None] | None = None,
    command: list[str] | None = None,
) -> tuple[int, str, int | None, float | None]:
    cmd = ["docker", "run", "--rm"]
    if container_name:
        cmd += ["--name", container_name]
    if gpus:
        cmd += ["--gpus", "all"]

    mount_items = mounts.items() if isinstance(mounts, dict) else mounts
    for host_path, container_path in mount_items:
        cmd += ["-v", f"{os.path.abspath(host_path)}:{container_path}"]
    if env:
        for k, v in env.items():
            cmd += ["-e", f"{k}={v}"]
    cmd.append(image)
    if command:
        cmd.extend(command)
    cmd += args

    log.info("Running: %s", " ".join(cmd))

    peak_ram = {"bytes": None}
    peak_cpu = {"pct": None}
    stop_monitor = threading.Event()
    t0 = time.time()

    def monitor_resources():
        if not container_name:
            return
        while not stop_monitor.is_set():
            try:
                stats = subprocess.run(
                    ["docker", "stats", "--no-stream", "--format",
                     "{{.CPUPerc}}|{{.MemUsage}}", container_name],
                    capture_output=True, text=True, timeout=5,
                )
                if stats.returncode == 0 and stats.stdout.strip():
                    cpu, current = _parse_docker_stats_line(stats.stdout.strip().splitlines()[0])
                    if current is not None and (peak_ram["bytes"] is None or current > peak_ram["bytes"]):
                        peak_ram["bytes"] = current
                    if cpu is not None and (peak_cpu["pct"] is None or cpu > peak_cpu["pct"]):
                        peak_cpu["pct"] = cpu
                    if on_metrics:
                        on_metrics(cpu, current, time.time() - t0, container_name or "")
            except Exception:
                pass
            stop_monitor.wait(0.5)

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        monitor = threading.Thread(target=monitor_resources, daemon=True)
        monitor.start()
        try:
            output, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            if container_name:
                subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, text=True, timeout=30)
            output, _ = proc.communicate()
            return -1, f"{output or ''}\nDocker timed out after {timeout}s", peak_ram["bytes"], peak_cpu["pct"]
        finally:
            stop_monitor.set()
            monitor.join(timeout=2)

        return proc.returncode, output or "", peak_ram["bytes"], peak_cpu["pct"]
    except subprocess.TimeoutExpired:
        return -1, f"Docker timed out after {timeout}s", peak_ram["bytes"], peak_cpu["pct"]
    except FileNotFoundError:
        return -1, "docker not found — is Docker installed and in PATH?", peak_ram["bytes"], peak_cpu["pct"]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    config: PipelineConfig,
    on_progress: ProgressCallback | None = None,
    on_build_log: BuildLogCallback | None = None,
    on_metrics: MetricsCallback | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[StepResult]:
    """Execute the full pipeline."""

    started_at = time.time()

    def progress(stage: str, status: str, pct: float, msg: str):
        if on_progress:
            on_progress(stage, status, pct, msg)
        log.info("[%s] %s (%.0f%%) %s", stage, status, pct * 100, msg)

    # Directory layout
    subject_dir = os.path.join(os.path.abspath(config.output_dir), config.subject_id)
    mri_dir = os.path.join(subject_dir, "mri")
    stats_dir = os.path.join(subject_dir, "stats")
    logs_dir = os.path.join(subject_dir, "logs")

    for d in (mri_dir, stats_dir, logs_dir):
        Path(d).mkdir(parents=True, exist_ok=True)

    state = _load_pipeline_state(logs_dir) if config.resume else {}
    if not state:
        state = _new_pipeline_state(config, subject_dir)
    state["status"] = "running"
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_pipeline_state(logs_dir, state)

    license_mount: list[tuple[str, str]] = []
    if config.license_dir:
        lic_path = Path(config.license_dir).absolute()
        if lic_path.is_file():
            license_mount.append((str(lic_path), "/license/license.txt"))
        else:
            license_mount.append((str(lic_path), "/license"))

    results: list[StepResult] = []
    input_for_next_step: str | None = None
    total_stages = len(STAGE_ORDER)
    paused = False

    for stage_idx, stage in enumerate(STAGE_ORDER):
        tool_key = config.selected_tools.get(stage)
        if not tool_key or tool_key not in TOOL_DEFS:
            continue

        tool = TOOL_DEFS[tool_key]
        stage_pct = stage_idx / total_stages

        if config.resume:
            resumed_output = _resume_output_for_stage(subject_dir, state, stage, tool_key, tool["output_files"])
            if resumed_output:
                input_for_next_step = resumed_output
                results.append(StepResult(
                    stage=stage,
                    tool=tool_key,
                    success=True,
                    duration_sec=0.0,
                    output_files=tool["output_files"],
                    log_text="resumed from completed state",
                ))
                progress(stage, "success", (stage_idx + 1) / total_stages,
                         f"Resume: skipping completed {STAGE_LABELS[stage]} with {tool_key}")
                continue

        progress(stage, "running", stage_pct, f"Starting {STAGE_LABELS[stage]} with {tool_key}")
        _set_stage_state(logs_dir, state, stage, tool_key, "running")

        # Ensure image
        ok, err, build_time = ensure_image(tool_key, on_progress=on_progress, on_build_log=on_build_log)
        if not ok:
            _set_stage_state(logs_dir, state, stage, tool_key, "failed", error=f"Image not available: {err}")
            results.append(StepResult(
                stage=stage, tool=tool_key, success=False, duration_sec=0,
                build_duration_sec=build_time, error=f"Image not available: {err}",
            ))
            progress(stage, "failed", (stage_idx + 1) / total_stages, f"{STAGE_LABELS[stage]} FAILED: {err}")
            break

        # Determine input
        if input_for_next_step is None:
            host_input_dir, _, input_path = (
                os.path.dirname(os.path.abspath(config.input_file)),
                "/input",
                f"/input/{os.path.basename(config.input_file)}",
            )
            mounts: list[tuple[str, str]] = [(host_input_dir, "/input")]
        else:
            # Previous output is inside subject_dir, mounted at /work
            rel = os.path.relpath(input_for_next_step, subject_dir)
            input_path = f"/work/{rel}"
            mounts = []

        # Mount subject_dir as both /output and /work
        mounts.append((subject_dir, "/output"))
        mounts.append((subject_dir, "/work"))
        if tool["needs_license"] and license_mount:
            mounts.extend(license_mount)

        # Extra mounts (e.g. hdbet weights)
        for rel, container in tool.get("extra_mounts", {}).items():
            host = os.path.join(subject_dir, "mri", rel)
            Path(host).mkdir(parents=True, exist_ok=True)
            mounts.append((host, container))
            
        norm_vol = Path(__file__).parent / "normalize_volumes.py"
        if norm_vol.exists():
            mounts.append((str(norm_vol.resolve()), "/app/normalize_volumes.py"))

        args = [
            "--input", input_path,
            "--output-dir", "/output",
            "--work-dir", "/work",
            "--subject-id", config.subject_id,
            "--threads", str(config.threads),
            "--device", config.device,
        ]

        t0 = time.time()
        container_name = _safe_container_name("mri", config.subject_id, tool_key)

        def _metrics_relay(cpu_pct, ram_bytes, elapsed, _cn=container_name, _stage=stage, _tool=tool_key):
            if on_metrics:
                on_metrics(_stage, _tool, cpu_pct, ram_bytes, elapsed, _cn)

        code, output, peak_ram, peak_cpu = _run_docker(
            image=tool["image"], args=args, mounts=mounts,
            gpus=(config.device == "gpu"),
            container_name=container_name,
            command=tool.get("command"),
            on_metrics=_metrics_relay if on_metrics else None,
        )
        duration = time.time() - t0

        # Organize scattered outputs into mri/, stats/, logs/
        _organize_output(subject_dir)

        success = code == 0
        if success:
            error = ""
        else:
            if not output.strip():
                try:
                    logs = [p for p in Path(logs_dir).glob("*.log") if p.name not in ("pipeline_metrics.log", "pipeline_state.json")]
                    if logs:
                        latest_log = max(logs, key=lambda p: p.stat().st_mtime)
                        output = latest_log.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

            tail = " | ".join(output.strip().splitlines()[-3:]) if output.strip() else "No output"
            error = f"exit code {code} ({tail})"
            if output.strip():
                print(f"\n--- DOCKER ERROR LOG ({tool_key}) ---", flush=True)
                for line in output.strip().splitlines()[-20:]:
                    print(line, flush=True)
                print("-" * 40, flush=True)
        if success:
            found = _find_output_file(subject_dir, tool["output_files"])
            if found:
                input_for_next_step = found
            else:
                success = False
                error = f"missing expected output files: {', '.join(tool['output_files'])}"

        outputs_found = _find_existing_outputs(subject_dir, tool["output_files"]) if success else []

        _set_stage_state(
            logs_dir,
            state,
            stage,
            tool_key,
            "completed" if success else "failed",
            output_file=input_for_next_step if success and input_for_next_step else "",
            output_files_found=outputs_found,
            error=error,
            duration_sec=duration,
        )

        # Write step timing to logs
        step_log = os.path.join(logs_dir, f"{tool_key}.log")
        with open(step_log, "a", encoding="utf-8") as f:
            f.write(f"Stage: {stage}\n")
            f.write(f"Tool: {tool_key}\n")
            f.write(f"Duration: {duration:.1f}s\n")
            f.write(f"Build: {build_time:.1f}s\n")
            f.write(f"Peak RAM: {_format_bytes(peak_ram)}\n")
            f.write(f"Peak CPU: {peak_cpu:.0f}%\n" if peak_cpu is not None else "Peak CPU: n/a\n")
            f.write(f"Exit code: {code}\n")
            if output.strip():
                f.write(f"\n--- Output ---\n{output[-3000:]}\n")

        results.append(StepResult(
            stage=stage, tool=tool_key, success=success,
            duration_sec=duration, build_duration_sec=build_time,
            peak_ram_bytes=peak_ram, peak_cpu_pct=peak_cpu,
            log_text=output[-2000:] if output else "",
            output_files=tool["output_files"],
            error=error,
        ))

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
                progress("pipeline", "paused", (stage_idx + 1) / total_stages,
                         f"Paused after {STAGE_LABELS[stage]}. Resume will continue from the next incomplete stage.")
                break
        else:
            progress(stage, "failed", (stage_idx + 1) / total_stages,
                     f"{STAGE_LABELS[stage]} FAILED: {error}")
            break

    if paused:
        state["status"] = "PAUSED"
    else:
        state["status"] = "SUCCESS" if results and all(r.success for r in results) else "FAILED"
    state["finished_at"] = datetime.now().isoformat(timespec="seconds")
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_pipeline_state(logs_dir, state)
    _write_pipeline_metrics_log(logs_dir, config, subject_dir, results, started_at, time.time())
    return results


def _unique_subject_id(
    input_file: str,
    used_subject_ids: set[str],
    dataset_root: str = "",
    duplicate_basenames: set[str] | None = None,
) -> str:
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
    on_progress: ProgressCallback | None = None,
    on_build_log: BuildLogCallback | None = None,
    on_image_done: Callable[[BatchImageResult, int, int], None] | None = None,
    on_image_start: Callable[[str, int, int], None] | None = None,
    on_metrics: MetricsCallback | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[BatchImageResult]:
    """Run the pipeline sequentially for every supported MRI file in a folder."""
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

        subject_id = _unique_subject_id(
            input_file, used_subject_ids, dataset_root, dup_basenames,
        )
        subject_dir = os.path.join(os.path.abspath(output_dir), subject_id)
        started_at = time.time()

        if on_image_start:
            on_image_start(input_file, idx, total)
        if on_progress:
            on_progress("batch", "running", (idx - 1) / total if total else 0, f"Starting image {idx}/{total}: {input_file}")

        try:
            config = PipelineConfig(
                input_file=input_file,
                output_dir=output_dir,
                subject_id=subject_id,
                license_dir=license_dir,
                device=device,
                threads=threads,
                resume=resume,
                selected_tools=selected_tools or PipelineConfig(input_file, output_dir, subject_id).selected_tools,
            )
            steps = run_pipeline(
                config,
                on_progress=on_progress,
                on_build_log=on_build_log,
                on_metrics=on_metrics,
                should_stop=should_stop,
            )
            success = bool(steps) and all(step.success for step in steps)
            error = "" if success else "one or more pipeline steps failed"
        except Exception as exc:
            steps = []
            success = False
            error = str(exc)
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

        image_result = BatchImageResult(
            input_file=input_file,
            subject_id=subject_id,
            subject_dir=subject_dir,
            success=success,
            duration_sec=time.time() - started_at,
            steps=steps,
            error=error,
        )
        batch_results.append(image_result)

        if on_image_done:
            on_image_done(image_result, idx, total)

    return batch_results


DEFAULT_BATCH_INPUT_DIR = "/mnt/c/Users/ADMIN/Desktop/MRI/ADNI"


def _cli_selected_tools(args: argparse.Namespace) -> dict[str, str]:
    return {
        "reorientation": args.reorientation,
        "brain_extraction": args.brain_extraction,
        "segmentation": args.segmentation,
        "bias_correction": args.bias_correction,
        "template_registration": args.template_registration,
        "white_matter_segmentation": args.white_matter_segmentation,
        "stats_extraction": args.stats_extraction,
    }


def _cli_progress(stage: str, status: str, pct: float, msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {status.upper()} {stage}: {msg}", flush=True)


def _cli_build_log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] DOCKER: {msg}", flush=True)


def _cli_image_done(result: BatchImageResult, idx: int, total: int) -> None:
    status = "OK" if result.success else "FAILED"
    metrics_log = Path(result.subject_dir) / "logs" / "pipeline_metrics.log"
    print(
        f"Đã xử lý xong ảnh {idx}/{total}: {result.input_file} | "
        f"status={status} | log={metrics_log}",
        flush=True,
    )


def _emit_json_event(kind: str, **payload) -> None:
    print("MRI_EVENT " + json.dumps({"kind": kind, **payload}, ensure_ascii=False), flush=True)


def main(argv: list[str] | None = None) -> int:
    default_tools = PipelineConfig("", "", "").selected_tools
    tools_by_stage = {
        stage: [key for key, tool in TOOL_DEFS.items() if tool["stage"] == stage]
        for stage in STAGE_ORDER
    }

    parser = argparse.ArgumentParser(
        description="Run the MRI pipeline for one file or a sequential batch folder.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input-file", help="Run one MRI file only")
    source.add_argument("--input-dir", help="Run every supported MRI file in this folder")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "outputs"), help="Base output directory")
    parser.add_argument("--license-dir", default=str(PROJECT_ROOT / "license"), help="FreeSurfer license directory")
    parser.add_argument("--device", choices=["cpu", "gpu"], default="cpu", help="Execution device")
    parser.add_argument("--threads", type=int, default=4, help="CPU threads passed to tools")
    parser.add_argument("--resume", action="store_true", help="Skip completed stages recorded in logs/pipeline_state.json")
    parser.add_argument("--stop-file", default="", help="Pause safely after current stage if this file exists")
    parser.add_argument("--non-recursive", action="store_true", help="Only scan files directly inside --input-dir")
    parser.add_argument("--json-events", action="store_true", help="Emit machine-readable progress events for GUI clients")
    parser.add_argument("--ensure-images-only", action="store_true", help="Only pull/build/check selected Docker images, then exit")
    parser.add_argument("--reorientation", choices=tools_by_stage["reorientation"], default=default_tools["reorientation"])
    parser.add_argument("--brain-extraction", choices=tools_by_stage["brain_extraction"], default=default_tools["brain_extraction"])
    parser.add_argument("--segmentation", choices=tools_by_stage["segmentation"], default=default_tools["segmentation"])
    parser.add_argument("--bias-correction", choices=tools_by_stage["bias_correction"], default=default_tools["bias_correction"])
    parser.add_argument("--template-registration", choices=tools_by_stage["template_registration"], default=default_tools["template_registration"])
    parser.add_argument("--white-matter-segmentation", choices=tools_by_stage["white_matter_segmentation"], default=default_tools["white_matter_segmentation"])
    parser.add_argument("--stats-extraction", choices=tools_by_stage["stats_extraction"], default=default_tools["stats_extraction"])
    args = parser.parse_args(argv)

    selected_tools = _cli_selected_tools(args)

    if args.ensure_images_only:
        ok = True
        for tool_key in dict.fromkeys(selected_tools.values()):
            if args.json_events:
                _emit_json_event("image_preflight", tool=tool_key, status="running")
            result, err, _build_time = ensure_image(
                tool_key,
                on_progress=_cli_progress,
                on_build_log=_cli_build_log,
            )
            if not result:
                ok = False
                if args.json_events:
                    _emit_json_event("image_preflight", tool=tool_key, status="failed", error=err)
                print(f"Image preflight failed for {tool_key}: {err}", file=sys.stderr, flush=True)
                break
            if args.json_events:
                _emit_json_event("image_preflight", tool=tool_key, status="success")
        return 0 if ok else 2

    progress_cb = _cli_progress
    image_start_cb = None
    image_done_cb = _cli_image_done
    if args.json_events:
        def progress_cb(stage: str, status: str, pct: float, msg: str) -> None:
            _cli_progress(stage, status, pct, msg)
            _emit_json_event("progress", stage=stage, status=status, pct=pct, msg=msg)

        def image_start_cb(input_file: str, idx: int, total: int) -> None:
            _emit_json_event("image_start", input_file=input_file, idx=idx, total=total)

        def image_done_cb(result: BatchImageResult, idx: int, total: int) -> None:
            _cli_image_done(result, idx, total)
            _emit_json_event(
                "image_done",
                input_file=result.input_file,
                subject_id=result.subject_id,
                idx=idx,
                total=total,
                success=result.success,
                error=result.error,
            )

    if args.input_file:
        input_path = str(Path(args.input_file).expanduser().resolve())
        root = args.input_dir or str(Path(input_path).parent)
        subject_id = _derive_subject_id(
            input_path,
            root,
            _duplicate_basenames([input_path]) if args.input_dir else None,
        )
        config = PipelineConfig(
            input_file=args.input_file,
            output_dir=args.output_dir,
            subject_id=subject_id,
            license_dir=args.license_dir,
            device=args.device,
            threads=args.threads,
            resume=args.resume,
            selected_tools=selected_tools,
        )
        should_stop = (lambda: Path(args.stop_file).exists()) if args.stop_file else None
        if image_start_cb:
            image_start_cb(args.input_file, 1, 1)
        results = run_pipeline(config, on_progress=progress_cb, on_build_log=_cli_build_log, should_stop=should_stop)
        success = bool(results) and all(step.success for step in results)
        subject_dir = Path(args.output_dir).resolve() / subject_id
        print(f"Đã xử lý xong ảnh: {args.input_file} | status={'OK' if success else 'FAILED'} | log={subject_dir / 'logs' / 'pipeline_metrics.log'}", flush=True)
        if args.json_events:
            _emit_json_event(
                "image_done",
                input_file=args.input_file,
                subject_id=subject_id,
                idx=1,
                total=1,
                success=success,
                error="" if success else "one or more pipeline steps failed",
            )
        return 0 if success else 1

    input_dir = args.input_dir or DEFAULT_BATCH_INPUT_DIR
    input_files = _discover_mri_files(input_dir, recursive=not args.non_recursive)
    if not input_files:
        print(f"Không tìm thấy file MRI hợp lệ trong folder: {input_dir}", file=sys.stderr, flush=True)
        return 1

    print(f"Tìm thấy {len(input_files)} ảnh MRI trong {input_dir}. Bắt đầu xử lý tuần tự.", flush=True)
    batch_results = run_batch_pipeline(
        input_dir=input_dir,
        output_dir=args.output_dir,
        license_dir=args.license_dir,
        device=args.device,
        threads=args.threads,
        resume=args.resume,
        selected_tools=selected_tools,
        recursive=not args.non_recursive,
        on_progress=progress_cb,
        on_build_log=_cli_build_log,
        on_image_start=image_start_cb,
        on_image_done=image_done_cb,
        should_stop=(lambda: Path(args.stop_file).exists()) if args.stop_file else None,
    )

    failed = [result for result in batch_results if not result.success]
    print(f"Batch hoàn tất: {len(batch_results) - len(failed)}/{len(batch_results)} ảnh thành công.", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
