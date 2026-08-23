from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .config import PROJECT_ROOT, BatchImageResult, ExportConfig, PipelineConfig, StatsVectorConfig
from .discovery import _derive_subject_id
from .hardware import _total_ram_bytes
from .presets import normalize_stats_vector_config_for_pipeline_mode
from .registry import STAGE_ORDER
from .reports import BatchReportContext, write_batch_reports
from .runner import run_pipeline_stage
from .state import PipelineTracker
from .stats import StatsGenerator


NEUROFLOW_STAGE_TO_LOCAL_STAGE = {
    "reorient_resize": "reorientation",
    "brain_extraction": "brain_extraction",
    "subcortical_segmentation": "segmentation",
    "template_registration": "template_registration",
    "image_standardization": "bias_correction",
    "wm_segmentation": "white_matter_segmentation",
    "surface_reconstruction": "surface_reconstruction",
    "surface_registration": "surface_registration",
    "statistics_atlas_mapping": "stats_extraction",
}

PIPELINE_MODE_TO_PRESET = {
    "FreeSurfer 8 + Volume": "freesurfer8_volumetrics",
    "FreeSurfer 8 + Cortical Thickness": "freesurfer8_cortical_thickness",
    "FreeSurfer 8 + Volume + Cortical Thickness": "freesurfer8_all",
    "FreeSurfer 7 + Volume": "freesurfer7_volumetrics",
    "FreeSurfer 7 + Cortical Thickness": "freesurfer7_cortical_thickness",
    "FreeSurfer 7 + Volume + Cortical Thickness": "freesurfer7_all",
    "FastSurfer + Volume": "fastsurfer_volumetrics",
    "FastSurfer + Cortical Thickness": "fastsurfer_cortical_thickness",
    "FastSurfer + Volume + Cortical Thickness": "fastsurfer_all",
}

ProgressCallback = Callable[[str, str, float, str], None]
BuildLogCallback = Callable[[str], None]
ImageStartCallback = Callable[[str, int, int], None]
ImageAwaitingInputCallback = Callable[[str, str, str], None]
ImageDoneCallback = Callable[[BatchImageResult, int, int], None]
MetricsCallback = Callable[[str, str, Optional[float], Optional[int], float, str], None]

LAZY_UPLOAD_TIMEOUT_SEC = 3600.0
LAZY_UPLOAD_POLL_SEC = 1.0


def _wait_for_input_marker(
    input_file: str,
    should_stop: Callable[[], bool] | None,
    timeout_sec: float | None = None,
) -> tuple[bool, str]:
    """Block until the lazy-upload `.ready` marker for `input_file` appears.

    Returns (ok, message). ok=False on cancel/timeout.
    """
    deadline = time.monotonic() + (timeout_sec if timeout_sec is not None else LAZY_UPLOAD_TIMEOUT_SEC)
    marker = Path(str(input_file) + ".ready")
    while not marker.exists():
        if should_stop and should_stop():
            return False, "cancelled while waiting for input upload"
        if time.monotonic() > deadline:
            return False, f"timed out waiting for input upload marker: {marker}"
        time.sleep(LAZY_UPLOAD_POLL_SEC)
    return True, ""


@dataclass
class _ImageRunContext:
    input_file: str
    subject_id: str
    subject_dir: str
    idx: int
    total: int
    config: PipelineConfig
    tracker: PipelineTracker
    started_at: float = field(default_factory=time.time)
    steps: list = field(default_factory=list)
    stage_outputs: dict[str, str] = field(default_factory=dict)
    completed: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def input_for_stage(self, local_stage: str) -> str | None:
        try:
            stage_index = STAGE_ORDER.index(local_stage)
        except ValueError:
            return None
        with self.lock:
            for previous in reversed(STAGE_ORDER[:stage_index]):
                output = self.stage_outputs.get(previous)
                if output:
                    return output
        return None

    def record_step(self, step: object, output_for_next: str | None, local_stage: str) -> None:
        with self.lock:
            self.steps.append(step)
            if getattr(step, "success", False) and output_for_next:
                self.stage_outputs[local_stage] = output_for_next


def _ensure_neuroflow_import_path() -> None:
    try:
        import neuroflow  # noqa: F401
        return
    except ModuleNotFoundError:
        checkout_src = PROJECT_ROOT / "NeuroFLOW-private" / "src"
        if checkout_src.exists():
            sys.path.insert(0, str(checkout_src))


