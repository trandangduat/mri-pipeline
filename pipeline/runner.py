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
from .stats import StatsGenerator, StatsResult
from .reports import write_batch_reports, BatchReportContext

from .export import _export_stage_outputs, _safe_export_stem
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
    StepResult,
    ToolContext,
)
from .registry import (
    STAGE_LABELS,
    STAGE_ORDER,
    TOOL_DEFS,
    is_tool_enabled,
    tool_display_name,
)
from .docker_ops import ensure_image
from .executor import LocalDockerExecutor
from .state import PipelineTracker
from .discovery import (
    _derive_subject_id,
    _dicom_files_in_series,
    _discover_mri_files,
    _duplicate_basenames,
    _first_dicom_file_in_series,
    build_subject_id_map,
)
from .utils import (
    _safe_container_name,
)
from .workspace import (
    _check_output_workspace,
    _describe_subject_files,
    _find_output_file,
    _organize_output,
    _repair_host_permissions,
)
from .reports import (
    _append_step_log,
    _format_bytes,
    _write_batch_benchmark_reports,
    _write_pipeline_metrics_log,
)
from .hardware import (
    _total_ram_bytes,
)


log = logging.getLogger(__name__)




def _docker_memory_limit_bytes(ram_percent: int) -> int | None:
    pct = max(1, min(int(ram_percent), 100))
    if pct >= 100:
        return None
    total = _total_ram_bytes()
    if not total:
        return None
    return max(1, int(total * pct / 100))




































































