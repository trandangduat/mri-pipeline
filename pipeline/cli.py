from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .config import BatchImageResult, ExportConfig, PROJECT_ROOT, PipelineConfig, STAGE_ORDER, TOOL_DEFS, StatsVectorConfig, enabled_tools_for_stage, is_tool_enabled, tool_display_name
from .docker_ops import ensure_image
from .runner import run_batch_pipeline, run_pipeline
from .utils import _derive_subject_id, _discover_mri_files, _duplicate_basenames


DEFAULT_BATCH_INPUT_DIR = "/mnt/c/Users/ADMIN/Desktop/MRI/ADNI"


def _cli_selected_tools(args: argparse.Namespace) -> dict[str, str]:
    return {
        "reorientation": args.reorientation,
        "brain_extraction": args.brain_extraction,
        "segmentation": args.segmentation,
        "template_registration": args.template_registration,
        "bias_correction": args.bias_correction,
        "white_matter_segmentation": args.white_matter_segmentation,
        "surface_reconstruction": args.surface_reconstruction,
        "surface_registration": args.surface_registration,
        "stats_extraction": args.stats_extraction,
    }


def _load_export_config(path: str) -> ExportConfig:
    if not path:
        return ExportConfig()
    with open(path, "r", encoding="utf-8") as f:
        return ExportConfig.from_dict(json.load(f))


def _load_subject_id_map(path: str) -> dict[str, str]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {str(k): str(v) for k, v in dict(data).items()}


def _load_stats_vector_config(path: str) -> StatsVectorConfig:
    if not path:
        return StatsVectorConfig()
    with open(path, "r", encoding="utf-8") as f:
        return StatsVectorConfig.from_dict(json.load(f))


def _cli_progress(stage: str, status: str, pct: float, msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {status.upper()} {stage}: {msg}", flush=True)


def _cli_build_log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] DOCKER: {msg}", flush=True)


def _cli_image_done(result: BatchImageResult, idx: int, total: int) -> None:
    status = "OK" if result.success else "FAILED"
    metrics_log = Path(result.subject_dir) / "logs" / "pipeline_metrics.log"
    print(f"Đã xử lý xong ảnh {idx}/{total}: {result.input_file} | status={status} | log={metrics_log}", flush=True)


def _emit_json_event(kind: str, **payload) -> None:
    print("MRI_EVENT " + json.dumps({"kind": kind, **payload}, ensure_ascii=False), flush=True)


