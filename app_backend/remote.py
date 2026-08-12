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

    def read_job_events(self, data: dict[str, object]) -> dict[str, JsonValue]:
        parsed = parse_remote_config(data)
        if parsed["errors"]:
            return {"ok": False, "errors": parsed["errors"]}
        config = parsed["config"]
        assert isinstance(config, RemoteRunConfig)
        remote_job_dir = str(data.get("remote_job_dir") or data.get("job_id") or "").strip()
        offset = _int_val(data.get("offset"), 0)
        limit = _int_val(data.get("limit"), 500)
        try:
            runner = self.runner_factory(config)
            if remote_job_dir and hasattr(runner, "remote_job_dir"):
                runner.remote_job_dir = remote_job_dir
            if hasattr(runner, "read_remote_events"):
                res = runner.read_remote_events(offset=offset, limit=limit)
                return _json_dict(res)
            return {"ok": True, "events": [], "warnings": [], "next_offset": offset}
        except Exception:
            return {"ok": True, "events": [], "warnings": [], "next_offset": offset}

    def read_job_log(self, data: dict[str, object]) -> dict[str, JsonValue]:
        parsed = parse_remote_config(data)
        if parsed["errors"]:
            return {"ok": False, "errors": parsed["errors"]}
        config = parsed["config"]
        assert isinstance(config, RemoteRunConfig)
        remote_job_dir = str(data.get("remote_job_dir") or data.get("job_id") or "").strip()
        offset = _int_val(data.get("offset"), 0)
        try:
            runner = self.runner_factory(config)
            if remote_job_dir and hasattr(runner, "remote_job_dir"):
                runner.remote_job_dir = remote_job_dir
            if hasattr(runner, "read_remote_log_since"):
                text, next_offset = runner.read_remote_log_since(offset=offset)
                return {"ok": True, "text": text, "next_offset": next_offset, "truncated": False}
            return {"ok": True, "text": "", "next_offset": offset, "truncated": False}
        except Exception:
            return {"ok": True, "text": "", "next_offset": offset, "truncated": False}

    def browse_path(self, data: dict[str, object]) -> dict[str, JsonValue]:
        """Read-only SFTP directory/file listing for a remote path.

        Optional request fields:
          path        – remote path to browse (default: workspace or ~)
          recursive   – bool; if True run batch-candidate scan instead of shallow list
          max_depth   – int; max recursion depth for recursive scan (default 1, cap 6)
          purpose     – "browse" | "batch"; batch enables recursive by default at depth 1
        """
        parsed = parse_remote_config(data)
        if parsed["errors"]:
            return {"ok": False, "errors": parsed["errors"]}
        config = parsed["config"]
        assert isinstance(config, RemoteRunConfig)
        raw_path = str(data.get("path", "") or "").strip()
        # Sanitise: reject NUL bytes
        if "\x00" in raw_path:
            return {"ok": False, "error": "Invalid path"}
        # Default to workspace when no path supplied
        browse = raw_path or config.remote_workspace or "~"
        # Recursive / depth params
        purpose = str(data.get("purpose", "browse") or "browse").strip()
        recursive_flag = data.get("recursive")
        if isinstance(recursive_flag, bool):
            recursive = recursive_flag
        elif isinstance(recursive_flag, str):
            recursive = recursive_flag.lower() in ("true", "1", "yes")
        else:
            # batch purpose implies recursive at depth 1 by default
            recursive = purpose == "batch"
        raw_depth = data.get("max_depth")
        try:
            max_depth = max(0, min(int(raw_depth), _BATCH_MAX_DEPTH))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            max_depth = 1 if recursive else 0
        try:
            if recursive:
                return _scan_batch_via_sftp(config.ssh, browse, max_depth=max_depth)
            return _browse_via_sftp(config.ssh, browse)
        except Exception as exc:
            return {"ok": False, "error": f"Browse failed: {exc}"}