def is_neuroflow_supported(req: dict) -> bool:
    explicit = str(req.get("neuroflow_preset") or "").strip()
    if explicit:
        return True
    mode = str(req.get("pipeline_mode") or "")
    return mode in PIPELINE_MODE_TO_PRESET


def _preset_id_from_request(req: dict) -> str:
    explicit = str(req.get("neuroflow_preset") or "").strip()
    if explicit:
        return explicit
    mode = str(req.get("pipeline_mode") or "")
    preset_id = PIPELINE_MODE_TO_PRESET.get(mode)
    if not preset_id:
        raise ValueError(f"No NeuroFLOW preset mapping for pipeline mode: {mode or 'Custom'}")
    return preset_id


def _neuroflow_config_root() -> Path:
    root = PROJECT_ROOT / "configs" / "neuroflow"
    if not (root / "presets").is_dir() or not (root / "profiles").is_dir():
        raise FileNotFoundError(f"NeuroFLOW preset/profile configs not found: {root}")
    return root


def _ram_limit_mib(ram_percent: int) -> int:
    total = _total_ram_bytes()
    if not total:
        return 1024
    pct = max(1, min(int(ram_percent), 100))
    return max(1, int(total * pct / 100 / (1024 * 1024)))


def _gpu_resources(device: str) -> tuple[object, ...]:
    from neuroflow import GPUResource

    if device.lower() not in {"gpu", "cuda"}:
        return ()
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free,memory.total,name", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return ()
    if result.returncode != 0:
        return ()
    gpus = []
    for index, line in enumerate(result.stdout.splitlines()):
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            free_mib = int(parts[0])
            total_mib = int(parts[1])
        except ValueError:
            continue
        gpus.append(
            GPUResource(
                gpu_id=f"gpu_{index}",
                available=free_mib > 0,
                free_memory_mib=free_mib,
                total_memory_mib=total_mib,
                device_class=parts[2] if len(parts) > 2 else "generic_cuda",
            )
        )
    return tuple(gpus)


def _scheduler_config(req: dict) -> object:
    from neuroflow.configuration import load_scheduler_dict

    threads = max(1, int(req.get("threads", 1) or 1))
    scheduler_thread_limit = threads
    max_concurrent = max(1, int(req.get("neuroflow_max_concurrent_tasks", 2) or 2))
    ram_mib = _ram_limit_mib(int(req.get("ram_percent", 100) or 100))

    warmup_enabled = bool(req.get("neuroflow_warmup_enabled", False))
    warmup_initial = max(1, min(max_concurrent, int(req.get("neuroflow_warmup_initial_concurrency", 1) or 1)))
    warmup_safe_successes = max(1, int(req.get("neuroflow_warmup_safe_successes", 3) or 3))

    max_retries = max(0, min(5, int(req.get("neuroflow_max_retries", 3) if req.get("neuroflow_max_retries") is not None else 3)))
    preserve_oom = bool(req.get("neuroflow_preserve_oom_bounds", True))
    delays = [5_000, 30_000, 120_000, 300_000, 600_000][:max(1, max_retries)]
    if len(delays) < max_retries:
        delays.extend([600_000] * (max_retries - len(delays)))

    est_mode = str(req.get("neuroflow_estimation_mode", "balanced")).lower()
    if est_mode == "conservative":
        runtime_dim = {"local_quantile": 0.95, "prior_guard": 1.30, "local_guard": 1.10}
        ram_dim = {"local_quantile": 0.98, "prior_guard": 1.30, "local_guard": 1.15}
    elif est_mode == "aggressive":
        runtime_dim = {"local_quantile": 0.75, "prior_guard": 1.15, "local_guard": 1.00}
        ram_dim = {"local_quantile": 0.85, "prior_guard": 1.15, "local_guard": 1.05}
    else:
        runtime_dim = {"local_quantile": 0.90, "prior_guard": 1.25, "local_guard": 1.05}
        ram_dim = {"local_quantile": 0.95, "prior_guard": 1.25, "local_guard": 1.10}

    max_io_tasks = max(1, int(req.get("neuroflow_max_io_heavy_tasks", 2) or 2))

    gpus = [
        {
            "id": gpu.gpu_id,
            "total_memory_mib": gpu.total_memory_mib or gpu.free_memory_mib,
            "device_class": gpu.device_class or "generic_cuda",
            "enabled": gpu.available,
        }
        for gpu in _gpu_resources(str(req.get("device", "cpu")))
    ]
    limits: dict[str, object] = {
        "max_concurrent_tasks": max_concurrent,
        "max_total_cpu_threads": scheduler_thread_limit,
        "max_threads_per_task": scheduler_thread_limit,
        "max_ram_mib": ram_mib,
    }
    if gpus:
        limits["gpus"] = gpus
    return load_scheduler_dict(
        {
            "schema_version": 1,
            "scheduler_id": "mri_pipeline_neuroflow",
            "policy": {"name": "neuroflow", "algorithm_version": "1"},
            "limits": limits,
            "warmup": {
                "enabled": warmup_enabled,
                "initial_concurrency": warmup_initial,
                "safe_successes_before_increase": warmup_safe_successes,
                "minimum_concurrency": 1,
            },
            "retry": {
                "max_retries": max_retries,
                "transient_delays_ms": delays if max_retries > 0 else [5_000],
                "preserve_oom_bounds_on_manual_retry": preserve_oom,
            },
            "estimation": {
                "runtime": runtime_dim,
                "ram": ram_dim,
            },
            "disk": {
                "enabled": True,
                "max_io_heavy_tasks": max_io_tasks,
            },
        }
    )


