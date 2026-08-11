from __future__ import annotations

import platform
import shutil
from typing import Callable, TypeAlias

from pipeline.hardware import _host_info

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
CommandLocator = Callable[[str], str | None]
VersionProvider = Callable[[], str]


class LocalEnvironmentService:
    def __init__(self, which: CommandLocator | None = None, python_version: VersionProvider | None = None) -> None:
        self.which = which or shutil.which
        self.python_version = python_version or platform.python_version

    def status(self) -> dict[str, JsonValue]:
        python = self._python_status()
        docker = self._command_status("docker")
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
    }
