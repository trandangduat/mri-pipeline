from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .config import PROJECT_ROOT, BatchImageResult, ExportConfig, PipelineConfig, StatsVectorConfig, StepResult
from .discovery import _derive_subject_id
from .hardware import _total_ram_bytes
from .gpu_execution_receipt import receipt_path
from .presets import normalize_stats_vector_config_for_pipeline_mode
from .registry import STAGE_ORDER, STAGE_LABELS, TOOL_DEFS
from .reports import BatchReportContext, write_batch_reports
from .runner import _resume_exports, run_pipeline_stage
from .state import PipelineTracker
from .stats import StatsGenerator
from pipeline.win_process import no_window_kwargs
from .policy_contract import FIXED_POLICIES, INTEGRATION_VERSION, STATIC_POLICIES, normalize_policy, resolve_defaults


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
    stage_steps: dict[str, list[object]] = field(default_factory=dict)
    completed_stages: set[str] = field(default_factory=set)
    committed_stages: set[str] = field(default_factory=set)
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
            if not hasattr(step, "stage") or not getattr(step, "stage", None):
                try:
                    setattr(step, "stage", local_stage)
                except Exception:
                    pass
            self.steps.append(step)
            self.stage_steps.setdefault(local_stage, []).append(step)
            if getattr(step, "success", False):
                self.completed_stages.add(local_stage)
                if output_for_next:
                    self.stage_outputs[local_stage] = output_for_next


def _ensure_neuroflow_import_path() -> None:
    # Imports must not create or replace cache files in the original checkout.
    sys.dont_write_bytecode = True
    try:
        import neuroflow  # noqa: F401
        return
    except ModuleNotFoundError:
        source = os.environ.get("NEUROFLOW_SOURCE_DIR")
        checkout_src = Path(source).expanduser() / "src" if source else PROJECT_ROOT / "NeuroFLOW-private" / "src"
        if checkout_src.exists():
            sys.path.insert(0, str(checkout_src))


def is_neuroflow_supported(req: dict) -> bool:
    explicit = str(req.get("neuroflow_preset") or "").strip()
    preset_file = str(req.get("neuroflow_preset_file") or "").strip()
    profile_file = str(req.get("neuroflow_profile_file") or "").strip()
    if explicit or (preset_file and profile_file):
        return True
    mode = str(req.get("pipeline_mode") or "")
    return mode in PIPELINE_MODE_TO_PRESET


def _preset_id_from_request(req: dict) -> str:
    explicit = str(req.get("neuroflow_preset") or "").strip()
    if explicit:
        return explicit
    preset_file = str(req.get("neuroflow_preset_file") or "").strip()
    if preset_file:
        return Path(preset_file).stem
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


def _ram_limit_mib(ram_percent: int, runtime_ram_bytes: int | None = None) -> int:
    total = runtime_ram_bytes if runtime_ram_bytes is not None else _total_ram_bytes()
    if not total:
        return 1024
    pct = max(1, min(int(ram_percent), 100))
    return max(1, int(total * pct / 100 / (1024 * 1024)))


def _request_ram_limit_mib(req: dict) -> int:
    percent = int(req.get("ram_percent", 100) or 100)
    if req.get("runtime_ram_bytes") is not None:
        return _ram_limit_mib(percent, req["runtime_ram_bytes"])
    return _ram_limit_mib(percent)


class _GPUPlacementError(RuntimeError):
    """The selected GPU cannot be bound to a verified execution-host device."""


def _gpu_resources(device: str) -> tuple[object, ...]:
    from neuroflow import GPUResource

    if device.lower() not in {"gpu", "cuda"}:
        return ()
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,uuid,memory.free,memory.total,name", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            **no_window_kwargs(),
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if result.returncode != 0:
        return ()
    gpus = []
    indexes: set[int] = set()
    uuids: set[str] = set()
    for row in csv.reader(result.stdout.splitlines(), skipinitialspace=True):
        if len(row) < 5:
            continue
        try:
            index, uuid = int(row[0]), row[1].strip()
            free_mib, total_mib = int(row[2]), int(row[3])
        except ValueError:
            continue
        if index < 0 or not uuid.startswith("GPU-") or not 0 <= free_mib <= total_mib or total_mib == 0:
            continue
        if index in indexes or uuid in uuids:
            return ()  # No trusted mapping exists for an ambiguous inventory.
        indexes.add(index)
        uuids.add(uuid)
        gpus.append(
            GPUResource(
                gpu_id=f"gpu_{index}",
                available=free_mib > 0,
                free_memory_mib=free_mib,
                total_memory_mib=total_mib,
                device_class="generic_cuda",
                metadata=(("host_index", str(index)), ("uuid", uuid),
                          ("name", ",".join(row[4:]).strip())),
            )
        )
    return tuple(gpus)