def run_pipeline(
    config: PipelineConfig,
    on_progress: ProgressCallback | None = None,
    on_build_log: Callable[[str], None] | None = None,
    on_metrics: MetricsCallback | None = None,
    should_stop: Callable[[], bool] | None = None,
    executor=None,
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

    tracker = PipelineTracker(logs_dir, config, subject_dir)
    tracker.mark_started(config.selected_tools)

    license_mount: list[tuple[str, str]] = []
    if config.license_dir:
        lic_path = Path(config.license_dir).absolute()
        license_mount.append((str(lic_path), "/license/license.txt" if lic_path.is_file() else "/license"))

    results: list[StepResult] = []
    input_for_next_step: str | None = None
    total_stages = len(STAGE_ORDER)
    paused = False
    ram_percent = max(1, min(int(config.ram_percent), 100))
    memory_limit_bytes = _docker_memory_limit_bytes(ram_percent)

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
                from .state import StageResult
                tracker.mark_stage_completed(StageResult(
                    stage=stage,
                    tool=tool_key,
                    success=True,
                    output_file=resumed_output,
                    outputs_found=resumed_outputs,
                    duration_sec=0.0
                ))
                results.append(StepResult(stage=stage, tool=tool_key, success=True, duration_sec=0.0, output_files=tool["output_files"], log_text="resumed from verified output files"))
                progress(stage, "success", (stage_idx + 1) / total_stages, f"Resume: verified outputs and skipped {STAGE_LABELS[stage]} with {tool_display_name(tool_key)}")
                continue

        progress(stage, "running", stage_pct, f"Starting {STAGE_LABELS[stage]} with {tool_display_name(tool_key)}")
        tracker.mark_stage_running(stage, tool_key)

        ok, err, build_time = ensure_image(tool_key, on_progress=on_progress, on_build_log=on_build_log)
        if not ok:
            error = f"Image not available: {err}"
            from .state import StageResult
            tracker.mark_stage_completed(StageResult(stage=stage, tool=tool_key, success=False, error=error))
            results.append(StepResult(stage=stage, tool=tool_key, success=False, duration_sec=0, build_duration_sec=build_time, error=error))
            progress(stage, "failed", (stage_idx + 1) / total_stages, f"{STAGE_LABELS[stage]} FAILED: {err}")
            break

        executor = executor or LocalDockerExecutor()
        exec_result = executor.execute(
            tool_key=tool_key,
            stage=stage,
            input_file=input_for_next_step,
            subject_dir=subject_dir,
            config=config,
            logs_dir=logs_dir,
            memory_limit_bytes=memory_limit_bytes,
            on_metrics=on_metrics
        )
        
        peak_ram = exec_result.metrics.peak_ram_bytes if exec_result.metrics else None
        peak_cpu = exec_result.metrics.peak_cpu_pct if exec_result.metrics else None
        duration = exec_result.duration_sec
        metrics = exec_result.metrics
        success = exec_result.success
        error = exec_result.error
        output = exec_result.output
        
        _organize_output(subject_dir, preserve_dirs={_safe_export_stem(config.export_config.folder, "exports")})
        
        if not success and output.strip():
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

        outputs_found = tracker.find_existing_outputs(subject_dir, tool["output_files"], tool.get("output_globs", [])) if success else []
        exported_outputs: list[str] = []
        export_error = ""
        if success:
            exported_outputs, export_error = _export_stage_outputs(subject_dir, stage, outputs_found, config.export_config)
            if export_error:
                progress(stage, "running", (stage_idx + 1) / total_stages, f"Export warning: {export_error}")
        from .state import StageResult
        result = StageResult(
            stage=stage,
            tool=tool_key,
            success=success,
            output_file=input_for_next_step if success and input_for_next_step else "",
            outputs_found=outputs_found,
            error=error,
            duration_sec=duration
        )
        tracker.mark_stage_completed(result)
        if success and (exported_outputs or export_error):
            tracker.add_exported_outputs(stage, exported_outputs, export_error)

        step_log_lines = [
            f"Stage: {stage}",
            f"Tool: {tool_display_name(tool_key)}",
            f"Duration: {duration:.1f}s",
            f"Build: {build_time:.1f}s",
            f"RAM limit: {_format_bytes(memory_limit_bytes)} ({ram_percent}%)" if memory_limit_bytes else f"RAM limit: unlimited ({ram_percent}%)",
            f"Peak RAM: {_format_bytes(peak_ram)}",
            f"Mean RAM: {_format_bytes(metrics.avg_ram_bytes)}",
            f"P95 RAM: {_format_bytes(metrics.p95_ram_bytes)}",
            f"Peak CPU: {peak_cpu:.0f}%" if peak_cpu is not None else "Peak CPU: n/a",
            f"Mean CPU: {metrics.avg_cpu_pct:.1f}%" if metrics.avg_cpu_pct is not None else "Mean CPU: n/a",
            f"P95 CPU: {metrics.p95_cpu_pct:.1f}%" if metrics.p95_cpu_pct is not None else "P95 CPU: n/a",
            f"Exit code: {code}",
        ]
        if exported_outputs:
            step_log_lines.append("Exported outputs: " + "; ".join(exported_outputs))
        if export_error:
            step_log_lines.append("Export warning: " + export_error)
        if output.strip():
            step_log_lines.append(f"\n--- Output ---\n{output[-3000:]}")
        _append_step_log(logs_dir, tool_key, step_log_lines)

        results.append(StepResult(stage=stage, tool=tool_key, success=success, duration_sec=duration, build_duration_sec=build_time, peak_ram_bytes=peak_ram, avg_ram_bytes=metrics.avg_ram_bytes, p95_ram_bytes=metrics.p95_ram_bytes, peak_cpu_pct=peak_cpu, avg_cpu_pct=metrics.avg_cpu_pct, p95_cpu_pct=metrics.p95_cpu_pct, log_text=output[-2000:] if output else "", output_files=tool["output_files"], error=error))

        if success:
            msg = f"{STAGE_LABELS[stage]} done in {duration:.0f}s"
            if build_time > 0:
                msg += f" (build: {build_time:.0f}s)"
            progress(stage, "success", (stage_idx + 1) / total_stages, msg)
            if should_stop and should_stop():
                paused = True
                tracker.mark_paused(stage)
                progress("pipeline", "paused", (stage_idx + 1) / total_stages, f"Paused after {STAGE_LABELS[stage]}. Resume will verify outputs and continue from the next incomplete stage.")
                break
        else:
            progress(stage, "failed", (stage_idx + 1) / total_stages, f"{STAGE_LABELS[stage]} FAILED: {error}")
            break

    if paused:
        tracker.mark_paused()
    else:
        success = bool(results and all(r.success for r in results))
        tracker.mark_completed(success)
    generator = StatsGenerator(config.stats_vector_config)
    result = generator.generate(subject_dir, config.subject_id)
    generated_vectors, vector_warnings = result.files, result.warnings
    if generated_vectors or vector_warnings:
        tracker.set_stats_vectors(generated_vectors, vector_warnings)
        if vector_warnings:
            _append_step_log(logs_dir, "stats_vectors", ["Stats vector warnings:", *vector_warnings])
        if generated_vectors:
            _append_step_log(logs_dir, "stats_vectors", ["Generated stats vectors:", *generated_vectors])
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
    ram_percent: int = 100,
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
    batch_config: dict | None = None,
) -> list[BatchImageResult]:
    if input_files is None:
        input_files = _discover_mri_files(input_dir, recursive=recursive)
    used_subject_ids: set[str] = set()
    batch_results: list[BatchImageResult] = []
    total = len(input_files)
    dup_basenames = _duplicate_basenames(input_files)
    dataset_root = str(Path(input_dir).expanduser().resolve())
    benchmark_config = dict(batch_config or {})
    benchmark_config.setdefault("version", 1)
    benchmark_config.setdefault("input_dir", input_dir)
    benchmark_config.setdefault("output_dir", output_dir)
    benchmark_config.setdefault("effective_output_dir", output_dir)
    benchmark_config.setdefault("license_dir", license_dir)
    benchmark_config.setdefault("device", device)
    benchmark_config.setdefault("threads", threads)
    benchmark_config.setdefault("ram_percent", ram_percent)
    benchmark_config.setdefault("selected_tools", selected_tools or PipelineConfig("", "", "").selected_tools)
    benchmark_config.setdefault("export_config", (export_config or ExportConfig()).to_dict())
    benchmark_config.setdefault("stats_vector_config", (stats_vector_config or StatsVectorConfig()).to_dict())
    benchmark_config.setdefault("recursive", recursive)
    benchmark_config.setdefault("input_file_count", total)
    report_stats_config = stats_vector_config or StatsVectorConfig()
    ctx = BatchReportContext(output_dir=output_dir, input_files=input_files, batch_results=batch_results, subject_id_map=subject_id_map, dataset_root=dataset_root, stats_vector_config=report_stats_config, running_input_file=input_file if 'input_file' in locals() else '')
    write_batch_reports(ctx)

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
        ctx = BatchReportContext(output_dir=output_dir, input_files=input_files, batch_results=batch_results, subject_id_map=subject_id_map, dataset_root=dataset_root, stats_vector_config=report_stats_config, running_input_file=input_file if 'input_file' in locals() else '')
        write_batch_reports(ctx)

        try:
            config = PipelineConfig(input_file=input_file, output_dir=output_dir, subject_id=subject_id, license_dir=license_dir, device=device, threads=threads, ram_percent=ram_percent, resume=resume, export_config=export_config or ExportConfig(), stats_vector_config=stats_vector_config or StatsVectorConfig(), selected_tools=selected_tools or PipelineConfig(input_file, output_dir, subject_id).selected_tools)
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
            _write_pipeline_metrics_log(str(logs_dir), PipelineConfig(input_file=input_file, output_dir=output_dir, subject_id=subject_id, license_dir=license_dir, device=device, threads=threads, ram_percent=ram_percent, selected_tools=selected_tools or PipelineConfig(input_file, output_dir, subject_id).selected_tools), subject_dir, steps, started_at, time.time())

        image_result = BatchImageResult(input_file=input_file, subject_id=subject_id, subject_dir=subject_dir, success=success, duration_sec=time.time() - started_at, steps=steps, error=error)
        batch_results.append(image_result)
        ctx = BatchReportContext(output_dir=output_dir, input_files=input_files, batch_results=batch_results, subject_id_map=subject_id_map, dataset_root=dataset_root, stats_vector_config=report_stats_config, running_input_file=input_file if 'input_file' in locals() else '')
        write_batch_reports(ctx)
        if on_image_done:
            on_image_done(image_result, idx, total)
    if batch_results:
        _write_batch_benchmark_reports(output_dir, batch_results, benchmark_config)
    return batch_results
