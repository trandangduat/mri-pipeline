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
"""

from __future__ import annotations

import glob
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOL_DEFS: dict[str, dict] = {
    "mri_convert": {
        "image": "mkdayyyy/mri-mri-convert:latest",
        "dockerfile": "docker/freesurfer-mri-convert",
        "base_image": "mkdayyyy/mri-freesurfer-base:latest",
        "base_dockerfile": "docker/freesurfer-base",
        "stage": "reorientation",
        "needs_license": True,
        "output_files": ["01_reoriented.nii.gz"],
    },
    "nibabel": {
        "image": "duattran05/mri-nibabel-utils:latest",
        "dockerfile": "docker/nibabel-utils",
        "stage": "reorientation",
        "needs_license": False,
        "output_files": ["01_nibabel_reoriented.nii.gz"],
    },
    "synthstrip": {
        "image": "mkdayyyy/mri-synthstrip:latest",
        "dockerfile": "docker/freesurfer-synthstrip",
        "base_image": "mkdayyyy/mri-freesurfer-base:latest",
        "base_dockerfile": "docker/freesurfer-base",
        "stage": "brain_extraction",
        "needs_license": True,
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
    "synthseg_freesurfer": {
        "image": "mkdayyyy/mri-synthseg-freesurfer:latest",
        "dockerfile": "docker/freesurfer-synthseg",
        "base_image": "mkdayyyy/mri-freesurfer-base:latest",
        "base_dockerfile": "docker/freesurfer-base",
        "stage": "segmentation",
        "needs_license": True,
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
}

STAGE_ORDER = ["reorientation", "brain_extraction", "segmentation", "bias_correction"]

STAGE_LABELS = {
    "reorientation": "Reorientation & Resampling",
    "brain_extraction": "Brain Extraction",
    "segmentation": "Subcortical Segmentation",
    "bias_correction": "Bias Field Correction (N4)",
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
    selected_tools: dict[str, str] = field(default_factory=lambda: {
        "reorientation": "mri_convert",
        "brain_extraction": "synthstrip",
        "segmentation": "synthseg_freesurfer",
        "bias_correction": "ants_n4",
    })


@dataclass
class StepResult:
    stage: str
    tool: str
    success: bool
    duration_sec: float
    build_duration_sec: float = 0.0
    log_text: str = ""
    output_files: list[str] = field(default_factory=list)
    error: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[str, str, float, str], None]
BuildLogCallback = Callable[[str], None]

PROJECT_ROOT = Path(__file__).parent


def _default_subject_id(input_file: str) -> str:
    """Derive subject_id from input filename: sub-002_T1w.nii -> sub-002_T1w"""
    name = Path(input_file).name
    for ext in (".nii.gz", ".nii", ".mgz", ".mgh", ".dcm"):
        if name.endswith(ext):
            name = name[: -len(ext)]
            break
    return name


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
    mounts: dict[str, str],
    env: dict[str, str] | None = None,
    gpus: bool = False,
    timeout: int = 7200,
) -> tuple[int, str]:
    cmd = ["docker", "run", "--rm"]
    if gpus:
        cmd += ["--gpus", "all"]
    for host_path, container_path in mounts.items():
        cmd += ["-v", f"{os.path.abspath(host_path)}:{container_path}"]
    if env:
        for k, v in env.items():
            cmd += ["-e", f"{k}={v}"]
    cmd.append(image)
    cmd += args

    log.info("Running: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout + "\n" + proc.stderr
    except subprocess.TimeoutExpired:
        return -1, f"Docker timed out after {timeout}s"
    except FileNotFoundError:
        return -1, "docker not found — is Docker installed and in PATH?"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    config: PipelineConfig,
    on_progress: ProgressCallback | None = None,
    on_build_log: BuildLogCallback | None = None,
) -> list[StepResult]:
    """Execute the full pipeline."""

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

    license_mount = {}
    if config.license_dir:
        license_mount[os.path.abspath(config.license_dir)] = "/license"

    results: list[StepResult] = []
    input_for_next_step: str | None = None
    total_stages = len(STAGE_ORDER)

    for stage_idx, stage in enumerate(STAGE_ORDER):
        tool_key = config.selected_tools.get(stage)
        if not tool_key or tool_key not in TOOL_DEFS:
            continue

        tool = TOOL_DEFS[tool_key]
        stage_pct = stage_idx / total_stages
        progress(stage, "running", stage_pct, f"Starting {STAGE_LABELS[stage]} with {tool_key}")

        # Ensure image
        ok, err, build_time = ensure_image(tool_key, on_progress=on_progress, on_build_log=on_build_log)
        if not ok:
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
            mounts = {host_input_dir: "/input"}
        else:
            # Previous output is inside subject_dir, mounted at /work
            rel = os.path.relpath(input_for_next_step, subject_dir)
            input_path = f"/work/{rel}"
            mounts = {}

        # Mount subject_dir as both /output and /work
        mounts[subject_dir] = "/output"
        mounts[subject_dir] = "/work"
        if tool["needs_license"] and license_mount:
            mounts.update(license_mount)

        # Extra mounts (e.g. hdbet weights)
        for rel, container in tool.get("extra_mounts", {}).items():
            host = os.path.join(subject_dir, "mri", rel)
            Path(host).mkdir(parents=True, exist_ok=True)
            mounts[host] = container

        args = [
            "--input", input_path,
            "--output-dir", "/output",
            "--work-dir", "/work",
            "--subject-id", config.subject_id,
            "--threads", str(config.threads),
            "--device", config.device,
        ]

        t0 = time.time()
        code, output = _run_docker(
            image=tool["image"], args=args, mounts=mounts,
            gpus=(config.device == "gpu"),
        )
        duration = time.time() - t0

        # Organize scattered outputs into mri/, stats/, logs/
        _organize_output(subject_dir)

        # Verify output
        success = code == 0
        if success:
            found = _find_output_file(subject_dir, tool["output_files"])
            if found:
                input_for_next_step = found
            else:
                success = False

        # Write step timing to logs
        step_log = os.path.join(logs_dir, f"{tool_key}.log")
        with open(step_log, "a", encoding="utf-8") as f:
            f.write(f"Stage: {stage}\n")
            f.write(f"Tool: {tool_key}\n")
            f.write(f"Duration: {duration:.1f}s\n")
            f.write(f"Build: {build_time:.1f}s\n")
            f.write(f"Exit code: {code}\n")
            if output.strip():
                f.write(f"\n--- Output ---\n{output[-3000:]}\n")

        results.append(StepResult(
            stage=stage, tool=tool_key, success=success,
            duration_sec=duration, build_duration_sec=build_time,
            log_text=output[-2000:] if output else "",
            output_files=tool["output_files"],
            error="" if success else f"exit code {code}",
        ))

        if success:
            msg = f"{STAGE_LABELS[stage]} done in {duration:.0f}s"
            if build_time > 0:
                msg += f" (build: {build_time:.0f}s)"
            progress(stage, "success", (stage_idx + 1) / total_stages, msg)
        else:
            progress(stage, "failed", (stage_idx + 1) / total_stages,
                     f"{STAGE_LABELS[stage]} FAILED: exit code {code}")
            break

    return results