def main(argv: list[str] | None = None) -> int:
    default_tools = PipelineConfig("", "", "").selected_tools
    tools_by_stage = {stage: enabled_tools_for_stage(stage) for stage in STAGE_ORDER}
    parser = argparse.ArgumentParser(description="Run the MRI pipeline for one file or a sequential batch folder.", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input-file", help="Run one MRI file only")
    source.add_argument("--input-dir", help="Run every supported MRI file in this folder")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "outputs"), help="Base output directory")
    parser.add_argument("--license-dir", default=str(PROJECT_ROOT / "license"), help="FreeSurfer license directory")
    parser.add_argument("--device", choices=["cpu", "gpu"], default="cpu", help="Execution device")
    parser.add_argument("--threads", type=int, default=4, help="CPU threads passed to tools")
    parser.add_argument("--ram-percent", type=int, default=100, help="Percent of host RAM available to each Docker container (100 disables Docker memory limit)")
    parser.add_argument("--resume", action="store_true", help="Verify existing outputs in pipeline_state.json/output folders and continue from the next incomplete stage")
    parser.add_argument("--stop-file", default="", help="Pause safely after current stage if this file exists")
    parser.add_argument("--non-recursive", action="store_true", help="Only scan files directly inside --input-dir")
    parser.add_argument("--json-events", action="store_true", help="Emit machine-readable progress events for GUI clients")
    parser.add_argument("--ensure-images-only", action="store_true", help="Only pull/build/check selected Docker images, then exit")
    parser.add_argument("--export-config", default="", help="JSON file with exported output names and formats")
    parser.add_argument("--subject-id-map", default="", help="JSON map from input path to output subject ID")
    parser.add_argument("--stats-vector-config", default="", help="JSON file with requested stat vectors and atlases")

    def add_tool_option(option: str, stage: str) -> None:
        choices = tools_by_stage[stage]
        if choices:
            parser.add_argument(option, choices=choices, default=default_tools[stage])
        else:
            parser.add_argument(option, default="", help="Temporarily disabled; no enabled tools for this stage")

    add_tool_option("--reorientation", "reorientation")
    add_tool_option("--brain-extraction", "brain_extraction")
    add_tool_option("--segmentation", "segmentation")
    add_tool_option("--template-registration", "template_registration")
    add_tool_option("--bias-correction", "bias_correction")
    add_tool_option("--white-matter-segmentation", "white_matter_segmentation")
    add_tool_option("--surface-reconstruction", "surface_reconstruction")
    add_tool_option("--surface-registration", "surface_registration")
    add_tool_option("--stats-extraction", "stats_extraction")
    args = parser.parse_args(argv)
    selected_tools = _cli_selected_tools(args)
    export_config = _load_export_config(args.export_config)
    subject_id_map = _load_subject_id_map(args.subject_id_map)
    stats_vector_config = _load_stats_vector_config(args.stats_vector_config)

    if args.ram_percent < 1 or args.ram_percent > 100:
        print("--ram-percent must be between 1 and 100", file=sys.stderr, flush=True)
        return 2

    if args.ensure_images_only:
        ok = True
        for tool_key in (tool for tool in dict.fromkeys(selected_tools.values()) if tool and is_tool_enabled(tool)):
            if args.json_events:
                _emit_json_event("image_preflight", tool=tool_key, status="running")
            result, err, _build_time = ensure_image(tool_key, on_progress=_cli_progress, on_build_log=_cli_build_log)
            if not result:
                ok = False
                if args.json_events:
                    _emit_json_event("image_preflight", tool=tool_key, status="failed", error=err)
                print(f"Image preflight failed for {tool_display_name(tool_key)}: {err}", file=sys.stderr, flush=True)
                break
            if args.json_events:
                _emit_json_event("image_preflight", tool=tool_key, status="success")
        return 0 if ok else 2

    progress_cb = _cli_progress
    metrics_cb = None
    image_start_cb = None
    image_done_cb = _cli_image_done
    if args.json_events:
        def progress_cb(stage: str, status: str, pct: float, msg: str) -> None:
            _cli_progress(stage, status, pct, msg)
            _emit_json_event("progress", stage=stage, status=status, pct=pct, msg=msg)

        def metrics_cb(stage: str, tool: str, cpu_pct: float | None, ram_bytes: int | None, elapsed: float, container_name: str) -> None:
            _emit_json_event("metrics", stage=stage, tool=tool, cpu_pct=cpu_pct, ram_bytes=ram_bytes, elapsed=elapsed, container_name=container_name, gpu_pct=0.0)

        def image_start_cb(input_file: str, idx: int, total: int) -> None:
            _emit_json_event("image_start", input_file=input_file, idx=idx, total=total)

        def image_done_cb(result: BatchImageResult, idx: int, total: int) -> None:
            _cli_image_done(result, idx, total)
            _emit_json_event("image_done", input_file=result.input_file, subject_id=result.subject_id, idx=idx, total=total, success=result.success, error=result.error)

    should_stop = (lambda: Path(args.stop_file).exists()) if args.stop_file else None
    if args.input_file:
        input_path = str(Path(args.input_file).expanduser().resolve())
        root = args.input_dir or str(Path(input_path).parent)
        subject_id = subject_id_map.get(args.input_file) or subject_id_map.get(input_path) or _derive_subject_id(input_path, root, _duplicate_basenames([input_path]) if args.input_dir else None)
        config = PipelineConfig(input_file=args.input_file, output_dir=args.output_dir, subject_id=subject_id, license_dir=args.license_dir, device=args.device, threads=args.threads, ram_percent=args.ram_percent, resume=args.resume, export_config=export_config, stats_vector_config=stats_vector_config, selected_tools=selected_tools)
        if image_start_cb:
            image_start_cb(args.input_file, 1, 1)
        results = run_pipeline(config, on_progress=progress_cb, on_build_log=_cli_build_log, on_metrics=metrics_cb, should_stop=should_stop)
        success = bool(results) and all(step.success for step in results)
        subject_dir = Path(args.output_dir).resolve() / subject_id
        print(f"Đã xử lý xong ảnh: {args.input_file} | status={'OK' if success else 'FAILED'} | log={subject_dir / 'logs' / 'pipeline_metrics.log'}", flush=True)
        if args.json_events:
            _emit_json_event("image_done", input_file=args.input_file, subject_id=subject_id, idx=1, total=1, success=success, error="" if success else "one or more pipeline steps failed")
        return 0 if success else 1

    input_dir = args.input_dir or DEFAULT_BATCH_INPUT_DIR
    input_files = _discover_mri_files(input_dir, recursive=not args.non_recursive)
    if not input_files:
        print(f"Không tìm thấy file MRI hợp lệ trong folder: {input_dir}", file=sys.stderr, flush=True)
        return 1
    print(f"Tìm thấy {len(input_files)} ảnh MRI trong {input_dir}. Bắt đầu xử lý tuần tự.", flush=True)
    batch_results = run_batch_pipeline(input_dir=input_dir, output_dir=args.output_dir, license_dir=args.license_dir, device=args.device, threads=args.threads, ram_percent=args.ram_percent, resume=args.resume, selected_tools=selected_tools, export_config=export_config, stats_vector_config=stats_vector_config, subject_id_map=subject_id_map, recursive=not args.non_recursive, on_progress=progress_cb, on_build_log=_cli_build_log, on_image_start=image_start_cb, on_image_done=image_done_cb, on_metrics=metrics_cb, should_stop=should_stop)
    failed = [result for result in batch_results if not result.success]
    print(f"Batch hoàn tất: {len(batch_results) - len(failed)}/{len(batch_results)} ảnh thành công.", flush=True)
    return 1 if failed else 0