def _require_local_gpu_docker_host() -> None:
    context = os.environ.get("DOCKER_CONTEXT", "").strip()
    endpoint = "" if context else os.environ.get("DOCKER_HOST", "").strip()
    if not endpoint:
        try:
            result = subprocess.run(
                ["docker", "context", "inspect", *([context] if context else []),
                 "--format", "{{.Endpoints.docker.Host}}"],
                capture_output=True, text=True, timeout=5, **no_window_kwargs(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise _GPUPlacementError("Cannot verify the Docker host for GPU placement") from exc
        if result.returncode != 0:
            raise _GPUPlacementError("Cannot verify the Docker host for GPU placement")
        endpoint = result.stdout.strip()
    endpoint = endpoint.replace("\\", "/")
    if not endpoint.startswith(("unix://", "npipe:////./pipe/", "npipe://./pipe/")):
        raise _GPUPlacementError("GPU placement requires a verified local Docker endpoint")


def _resolve_gpu_device_id(launch: object, scheduled_gpus: tuple[object, ...]) -> str | None:
    if str(launch.execution_mode.value) != "gpu":
        return None
    selected = str(launch.gpu_id or "")
    if selected.startswith("GPU-"):
        field, device_id = "uuid", selected
    else:
        index = selected.removeprefix("gpu_")
        if not index.isascii() or not index.isdecimal():
            raise _GPUPlacementError(f"Invalid selected GPU ID: {selected!r}")
        field, device_id = "host_index", str(int(index))

    expected = [gpu for gpu in scheduled_gpus
                if dict(gpu.metadata).get(field) == device_id]
    if len(expected) != 1:
        raise _GPUPlacementError(f"Selected GPU {selected!r} is missing or ambiguous in the launch snapshot")
    uuid = str(dict(expected[0].metadata).get("uuid", ""))
    if not expected[0].available or not uuid.startswith("GPU-"):
        raise _GPUPlacementError(f"Selected GPU {selected!r} is unavailable or has no verified UUID")

    _require_local_gpu_docker_host()
    current = [gpu for gpu in _gpu_resources("gpu")
               if dict(gpu.metadata).get(field) == device_id]
    required_memory = int(getattr(launch, "reserved_gpu_memory_mib", 0) or 0)
    if (len(current) != 1 or dict(current[0].metadata).get("uuid") != uuid
            or not current[0].available or current[0].free_memory_mib < required_memory):
        raise _GPUPlacementError(f"Selected GPU {selected!r} disappeared, changed identity, or is unavailable")
    return device_id


def _scheduler_config(req: dict) -> object:
    _ensure_neuroflow_import_path()
    from neuroflow.configuration import load_scheduler_dict

    threads = max(1, int(req.get("threads", 1) or 1))
    scheduler_thread_limit = threads
    max_concurrent = max(1, int(req.get("neuroflow_max_concurrent_tasks", 2) or 2))
    ram_mib = _request_ram_limit_mib(req)

    warmup_enabled = bool(req.get("neuroflow_warmup_enabled", True))
    warmup_initial = max(1, min(max_concurrent, int(req.get("neuroflow_warmup_initial_concurrency", 2) or 2)))
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
    policy_choice = normalize_policy(req.get("neuroflow_policy"))
    policy_variant = policy_choice
    policy_metadata = {"policy_choice": policy_choice, "policy_variant": policy_variant}
    if policy_choice != "B6":
        policy_metadata.update(engine="external_baseline", integration_version=INTEGRATION_VERSION)
    if policy_choice == "B0":
        max_concurrent = 1
    if policy_choice in STATIC_POLICIES:
        warmup_enabled = False
        warmup_initial = max_concurrent

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
            "metadata": policy_metadata,
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


def _filter_profiles_for_thread_limit(
    pipeline: object,
    profiles: object,
    thread_limit: int,
    available_gpus: int = 0,
) -> tuple[object, object]:
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
            and (available_gpus > 0 or str(getattr(config, "execution_mode", "")).lower() != "gpu")
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
    policy_choice = normalize_policy(req.get("neuroflow_policy"))
    if policy_choice == "B0":
        max_concurrent = 1
    else:
        max_concurrent = max(1, int(req.get("neuroflow_max_concurrent_tasks", 2) or 2))
    slots = max_concurrent if available_slots is None else max(0, available_slots)
    threads = max(1, int(req.get("threads", 1) or 1)) if available_threads is None else max(0, available_threads)
    ram = _request_ram_limit_mib(req) if available_ram_mib is None else max(0, available_ram_mib)
    return ResourceSnapshot(
        snapshot_id=f"mri-pipeline-{int(now.timestamp() * 1000)}",
        captured_at=now,
        available_cpu_threads=threads,
        available_ram_mib=ram,
        available_concurrency_slots=slots,
        gpus=_gpu_resources(str(req.get("device", "cpu"))),
    )


def _memory_mib(bytes_value: int | None) -> int | None:
    if bytes_value is None:
        return None
    if bytes_value <= 0:
        return 0
    return max(1, math.ceil(bytes_value / (1024 * 1024)))


def _write_observation(job_dir: Path, observation: dict[str, object]) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = job_dir / "neuroflow_observations.jsonl"
    result_id = observation.get("result_id")
    if result_id and jsonl_path.exists():
        with jsonl_path.open(encoding="utf-8") as stream:
            if any(json.loads(line).get("result_id") == result_id for line in stream if line.strip()):
                return
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
    preset_file = str(req.get("neuroflow_preset_file") or "").strip()
    profile_file = str(req.get("neuroflow_profile_file") or "").strip()
    preset_source = Path(preset_file) if preset_file else config_root / "presets" / f"{preset_id}.yaml"
    pipeline = load_pipeline_file(preset_source)
    if not profile_file and preset_file:
        profile_set_id = f"{pipeline.pipeline_id}_default"
    profile_source = Path(profile_file) if profile_file else config_root / "profiles" / f"{profile_set_id}.yaml"
    profiles = load_profile_set_file(profile_source)
    preset_id = str(pipeline.pipeline_id)
    profile_set_id = str(getattr(profiles, "profile_set_id", profile_set_id))
    thread_limit = max(1, int(req.get("threads", 1) or 1))
    scheduler_config = _scheduler_config(req)
    policy_choice = normalize_policy(req.get("neuroflow_policy"))
    defaults = {}
    if policy_choice in FIXED_POLICIES:
        defaults = resolve_defaults(pipeline, req.get("neuroflow_default_configurations"), scheduler_config.limits)
        pipeline = replace(pipeline, stages=tuple(
            replace(stage, execution_configurations=tuple(
                c for c in stage.execution_configurations
                if str(c.configuration_id) == defaults[str(stage.stage_id)]
            )) if stage.enabled else stage for stage in pipeline.stages
        ))
    limits = getattr(scheduler_config, "limits", None)
    if limits is None and isinstance(scheduler_config, dict):
        limits = scheduler_config.get("limits")
    gpu_list = getattr(limits, "gpus", None)
    if gpu_list is None and isinstance(limits, dict):
        gpu_list = limits.get("gpus")
    gpu_list = gpu_list or ()
    available_gpus = len(tuple(g for g in gpu_list if (getattr(g, "enabled", True) if not isinstance(g, dict) else g.get("enabled", True))))
    pipeline, profiles = _filter_profiles_for_thread_limit(
        pipeline, profiles, thread_limit, available_gpus=available_gpus
    )
    validate_cross_documents(pipeline, profiles, scheduler_config)

    database = job_dir / "neuroflow_workspace.sqlite"
    workspace_id = f"mri-pipeline-{job_dir.name}"
    contract = None
    restored_steps = []
    if policy_choice != "B6":
        from .policy_runtime import check_resume, make_contract, preflight_baseline
        preflight_baseline(pipeline, profiles, scheduler_config, req)
        contract = make_contract(policy_choice, pipeline, profiles, scheduler_config, defaults, req)
        contract["inputs"] = [
            {"path": str(path), "image_id": subject_id_map.get(path)
             or subject_id_map.get(str(Path(path).resolve())) or _derive_subject_id(path)}
            for path in input_files
        ]
        contract["output_dir"] = str(req.get("effective_output_dir", req.get("output_dir", "")))
        contract["preset_file_sha256"] = hashlib.sha256(preset_source.read_bytes()).hexdigest()
        contract["profile_file_sha256"] = hashlib.sha256(profile_source.read_bytes()).hexdigest()
        check_resume(database, contract)
        if database.exists():
            from .policy_runtime import completed_execution_steps
            restored_steps = completed_execution_steps(database)
    elif database.exists():
        # Read-only inspection must precede the library's recovery writes.
        from .policy_runtime import check_resume
        sidecar = database.with_name("neuroflow_policy_contract.json")
        if sidecar.exists():
            if json.loads(sidecar.read_text(encoding="utf-8")).get("policy_id") != "B6":
                raise ValueError("Workspace used a different policy. Use a new job directory.")
        else:
            check_resume(database, {"policy_id": "B6"})

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
            runtime_ram_bytes=req.get("runtime_ram_bytes"),
            resume=bool(req.get("resume", False)) or (policy_choice != "B6" and database.exists()),
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

    for image_id, step, output in restored_steps:
        if image_id in contexts:
            contexts[image_id].record_step(step, output, step.stage)
            if step.success:
                contexts[image_id].committed_stages.add(step.stage)

    if database.exists():
        # Repair exports from verified intermediate files without resubmitting scheduler tasks.
        for context in contexts.values():
            for stage, key in selected_tools.items():
                tool = TOOL_DEFS.get(key, {})
                outputs = context.tracker.find_existing_outputs(
                    context.subject_dir, tool.get("output_files", []), tool.get("output_globs", []),
                )
                if outputs:
                    _resume_exports(context.config, stage, context.subject_dir, outputs, context.tracker, on_progress)

    if policy_choice != "B6":
        from .policy_runtime import create_baseline_scheduler, load_baseline_scheduler, write_contract
        if database.exists():
            scheduler = load_baseline_scheduler(database, workspace_id)
        else:
            scheduler = create_baseline_scheduler(
                database_path=database, workspace_id=workspace_id,
                pipeline_configs=(pipeline,), default_profiles=profiles,
                scheduler_config=scheduler_config,
                machine_profile_id=str(req.get("neuroflow_machine_profile_id") or "application_default"))
        write_contract(database, contract)
    elif database.exists():
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
        on_progress("batch", "running", 0.0, f"NeuroFLOW preset {preset_id} loaded with profile {profile_set_id} ({policy_choice})")

    if policy_choice == "B0":
        max_concurrent = 1
    else:
        max_concurrent = max(1, int(req.get("neuroflow_max_concurrent_tasks", 2) or 2))
    lazy_upload = bool(req.get("lazy_upload"))
    awaiting_emitted: set[str] = set()
    started_subjects: set[str] = set()
    # Also guard this running job if the disk cannot accept a receipt.
    unpersisted_gpu_executions: dict[str, tuple[object, object, str | None]] = {}
    gpu_execution_keys = {path.stem for path in (job_dir / "gpu_execution_receipts").glob("*.json")
                          if not path.name.startswith("report-")}

    def _run_launch_stage(
        launch: object,
        context: _ImageRunContext,
        local_stage: str,
        execution_id: str,
        scheduled_gpus: tuple[object, ...],
    ) -> tuple[object, dict[str, object]]:
        if lazy_upload and context.input_for_stage(local_stage) is None:
            ok, message = _wait_for_input_marker(context.input_file, should_stop)
            if not ok:
                raise RuntimeError(
                    f"Input upload for {context.subject_id} {message}."
                )
            if on_progress:
                on_progress("upload", "success", 100.0, f"Input upload complete: {context.subject_id}")
        is_gpu = str(launch.execution_mode.value) == "gpu"
        evidence = None
        telemetry_error = ""
        reused_execution = False
        evidence_path = receipt_path(job_dir, str(launch.task_id))
        guard_gpu_execution = (is_gpu or evidence_path.stem in gpu_execution_keys
                               or str(launch.task_id) in unpersisted_gpu_executions)
        if guard_gpu_execution:
            from .gpu_execution_receipt import (
                execution_provenance, load_execution, save_execution,
            )
            source_hashes = (hashlib.sha256(preset_source.read_bytes()).hexdigest(),
                             hashlib.sha256(profile_source.read_bytes()).hexdigest())
            cached = unpersisted_gpu_executions.get(str(launch.task_id))
            if cached is not None:
                step, source_attempt, output_for_next = cached
                evidence = {"attempt_id": source_attempt, "execution_id": source_attempt}
                reused_execution = True
                telemetry_error = ("GPU outputs preserved from attempt "
                                   f"{source_attempt}; execution receipt could not be saved")
            elif evidence_path.exists():
                try:
                    provenance = execution_provenance(
                        context, launch, local_stage,
                        source_hashes,
                    )
                    evidence = load_execution(evidence_path, provenance)
                    step = StepResult(**evidence["step"])
                    output_for_next = evidence["output"]["path"]
                    reused_execution = (evidence["attempt_id"] != str(launch.attempt_id)
                                        or evidence["execution_id"] != execution_id)
                    if reused_execution:
                        telemetry_error = ("GPU processing outputs preserved from attempt "
                                           f"{evidence['attempt_id']}; telemetry cannot be "
                                           "remeasured without rerunning MRI")
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    # A mismatched receipt cannot authorize reuse or an automatic rerun.
                    telemetry_error = f"GPU execution evidence cannot be reconciled: {exc}"
                    reused_execution = True
                    step = StepResult(stage=local_stage,
                                      tool=context.config.selected_tools.get(local_stage, ""),
                                      success=False, duration_sec=0, error=telemetry_error)
                    output_for_next = None
        if evidence is None and not telemetry_error:
            stage_config = PipelineConfig(
                input_file=context.config.input_file,
                output_dir=context.config.output_dir,
                subject_id=context.config.subject_id,
                license_dir=context.config.license_dir,
                device="gpu" if str(launch.execution_mode.value) == "gpu" else "cpu",
                threads=int(launch.cpu_threads),
                ram_percent=context.config.ram_percent,
                runtime_ram_bytes=context.config.runtime_ram_bytes,
                # Only committed scheduler completions are reused for baselines.
                # An uncommitted task must run and produce real measurements.
                resume=context.config.resume if policy_choice == "B6" else False,
                selected_tools=context.config.selected_tools,
                export_config=context.config.export_config,
                stats_vector_config=context.config.stats_vector_config,
                container_name_suffix=f"{local_stage}_{launch.attempt_id}",
                gpu_device_id=_resolve_gpu_device_id(launch, scheduled_gpus),
                cpu_thread_limit=int(launch.cpu_threads),
                console_job_dir=str(job_dir),
                console_attempt_id=str(launch.attempt_id),
            )
            def _stage_progress(stg: str, status: str, pct: float, msg: str) -> None:
                if on_progress:
                    on_progress(stg, status, pct, f"[{context.subject_id}] {msg}")

            step, output_for_next = run_pipeline_stage(
                stage_config,
                local_stage,
                input_for_stage=context.input_for_stage(local_stage),
                on_progress=_stage_progress,
                on_build_log=on_build_log,
                on_metrics=on_metrics,
                tracker=context.tracker,
                stage_idx=STAGE_ORDER.index(local_stage) if local_stage in STAGE_ORDER else None,
                total_stages=len(STAGE_ORDER),
                should_stop=should_stop,
            )
        processing_success = bool(step.success)
        if is_gpu and processing_success and evidence is None and not reused_execution:
            gpu_execution_keys.add(evidence_path.stem)
            try:
                provenance = execution_provenance(
                    context, launch, local_stage,
                    source_hashes,
                )
                tool = TOOL_DEFS.get(provenance["tool"], {})
                outputs = context.tracker.find_existing_outputs(
                    context.subject_dir, tool.get("output_files", []), tool.get("output_globs", []))
                evidence = save_execution(evidence_path, provenance, launch, execution_id,
                                          step, output_for_next, outputs)
            except (OSError, ValueError, TypeError) as exc:
                telemetry_error = f"Cannot preserve GPU execution evidence: {exc}"
                unpersisted_gpu_executions[str(launch.task_id)] = (
                    step, str(launch.attempt_id), output_for_next)
        if is_gpu and processing_success and evidence is not None and not reused_execution:
            # Restore only evidence for this exact attempt and execution.
            try:
                recovered = load_execution(evidence_path, provenance)
                if (recovered["attempt_id"] == str(launch.attempt_id)
                        and recovered["execution_id"] == execution_id):
                    step = StepResult(**recovered["step"])
            except (OSError, ValueError, KeyError, TypeError) as exc:
                telemetry_error = f"GPU execution evidence cannot be verified: {exc}"
        peak_gpu_memory_mib = getattr(step, "peak_gpu_memory_mib", None) if is_gpu else None
        if is_gpu and processing_success and peak_gpu_memory_mib is None:
            diagnostics = getattr(step, "gpu_telemetry", None) or {}
            telemetry_error = telemetry_error or (
                "Missing measured container GPU memory: "
                + str(diagnostics.get("reason") or "no valid GPU sample"))
        if (processing_success and not reused_execution
                and policy_choice in {"B5", "B6"}):
            if is_gpu and peak_gpu_memory_mib == 0:
                telemetry_error = telemetry_error or (
                    "Measured GPU memory is 0 MiB; scheduler profile learning requires a positive sample")
            if step.peak_ram_bytes == 0:
                telemetry_error = telemetry_error or (
                    "Measured RAM is 0 bytes; scheduler profile learning requires a positive sample")
        if reused_execution:
            # A retry is not a fresh execution. Never teach profiles with cached metrics.
            step = replace(step, duration_sec=0, peak_ram_bytes=None, avg_ram_bytes=None,
                           p95_ram_bytes=None, peak_cpu_pct=None, avg_cpu_pct=None,
                           p95_cpu_pct=None, peak_gpu_memory_mib=None, gpu_telemetry=None)
            peak_gpu_memory_mib = None
        missing_ram_measurement = (not reused_execution and step.success
                                   and step.peak_ram_bytes is None)
        if missing_ram_measurement:
            telemetry_error = telemetry_error or (
                "Missing measured peak RAM for scheduler validation"
                if (is_gpu or policy_choice == "B6")
                else "Missing measured peak RAM for baseline validation")
        if telemetry_error:
            step = replace(step, success=False, error=telemetry_error)
        context.record_step(step, output_for_next, local_stage)
        runtime_ms = None if reused_execution else max(1, int(step.duration_sec * 1000))
        if reused_execution:
            peak_ram_mib = None
        else:
            peak_ram_mib = _memory_mib(step.peak_ram_bytes)
        success = bool(step.success)
        category = ErrorCategory.PROCESS_CRASH
        if not success and (policy_choice != "B6" or is_gpu):
            from .policy_contract import classify_failure
            category = getattr(ErrorCategory, classify_failure(step))
        if telemetry_error:
            category = ErrorCategory.VALIDATION_FAILURE
        interrupted = policy_choice != "B6" and not success and should_stop and should_stop()
        if interrupted:
            category = ErrorCategory.INTERRUPTED
        error = None if success else TaskError(category=category, message=step.error or "Pipeline stage failed")
        exit_code = step.return_code if step.return_code is not None else (0 if success else 1)
        metadata = ()
        if policy_choice != "B6" or guard_gpu_execution:
            metadata = (("application_step", asdict(step)), ("output_for_next", output_for_next))
        metadata += (("processing_success", processing_success),)
        if guard_gpu_execution:
            metadata += (("source_attempt_id", evidence["attempt_id"] if evidence else None),
                         ("preserved_output", output_for_next if processing_success else None))
        result = TaskResult(
            result_id=f"result-{launch.attempt_id}",
            task_id=str(launch.task_id),
            attempt_id=str(launch.attempt_id),
            execution_id=execution_id,
            status=ResultStatus.SUCCEEDED if success else (ResultStatus.INTERRUPTED if interrupted else ResultStatus.FAILED),
            exit_code=exit_code,
            validation_passed=True if success else False,
            error=error,
            metrics=TaskMetrics(
                runtime_ms=runtime_ms,
                peak_ram_mib=peak_ram_mib,
                allocated_cpu_threads=int(launch.cpu_threads),
                execution_mode=launch.execution_mode,
                gpu_id=launch.gpu_id,
                peak_cpu_utilization=step.peak_cpu_pct,
                peak_gpu_memory_mib=peak_gpu_memory_mib,
            ),
            finished_at=datetime.now(timezone.utc),
            metadata=metadata,
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
            "peak_gpu_memory_mib": peak_gpu_memory_mib,
            "exit_code": exit_code,
            "success": success,
            "error": step.error,
        }
        if guard_gpu_execution:
            observation.update(gpu_evidence_guard=True, result_id=str(result.result_id),
                               processing_success=processing_success,
                               source_attempt_id=evidence["attempt_id"] if evidence else None,
                               preserved_output=output_for_next if processing_success else None)
        return result, observation

    running_futures: dict[concurrent.futures.Future, tuple[object, _ImageRunContext, str, str]] = {}
    last_response_terminal = False
    stopping = False

    def _scheduler_is_terminal() -> bool:
        if hasattr(scheduler, "get_status"):
            status = scheduler.get_status()
            return bool(getattr(status, "terminal", False))
        return bool(last_response_terminal)

    generator = StatsGenerator(stats_vector_config)
    finished_results: dict[str, BatchImageResult] = {}
    if hasattr(pipeline, "stages"):
        expected_stage_set = {
            NEUROFLOW_STAGE_TO_LOCAL_STAGE.get(str(stage.stage_id), str(stage.stage_id))
            for stage in pipeline.stages if getattr(stage, "enabled", True)
        }
    else:
        expected_stage_set = {stage for stage, tool in selected_tools.items() if tool}

    def _finalize_subject(context: _ImageRunContext, allow_partial: bool = False) -> BatchImageResult | None:
        if context.completed:
            return finished_results[context.subject_id]
        # A worker records its step before the scheduler commits its result.
        # Wait until every result for this subject has been processed.
        if not allow_partial and any(item[1] is context for item in running_futures.values()):
            return None
        latest_step_per_stage: dict[str, object] = {
            stg: steps[-1] for stg, steps in context.stage_steps.items() if steps
        }
        for step in context.steps:
            stg = getattr(step, "stage", None)
            if stg and stg not in latest_step_per_stage:
                latest_step_per_stage[stg] = step

        if expected_stage_set:
            all_stages_completed = expected_stage_set.issubset(context.committed_stages)
            all_steps_succeeded = all(
                getattr(latest_step_per_stage.get(stg), "success", False) for stg in expected_stage_set
            )
            success = all_stages_completed and all_steps_succeeded
        else:
            all_stages_completed = bool(context.committed_stages)
            all_steps_succeeded = bool(latest_step_per_stage) and all(
                getattr(step, "success", False) for step in latest_step_per_stage.values()
            )
            success = all_stages_completed and all_steps_succeeded

        if not allow_partial and not success:
            return None
        is_stopped = bool(should_stop and should_stop())
        stats_result = generator.generate(context.subject_dir, context.subject_id)
        if stats_result.files or stats_result.warnings:
            context.tracker.set_stats_vectors(stats_result.files, stats_result.warnings)
        context.tracker.mark_completed(success)
        if is_stopped and not success:
            err = "Job stopped before all pipeline stages completed"
        elif not success:
            err = "one or more NeuroFLOW scheduled steps failed"
        else:
            err = ""

        final_steps: list[object] = []
        for s in STAGE_ORDER:
            if s in latest_step_per_stage:
                final_steps.append(latest_step_per_stage[s])
        for stg, step in latest_step_per_stage.items():
            if stg not in STAGE_ORDER:
                final_steps.append(step)
        if not final_steps and context.steps:
            final_steps = list(context.steps)

        image_result = BatchImageResult(
            input_file=context.input_file,
            subject_id=context.subject_id,
            subject_dir=context.subject_dir,
            success=success,
            duration_sec=time.time() - context.started_at,
            steps=final_steps,
            error=err,
        )
        finished_results[context.subject_id] = image_result
        context.completed = True
        if on_image_done:
            on_image_done(image_result, context.idx, context.total)
        return image_result

    for context in contexts.values():
        if context.committed_stages:
            _finalize_subject(context)

    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        while True:
            if should_stop and should_stop():
                if policy_choice == "B6":
                    break
                if not stopping:
                    from neuroflow import ShutdownMode, ShutdownRequest
                    scheduler.begin_shutdown(request=ShutdownRequest("adapter-stop", ShutdownMode.WAIT))
                    stopping = True

            # 1. Process any completed tasks
            completed = [f for f in list(running_futures) if f.done()]
            completed_contexts: dict[str, _ImageRunContext] = {}
            for future in completed:
                launch, context, local_stage, execution_id = running_futures.pop(future)
                try:
                    result, observation = future.result()
                except Exception as exc:
                    placement_failure = isinstance(exc, _GPUPlacementError)
                    unknown_runtime = None
                    unknown_ram = None
                    result = TaskResult(
                        result_id=f"result-{launch.attempt_id}",
                        task_id=str(launch.task_id),
                        attempt_id=str(launch.attempt_id),
                        execution_id=execution_id,
                        status=ResultStatus.FAILED,
                        exit_code=1,
                        validation_passed=False,
                        error=TaskError(
                            category=ErrorCategory.CONTAINER_START_FAILURE if placement_failure else ErrorCategory.PROCESS_CRASH,
                            message=str(exc),
                        ),
                        metrics=TaskMetrics(
                            runtime_ms=unknown_runtime,
                            peak_ram_mib=unknown_ram,
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
                        "runtime_ms": unknown_runtime,
                        "peak_ram_mib": unknown_ram,
                        "peak_gpu_memory_mib": None,
                        "exit_code": 1,
                        "success": False,
                        "error": str(exc),
                    }
                gpu_report_path = None
                if str(launch.execution_mode.value) == "gpu" or observation.get("gpu_evidence_guard"):
                    from .gpu_execution_receipt import mark_reported, write_report
                    observation["result_id"] = str(result.result_id)
                    gpu_report_path = write_report(job_dir, result, observation)
                receipt = scheduler.report_result(result=result)
                if gpu_report_path is not None:
                    try:
                        mark_reported(gpu_report_path)
                        evidence_path = receipt_path(job_dir, str(launch.task_id))
                        if evidence_path.exists():
                            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                            if isinstance(evidence, dict) and evidence.get("attempt_id") == str(launch.attempt_id):
                                mark_reported(evidence_path)
                    except (OSError, ValueError, TypeError) as exc:
                        if on_build_log:
                            on_build_log(f"GPU result committed; receipt marker could not be saved: {exc}")
                completed_contexts[context.subject_id] = context
                if result.status == ResultStatus.SUCCEEDED and result.validation_passed:
                    context.committed_stages.add(local_stage)
                from .tool_output import record_scheduler_result
                record_scheduler_result(job_dir, context.subject_id, launch.attempt_id, receipt)
                _write_observation(job_dir, observation)
                output_observation_dir = Path(output_dir)
                if output_observation_dir.resolve() != job_dir.resolve():
                    _write_observation(output_observation_dir, observation)

            for context in completed_contexts.values():
                _finalize_subject(context)

            # 2. Check available concurrency slots and request new launches
            if stopping:
                if not running_futures:
                    break
                time.sleep(0.05)
                continue
            available_slots = max_concurrent - len(running_futures)
            if available_slots > 0:
                # The coordinator subtracts active reservations from the full budget.
                # maximum_number separately limits submissions to free executor slots.
                snapshot = _resource_snapshot(req, available_slots=max_concurrent)
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
                        if on_image_start and context.subject_id not in started_subjects:
                            started_subjects.add(context.subject_id)
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
                        future = executor.submit(
                            _run_launch_stage, launch, context, local_stage, execution_id, snapshot.gpus,
                        )
                        running_futures[future] = (launch, context, local_stage, execution_id)
                elif _scheduler_is_terminal() and not running_futures:
                    break
                elif not running_futures:
                    if on_progress:
                        on_progress("batch", "running", 0.0, f"NeuroFLOW waiting: {response.reason}")
            elif not running_futures:
                break

            time.sleep(0.05)

    for context in contexts.values():
        _finalize_subject(context, allow_partial=True)
    results = [finished_results[context.subject_id] for context in contexts.values()]

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
    try:
        scheduler.save()
    except Exception as exc:
        if on_build_log:
            on_build_log(f"NeuroFLOW save notice: {exc}")
    try:
        scheduler.close()
    except Exception as exc:
        if on_build_log:
            on_build_log(f"NeuroFLOW close notice: {exc}")
    return results
