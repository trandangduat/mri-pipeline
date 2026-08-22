from __future__ import annotations
import os
import socket
import platform
import json
import subprocess
from pathlib import Path
from datetime import datetime

def _read_cpuinfo() -> dict[str, str | int | None]:
    info: dict[str, str | int | None] = {
        "cpu_vendor": None,
        "cpu_model": None,
        "physical_cores": None,
    }
    path = Path("/proc/cpuinfo")
    if not path.exists():
        return info
    try:
        blocks = path.read_text(encoding="utf-8", errors="replace").strip().split("\n\n")
    except OSError:
        return info

    physical_core_ids: set[tuple[str, str]] = set()
    physical_ids: set[str] = set()
    core_count_values: set[int] = set()
    for block in blocks:
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
        if not fields:
            continue
        info["cpu_vendor"] = info["cpu_vendor"] or fields.get("vendor_id") or fields.get("CPU implementer")
        info["cpu_model"] = info["cpu_model"] or fields.get("model name") or fields.get("Hardware") or fields.get("Processor")
        physical_id = fields.get("physical id")
        core_id = fields.get("core id")
        if physical_id is not None:
            physical_ids.add(physical_id)
        if physical_id is not None and core_id is not None:
            physical_core_ids.add((physical_id, core_id))
        if fields.get("cpu cores"):
            try:
                core_count_values.add(int(fields["cpu cores"]))
            except ValueError:
                pass

    if physical_core_ids:
        info["physical_cores"] = len(physical_core_ids)
    elif physical_ids and core_count_values:
        info["physical_cores"] = len(physical_ids) * max(core_count_values)
    elif core_count_values:
        info["physical_cores"] = max(core_count_values)
    return info

def _total_ram_bytes() -> int | None:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages * page_size)
    except (AttributeError, OSError, ValueError):
        return None


def _gpu_info() -> list[dict]:
    """Probe local NVIDIA GPUs via nvidia-smi; [] when unavailable."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free,memory.total,name", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    gpus: list[dict] = []
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
            {
                "name": parts[2] if len(parts) > 2 else f"gpu_{index}",
                "total_memory_mib": total_mib,
                "free_memory_mib": free_mib,
            }
        )
    return gpus


def _host_info() -> dict:
    cpuinfo = _read_cpuinfo()
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "cpu_vendor": cpuinfo.get("cpu_vendor"),
        "cpu_model": cpuinfo.get("cpu_model") or platform.processor() or None,
        "logical_cores": os.cpu_count(),
        "physical_cores": cpuinfo.get("physical_cores"),
        "total_ram_bytes": _total_ram_bytes(),
        "gpus": _gpu_info(),
    }

def _safe_batch_config(config: dict | None) -> dict:
    data = dict(config or {})
    for key in ("remote",):
        data.pop(key, None)
    return data
