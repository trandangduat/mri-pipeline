from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

from .config import BatchImageResult, ExportConfig, PipelineConfig, StatsVectorConfig
from .jobs import read_json, write_json
from .runner import _write_stats_vector_reports, run_batch_pipeline, run_pipeline
from .utils import _derive_subject_id, _discover_mri_files, build_subject_id_map


def _append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _emit_event(job_dir: Path, kind: str, **payload) -> None:
    event = {"kind": kind, "time": time.time(), **payload}
    line = "MRI_EVENT " + json.dumps(event, ensure_ascii=False)
    _append_line(job_dir / "events.jsonl", json.dumps(event, ensure_ascii=False))
    _append_line(job_dir / "run.log", line)


def _log(job_dir: Path, message: str) -> None:
    ts = time.strftime("%H:%M:%S")
    _append_line(job_dir / "run.log", f"[{ts}] {message}")


def _write_status(job_path: Path, **updates) -> None:
    status_path = job_path / "job_status.json"
    status = read_json(status_path, {})
    status.update(updates)
    status["updated_at"] = time.time()
    write_json(status_path, status)


def _delete_restart_outputs(req: dict, job_dir: Path) -> None:
    output_dir = Path(req.get("effective_output_dir", req["output_dir"])).resolve()
    mode = req.get("mode")
    subject_id_map = req.get("subject_id_map") if isinstance(req.get("subject_id_map"), dict) else {}
    subject_ids: list[str]
    if mode == "file":
        subject_ids = [req.get("subject_id") or subject_id_map.get(req["input_file"]) or _derive_subject_id(req["input_file"])]
    elif mode == "files":
        files = req.get("input_files", [])
        subject_id_map = subject_id_map or build_subject_id_map(files, req.get("input_dir", ""))
        subject_ids = [subject_id_map.get(path, _derive_subject_id(path)) for path in files]
    else:
        files = _discover_mri_files(req.get("input_dir", ""), recursive=req.get("recursive", True))
        subject_id_map = subject_id_map or build_subject_id_map(files, req.get("input_dir", ""))
        subject_ids = [subject_id_map.get(path, _derive_subject_id(path)) for path in files]

    for subject_id in subject_ids:
        subject_dir = output_dir / subject_id
        if subject_dir.exists():
            _log(job_dir, f"Restart: removing {subject_dir}")
            shutil.rmtree(subject_dir)


