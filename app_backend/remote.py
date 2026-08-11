from __future__ import annotations

import stat
from pathlib import Path
from typing import Callable, Protocol, TypeAlias

from remote.remote_runner import RemoteRunConfig, RemoteRunner
from remote.ssh_client import SSHConfig

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


class RemoteJobLister(Protocol):
    def list_background_jobs(self) -> list[dict[str, object]]:
        ...


class RemoteConnectionInspector(RemoteJobLister, Protocol):
    def test_ssh(self) -> None:
        ...

    def remote_hardware_info(self) -> dict[str, object]:
        ...


RunnerFactory = Callable[[RemoteRunConfig], RemoteJobLister]


class RemoteJobService:
    def __init__(self, runner_factory: RunnerFactory | None = None) -> None:
        self.runner_factory = runner_factory or _default_runner_factory

    def validate_config(self, data: dict[str, object]) -> dict[str, JsonValue]:
        parsed = parse_remote_config(data)
        if parsed["errors"]:
            return {"ok": False, "errors": parsed["errors"]}
        config = parsed["config"]
        assert isinstance(config, RemoteRunConfig)
        from remote.ssh_key import inspect_ssh_key
        inspection = inspect_ssh_key(config.ssh.key_path)
        if inspection.error_message:
            return {
                "ok": False,
                "connected": False,
                "error": inspection.error_message,
                "config": _safe_config_summary(config),
            }
        try:
            runner = self.runner_factory(config)
            runner.test_ssh()
            hardware = runner.remote_hardware_info()
        except Exception as exc:
            return {
                "ok": False,
                "connected": False,
                "error": _safe_error_message(exc, config),
                "config": _safe_config_summary(config),
            }
        response: dict[str, JsonValue] = {
            "ok": True,
            "connected": True,
            "config": _safe_config_summary(config),
            "hardware": _hardware_summary(hardware),
        }
        if inspection.warning_message:
            response["warnings"] = [inspection.warning_message]
        return response

    def list_jobs(self, data: dict[str, object]) -> dict[str, JsonValue]:
        parsed = parse_remote_config(data)
        if parsed["errors"]:
            return {"ok": False, "errors": parsed["errors"]}
        config = parsed["config"]
        assert isinstance(config, RemoteRunConfig)
        try:
            jobs = self.runner_factory(config).list_background_jobs()
        except Exception:
            return {"ok": False, "error": "Remote job listing failed"}
        return {"ok": True, "jobs": [_job_summary(job) for job in jobs]}


def _default_runner_factory(config: RemoteRunConfig) -> RemoteJobLister:
    return RemoteRunner(config, on_log=lambda _line: None)


def parse_remote_config(data: dict[str, object]) -> dict[str, object]:
    host = str(data.get("host", "") or "").strip()
    username = str(data.get("username", "") or "").strip()
    key_path = str(data.get("key_path", "") or "").strip()
    workspace = str(data.get("workspace", "~/mri-remote-jobs") or "~/mri-remote-jobs").strip()
    remote_python = str(data.get("python", data.get("remote_python", "python3")) or "python3").strip()
    errors: list[JsonValue] = []
    try:
        port = int(data.get("port", 22) or 22)
    except (TypeError, ValueError):
        port = 0
    if not host:
        errors.append("Remote host is required.")
    if not username:
        errors.append("Remote username is required.")
    if port < 1 or port > 65535:
        errors.append("Remote port must be between 1 and 65535.")
    if not workspace:
        errors.append("Remote workspace is required.")
    if not remote_python:
        errors.append("Remote Python command is required.")
    if errors:
        return {"errors": errors, "config": None}
    return {
        "errors": [],
        "config": RemoteRunConfig(
            ssh=SSHConfig(
                host=host,
                port=port,
                username=username,
                password=str(data.get("password", "") or ""),
                key_path=key_path,
            ),
            remote_workspace=workspace,
            remote_python=remote_python,
            output_dir=str(data.get("output_dir", "") or ""),
        ),
    }


def _safe_config_summary(config: object) -> dict[str, JsonValue]:
    assert isinstance(config, RemoteRunConfig)
    return {
        "host": config.ssh.host,
        "port": int(config.ssh.port),
        "username": config.ssh.username,
        "auth_method": "key" if config.ssh.key_path else ("password" if config.ssh.password else "none"),
        "workspace": config.remote_workspace,
        "python": config.remote_python,
    }


def _ssh_key_error(key_path: str) -> str:
    if not key_path:
        return ""
    path = Path(key_path).expanduser()
    if not path.exists():
        return f"SSH key file was not found: {key_path}"
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        return _safe_error_message(exc)
    if mode & 0o077:
        return (
            f"SSH key file permissions are too open ({mode:04o}). "
            "Copy the key into the Linux filesystem, run chmod 600 on it, then use that path."
        )
    return ""


def _safe_error_message(exc: Exception, config: RemoteRunConfig | None = None) -> str:
    message = str(exc).strip()
    if not message:
        return "SSH connection failed"
    if config is not None:
        for secret in (config.ssh.password, config.ssh.key_path):
            if secret:
                message = message.replace(secret, "[redacted]")
    return f"SSH connection failed: {message}"


def _hardware_summary(hardware: dict[str, object]) -> dict[str, JsonValue]:
    return {
        "hostname": str(hardware.get("hostname", "") or ""),
        "logical_cores": _int_or_none(hardware.get("logical_cores")),
        "total_ram_bytes": _int_or_none(hardware.get("total_ram_bytes")),
    }


def _int_or_none(value: object) -> int | None:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _job_summary(job: dict[str, object]) -> dict[str, JsonValue]:
    return {
        "target": "Server",
        "state": str(job.get("state", "unknown") or "unknown"),
        "pid": str(job.get("pid", "") or ""),
        "remote_job_dir": str(job.get("remote_job_dir", "") or ""),
    }