def _filter_profiles_for_thread_limit(pipeline: object, profiles: object, thread_limit: int) -> tuple[object, object]:
    if not hasattr(pipeline, "stages") or not hasattr(profiles, "profiles"):
        return pipeline, profiles
    limit = max(1, int(thread_limit))
    stage_ids: set[str] = set()
    profile_refs: set[str] = set()
    filtered_stages = []
    for stage in getattr(pipeline, "stages", ()):  # NeuroFLOW models are dataclasses.
        configs = [
            config
            for config in getattr(stage, "execution_configurations", ())
            if int(getattr(config, "cpu_threads", 1) or 1) <= limit
        ]
        if not configs:
            raise ValueError(
                f"No NeuroFLOW execution configuration for stage '{getattr(stage, 'stage_id', 'unknown')}' fits thread limit {limit}."
            )
        stage_ids.add(str(getattr(stage, "stage_id")))
        profile_refs.update(str(getattr(config, "profile_ref", "")) for config in configs if getattr(config, "profile_ref", ""))
        filtered_stages.append(replace(stage, execution_configurations=tuple(configs)))

    filtered_profiles = [
        profile
        for profile in getattr(profiles, "profiles", ())
        if str(getattr(profile, "stage_id", "")) in stage_ids
        and str(getattr(profile, "profile_id", "")) in profile_refs
        and int(getattr(profile, "cpu_threads", 1) or 1) <= limit
    ]
    return replace(pipeline, stages=tuple(filtered_stages)), replace(profiles, profiles=tuple(filtered_profiles))


def _resource_snapshot(
    req: dict,
    available_slots: int | None = None,
    available_threads: int | None = None,
    available_ram_mib: int | None = None,
) -> object:
    from neuroflow import ResourceSnapshot

    now = datetime.now(timezone.utc)
    max_concurrent = max(1, int(req.get("neuroflow_max_concurrent_tasks", 2) or 2))
    slots = max_concurrent if available_slots is None else max(0, available_slots)
    threads = max(1, int(req.get("threads", 1) or 1)) if available_threads is None else max(0, available_threads)
    ram = _ram_limit_mib(int(req.get("ram_percent", 100) or 100)) if available_ram_mib is None else max(0, available_ram_mib)
    return ResourceSnapshot(
        snapshot_id=f"mri-pipeline-{int(now.timestamp() * 1000)}",
        captured_at=now,
        available_cpu_threads=threads,
        available_ram_mib=ram,
        available_concurrency_slots=slots,
        gpus=_gpu_resources(str(req.get("device", "cpu"))),
    )


def _memory_mib(bytes_value: int | None) -> int:
    if not bytes_value:
        return 1
    return max(1, math.ceil(bytes_value / (1024 * 1024)))