def _run_job(job_dir: Path, req: dict) -> int:
    stop_file = job_dir / "stop_requested"
    mode = req.get("mode")
    output_dir = req.get("effective_output_dir", req.get("output_dir", ""))
    selected_tools = req.get("selected_tools", {})
    export_config = ExportConfig.from_dict(req.get("export_config"))
    stats_vector_config = StatsVectorConfig.from_dict(req.get("stats_vector_config"))

    def progress_cb(stage: str, status: str, pct: float, msg: str) -> None:
        _log(job_dir, f"{status.upper()} {stage}: {msg}")
        _emit_event(job_dir, "progress", stage=stage, status=status, pct=pct, msg=msg)

    def build_log_cb(msg: str) -> None:
        _log(job_dir, f"DOCKER: {msg}")

    def metrics_cb(stage: str, tool: str, cpu_pct: float | None, ram_bytes: int | None, elapsed: float, container_name: str) -> None:
        _emit_event(
            job_dir,
            "metrics",
            stage=stage,
            tool=tool,
            cpu_pct=cpu_pct,
            ram_bytes=ram_bytes,
            elapsed=elapsed,
            container_name=container_name,
            gpu_pct=0.0,
        )

    def image_start_cb(input_file: str, idx: int, total: int) -> None:
        _log(job_dir, f"Starting image {idx}/{total}: {input_file}")
        _emit_event(job_dir, "image_start", input_file=input_file, idx=idx, total=total)

    def image_done_cb(result: BatchImageResult, idx: int, total: int) -> None:
        status = "OK" if result.success else "FAILED"
        _log(job_dir, f"Done image {idx}/{total}: {result.subject_id} | {status}")
        for step in result.steps:
            _emit_event(
                job_dir,
                "step_result",
                input_file=result.input_file,
                subject_id=result.subject_id,
                idx=idx,
                total=total,
                stage=step.stage,
                tool=step.tool,
                success=step.success,
                duration_sec=step.duration_sec,
                build_duration_sec=step.build_duration_sec,
                peak_ram_bytes=step.peak_ram_bytes,
                avg_ram_bytes=step.avg_ram_bytes,
                p95_ram_bytes=step.p95_ram_bytes,
                peak_cpu_pct=step.peak_cpu_pct,
                avg_cpu_pct=step.avg_cpu_pct,
                p95_cpu_pct=step.p95_cpu_pct,
                error=step.error,
            )
        _emit_event(
            job_dir,
            "image_done",
            input_file=result.input_file,
            subject_id=result.subject_id,
            idx=idx,
            total=total,
            success=result.success,
            error=result.error,
        )

    if req.get("restart"):
        _delete_restart_outputs(req, job_dir)

    should_stop = stop_file.exists
    if mode == "file":
        input_file = req["input_file"]
        subject_id_map = req.get("subject_id_map") if isinstance(req.get("subject_id_map"), dict) else {}
        subject_id = req.get("subject_id") or subject_id_map.get(input_file) or _derive_subject_id(input_file)
        dataset_root = str(Path(input_file).expanduser().resolve().parent)
        _write_stats_vector_reports(output_dir, [input_file], [], {input_file: subject_id}, dataset_root, stats_vector_config, running_input_file=input_file)
        image_start_cb(input_file, 1, 1)
        config = PipelineConfig(
            input_file=input_file,
            output_dir=output_dir,
            subject_id=subject_id,
            license_dir=req.get("license_dir", ""),
            device=req.get("device", "cpu"),
            threads=int(req.get("threads", 4)),
            resume=bool(req.get("resume", False)),
            export_config=export_config,
            stats_vector_config=stats_vector_config,
            selected_tools=selected_tools,
        )
        results = run_pipeline(config, on_progress=progress_cb, on_build_log=build_log_cb, on_metrics=metrics_cb, should_stop=should_stop)
        success = bool(results) and all(step.success for step in results)
        image_result = BatchImageResult(input_file, subject_id, str(Path(output_dir) / subject_id), success, 0.0, results)
        _write_stats_vector_reports(output_dir, [input_file], [image_result], {input_file: subject_id}, dataset_root, stats_vector_config)
        image_done_cb(image_result, 1, 1)
        return 0 if success else 1

    if mode == "files":
        files = list(req.get("input_files", []))
        input_dir = req.get("input_dir", "")
        recursive = True
    else:
        input_dir = req.get("input_dir", "")
        recursive = bool(req.get("recursive", True))
        files = _discover_mri_files(input_dir, recursive=recursive)

    if not files:
        _log(job_dir, f"No MRI files found in: {input_dir}")
        return 1

    _log(job_dir, f"Found {len(files)} MRI files. Running sequentially.")
    subject_id_map = req.get("subject_id_map") if isinstance(req.get("subject_id_map"), dict) else {}
    if not subject_id_map:
        subject_id_map = build_subject_id_map(files, input_dir)
    results = run_batch_pipeline(
        input_dir=input_dir,
        output_dir=output_dir,
        license_dir=req.get("license_dir", ""),
        device=req.get("device", "cpu"),
        threads=int(req.get("threads", 4)),
        resume=bool(req.get("resume", False)),
        selected_tools=selected_tools,
        export_config=export_config,
        stats_vector_config=stats_vector_config,
        subject_id_map=subject_id_map,
        recursive=recursive,
        input_files=files,
        on_progress=progress_cb,
        on_build_log=build_log_cb,
        on_image_start=image_start_cb,
        on_image_done=image_done_cb,
        on_metrics=metrics_cb,
        should_stop=should_stop,
        batch_config=req,
    )
    failed = [result for result in results if not result.success]
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one MRI GUI job in a detached worker process.")
    parser.add_argument("--job-config", required=True)
    args = parser.parse_args(argv)

    config_path = Path(args.job_config).resolve()
    job_dir = config_path.parent
    req = read_json(config_path, {})
    start = time.time()
    code = 1
    with open(job_dir / "pid.txt", "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    _write_status(job_dir, state="running", pid=os.getpid(), started_at=start, job_dir=str(job_dir), output_dir=req.get("output_dir", ""))
    _log(job_dir, f"Background job started: {job_dir}")
    try:
        code = _run_job(job_dir, req)
        state = "completed" if code == 0 else "failed"
        _write_status(job_dir, state=state, exit_code=code, finished_at=time.time(), duration_sec=time.time() - start)
        _log(job_dir, f"Background job finished with exit code {code}")
    except Exception as exc:
        code = 1
        _write_status(job_dir, state="failed", exit_code=1, error=f"{type(exc).__name__}: {exc}", finished_at=time.time(), duration_sec=time.time() - start)
        _log(job_dir, f"ERROR: {type(exc).__name__}: {exc}")
    with open(job_dir / "exit_code.txt", "w", encoding="utf-8") as f:
        f.write(str(code))
    return code


if __name__ == "__main__":
    sys.exit(main())
