from __future__ import annotations

import platform
import shutil
import re
import subprocess
from typing import Callable, TypeAlias

from pipeline.hardware import _host_info
from pipeline.win_process import no_window_kwargs

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
CommandLocator = Callable[[str], str | None]
VersionProvider = Callable[[], str]


def _docker_version(docker_path: str) -> str:
    if not docker_path:
        return ""
    try:
        res = subprocess.run([docker_path, "--version"], capture_output=True, text=True, timeout=3, **no_window_kwargs())
        if res.returncode == 0 and res.stdout:
            m = re.search(r"version\s+([0-9]+(?:\.[0-9]+)+)", res.stdout.strip(), re.IGNORECASE)
            return m.group(1) if m else res.stdout.strip()
    except Exception:
        pass
    return ""


class LocalEnvironmentService:
    def __init__(
        self,
        which: CommandLocator | None = None,
        python_version: VersionProvider | None = None,
        docker_version: Callable[[str], str] | None = None,
    ) -> None:
        self.which = which or shutil.which
        self.python_version = python_version or platform.python_version
        self.docker_version = docker_version or _docker_version

    def status(self) -> dict[str, JsonValue]:
        python = self._python_status()
        docker = self._docker_status()
        ssh = self._command_status("ssh")
        return {
            "ok": bool(python["ok"] and docker["ok"] and ssh["ok"]),
            "python": python,
            "docker": docker,
            "ssh": ssh,
            "hardware": _hardware_status(),
        }

    def _python_status(self) -> dict[str, JsonValue]:
        path = self.which("python3") or self.which("python") or ""
        return {"ok": bool(path), "path": path, "version": self.python_version()}

    def _docker_status(self) -> dict[str, JsonValue]:
        path = self.which("docker") or ""
        version = self.docker_version(path) if path else ""
        data: dict[str, JsonValue] = {"ok": bool(path), "path": path}
        if version:
            data["version"] = version
        return data

    def _command_status(self, command: str) -> dict[str, JsonValue]:
        path = self.which(command) or ""
        return {"ok": bool(path), "path": path}


def _hardware_status() -> dict[str, JsonValue]:
    info = _host_info()
    return {
        "hostname": str(info.get("hostname", "") or ""),
        "logical_cores": info.get("logical_cores"),
        "physical_cores": info.get("physical_cores"),
        "total_ram_bytes": info.get("total_ram_bytes"),
        "gpus": info.get("gpus", []),
    }
