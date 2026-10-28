"""Sample GPU process memory only when container ownership can be verified."""
from __future__ import annotations

import csv
import json
import re
import subprocess
from pathlib import Path

from .win_process import no_window_kwargs


def _query(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=1,
                            **no_window_kwargs())
    if result.returncode:
        raise ValueError(f"{command[0]} query failed")
    return result.stdout.strip()


def _process_identity(pid: int, container_id: str) -> str:
    """Check the full Docker cgroup ID, namespace, and process start time."""
    root = Path("/proc") / str(pid)
    cgroups = (root / "cgroup").read_text()
    if not re.search(rf"(?:/|:){re.escape(container_id)}(?:/|$)|"
                     rf"/docker-{re.escape(container_id)}\.scope(?:/|$)", cgroups, re.M):
        raise ValueError("Container PID namespace or cgroup ownership is unverifiable")
    # NVML PIDs must be visible in the host namespace used by Docker top.
    status = (root / "status").read_text()
    nspid = next((line.split()[1:] for line in status.splitlines()
                  if line.startswith("NSpid:")), [])
    if not nspid or nspid[0] != str(pid):
        raise ValueError("Host process identity is unverifiable")
    fields = (root / "stat").read_text().rsplit(")", 1)[1].split()
    return fields[19]  # starttime, field 22; comm may contain spaces or parentheses.


class ContainerGPUMemoryCollector:
    """No samples means unknown, including when CUDA has not started yet."""

    def __init__(self, container: str | None, device: str | None) -> None:
        self.container = container
        self.device = device
        self.uuid: str | None = None
        self.container_id: str | None = None
        self.valid_samples = 0

    def _members(self) -> tuple[str, dict[int, str]]:
        details = json.loads(_query(["docker", "inspect", self.container]))[0]
        container_id = details["Id"]
        if not re.fullmatch(r"[0-9a-f]{64}", container_id) or not details["State"]["Running"]:
            raise ValueError("Container is not running with a full identity")
        if self.container_id is not None and container_id != self.container_id:
            raise ValueError("Container identity changed during measurement")
        if details["HostConfig"].get("PidMode") == "host":
            raise ValueError("Shared host PID mode is unsupported")
        root_pid = int(details["State"]["Pid"])
        pids = _query(["docker", "top", self.container, "-eo", "pid"]).splitlines()
        if not pids or pids[0].strip() != "PID":
            raise ValueError("Docker process membership is unavailable")
        owned = [int(line.strip()) for line in pids[1:]]
        if root_pid not in owned or len(owned) != len(set(owned)):
            raise ValueError("Docker process membership is ambiguous")
        return container_id, {pid: _process_identity(pid, container_id) for pid in owned}

    def sample(self) -> tuple[int | None, dict]:
        reason = ""
        value = None
        try:
            if not self.container or self.device is None:
                raise ValueError("A named container and one selected GPU are required")
            if self.uuid is None:
                rows = list(csv.reader(_query([
                    "nvidia-smi", "-i", self.device,
                    "--query-gpu=uuid,mig.mode.current", "--format=csv,noheader,nounits",
                ]).splitlines(), skipinitialspace=True))
                if (len(rows) != 1 or len(rows[0]) != 2
                        or not rows[0][0].startswith("GPU-")
                        or rows[0][1].strip().lower() not in {"disabled", "n/a", "[n/a]"}):
                    raise ValueError("Physical GPU UUID or non-MIG mode is unverifiable")
                self.uuid = rows[0][0].strip()
            container_id, before = self._members()
            self.container_id = container_id
            output = _query([
                "nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_gpu_memory,process_name",
                "--format=csv,noheader,nounits",
            ])
            samples = []
            seen = set()
            for row in csv.reader(output.splitlines(), skipinitialspace=True):
                if len(row) < 4:
                    raise ValueError("Incomplete GPU process query")
                uuid, pid = row[0].strip(), int(row[1])
                if uuid != self.uuid or pid not in before:
                    continue
                if pid in seen:
                    raise ValueError("Duplicate owned GPU process record")
                seen.add(pid)
                if "nvidia-cuda-mps" in ",".join(row[3:]).lower():
                    raise ValueError("Shared MPS process attribution is unsupported")
                memory = int(row[2])
                if memory < 0:
                    raise ValueError("Negative GPU process memory")
                samples.append(memory)
            if not samples:
                raise ValueError("No measured container GPU process memory")
            after_id, after = self._members()
            if after_id != container_id or before != after:
                raise ValueError("Container processes changed during measurement")
            value = sum(samples)
            self.valid_samples += 1
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError, TypeError) as exc:
            reason = str(exc) or type(exc).__name__
        return value, {
            "method": "nvidia-smi-processes+cgroup",
            "container_id": self.container_id,
            "gpu_uuid": self.uuid,
            "valid_samples": self.valid_samples,
            "reason": reason,
        }