_IMAGE_EXTENSIONS = {".nii", ".nii.gz", ".mgz", ".mgh", ".dcm", ".dicom"}
_BROWSE_ENTRY_LIMIT = 500
_BATCH_CANDIDATE_LIMIT = 1000
_BATCH_MAX_DEPTH = 6


def _is_image_file(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(ext) for ext in _IMAGE_EXTENSIONS)


def _file_stem(name: str) -> str:
    """Return filename without any known image extension."""
    lower = name.lower()
    # longest-match first
    for ext in sorted(_IMAGE_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(ext):
            return name[: -len(ext)]
    # fallback: strip last dot-extension
    dot = name.rfind(".")
    return name[:dot] if dot > 0 else name


def _browse_via_sftp(ssh: object, path: str) -> dict[str, JsonValue]:
    import posixpath
    import stat as _stat
    from remote.ssh_client import RemoteSSHClient, SSHConfig
    assert isinstance(ssh, SSHConfig)
    with RemoteSSHClient(ssh) as client:
        try:
            expanded = client.sftp.normalize(path)
        except OSError:
            expanded = path
        try:
            attr = client.sftp.stat(expanded)
        except OSError as exc:
            return {"ok": False, "error": f"Path not found: {exc}"}
        is_dir = _stat.S_ISDIR(attr.st_mode) if attr.st_mode else False
        if is_dir:
            browse_dir = expanded
        else:
            browse_dir = posixpath.dirname(expanded)
        parent = posixpath.dirname(browse_dir)
        if parent == browse_dir:
            parent = browse_dir
        try:
            raw_entries = client.sftp.listdir_attr(browse_dir)
        except OSError as exc:
            return {"ok": False, "error": f"Cannot list directory: {exc}"}
        dirs: list[dict[str, JsonValue]] = []
        files: list[dict[str, JsonValue]] = []
        image_count = 0
        for entry in raw_entries:
            if len(dirs) + len(files) >= _BROWSE_ENTRY_LIMIT:
                break
            entry_mode = entry.st_mode or 0
            is_entry_dir = _stat.S_ISDIR(entry_mode)
            entry_name: str = entry.filename
            entry_path = posixpath.join(browse_dir, entry_name)
            is_img = not is_entry_dir and _is_image_file(entry_name)
            if is_img:
                image_count += 1
            row: dict[str, JsonValue] = {
                "name": entry_name,
                "path": entry_path,
                "kind": "directory" if is_entry_dir else "file",
                "size": int(entry.st_size or 0) if not is_entry_dir else None,
                "modified_at": int(entry.st_mtime or 0) if entry.st_mtime else None,
                "selectable": is_entry_dir or is_img,
            }
            if is_entry_dir:
                dirs.append(row)
            else:
                files.append(row)
        dirs.sort(key=lambda e: str(e["name"]).lower())
        files.sort(key=lambda e: str(e["name"]).lower())
        return {
            "ok": True,
            "path": browse_dir,
            "parent": parent,
            "entries": dirs + files,
            "image_count": image_count,
        }


def _scan_batch_via_sftp(ssh: object, root: str, *, max_depth: int = 1) -> dict[str, JsonValue]:
    """Recursively collect image-file candidates under root for batch processing.

    Returns entries with optional subject_label, relative_path, depth fields.
    Directories are NOT included in results – only image file candidates.
    Result is capped at _BATCH_CANDIDATE_LIMIT entries.
    """
    import posixpath
    import stat as _stat
    from remote.ssh_client import RemoteSSHClient, SSHConfig
    assert isinstance(ssh, SSHConfig)
    with RemoteSSHClient(ssh) as client:
        try:
            expanded = client.sftp.normalize(root)
        except OSError:
            expanded = root
        try:
            attr = client.sftp.stat(expanded)
        except OSError as exc:
            return {"ok": False, "error": f"Path not found: {exc}"}
        is_dir = _stat.S_ISDIR(attr.st_mode) if attr.st_mode else False
        scan_root = expanded if is_dir else posixpath.dirname(expanded)

        candidates: list[dict[str, JsonValue]] = []

        def _recurse(current_dir: str, depth: int, subject_hint: str | None) -> None:
            if len(candidates) >= _BATCH_CANDIDATE_LIMIT:
                return
            try:
                entries = client.sftp.listdir_attr(current_dir)
            except OSError:
                return
            for entry in entries:
                if len(candidates) >= _BATCH_CANDIDATE_LIMIT:
                    return
                if not entry.filename or "\x00" in entry.filename:
                    continue
                entry_mode = entry.st_mode or 0
                is_entry_dir = _stat.S_ISDIR(entry_mode)
                entry_path = posixpath.join(current_dir, entry.filename)
                if is_entry_dir:
                    if depth < max_depth:
                        # Use immediate child folder name as subject label hint
                        label = entry.filename if depth == 0 else subject_hint
                        _recurse(entry_path, depth + 1, label)
                else:
                    if _is_image_file(entry.filename):
                        # Relative path from scan root
                        rel = entry_path[len(scan_root):].lstrip("/")
                        # Subject label: parent folder name for nested, file stem for flat
                        if depth == 0:
                            # file is directly in scan_root
                            label: str = _file_stem(entry.filename)
                        else:
                            label = subject_hint or posixpath.basename(current_dir)
                        candidates.append({
                            "name": entry.filename,
                            "path": entry_path,
                            "kind": "file",
                            "size": int(entry.st_size or 0),
                            "modified_at": int(entry.st_mtime or 0) if entry.st_mtime else None,
                            "selectable": True,
                            "relative_path": rel,
                            "subject_label": label,
                            "depth": depth,
                            "parent": current_dir,
                        })

        _recurse(scan_root, 0, None)

        # Sort: by subject_label then name
        candidates.sort(key=lambda e: (str(e.get("subject_label", "")).lower(), str(e["name"]).lower()))

        # Detect subjects with multiple candidates
        from collections import Counter
        label_counts: Counter[str] = Counter(str(e.get("subject_label", "")) for e in candidates)
        has_multi_subject_conflict = any(v > 1 for v in label_counts.values())

        return {
            "ok": True,
            "path": scan_root,
            "parent": posixpath.dirname(scan_root),
            "entries": candidates,
            "image_count": len(candidates),
            "is_batch_scan": True,
            "has_multi_subject_conflict": has_multi_subject_conflict,
        }


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


def _int_val(value: object, default: int = 0) -> int:
    try:
        return int(str(value or default))
    except (TypeError, ValueError):
        return default


def _json_dict(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        return {}
    return {str(k): _json_value(v) for k, v in value.items()}


def _json_value(value: object) -> JsonValue:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


def _job_summary(job: dict[str, object]) -> dict[str, JsonValue]:
    remote_dir = str(job.get("remote_job_dir", "") or "")
    job_id = str(job.get("job_id", "") or (Path(remote_dir).name if remote_dir else "remote-job"))
    run_req = job.get("run_request_summary")
    req_dict = run_req if isinstance(run_req, dict) else {}
    from app_backend.jobs import _make_run_request_summary
    return {
        "job_id": job_id,
        "target": "Server",
        "state": str(job.get("state", "unknown") or "unknown"),
        "pid": str(job.get("pid", "") or ""),
        "exit_code": job.get("exit_code") if isinstance(job.get("exit_code"), int) else None,
        "remote_job_dir": remote_dir,
        "job_dir": remote_dir,
        "started_at": float(job.get("started_at", 0.0) or 0.0),
        "finished_at": float(job.get("finished_at", 0.0) or 0.0) if job.get("finished_at") else None,
        "output_dir": str(job.get("output_dir", "") or ""),
        "effective_output_dir": str(job.get("effective_output_dir", "") or ""),
        "download_subdir": str(job.get("download_subdir", "") or ""),
        "input_files": _json_value(job.get("input_files", [])) if isinstance(job.get("input_files"), list) else [],
        "run_request_summary": _make_run_request_summary(req_dict),
    }