def _write_observation(job_dir: Path, observation: dict[str, object]) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = job_dir / "neuroflow_observations.jsonl"
    with open(jsonl_path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(observation, ensure_ascii=False) + "\n")

    tsv_path = job_dir / "neuroflow_observations.tsv"
    fieldnames = [
        "preset_id",
        "profile_set_id",
        "image_id",
        "subject_id",
        "stage_id",
        "local_stage",
        "tool",
        "configuration_id",
        "mode",
        "cpu_threads",
        "gpu_id",
        "runtime_ms",
        "peak_ram_mib",
        "peak_gpu_memory_mib",
        "exit_code",
        "success",
        "error",
    ]
    write_header = not tsv_path.exists()
    with open(tsv_path, "a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter="\t", extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(observation)


def run_neuroflow_batch(
    *,
    job_dir: Path,
    req: dict,
    input_files: list[str],
    subject_id_map: dict[str, str],
    on_progress: ProgressCallback | None = None,
    on_build_log: BuildLogCallback | None = None,
    on_image_start: ImageStartCallback | None = None,
    on_image_awaiting_input: ImageAwaitingInputCallback | None = None,
    on_image_done: ImageDoneCallback | None = None,
    on_metrics: MetricsCallback | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[BatchImageResult]:
    _ensure_neuroflow_import_path()

    from neuroflow import (
        AdaptiveScheduler,
        AddImagesRequest,
        ConfirmStart,
        ErrorCategory,
        ImageSpec,
        LaunchRequest,
        ResultStatus,
        TaskError,
        TaskMetrics,
        TaskResult,
    )
    from neuroflow.configuration import load_pipeline_file, load_profile_set_file, validate_cross_documents

    preset_id = _preset_id_from_request(req)
    profile_set_id = str(req.get("neuroflow_profile") or f"{preset_id}_default")
    config_root = _neuroflow_config_root()
    pipeline = load_pipeline_file(config_root / "presets" / f"{preset_id}.yaml")
    profiles = load_profile_set_file(config_root / "profiles" / f"{profile_set_id}.yaml")
    thread_limit = max(1, int(req.get("threads", 1) or 1))
    pipeline, profiles = _filter_profiles_for_thread_limit(pipeline, profiles, thread_limit)
    scheduler_config = _scheduler_config(req)
    validate_cross_documents(pipeline, profiles, scheduler_config)

    output_dir = str(req.get("effective_output_dir", req.get("output_dir", "")))
    export_config = ExportConfig.from_dict(req.get("export_config"))
    stats_vector_config = StatsVectorConfig.from_dict(
        normalize_stats_vector_config_for_pipeline_mode(
            str(req.get("pipeline_mode") or ""), req.get("stats_vector_config")
        )
    )
    selected_tools = dict(req.get("selected_tools", {}))
    total = len(input_files)
    contexts: dict[str, _ImageRunContext] = {}
    image_specs = []
    for idx, input_file in enumerate(input_files, start=1):
        subject_id = subject_id_map.get(input_file) or subject_id_map.get(str(Path(input_file).resolve())) or _derive_subject_id(input_file)
        subject_dir = str(Path(output_dir) / subject_id)
        logs_dir = Path(subject_dir) / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        config = PipelineConfig(
            input_file=input_file,
            output_dir=output_dir,
            subject_id=subject_id,
            license_dir=str(req.get("license_dir", "")),
            device=str(req.get("device", "cpu")),
            threads=int(req.get("threads", 1) or 1),
            ram_percent=int(req.get("ram_percent", 100) or 100),
            resume=bool(req.get("resume", False)),
            export_config=export_config,
            stats_vector_config=stats_vector_config,
            selected_tools=selected_tools,
        )
        tracker = PipelineTracker(str(logs_dir), config, subject_dir)
        tracker.mark_started(list(selected_tools))
        image_id = subject_id
        contexts[image_id] = _ImageRunContext(input_file, subject_id, subject_dir, idx, total, config, tracker)
        image_specs.append(
            ImageSpec(
                image_id=image_id,
                pipeline_id=str(pipeline.pipeline_id),
                pipeline_version=str(pipeline.pipeline_version),
                metadata={"input_file": input_file, "subject_id": subject_id},
            )
        )

    database = job_dir / "neuroflow_workspace.sqlite"
    workspace_id = f"mri-pipeline-{job_dir.name}"
    if database.exists():
        scheduler = AdaptiveScheduler.load(database_path=database, expected_workspace_id=workspace_id).scheduler
    else:
        scheduler = AdaptiveScheduler.create(
            database_path=database,
            workspace_id=workspace_id,
            pipeline_configs=(pipeline,),
            default_profiles=profiles,
            scheduler_config=scheduler_config,
            machine_profile_id=str(req.get("neuroflow_machine_profile_id") or "application_default"),
        )
    scheduler.add_images(request=AddImagesRequest(request_id="add-neuroflow-images", images=tuple(image_specs)))

    if on_progress:
        on_progress("batch", "running", 0.0, f"NeuroFLOW preset {preset_id} loaded with profile {profile_set_id}")

    max_concurrent = max(1, int(req.get("neuroflow_max_concurrent_tasks", 2) or 2))
    lazy_upload = bool(req.get("lazy_upload"))
    awaiting_emitted: set[str] = set()

    def _run_launch_stage(
        launch: object,
        context: _ImageRunContext,
        local_stage: str,
        execution_id: str,
    ) -> tuple[object, dict[str, object]]:
        if lazy_upload and context.input_for_stage(local_stage) is None:
            ok, message = _wait_for_input_marker(context.input_file, should_stop)
            if not ok:
                raise RuntimeError(
                    f"Input upload for {context.subject_id} {message}."
                )
            if on_progress:
                on_progress("upload", "success", 100.0, f"Input upload complete: {context.subject_id}")
        stage_config = PipelineConfig(
            input_file=context.config.input_file,
            output_dir=context.config.output_dir,
            subject_id=context.config.subject_id,
            license_dir=context.config.license_dir,
            device="gpu" if str(launch.execution_mode.value) == "gpu" else "cpu",
            threads=int(launch.cpu_threads),
            ram_percent=context.config.ram_percent,
            resume=context.config.resume,
            selected_tools=context.config.selected_tools,
            export_config=context.config.export_config,
            stats_vector_config=context.config.stats_vector_config,
            container_name_suffix=f"{local_stage}_{launch.attempt_id}",
        )
        step, output_for_next = run_pipeline_stage(
            stage_config,
            local_stage,
            input_for_stage=context.input_for_stage(local_stage),
            on_progress=on_progress,
            on_build_log=on_build_log,
            on_metrics=on_metrics,
            tracker=context.tracker,
            stage_idx=STAGE_ORDER.index(local_stage) if local_stage in STAGE_ORDER else None,
            total_stages=len(STAGE_ORDER),
        )
        context.record_step(step, output_for_next, local_stage)
        runtime_ms = max(1, int(step.duration_sec * 1000))
        peak_ram_mib = _memory_mib(step.peak_ram_bytes)
        success = bool(step.success)
        error = None if success else TaskError(category=ErrorCategory.PROCESS_CRASH, message=step.error or "Pipeline stage failed")
        result = TaskResult(
            result_id=f"result-{launch.attempt_id}",
            task_id=str(launch.task_id),
            attempt_id=str(launch.attempt_id),
            execution_id=execution_id,
            status=ResultStatus.SUCCEEDED if success else ResultStatus.FAILED,
            exit_code=0 if success else (step.return_code or 1),
            validation_passed=True if success else False,
            error=error,
            metrics=TaskMetrics(
                runtime_ms=runtime_ms,
                peak_ram_mib=peak_ram_mib,
                allocated_cpu_threads=int(launch.cpu_threads),
                execution_mode=launch.execution_mode,
                gpu_id=launch.gpu_id,
                peak_cpu_utilization=step.peak_cpu_pct,
            ),
            finished_at=datetime.now(timezone.utc),
        )
        observation = {
            "preset_id": preset_id,
            "profile_set_id": profile_set_id,
            "image_id": str(launch.image_id),
            "subject_id": context.subject_id,
            "stage_id": str(launch.stage_id),
            "local_stage": local_stage,
            "tool": step.tool,
            "configuration_id": str(launch.configuration_id),
            "mode": str(launch.execution_mode.value),
            "cpu_threads": int(launch.cpu_threads),
            "gpu_id": launch.gpu_id or "",
            "runtime_ms": runtime_ms,
            "peak_ram_mib": peak_ram_mib,
            "peak_gpu_memory_mib": "",
            "exit_code": 0 if success else (step.return_code or 1),
            "success": success,
            "error": step.error,
        }
        return result, observation

    running_futures: dict[concurrent.futures.Future, tuple[object, _ImageRunContext, str, str]] = {}
    last_response_terminal = False

    def _scheduler_is_terminal() -> bool:
        if hasattr(scheduler, "get_status"):
            status = scheduler.get_status()
            return bool(getattr(status, "terminal", False))
        return bool(last_response_terminal)

    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        while True:
            if should_stop and should_stop():
                break

            # 1. Process any completed tasks
            completed = [f for f in list(running_futures) if f.done()]
            for future in completed:
                launch, context, local_stage, execution_id = running_futures.pop(future)
                try:
                    result, observation = future.result()
                except Exception as exc:
                    result = TaskResult(
                        result_id=f"result-{launch.attempt_id}",
                        task_id=str(launch.task_id),
                        attempt_id=str(launch.attempt_id),
                        execution_id=execution_id,
                        status=ResultStatus.FAILED,
                        exit_code=1,
                        validation_passed=False,
                        error=TaskError(category=ErrorCategory.PROCESS_CRASH, message=str(exc)),
                        metrics=TaskMetrics(
                            runtime_ms=1000,
                            peak_ram_mib=512,
                            allocated_cpu_threads=int(launch.cpu_threads),
                            execution_mode=launch.execution_mode,
                            gpu_id=launch.gpu_id,
                        ),
                        finished_at=datetime.now(timezone.utc),
                    )
                    observation = {
                        "preset_id": preset_id,
                        "profile_set_id": profile_set_id,
                        "image_id": str(launch.image_id),
                        "subject_id": context.subject_id,
                        "stage_id": str(launch.stage_id),
                        "local_stage": local_stage,
                        "tool": "unknown",
                        "configuration_id": str(launch.configuration_id),
                        "mode": str(launch.execution_mode.value),
                        "cpu_threads": int(launch.cpu_threads),
                        "gpu_id": launch.gpu_id or "",
                        "runtime_ms": 1000,
                        "peak_ram_mib": 512,
                        "peak_gpu_memory_mib": "",
                        "exit_code": 1,
                        "success": False,
                        "error": str(exc),
                    }
                scheduler.report_result(result=result)
                _write_observation(job_dir, observation)
                output_observation_dir = Path(output_dir)
                if output_observation_dir.resolve() != job_dir.resolve():
                    _write_observation(output_observation_dir, observation)

            # 2. Check available concurrency slots and request new launches
            available_slots = max_concurrent - len(running_futures)
            if available_slots > 0:
                snapshot = _resource_snapshot(req, available_slots=available_slots)
                response = scheduler.request_launches(
                    request=LaunchRequest(resource_snapshot=snapshot, maximum_number=available_slots)
                )
                last_response_terminal = bool(getattr(response, "terminal", False))
                if response.launches:
                    for launch in response.launches:
                        context = contexts.get(str(launch.image_id))
                        if context is None:
                            continue
                        local_stage = NEUROFLOW_STAGE_TO_LOCAL_STAGE.get(str(launch.stage_id), str(launch.stage_id))
                        execution_id = str(launch.attempt_id)
                        if on_image_start:
                            on_image_start(context.input_file, context.idx, context.total)
                        if on_image_awaiting_input and context.subject_id not in awaiting_emitted:
                            awaiting_emitted.add(context.subject_id)
                            on_image_awaiting_input(context.input_file, context.subject_id, local_stage)
                        scheduler.confirm_started(
                            confirmation=ConfirmStart(
                                confirmation_id=f"confirm-{launch.attempt_id}",
                                reservation_id=str(launch.reservation_id),
                                attempt_id=str(launch.attempt_id),
                                task_id=str(launch.task_id),
                                execution_id=execution_id,
                                started_at=datetime.now(timezone.utc),
                            )
                        )
                        future = executor.submit(_run_launch_stage, launch, context, local_stage, execution_id)
                        running_futures[future] = (launch, context, local_stage, execution_id)
                elif _scheduler_is_terminal() and not running_futures:
                    break
                elif not running_futures:
                    if on_progress:
                        on_progress("batch", "running", 0.0, f"NeuroFLOW waiting: {response.reason}")
            elif not running_futures:
                break

            time.sleep(0.05)

    results: list[BatchImageResult] = []
    generator = StatsGenerator(stats_vector_config)
    for context in contexts.values():
        success = bool(context.steps) and all(step.success for step in context.steps)
        context.tracker.mark_completed(success)
        stats_result = generator.generate(context.subject_dir, context.subject_id)
        if stats_result.files or stats_result.warnings:
            context.tracker.set_stats_vectors(stats_result.files, stats_result.warnings)
        image_result = BatchImageResult(
            input_file=context.input_file,
            subject_id=context.subject_id,
            subject_dir=context.subject_dir,
            success=success,
            duration_sec=time.time() - context.started_at,
            steps=context.steps,
            error="" if success else "one or more NeuroFLOW scheduled steps failed",
        )
        results.append(image_result)
        if on_image_done:
            on_image_done(image_result, context.idx, context.total)

    write_batch_reports(
        BatchReportContext(
            output_dir=output_dir,
            input_files=input_files,
            batch_results=results,
            subject_id_map=subject_id_map,
            dataset_root=str(req.get("input_dir", "")),
            stats_vector_config=stats_vector_config,
        )
    )
    scheduler.save()
    scheduler.close()
    return results
