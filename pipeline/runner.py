from __future__ import annotations

import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from .config import (
    BatchImageResult,
    MetricsCallback,
    PipelineConfig,
    ProgressCallback,
    STAGE_LABELS,
    STAGE_ORDER,
    StepResult,
    TOOL_DEFS,
    ToolContext,
    is_tool_enabled,
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
    _write_pipeline_metrics_log,
    _write_pipeline_state,
)


log = logging.getLogger(__name__)


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
        if not tool_key or tool_key not in TOOL_DEFS:
            continue
        if not is_tool_enabled(tool_key):
            progress(stage, "success", (stage_idx + 1) / total_stages, f"Skipping disabled tool: {tool_key}")
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
                progress(stage, "success", (stage_idx + 1) / total_stages, f"Resume: verified outputs and skipped {STAGE_LABELS[stage]} with {tool_key}")
                continue

        progress(stage, "running", stage_pct, f"Starting {STAGE_LABELS[stage]} with {tool_key}")
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
            command = ["bash", "-c", actual_cmd]
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
            on_metrics=_metrics_relay if on_metrics else None,
        )
        duration = time.time() - t0
        _repair_host_permissions(subject_dir, tool["image"])
        _organize_output(subject_dir)

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
        _set_stage_state(logs_dir, state, stage, tool_key, "completed" if success else "failed", output_file=input_for_next_step if success and input_for_next_step else "", output_files_found=outputs_found, error=error, duration_sec=duration)

        step_log_lines = [
            f"Stage: {stage}",
            f"Tool: {tool_key}",
            f"Duration: {duration:.1f}s",
            f"Build: {build_time:.1f}s",
            f"Peak RAM: {_format_bytes(peak_ram)}",
            f"Peak CPU: {peak_cpu:.0f}%" if peak_cpu is not None else "Peak CPU: n/a",
            f"Exit code: {code}",
        ]
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
        subject_id = _unique_subject_id(input_file, used_subject_ids, dataset_root, dup_basenames)
        subject_dir = os.path.join(os.path.abspath(output_dir), subject_id)
        started_at = time.time()
        if on_image_start:
            on_image_start(input_file, idx, total)
        if on_progress:
            on_progress("batch", "running", (idx - 1) / total if total else 0, f"Starting image {idx}/{total}: {input_file}")

        try:
            config = PipelineConfig(input_file=input_file, output_dir=output_dir, subject_id=subject_id, license_dir=license_dir, device=device, threads=threads, resume=resume, selected_tools=selected_tools or PipelineConfig(input_file, output_dir, subject_id).selected_tools)
            steps = run_pipeline(config, on_progress=on_progress, on_build_log=on_build_log, on_metrics=on_metrics, should_stop=should_stop)
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

        image_result = BatchImageResult(input_file=input_file, subject_id=subject_id, subject_dir=subject_dir, success=success, duration_sec=time.time() - started_at, steps=steps, error=error)
        batch_results.append(image_result)
        if on_image_done:
            on_image_done(image_result, idx, total)
    return batch_results
