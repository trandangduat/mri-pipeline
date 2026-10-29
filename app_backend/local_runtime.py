"""Local preflight checks shared by both local start endpoints."""
from __future__ import annotations

import importlib
from typing import Iterator

from app_backend.sse_utils import SSEEvent, complete_event, step_event
from pipeline.docker_ops import image_exists
from pipeline.docker_runtime import inspect_docker_runtime
from pipeline.profile_memory import build_resource_shortage, get_profile_peak_ram_mib
from pipeline.registry import TOOL_DEFS, is_tool_enabled


def check_scheduler_runtime(request: dict) -> None:
    if not request.get("neuroflow_enabled"):
        return
    from pipeline.neuroflow_adapter import _ensure_neuroflow_import_path
    try:
        _ensure_neuroflow_import_path()
        scheduler = importlib.import_module("neuroflow")
        configuration = importlib.import_module("neuroflow.configuration")
        if not hasattr(scheduler, "AdaptiveScheduler") or not hasattr(configuration, "load_pipeline_file"):
            raise ImportError("Incomplete NeuroFLOW scheduler package")
    except Exception as exc:
        raise RuntimeError(
            "The NeuroFLOW scheduler is unavailable. Repair the installation or set "
            "NEUROFLOW_SOURCE_DIR to the scheduler source folder."
        ) from exc


def local_runtime_checks(request: dict) -> Iterator[SSEEvent]:
    yield step_event("runtime", "running", "Checking Docker and scheduler...")
    try:
        runtime = inspect_docker_runtime()
        check_scheduler_runtime(request)
    except Exception as exc:
        yield step_event("runtime", "failed", str(exc))
        yield complete_event(False, error=str(exc))
        return
    # Only engine-derived capacity can reach the worker. Ignore client snapshots.
    request["runtime_ram_bytes"] = runtime.ram_bytes
    request["runtime_cpu_threads"] = runtime.cpu_threads
    yield step_event("runtime", "done", f"Docker is ready: {runtime.cpu_threads} CPU threads, {runtime.ram_bytes / (1024 ** 3):.1f} GiB RAM")

    yield step_event("resources", "running", "Checking local resources...")
    try:
        threads = int(request.get("threads", 4))
        if threads > runtime.cpu_threads:
            raise ValueError(
                f"Threads ({threads}) exceed Docker's {runtime.cpu_threads} available CPU threads."
            )
        total_mib = runtime.ram_bytes // (1024 * 1024)
        percent = int(request.get("ram_percent", 100))
        allocated = total_mib * percent // 100
        required = get_profile_peak_ram_mib(request)
        if required > allocated:
            shortage = build_resource_shortage(allocated, required, total_mib, percent)
            summary = str(shortage["summary"])
            yield step_event("resources", "failed", summary, solutions=shortage)
            yield complete_event(False, error=summary)
            return
    except Exception as exc:
        yield step_event("resources", "failed", str(exc))
        yield complete_event(False, error=str(exc))
        return
    yield step_event("resources", "done", "Sufficient Docker resources")

    yield step_event("images", "running", "Checking Docker images...")
    try:
        images = set()
        for key in request.get("selected_tools", {}).values():
            tool = TOOL_DEFS.get(key, {})
            if not tool or not is_tool_enabled(key):
                continue
            images.update(str(tool[name]) for name in ("image", "base_image") if tool.get(name))
        missing = [name for name in sorted(images) if not image_exists(name)]
        if missing:
            raise RuntimeError(
                "Docker images are missing. Download them from Tools Configuration: " + ", ".join(missing)
            )
    except Exception as exc:
        yield step_event("images", "failed", str(exc))
        yield complete_event(False, error=str(exc))
        return
    from pipeline.export import export_conversion_error
    error = export_conversion_error(request)
    if error:
        yield step_event("images", "failed", error)
        yield complete_event(False, error=error)
        return
    yield step_event("images", "done", "All Docker images are ready")
