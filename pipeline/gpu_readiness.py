"""GPU compute readiness. This does not measure MRI telemetry."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path

from .win_process import no_window_kwargs

CUDA_PROBE = (
    "import torch; assert torch.cuda.is_available(), 'CUDA is unavailable'; "
    "x=torch.ones(1024,device='cuda'); "
    "assert x.sum().item()==1024; torch.cuda.synchronize(); print('GPU_CHECK_OK')"
)
TF_PROBE = (
    "import tensorflow as tf; assert tf.config.list_physical_devices('GPU'), 'CUDA is unavailable'; "
    "tf.config.set_soft_device_placement(False); "
    "\nwith tf.device('/GPU:0'): x=tf.reduce_sum(tf.ones([1024]))"
    "\nassert float(x.numpy())==1024; print('GPU_CHECK_OK')"
)
TORCH_TOOLS = {"fastsurfer_segmentation", "fastsurfervinn", "hdbet", "corticalflow", "sugar"}
FSPYTHON_TOOLS = {"synthstrip_fs7"}
TF_TOOLS = {"synthseg_freesurfer_fs7"}
UNSUPPORTED_TOOLS = {"synthseg_standalone"}

MANUAL_URL = "https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
DESKTOP_URL = "https://docs.docker.com/desktop/features/gpu/"


def gpu_enabled(request: dict) -> bool:
    return str(request.get("device", "cpu")).lower() in {"gpu", "cuda"}


def _run(args: list[str], timeout: float = 3, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          **no_window_kwargs(), **kwargs)


def _endpoint() -> str:
    context = os.environ.get("DOCKER_CONTEXT", "").strip()
    host = "" if context else os.environ.get("DOCKER_HOST", "").strip()
    if not host:
        result = _run(["docker", "context", "inspect", *([context] if context else []),
                       "--format", "{{.Endpoints.docker.Host}}"])
        if result.returncode:
            raise ValueError("Cannot identify the Docker endpoint.")
        host = result.stdout.strip()
    if not host.startswith(("unix://", "npipe://")):
        raise ValueError("GPU setup requires a local Docker endpoint on the execution host.")
    return host


def execution_target() -> dict:
    result = _run(["docker", "info", "--format", "{{json .}}"])
    if result.returncode:
        raise ValueError("Docker is unavailable on the execution host.")
    info = json.loads(result.stdout)
    if info.get("OSType") != "linux" or not info.get("ID"):
        raise ValueError("Docker must report a Linux engine identity.")
    endpoint = _endpoint()
    machine_id = ""
    if os.name == "posix":
        try:
            machine_id = Path("/etc/machine-id").read_text().strip()
        except OSError:
            pass
    native = (os.name == "posix" and endpoint.startswith("unix://")
              and "docker desktop" not in str(info.get("OperatingSystem", "")).lower()
              and "linuxkit" not in str(info.get("KernelVersion", "")).lower()
              and str(info.get("Name", "")).split(".")[0].lower() == socket.gethostname().split(".")[0].lower()
              and not any("rootless" in str(item) for item in info.get("SecurityOptions", [])))
    identity = [socket.gethostname(), machine_id, info["ID"], endpoint]
    return {
        "fingerprint": hashlib.sha256(json.dumps(identity).encode()).hexdigest(),
        "label": socket.gethostname(), "engine_id": info["ID"], "endpoint": endpoint,
        "machine_id": machine_id, "native": native,
        "runtimes": sorted(info.get("Runtimes", {})), "os": platform.system(),
    }


def privileged_prefix(target: dict, allow_wsl: bool = False) -> list[str] | None:
    """Only advertise authority verified against this exact Docker daemon."""
    if not target.get("native") or not target.get("machine_id"):
        return None
    candidates = []
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        candidates.append([])
    elif shutil.which("sudo"):
        if _run(["sudo", "-n", "true"]).returncode == 0:
            candidates.append(["sudo", "-n"])
    distro = os.environ.get("WSL_DISTRO_NAME", "")
    if allow_wsl and distro and shutil.which("wsl.exe"):
        candidates.append(["wsl.exe", "-d", distro, "-u", "root", "--"])
    for prefix in candidates:
        try:
            identity = _run([*prefix, "cat", "/etc/machine-id"]).stdout.strip()
            engine = _run([*prefix, "env", "-u", "DOCKER_CONTEXT", "-u", "DOCKER_HOST",
                           "docker", "--host", target["endpoint"], "info", "--format", "{{.ID}}"])
            if identity == target["machine_id"] and engine.returncode == 0 and engine.stdout.strip() == target["engine_id"]:
                if _run([*prefix, "python3", "--version"]).returncode == 0:
                    return prefix
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def repair_capability(target: dict, allow_wsl: bool = False) -> tuple[bool, str]:
    if not target.get("native"):
        return False, "Use the setup instructions for the Docker host. Docker Desktop and rootless Docker require their own setup."
    if target.get("endpoint") not in {"unix:///var/run/docker.sock", "unix:///run/docker.sock"}:
        return False, "Custom Docker sockets require administrator setup."
    try:
        os_release = platform.freedesktop_os_release()
        if os_release.get("ID") not in {"ubuntu", "debian"}:
            return False, "Automatic setup supports Ubuntu and Debian with native Docker."
        if not all(shutil.which(cmd) for cmd in ("apt-get", "curl", "gpg", "systemctl", "python3")):
            return False, "Install the required system utilities using your administrator account."
        service = _run(["systemctl", "show", "docker", "--property=ExecStart", "--value"])
        if service.returncode or "--config-file" in service.stdout:
            return False, "A custom Docker service configuration requires administrator setup."
        if _run(["systemctl", "is-active", "docker"]).returncode != 0:
            return False, "Start the native Docker service before configuring GPU support."
        if privileged_prefix(target, allow_wsl) is None:
            return False, "Administrative access is unavailable. Ask an administrator to follow the setup instructions."
        if shutil.which("fuser") and _run(["fuser", "/var/lib/dpkg/lock-frontend"]).returncode == 0:
            return False, "The package manager is busy. Wait for it to finish, then retry."
        # The installer still handles network failures at each signed-repository step.
        from urllib.request import Request, urlopen
        with urlopen(Request("https://nvidia.github.io/libnvidia-container/gpgkey", method="HEAD"), timeout=3) as response:
            if response.status != 200:
                return False, "The NVIDIA package repository is unavailable."
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return False, "Automatic setup is unavailable: " + str(exc)[:200]
    return True, ""


def failure(code: str, summary: str, target: dict | None = None, *, detail: str = "",
            action: str | None = None, request: dict | None = None) -> dict:
    target = target or {}
    can_execute, reason = False, ""
    if action:
        can_execute, reason = repair_capability(target, allow_wsl=not bool((request or {}).get("_gpu_remote")))
    if code == "GPU_CONFIG_INCOMPATIBLE":
        instructions = ["Check the selected preset/profile, GPU class, device mapping, and memory requirements."]
    elif code == "GPU_RESOURCES_BUSY":
        instructions = ["Wait for other GPU work to finish, then retry preflight."]
    elif code == "GPU_PROBE_UNSUPPORTED":
        instructions = ["Verify CUDA in this tool's processing image, or use a supported tool runtime."]
    else:
        instructions = ["Verify the NVIDIA driver on the Docker execution host.",
                        "For native Linux Docker, install NVIDIA Container Toolkit and configure the Docker runtime.",
                        "For WSL, use the Windows NVIDIA driver; do not install a Linux display driver.",
                        MANUAL_URL]
        if not target.get("native"):
            instructions += ["For Docker Desktop, enable its WSL 2 backend and follow:", DESKTOP_URL]
    title = {"install_toolkit": "Install NVIDIA Container Toolkit and configure Docker",
             "configure_runtime": "Configure NVIDIA support for Docker"}.get(action, "Set up GPU support on the execution host")
    return {
        "ready": False, "code": code, "summary": summary, "target": target,
        "details": detail[-2000:],
        "solutions": [{
            "title": title, "instructions": instructions, "action_id": action if can_execute else None,
            "can_execute": can_execute, "unavailable_reason": reason,
            "target_label": target.get("label", "execution host"),
            "requires_admin": bool(action), "requires_docker_restart": bool(action),
        }],
    }


def _documents(request: dict, gpus: tuple) -> set[str] | None:
    if not request.get("neuroflow_enabled"):
        return
    from . import neuroflow_adapter as adapter
    adapter._ensure_neuroflow_import_path()
    from neuroflow.configuration import (
        load_pipeline_dict, load_pipeline_file, load_profile_set_dict,
        load_profile_set_file, validate_cross_documents,
    )
    import yaml
    root = adapter._neuroflow_config_root()
    if request.get("_gpu_preset_content"):
        pipeline = load_pipeline_dict(yaml.safe_load(request["_gpu_preset_content"]))
    else:
        preset = adapter._preset_id_from_request(request)
        pipeline = load_pipeline_file(request.get("neuroflow_preset_file") or root / "presets" / f"{preset}.yaml")
    profile_id = request.get("neuroflow_profile") or f"{pipeline.pipeline_id}_default"
    if request.get("_gpu_profile_content"):
        profiles = load_profile_set_dict(yaml.safe_load(request["_gpu_profile_content"]))
    else:
        profiles = load_profile_set_file(request.get("neuroflow_profile_file") or root / "profiles" / f"{profile_id}.yaml")
    config = adapter._scheduler_config(request)
    policy = adapter.normalize_policy(request.get("neuroflow_policy"))
    if policy in adapter.FIXED_POLICIES:
        from dataclasses import replace
        defaults = adapter.resolve_defaults(pipeline, request.get("neuroflow_default_configurations"), config.limits)
        pipeline = replace(pipeline, stages=tuple(
            replace(stage, execution_configurations=tuple(c for c in stage.execution_configurations
                if str(c.configuration_id) == defaults[str(stage.stage_id)]))
            if stage.enabled else stage for stage in pipeline.stages))
    pipeline, profiles = adapter._filter_profiles_for_thread_limit(
        pipeline, profiles, int(request.get("threads", 4)), available_gpus=len(gpus))
    validate_cross_documents(pipeline, profiles, config)
    profile_by_id = {profile.profile_id: profile for profile in profiles.profiles}
    candidates = set()
    has_gpu_configuration = False
    for stage in pipeline.stages:
        for execution in stage.execution_configurations:
            if str(execution.execution_mode.value) != "gpu":
                continue
            has_gpu_configuration = True
            profile = profile_by_id[execution.profile_ref]
            memory = max(execution.gpu.minimum_memory_mib or 0,
                         profile.gpu_memory.reservation_mib if profile.gpu_memory else 0)
            classes = execution.gpu.device_classes
            candidates.update(gpu.gpu_id for gpu in gpus
                if gpu.total_memory_mib >= memory and (not classes or gpu.device_class in classes))
    return candidates if has_gpu_configuration else None


def gpu_inventory() -> tuple:
    # Readiness also works without the optional NeuroFLOW scheduler package.
    from types import SimpleNamespace
    query = _run(["nvidia-smi", "--query-gpu=index,uuid,memory.free,memory.total,name",
                  "--format=csv,noheader,nounits"])
    if query.returncode:
        return ()
    gpus, indexes, uuids = [], set(), set()
    for row in csv.reader(query.stdout.splitlines(), skipinitialspace=True):
        try:
            index, device, free, total = int(row[0]), row[1].strip(), int(row[2]), int(row[3])
            if index < 0 or not device.startswith("GPU-") or not 0 <= free <= total or total == 0:
                continue
            if index in indexes or device in uuids:
                raise ValueError("GPU inventory is ambiguous.")
            indexes.add(index)
            uuids.add(device)
            gpus.append(SimpleNamespace(gpu_id=f"gpu_{index}", available=free > 0,
                free_memory_mib=free, total_memory_mib=total, device_class="generic_cuda",
                metadata=(("host_index", str(index)), ("uuid", device))))
        except (IndexError, TypeError):
            continue
    return tuple(gpus)


def probe_specs(request: dict) -> list[tuple[str, str]]:
    from .registry import TOOL_DEFS, is_tool_enabled
    specs = []
    for key in dict(request.get("selected_tools") or {}).values():
        if not key:
            continue
        if key not in TOOL_DEFS:
            raise ValueError(f"Unknown tool: {key}")
        if not is_tool_enabled(key):
            continue
        if key in UNSUPPORTED_TOOLS:
            raise NotImplementedError(f"No supported GPU probe for {key}.")
        kind = ("torch" if key in TORCH_TOOLS else "fspython" if key in FSPYTHON_TOOLS
                else "tensorflow" if key in TF_TOOLS else "access")
        spec = (str(TOOL_DEFS[key]["image"]), kind)
        if spec not in specs:
            specs.append(spec)
    return specs


def _probe(image: str, kind: str, device: str, cancel: threading.Event, timeout: float) -> tuple[int, str]:
    name = "neuroflow-gpu-check-" + uuid.uuid4().hex
    if kind == "access":
        entrypoint, command = "nvidia-smi", ["--query-gpu=uuid", "--format=csv,noheader"]
    elif kind == "torch":
        entrypoint, command = "python3", ["-s", "-c", CUDA_PROBE]
    else:
        import shlex
        code = TF_PROBE if kind == "tensorflow" else CUDA_PROBE
        entrypoint, command = "bash", ["-lc", 'exec "$FREESURFER_HOME/python/bin/python3" -c ' + shlex.quote(code)]
    args = ["docker", "run", "--rm", "--pull=never", "--name", name,
            "--cpus", "1", "--gpus", f"device={device}",
            "-e", "NVIDIA_DRIVER_CAPABILITIES=compute,utility", "--entrypoint", entrypoint, image, *command]
    process = None
    try:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, **no_window_kwargs())
        end = time.monotonic() + timeout
        while True:
            if cancel.is_set():
                raise InterruptedError("GPU check cancelled.")
            if time.monotonic() >= end:
                raise subprocess.TimeoutExpired(args, timeout)
            try:
                output, _ = process.communicate(timeout=min(0.2, max(0.01, end - time.monotonic())))
                return process.returncode, output[-4000:]
            except subprocess.TimeoutExpired:
                continue
    finally:
        try:
            if process is not None and process.poll() is None:
                process.kill()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    if process.stdout:
                        process.stdout.close()
        finally:
            try:
                _run(["docker", "rm", "-f", name], timeout=3)
            except (OSError, subprocess.SubprocessError):
                pass


def check_gpu(request: dict, cancel: threading.Event | None = None) -> dict:
    if not gpu_enabled(request):
        return {"ready": True, "code": "GPU_NOT_REQUIRED", "summary": "GPU acceleration is off.", "solutions": []}
    cancel = cancel or threading.Event()
    target = None
    started = time.monotonic()
    try:
        target = execution_target()
        gpus = gpu_inventory()
        if not gpus:
            return failure("GPU_NOT_FOUND", "No usable NVIDIA GPU was detected on the execution host.", target)
        try:
            candidates = _documents(request, gpus)
            specs = probe_specs(request)
            if not specs:
                return failure("GPU_CONFIG_INCOMPATIBLE", "Select an enabled processing tool before checking GPU support.", target)
        except NotImplementedError as exc:
            return failure("GPU_PROBE_UNSUPPORTED", str(exc), target)
        except Exception as exc:
            return failure("GPU_CONFIG_INCOMPATIBLE", "GPU configuration does not match the selected preset/profile.",
                           target, detail=str(exc))
        available = [gpu for gpu in gpus if gpu.available and
                     (candidates is None or gpu.gpu_id in candidates)]
        if not available:
            return failure("GPU_RESOURCES_BUSY", "No GPU is currently available for the readiness check.", target)
        for gpu in available:
            metadata = dict(gpu.metadata)
            device = metadata["host_index"]
            expected_uuid = metadata["uuid"]
            for image, kind in specs:
                remaining = 60 - (time.monotonic() - started)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired("GPU preflight", 60)
                code, output = _probe(image, kind, device, cancel, min(30, remaining))
                if code == 0 and ((kind == "access" and expected_uuid in output) or
                                  (kind != "access" and "GPU_CHECK_OK" in output)):
                    continue
                text = output.lower()
                runtime_error = code == 125 and any(value in text for value in (
                    "cdi", "capabilities: [[gpu]]", "nvidia-container", "device driver"))
                if runtime_error and target["native"]:
                    toolkit = shutil.which("nvidia-ctk")
                    action = "configure_runtime" if toolkit else "install_toolkit"
                    return failure("GPU_RUNTIME_UNCONFIGURED" if toolkit else "GPU_TOOLKIT_MISSING",
                                   "Docker cannot start a GPU container. NVIDIA container support needs setup.",
                                   target, detail=output, action=action, request=request)
                if "out of memory" in text or "all cuda-capable devices are busy" in text:
                    return failure("GPU_RESOURCES_BUSY", "GPU resources are busy. Retry when they are available.",
                                   target, detail=output)
                return failure("GPU_IMAGE_RUNTIME_FAILED", "The processing image could not run its GPU check.",
                               target, detail=output)
        return {"ready": True, "code": "GPU_READY", "summary": "GPU container checks passed.",
                "target": target, "solutions": [], "details": ""}
    except InterruptedError:
        return failure("GPU_CHECK_CANCELLED", "GPU check cancelled.", target)
    except subprocess.TimeoutExpired:
        return failure("GPU_PROBE_TIMEOUT", "GPU check timed out. Check Docker and the selected processing image.", target)
    except Exception as exc:
        return failure("GPU_SETUP_UNKNOWN", "GPU setup could not be verified.", target, detail=str(exc))


def cli_request() -> dict:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload")
    args = parser.parse_args()
    if args.payload:
        return json.loads(base64.b64decode(args.payload, validate=True))
    import sys
    return json.load(sys.stdin)


if __name__ == "__main__":
    import signal
    stop = threading.Event()
    for name in ("SIGTERM", "SIGHUP", "SIGINT"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: stop.set())
    request = cli_request()
    print("GPU_CHECK:" + json.dumps(check_gpu(request, stop)), flush=True)
