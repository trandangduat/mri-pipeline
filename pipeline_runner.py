"""Real MRI pipeline runner — executes Docker containers in sequence.

Pipeline stages:
  1. Reorientation:      mri-mri-convert OR mri-nibabel-utils
  2. Brain Extraction:   mri-synthstrip OR mri-hdbet
  3. Segmentation:       mri-synthseg-freesurfer OR mri-synthseg-standalone OR mri-fastsurfervinn
  4. Bias Correction:    mri-ants
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

# Map tool key -> (docker image name, dockerfile context directory)
TOOL_DEFS: dict[str, dict] = {
    # Stage 1: Reorientation
    "mri_convert": {
        "image": "mkdayyyy/mri-mri-convert:latest",
        "dockerfile": "docker/freesurfer-mri-convert",
        "base_image": "mkdayyyy/mri-freesurfer-base:latest",
        "base_dockerfile": "docker/freesurfer-base",
        "stage": "reorientation",
        "needs_license": True,
        "output_in_work": True,
        "output_files": ["01_reoriented.nii.gz"],
    },
    "nibabel": {
        "image": "duattran05/mri-nibabel-utils:latest",
        "dockerfile": "docker/nibabel-utils",
        "stage": "reorientation",
        "needs_license": False,
        "output_in_work": True,
        "output_files": ["01_nibabel_reoriented.nii.gz"],
    },
    # Stage 2: Brain extraction
    "synthstrip": {
        "image": "mkdayyyy/mri-synthstrip:latest",
        "dockerfile": "docker/freesurfer-synthstrip",
        "base_image": "mkdayyyy/mri-freesurfer-base:latest",
        "base_dockerfile": "docker/freesurfer-base",
        "stage": "brain_extraction",
        "needs_license": True,
        "output_in_work": True,
        "output_files": ["02_synthstrip_brain.nii.gz"],
        "output_mask": "02_synthstrip_brain_mask.nii.gz",
    },
    "hdbet": {
        "image": "duattran05/mri-hdbet:latest",
        "dockerfile": "docker/hdbet",
        "stage": "brain_extraction",
        "needs_license": False,
        "output_in_work": True,
        "output_files": ["02_hdbet_brain.nii.gz"],
        "output_mask": "02_hdbet_brain_bet.nii.gz",
        "extra_mounts": {"hdbet_weights": "/root/.cache/torch/hub/checkpoints"},
    },
    # Stage 3: Segmentation
    "synthseg_freesurfer": {
        "image": "mkdayyyy/mri-synthseg-freesurfer:latest",
        "dockerfile": "docker/freesurfer-synthseg",
        "base_image": "mkdayyyy/mri-freesurfer-base:latest",
        "base_dockerfile": "docker/freesurfer-base",
        "stage": "segmentation",
        "needs_license": True,
        "output_in_work": True,
        "output_files": ["03_freesurfer_synthseg_segmentation.nii.gz"],
    },
    "synthseg_standalone": {
        "image": "duattran05/mri-synthseg-standalone:latest",
        "dockerfile": "docker/synthseg-standalone",
        "stage": "segmentation",
        "needs_license": False,
        "output_in_work": False,
        "output_files": ["03_synthseg_standalone_segmentation.nii.gz"],
    },
    "fastsurfervinn": {
        "image": "duattran05/mri-fastsurfervinn:latest",
        "dockerfile": "docker/fastsurfervinn",
        "stage": "segmentation",
        "needs_license": True,
        "output_in_work": False,
        "output_files": ["03_fastsurfervinn_segmentation.nii.gz"],
    },
    # Stage 4: Bias correction
    "ants_n4": {
        "image": "duattran05/mri-ants:latest",
        "dockerfile": "docker/ants",
        "stage": "bias_correction",
        "needs_license": False,
        "output_in_work": True,
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
    output_dir: str
    work_dir: str
    subject_id: str
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
# Runner
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[str, str, float, str], None]  # (stage, status, pct, msg)
BuildLogCallback = Callable[[str], None]  # called per line of docker build output

PROJECT_ROOT = Path(__file__).parent


def image_exists(image: str) -> bool:
    """Check if a Docker image exists locally."""
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
    """Build a Docker image, streaming output line-by-line. Returns True on success."""
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
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # Track which progress bars we've already emitted (by layer hash)
        # so we only send the final state, not every intermediate update
        last_progress: dict[str, str] = {}  # layer_id -> last line seen
        pending_non_progress: list[str] = []

        def flush_progress():
            """Emit only the latest state of each progress bar."""
            for line in last_progress.values():
                if on_build_log:
                    on_build_log(line)
            last_progress.clear()

        raw = ""
        for chunk in proc.stdout:  # type: ignore[union-attr]
            raw += chunk
            while "\n" in raw or "\r" in raw:
                # Find the earliest line break
                idx_n = raw.find("\n")
                idx_r = raw.find("\r")
                if idx_n == -1:
                    idx = idx_r
                elif idx_r == -1:
                    idx = idx_n
                else:
                    idx = min(idx_n, idx_r)

                line = raw[:idx].strip()
                raw = raw[idx + 1:]

                if not line:
                    continue

                # Is this a progress bar line? (contains MB/s or GB/s and %)
                if ("MB/s" in line or "GB/s" in line or "kB/s" in line) and "%" in line:
                    # Extract layer ID (e.g., "#5" at the start)
                    parts = line.split()
                    layer_id = parts[0] if parts and parts[0].startswith("#") else line[:20]
                    last_progress[layer_id] = line
                else:
                    # Non-progress line: flush pending progress first, then emit
                    flush_progress()
                    if on_build_log:
                        on_build_log(line)

        # Flush any remaining progress and raw data
        flush_progress()
        if raw.strip():
            if on_build_log:
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


def _try_pull(image: str, on_progress: ProgressCallback | None = None, on_build_log: BuildLogCallback | None = None) -> bool:
    """Try to pull an image from Docker Hub. Returns True on success."""
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
        for chunk in proc.stdout:  # type: ignore[union-attr]
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
    """Ensure a Docker image exists. Pulls or builds as needed.
    Returns (success, error_message, total_build_seconds)."""
    tool = TOOL_DEFS.get(tool_key)
    if not tool:
        return False, f"Unknown tool: {tool_key}", 0.0

    image = tool["image"]
    total_build = 0.0

    # --- Base image ---
    base_image = tool.get("base_image")
    base_dockerfile = tool.get("base_dockerfile")
    if base_image and not image_exists(base_image):
        # Try pull first
        if on_progress:
            on_progress("build", "running", 0, f"Pulling base {base_image}...")
        t0 = time.time()
        pulled = _try_pull(base_image, on_progress, on_build_log)
        total_build += time.time() - t0
        if not pulled:
            # Fall back to build
            if base_dockerfile:
                if on_progress:
                    on_progress("build", "running", 0, f"Pull failed, building {base_image}...")
                t0 = time.time()
                if not build_image(base_image, base_dockerfile, on_progress, on_build_log):
                    return False, f"Failed to get base image {base_image}", total_build
                total_build += time.time() - t0
            else:
                return False, f"Base image {base_image} not available and no Dockerfile", total_build

    # --- Tool image ---
    if not image_exists(image):
        # Try pull first
        if on_progress:
            on_progress("build", "running", 0, f"Pulling {image}...")
        t0 = time.time()
        pulled = _try_pull(image, on_progress, on_build_log)
        total_build += time.time() - t0
        if not pulled:
            # Fall back to build
            dockerfile = tool.get("dockerfile")
            if dockerfile:
                if on_progress:
                    on_progress("build", "running", 0, f"Pull failed, building {image}...")
                t0 = time.time()
                if not build_image(image, dockerfile, on_progress, on_build_log):
                    return False, f"Failed to build {image}", total_build
                total_build += time.time() - t0
            else:
                return False, f"Image {image} not available and no Dockerfile", total_build

    return True, "", total_build


def _run_docker(
    image: str,
    args: list[str],
    mounts: dict[str, str],
    env: dict[str, str] | None = None,
    gpus: bool = False,
    timeout: int = 7200,
) -> tuple[int, str]:
    """Run a Docker container and return (exit_code, combined_output)."""
    cmd = ["docker", "run", "--rm"]
    if gpus:
        cmd += ["--gpus", "all"]
    for host_path, container_path in mounts.items():
        host_path = os.path.abspath(host_path)
        cmd += ["-v", f"{host_path}:{container_path}"]
    if env:
        for k, v in env.items():
            cmd += ["-e", f"{k}={v}"]
    cmd.append(image)
    cmd += args

    log.info("Running: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        output = proc.stdout + "\n" + proc.stderr
        return proc.returncode, output
    except subprocess.TimeoutExpired:
        return -1, f"Docker timed out after {timeout}s"
    except FileNotFoundError:
        return -1, "docker not found — is Docker installed and in PATH?"


def _resolve_input_mount(input_file: str) -> tuple[str, str, str]:
    """Return (host_input_dir, container_input_path, filename_inside_container)."""
    p = os.path.abspath(input_file)
    parent = os.path.dirname(p)
    name = os.path.basename(p)
    return parent, "/input", f"/input/{name}"


def _find_input_file(work_dir: str, possible_names: list[str]) -> str | None:
    """Look for an output file from a previous step in work_dir."""
    for name in possible_names:
        candidate = Path(work_dir) / name
        if candidate.exists():
            return str(candidate)
    return None


def run_pipeline(
    config: PipelineConfig,
    on_progress: ProgressCallback | None = None,
    on_build_log: BuildLogCallback | None = None,
) -> list[StepResult]:
    """Execute the full pipeline and return results per stage."""

    def progress(stage: str, status: str, pct: float, msg: str):
        if on_progress:
            on_progress(stage, status, pct, msg)
        log.info("[%s] %s (%.0f%%) %s", stage, status, pct * 100, msg)

    # Ensure directories exist
    out_abs = os.path.abspath(config.output_dir)
    work_abs = os.path.abspath(config.work_dir)
    Path(out_abs).mkdir(parents=True, exist_ok=True)
    Path(work_abs).mkdir(parents=True, exist_ok=True)

    # Prepare license mount
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

        # Ensure image exists (auto-build if needed)
        ok, err, build_time = ensure_image(tool_key, on_progress=on_progress, on_build_log=on_build_log)
        if not ok:
            result = StepResult(
                stage=stage, tool=tool_key, success=False, duration_sec=0,
                build_duration_sec=build_time,
                error=f"Image not available: {err}",
            )
            results.append(result)
            progress(stage, "failed", (stage_idx + 1) / total_stages,
                     f"{STAGE_LABELS[stage]} FAILED: {err}")
            break

        # Determine input
        if input_for_next_step is None:
            host_input_dir, container_input_dir, input_path = _resolve_input_mount(config.input_file)
            mounts = {host_input_dir: container_input_dir}
        else:
            # Use output from previous step — convert host path to container path
            # The work dir is mounted at /work, so replace host prefix with /work
            if input_for_next_step.startswith(work_abs):
                rel = input_for_next_step[len(work_abs):].lstrip("/")
                input_path = f"/work/{rel}"
            else:
                input_path = input_for_next_step
            mounts = {}

        # Standard mounts
        mounts[out_abs] = "/output"
        mounts[work_abs] = "/work"
        if tool["needs_license"] and license_mount:
            mounts.update(license_mount)

        # Extra mounts (e.g. hdbet weights cache)
        extra = tool.get("extra_mounts", {})
        for rel, container in extra.items():
            host = os.path.join(work_abs, rel)
            Path(host).mkdir(parents=True, exist_ok=True)
            mounts[host] = container

        # Build CLI args
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
            image=tool["image"],
            args=args,
            mounts=mounts,
            gpus=(config.device == "gpu"),
        )
        duration = time.time() - t0

        # Check result
        success = code == 0
        if success:
            # Verify output exists
            for fname in tool["output_files"]:
                candidate = os.path.join(work_abs, fname)
                if not os.path.exists(candidate):
                    # Some tools put output in output_dir/work/
                    candidate = os.path.join(out_abs, "work", fname)
                if os.path.exists(candidate):
                    success = True
                    input_for_next_step = candidate
                    break
            else:
                success = False

        result = StepResult(
            stage=stage,
            tool=tool_key,
            success=success,
            duration_sec=duration,
            build_duration_sec=build_time,
            log_text=output[-2000:] if output else "",
            output_files=tool["output_files"],
            error="" if success else f"exit code {code}",
        )
        results.append(result)

        if success:
            msg = f"{STAGE_LABELS[stage]} done in {duration:.0f}s"
            if build_time > 0:
                msg += f" (build: {build_time:.0f}s)"
            progress(stage, "success", (stage_idx + 1) / total_stages, msg)
        else:
            progress(stage, "failed", (stage_idx + 1) / total_stages,
                     f"{STAGE_LABELS[stage]} FAILED: {result.error}")
            break  # Stop pipeline on failure

    return results
