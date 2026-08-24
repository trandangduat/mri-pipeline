from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from typing import Callable, TypeAlias

from pipeline.docker_ops import format_image_size, image_size_bytes
from pipeline.registry import TOOL_DEFS, tool_display_name
from remote.remote_runner import RemoteRunConfig, RemoteRunner
from remote.ssh_client import RemoteSSHClient
from app_backend.remote import parse_remote_config

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True)
class CommandResult:
    returncode: int


@dataclass(frozen=True)
class ImageInfo:
    size_bytes: int | None = None
    image_id: str | None = None


CommandRunner = Callable[[list[str]], CommandResult]
ImageInfoProvider = Callable[[str], ImageInfo]


class LocalToolService:
    def __init__(
        self,
        command_runner: CommandRunner | None = None,
        remote_runner_factory: Callable[[RemoteRunConfig], object] | None = None,
        image_info_provider: ImageInfoProvider | None = None,
    ) -> None:
        self.command_runner = command_runner or _default_command_runner
        self.remote_runner_factory = remote_runner_factory or _default_remote_runner_factory
        self.image_info_provider = image_info_provider or _default_image_info_provider

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

        image_tools, image_tool_details, warnings = _image_tools(selected_tools)

        if target == "Server":
            if not isinstance(remote, dict):
                return {"ok": False, "error": "remote config is required for Server target"}
            parsed = parse_remote_config(remote)
            if parsed["errors"]:
                return {"ok": False, "errors": parsed["errors"]}
            config = parsed["config"]
            assert isinstance(config, RemoteRunConfig)
            try:
                runner: RemoteRunner = self.remote_runner_factory(config)  # type: ignore[assignment]
                image_list = list(image_tools.keys())
                states = runner.check_image_states(image_list)
            except Exception:
                return {"ok": False, "target": "Server", "error": "Remote Docker image check failed"}

            images: list[JsonValue] = []
            for image, tools in image_tools.items():
                state = states.get(image, {"status": "Missing"})
                status = str(state.get("status", "Missing"))
                entry: dict[str, JsonValue] = {
                    "image": image,
                    "status": status,
                    "tools": tools,
                    "tool_details": image_tool_details.get(image, []),
                    "repo_size": None,
                    "uncompressed_size": None,
                    "image_id": None,
                }
                pull_status = state.get("pull_status")
                if pull_status:
                    entry["pull_status"] = pull_status
                    entry["pull_pid"] = state.get("pull_pid")
                    entry["pull_started_at"] = state.get("pull_started_at")
                    entry["pull_updated_at"] = state.get("pull_updated_at")
                    entry["pull_error"] = state.get("pull_error")
                images.append(entry)
            return {"ok": True, "target": "Server", "images": images, "warnings": warnings}

        images: list[JsonValue] = []
        for image, tools in image_tools.items():
            try:
                result = self.command_runner(["docker", "image", "inspect", image])
            except Exception:
                return {"ok": False, "error": "Docker command failed"}
            installed = result.returncode == 0
            entry: dict[str, JsonValue] = {
                "image": image,
                "status": "Installed" if installed else "Missing",
                "tools": tools,
                "tool_details": image_tool_details.get(image, []),
            }
            if installed:
                info = self.image_info_provider(image)
                entry["repo_size"] = format_image_size(info.size_bytes)
                entry["uncompressed_size"] = format_image_size(info.size_bytes)
                entry["image_id"] = info.image_id
            else:
                entry["repo_size"] = None
                entry["uncompressed_size"] = None
                entry["image_id"] = None
            images.append(entry)
        return {"ok": True, "target": "Local", "images": images, "warnings": warnings}

    def local_image_status(self, selected_tools: dict[str, object] | None = None) -> dict[str, JsonValue]:
        return self.image_status(selected_tools=selected_tools, target="Local")

    def pull_image(
        self,
        image: str,
        target: str = "Local",
        remote: dict[str, object] | None = None,
    ) -> dict[str, JsonValue]:
        if target == "Server":
            return self._pull_image_server(image, remote)
        return self._pull_image_local(image)

    def _pull_image_local(self, image: str) -> dict[str, JsonValue]:
        try:
            proc = subprocess.Popen(
                ["docker", "pull", image],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            logs: list[str] = []
            for line in proc.stdout:
                line = line.strip()
                if line:
                    logs.append(line)
            proc.wait()
            if proc.returncode == 0:
                return {"ok": True, "target": "Local", "image": image, "status": "success"}
            return {"ok": False, "error": "\n".join(logs[-5:]) if logs else f"Pull failed (exit {proc.returncode})"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _pull_image_server(
        self,
        image: str,
        remote: dict[str, object] | None = None,
    ) -> dict[str, JsonValue]:
        if not isinstance(remote, dict):
            return {"ok": False, "error": "remote config is required for Server target"}
        parsed = parse_remote_config(remote)
        if parsed["errors"]:
            return {"ok": False, "errors": parsed["errors"]}
        config = parsed["config"]
        assert isinstance(config, RemoteRunConfig)
        try:
            runner: RemoteRunner = self.remote_runner_factory(config)  # type: ignore[assignment]
            result = runner.start_remote_image_pull(image)
            return result  # type: ignore[return-value]
        except Exception as exc:
            return {"ok": False, "target": "Server", "error": str(exc)}

    def server_pull_status(
        self,
        image: str,
        remote: dict[str, object] | None = None,
        log_offset: int = 0,
    ) -> dict[str, JsonValue]:
        """Poll the background docker pull state on the server for the Tools page.

        Reads the pull tracking JSON and the tail of the pull log (from
        ``log_offset`` on) without modifying the remote runner.
        """
        if not isinstance(remote, dict):
            return {"ok": False, "error": "remote config is required for Server target"}
        parsed = parse_remote_config(remote)
        if parsed["errors"]:
            return {"ok": False, "errors": parsed["errors"]}
        config = parsed["config"]
        assert isinstance(config, RemoteRunConfig)
        try:
            runner: RemoteRunner = self.remote_runner_factory(config)  # type: ignore[assignment]
            paths = RemoteRunner.remote_pull_paths(image)
            state: dict[str, object] = {}
            log_text = ""
            with RemoteSSHClient(runner.config.ssh, runner.on_log) as ssh:
                json_code, json_text = ssh.read_text(f"cat {shlex.quote(paths['json'])} 2>/dev/null")
                if json_code == 0 and json_text.strip():
                    try:
                        loaded = json.loads(json_text.strip())
                        if isinstance(loaded, dict):
                            state = loaded
                    except (json.JSONDecodeError, ValueError):
                        pass
                log_code, log_text = ssh.read_text(
                    f"tail -c +{int(log_offset) + 1} {shlex.quote(paths['log'])} 2>/dev/null | head -c 65536"
                )
                if log_code != 0:
                    log_text = ""
            exit_code = state.get("exit_code") if isinstance(state.get("exit_code"), int) else None
            return {
                "ok": True,
                "target": "Server",
                "image": image,
                "status": str(state.get("status") or ""),
                "exit_code": exit_code,
                "error": str(state.get("error") or "") or None,
                "log_text": log_text,
                "next_offset": int(log_offset) + len(log_text.encode("utf-8")),
            }
        except Exception as exc:
            return {"ok": False, "target": "Server", "error": str(exc)}

    def remove_image(self, image: str, target: str = "Local", remote: dict[str, object] | None = None) -> dict[str, JsonValue]:
        if target == "Server":
            return self._remove_image_server(image, remote)
        ok, error = self._remove_image_local(image)
        return {"ok": ok, "error": error or None}

    def _remove_image_local(self, image: str) -> tuple[bool, str]:
        from pipeline.docker_ops import remove_image as _remove_image
        return _remove_image(image)

    def _remove_image_server(
        self,
        image: str,
        remote: dict[str, object] | None = None,
    ) -> dict[str, JsonValue]:
        if not isinstance(remote, dict):
            return {"ok": False, "error": "remote config is required for Server target"}
        parsed = parse_remote_config(remote)
        if parsed["errors"]:
            return {"ok": False, "errors": parsed["errors"]}
        config = parsed["config"]
        assert isinstance(config, RemoteRunConfig)
        try:
            runner: RemoteRunner = self.remote_runner_factory(config)  # type: ignore[assignment]
            results = runner.remove_images([image])
            ok, msg = results.get(image, (False, "Unknown error"))
            return {"ok": ok, "target": "Server", "error": msg or None}
        except Exception as exc:
            return {"ok": False, "target": "Server", "error": str(exc)}


def _default_command_runner(command: list[str]) -> CommandResult:
    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    return CommandResult(returncode=int(result.returncode))


def _default_remote_runner_factory(config: RemoteRunConfig) -> object:
    return RemoteRunner(config, on_log=lambda _line: None)


def _default_image_info_provider(image: str) -> ImageInfo:
    size = image_size_bytes(image)
    image_id = None
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", image, "--format", "{{.Id}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        raw_id = proc.stdout.strip() if proc.returncode == 0 else ""
        image_id = raw_id[:19] if raw_id else None
    except Exception:
        pass
    return ImageInfo(size_bytes=size, image_id=image_id)


def _image_tools(selected_tools: dict[str, object] | None) -> tuple[dict[str, list[str]], dict[str, list[dict[str, str]]], list[JsonValue]]:
    image_tools: dict[str, list[str]] = {}
    image_tool_details: dict[str, list[dict[str, str]]] = {}
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
        image_tool_details.setdefault(image, []).append({"key": tool_key, "name": tool_display_name(tool_key)})
    return image_tools, image_tool_details, warnings
