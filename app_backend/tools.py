from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Callable, TypeAlias

from pipeline.registry import TOOL_DEFS
from remote.remote_runner import RemoteRunConfig, RemoteRunner
from app_backend.remote import parse_remote_config

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True)
class CommandResult:
    returncode: int


CommandRunner = Callable[[list[str]], CommandResult]


class LocalToolService:
    def __init__(
        self,
        command_runner: CommandRunner | None = None,
        remote_runner_factory: Callable[[RemoteRunConfig], object] | None = None,
    ) -> None:
        self.command_runner = command_runner or _default_command_runner
        self.remote_runner_factory = remote_runner_factory or _default_remote_runner_factory

    def image_status(
        self,
        selected_tools: dict[str, object] | None = None,
        target: str = "Local",
        remote: dict[str, object] | None = None,
    ) -> dict[str, JsonValue]:
        if target not in {"Local", "Server"}:
            return {"ok": False, "error": "target must be Local or Server"}
        if selected_tools is not None and any(not isinstance(tool, str) for tool in selected_tools.values()):
            return {"ok": False, "error": "selected_tools values must be strings"}

        image_tools, warnings = _image_tools(selected_tools)

        if target == "Server":
            if not isinstance(remote, dict):
                return {"ok": False, "error": "remote config is required for Server target"}
            parsed = parse_remote_config(remote)
            if parsed["errors"]:
                return {"ok": False, "errors": parsed["errors"]}
            config = parsed["config"]
            assert isinstance(config, RemoteRunConfig)
            try:
                runner = self.remote_runner_factory(config)
                statuses = runner.check_image_statuses(list(image_tools.keys()))  # type: ignore[attr-defined]
            except Exception:
                return {"ok": False, "target": "Server", "error": "Remote Docker image check failed"}

            images: list[JsonValue] = []
            for image, tools in image_tools.items():
                installed = bool(statuses.get(image, False))
                images.append({"image": image, "status": "Installed" if installed else "Missing", "tools": tools})
            return {"ok": True, "target": "Server", "images": images, "warnings": warnings}

        images: list[JsonValue] = []
        for image, tools in image_tools.items():
            try:
                result = self.command_runner(["docker", "image", "inspect", image])
            except Exception:
                return {"ok": False, "error": "Docker command failed"}
            images.append({"image": image, "status": "Installed" if result.returncode == 0 else "Missing", "tools": tools})
        return {"ok": True, "target": "Local", "images": images, "warnings": warnings}

    def local_image_status(self, selected_tools: dict[str, object] | None = None) -> dict[str, JsonValue]:
        return self.image_status(selected_tools=selected_tools, target="Local")


def _default_command_runner(command: list[str]) -> CommandResult:
    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    return CommandResult(returncode=int(result.returncode))


def _default_remote_runner_factory(config: RemoteRunConfig) -> object:
    return RemoteRunner(config, on_log=lambda _line: None)


def _image_tools(selected_tools: dict[str, object] | None) -> tuple[dict[str, list[str]], list[JsonValue]]:
    image_tools: dict[str, list[str]] = {}
    warnings: list[JsonValue] = []
    tool_keys = list(selected_tools.values()) if selected_tools else list(TOOL_DEFS)
    for tool_key in tool_keys:
        tool = TOOL_DEFS.get(tool_key)
        if not tool:
            warnings.append(f"Unknown tool ignored: {tool_key}")
            continue
        image = str(tool.get("image", "") or "")
        if not image:
            continue
        image_tools.setdefault(image, []).append(tool_key)
    return image_tools, warnings
