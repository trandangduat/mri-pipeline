"""Inspect the Docker engine without creating a container."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

from .hardware import _total_ram_bytes
from .win_process import no_window_kwargs


@dataclass(frozen=True)
class DockerRuntime:
    cpu_threads: int
    ram_bytes: int


def inspect_docker_runtime() -> DockerRuntime:
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{json .}}"],
            capture_output=True, text=True, timeout=15, **no_window_kwargs(),
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Docker is not installed or is not in PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Docker did not respond. Start Docker and retry.") from exc
    except OSError as exc:
        raise RuntimeError(f"Could not start Docker: {exc}") from exc
    if result.returncode != 0:
        raise RuntimeError("The Docker engine is unavailable. Start Docker and retry.")
    try:
        info = json.loads(result.stdout)
        if str(info.get("OSType", "")).lower() != "linux":
            raise RuntimeError("This pipeline requires Docker Linux containers.")
        cpus = int(info["NCPU"])
        memory = int(info["MemTotal"])
        if cpus < 1 or memory < 1:
            raise ValueError("invalid engine capacity")
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise RuntimeError("Docker did not report valid CPU and RAM capacity.") from exc
    host_memory = _total_ram_bytes()
    return DockerRuntime(
        cpu_threads=min(cpus, os.cpu_count() or cpus),
        ram_bytes=min(memory, host_memory) if host_memory else memory,
    )
