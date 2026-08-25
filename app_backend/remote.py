from __future__ import annotations

import re
import stat
import threading
from pathlib import Path
from queue import Queue, Empty
from typing import Callable, Iterator, Protocol, TypeAlias

from app_backend.sse_utils import step_event, complete_event, SSEEvent
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
    def __init__(
        self,
        runner_factory: RunnerFactory | None = None,
        register_remote_job: Callable[..., dict[str, JsonValue]] | None = None,
    ) -> None:
        self.runner_factory = runner_factory or _default_runner_factory
        self.register_remote_job = register_remote_job
        self._lazy_uploads: dict[str, object] = {}

    # ------------------------------------------------------------- lazy upload
    def upload_state(self, data: dict[str, object]) -> dict[str, JsonValue]:
        job_id = str(data.get("job_id", "")).strip()
        orchestrator = self._lazy_uploads.get(job_id)
        if orchestrator is None:
            return {"ok": False, "error": f"No active upload for {job_id}"}
        return {"ok": True, "uploads": orchestrator.snapshot(), "terminal": orchestrator.is_terminal()}

    def upload_cancel(self, data: dict[str, object]) -> dict[str, JsonValue]:
        job_id = str(data.get("job_id", "")).strip()
        orchestrator = self._lazy_uploads.pop(job_id, None)
        if orchestrator is None:
            return {"ok": True, "cancelled": False}
        orchestrator.cancel()
        return {"ok": True, "cancelled": True}

    def upload_stage(self, data: dict[str, object]) -> dict[str, JsonValue]:
        import posixpath
        parsed = parse_remote_config(data)
        if parsed["errors"]:
            return {"ok": False, "errors": parsed["errors"]}
        config = parsed["config"]
        assert isinstance(config, RemoteRunConfig)
        local_path = str(data.get("local_path", "") or "").strip()
        local_paths_raw = data.get("local_paths")
        if isinstance(local_paths_raw, list):
            local_paths = [str(p).strip() for p in local_paths_raw if str(p).strip()]
        elif local_path:
            local_paths = [local_path]
        else:
            local_paths = []
        remote_path = str(data.get("remote_path", "") or data.get("remote_dir", "") or "").strip()
        if not local_paths or not remote_path:
            return {"ok": False, "error": "local_paths (or local_path) and remote_path are required"}
        
        resolved_local_paths: list[Path] = []
        for lp in local_paths:
            p = Path(lp).expanduser()
            if not p.exists():
                return {"ok": False, "error": f"Local path not found: {lp}"}
            resolved_local_paths.append(p)

        try:
            from remote.ssh_client import RemoteSSHClient
            with RemoteSSHClient(config.ssh, lambda _line: None) as ssh:
                expanded_remote = ssh.expand_path(remote_path)
                ssh.mkdir_p(expanded_remote)
                for local_p in resolved_local_paths:
                    if local_p.is_dir():
                        dest_dir = posixpath.join(expanded_remote, local_p.name)
                        ssh.upload_dir(local_p, dest_dir)
                    else:
                        dest = posixpath.join(expanded_remote, local_p.name)
                        ssh.upload_file(local_p, dest)
            return {
                "ok": True,
                "local_path": str(resolved_local_paths[0]) if resolved_local_paths else "",
                "local_paths": [str(p) for p in resolved_local_paths],
                "remote_path": remote_path,
                "uploaded_count": len(resolved_local_paths),
            }
        except Exception as exc:
            return {"ok": False, "error": _safe_error_message(exc, config)}

    def remote_mkdir(self, data: dict[str, object]) -> dict[str, JsonValue]:
        parsed = parse_remote_config(data)
        if parsed["errors"]:
            return {"ok": False, "errors": parsed["errors"]}
        config = parsed["config"]
        assert isinstance(config, RemoteRunConfig)
        path = str(data.get("path", "") or data.get("remote_path", "") or "").strip()
        if not path:
            return {"ok": False, "error": "path is required"}
        if "\x00" in path:
            return {"ok": False, "error": "Invalid path"}
        try:
            from remote.ssh_client import RemoteSSHClient
            with RemoteSSHClient(config.ssh, lambda _line: None) as ssh:
                expanded = ssh.expand_path(path)
                ssh.mkdir_p(expanded)
            return {"ok": True, "path": path}
        except Exception as exc:
            return {"ok": False, "error": _safe_error_message(exc, config)}

    def request_remote_stop(self, data: dict[str, object]) -> dict[str, JsonValue]:
        parsed = parse_remote_config(data)
        if parsed["errors"]:
            return {"ok": False, "errors": parsed["errors"]}
        config = parsed["config"]
        assert isinstance(config, RemoteRunConfig)
        remote_job_dir = str(data.get("remote_job_dir") or data.get("job_id") or "").strip()
        if not remote_job_dir:
            return {"ok": False, "errors": ["remote_job_dir or job_id is required"]}
        # Also abort any in-flight lazy uploads for this job.
        self.upload_cancel({"job_id": remote_job_dir.split("/")[-1]})
        runner = self.runner_factory(config)
        runner.remote_job_dir = remote_job_dir
        try:
            runner.request_pause()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "errors": [_safe_error_message(exc)]}

    def _start_lazy_uploads(self, job_id: str, runner, source_paths: dict[str, str], max_concurrent: int) -> None:
        if not source_paths:
            return
        from remote.lazy_upload import LazyUploadOrchestrator

        try:
            orchestrator = LazyUploadOrchestrator(
                runner,
                source_paths=source_paths,
                max_concurrent=max_concurrent,
                on_log=lambda line: print(f"[lazy-upload] {line}", flush=True),
            )
            orchestrator.start()
            self._lazy_uploads[job_id] = orchestrator
        except Exception as exc:
            print(f"[lazy-upload] failed to start orchestrator: {exc}", flush=True)

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

    def delete_job(self, data: dict[str, object]) -> dict[str, JsonValue]:
        parsed = parse_remote_config(data)
        if parsed["errors"]:
            return {"ok": False, "errors": parsed["errors"]}
        config = parsed["config"]
        assert isinstance(config, RemoteRunConfig)
        remote_job_dir = str(data.get("remote_job_dir") or data.get("job_id") or "").strip()
        if not remote_job_dir:
            return {"ok": False, "error": "remote_job_dir is required"}
        try:
            runner = self.runner_factory(config)
            if hasattr(runner, "attach_job"):
                runner.attach_job(remote_job_dir)
            if not hasattr(runner, "clean_remote"):
                return {"ok": False, "error": "Remote job deletion is unavailable"}
            runner.clean_remote()  # type: ignore[attr-defined]
            return {"ok": True, "job_id": str(data.get("job_id") or remote_job_dir)}
        except Exception:
            return {"ok": False, "error": "Remote job deletion failed"}

    def stop_job(self, data: dict[str, object]) -> dict[str, JsonValue]:
        parsed = parse_remote_config(data)
        if parsed["errors"]:
            return {"ok": False, "errors": parsed["errors"]}
        config = parsed["config"]
        assert isinstance(config, RemoteRunConfig)
        remote_job_dir = str(data.get("remote_job_dir") or data.get("job_id") or "").strip()
        if not remote_job_dir:
            return {"ok": False, "error": "remote_job_dir is required"}
        try:
            runner = self.runner_factory(config)
            if hasattr(runner, "attach_job"):
                runner.attach_job(remote_job_dir)
            if not hasattr(runner, "request_pause"):
                return {"ok": False, "error": "Remote job stopping is unavailable"}
            runner.request_pause()  # type: ignore[attr-defined]
            return {"ok": True, "accepted": True, "job_id": str(data.get("job_id") or remote_job_dir)}
        except Exception:
            return {"ok": False, "error": "Remote job stop failed"}

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

    def stream_start_job(self, data: dict[str, object]) -> Iterator[SSEEvent]:
        raw_run_request = data.get("run_request")
        if not isinstance(raw_run_request, dict):
            yield step_event("ssh", "failed", "run_request must be an object")
            yield complete_event(False, error="run_request must be an object")
            return

        # Step 1: SSH connection
        yield step_event("ssh", "running", "Connecting to server...")
        parsed = parse_remote_config(data)
        if parsed.get("errors"):
            yield step_event("ssh", "failed", "; ".join(str(e) for e in parsed["errors"]))
            yield complete_event(False, errors=parsed["errors"])
            return
        base_config: RemoteRunConfig = parsed["config"]  # type: ignore[assignment]

        try:
            test_runner = self.runner_factory(base_config)
            if hasattr(test_runner, "test_ssh"):
                test_runner.test_ssh()
            yield step_event("ssh", "done", f"Connected to {base_config.ssh.host}")
        except Exception as exc:
            yield step_event("ssh", "failed", _safe_error_message(exc))
            yield complete_event(False, error=_safe_error_message(exc))
            return

        # Step 2: Validate and normalize run request (maps input_path → input_dir/file/files)
        yield step_event("validate", "running", "Validating configuration...")
        from app_backend.run_request import prepare_run_request
        # License validation is a distinct preflight step for remote runs. It
        # must be reported by the license step rather than by generic request
        # validation, before any remote job files are written.
        result = prepare_run_request(raw_run_request, validate_license=False)
        if not result.get("ok"):
            errors = result.get("errors", [])
            yield step_event("validate", "failed", "; ".join(str(e) for e in errors))
            yield complete_event(False, errors=errors)
            return
        run_request = result["request"]
        yield step_event("validate", "done", "Configuration valid")

        # Step 3: Input/output paths
        yield step_event("paths", "running", "Validating input/output paths...")
        yield step_event("paths", "done", "Paths validated")

        # Step 4: Docker images (resolve tool keys → actual image names via TOOL_DEFS)
        from pipeline.registry import TOOL_DEFS
        tool_keys = [v for v in run_request.get("selected_tools", {}).values() if v]
        if tool_keys:
            yield step_event("images", "running", "Checking Docker image(s)...")
            try:
                image_names: list[str] = []
                for tk in tool_keys:
                    tool_def = TOOL_DEFS.get(tk, {})
                    img = str(tool_def.get("image", "") or "")
                    if img and img not in image_names:
                        image_names.append(img)
                runner = self.runner_factory(base_config)
                if image_names and hasattr(runner, "check_image_statuses"):
                    image_statuses = runner.check_image_statuses(image_names)
                    missing = [img for img, ok in image_statuses.items() if not ok]
                    if missing:
                        count = len(missing)
                        noun = "image" if count == 1 else "images"
                        verb = "it" if count == 1 else "them"
                        image_list = ", ".join(missing)
                        message = f"{count} Docker {noun} missing. Download {verb} from Tools Configuration before starting the pipeline: {image_list}"
                        yield step_event("images", "failed", message)
                        yield complete_event(False, error=message)
                        return
                    else:
                        yield step_event("images", "done", "All images ready")
                else:
                    yield step_event("images", "done", "Skipped")
            except Exception as exc:
                yield step_event("images", "failed", _safe_error_message(exc))
                yield complete_event(False, error=_safe_error_message(exc))
                return

        # Step 5: Code upload
        yield step_event("code", "running", "Checking code changes...")
        yield step_event("code", "done", "Code is up to date")

        # Step 6: Python environment
        yield step_event("venv", "running", "Checking Python environment...")
        yield step_event("venv", "done", "Python environment ready")

        if (
            run_request.get("pipeline_mode") == "Custom"
            and run_request.get("neuroflow_enabled")
            and not run_request.get("neuroflow_preset_file")
        ):
            from pipeline.presets import infer_pipeline_mode_from_tools

            inferred_mode = infer_pipeline_mode_from_tools(run_request.get("selected_tools"))
            if inferred_mode != "Custom":
                run_request = {**run_request, "pipeline_mode": inferred_mode}
        remote_config = RemoteRunConfig(
            ssh=base_config.ssh,
            remote_workspace=base_config.remote_workspace,
            remote_python=base_config.remote_python,
            input_mode=str(run_request.get("mode", "file")),
            input_file=str(run_request.get("input_file", "")),
            input_files=list(run_request.get("input_files") or []),
            input_dir=str(run_request.get("input_dir", "")),
            output_dir=str(run_request.get("output_dir", "")),
            server_output_dir=str(run_request.get("server_output_dir", "")),
            license_dir=str(run_request.get("license_dir", "")),
            device=str(run_request.get("device", "cpu")),
            threads=int(run_request.get("threads", 4) or 4),
            ram_percent=int(run_request.get("ram_percent", 100) or 100),
            selected_tools=dict(run_request.get("selected_tools") or {}),
            export_config=dict(run_request.get("export_config") or {}),
            stats_vector_config=dict(run_request.get("stats_vector_config") or {}),
            pipeline_mode=str(run_request.get("pipeline_mode", "Custom")),
            neuroflow_enabled=bool(run_request.get("neuroflow_enabled", False)),
            neuroflow_max_concurrent_tasks=int(run_request.get("neuroflow_max_concurrent_tasks", 2) or 2),
            neuroflow_max_retries=int(run_request.get("neuroflow_max_retries", 3) or 3),
            neuroflow_warmup_enabled=bool(run_request.get("neuroflow_warmup_enabled", True)),
            neuroflow_warmup_initial_concurrency=int(run_request.get("neuroflow_warmup_initial_concurrency", 2) or 2),
            neuroflow_warmup_safe_successes=int(run_request.get("neuroflow_warmup_safe_successes", 3) or 3),
            neuroflow_preserve_oom_bounds=bool(run_request.get("neuroflow_preserve_oom_bounds", True)),
            neuroflow_estimation_mode=str(run_request.get("neuroflow_estimation_mode", "balanced")),
            neuroflow_max_io_heavy_tasks=int(run_request.get("neuroflow_max_io_heavy_tasks", 2) or 2),
            neuroflow_machine_profile_id=str(run_request.get("neuroflow_machine_profile_id", "application_default")),
            neuroflow_preset_file=str(run_request.get("neuroflow_preset_file", "") or ""),
            neuroflow_profile_file=str(run_request.get("neuroflow_profile_file", "") or ""),
            resume=bool(run_request.get("resume", False)),
            restart=bool(run_request.get("restart", False)),
            lazy_upload=(
                str(run_request.get("input_source", "")) == "Local"
                and str(run_request.get("run_target", "")) == "Server"
            ),
            input_source=str(run_request.get("input_source", "Server")),
            input_server_dir=str(run_request.get("input_server_dir", "")),
        )

        # License staging and validation must happen before upload_job(),
        # because upload_job() writes the remote job configuration.
        yield step_event("license", "running", "Checking FreeSurfer license...")
        try:
            runner = self.runner_factory(remote_config)
            runner.stage_freesurfer_license()
            license_ok, license_detail = runner.check_freesurfer_license()
        except Exception as exc:
            license_detail = _safe_preflight_error(exc, remote_config)
            yield step_event("license", "failed", license_detail)
            yield complete_event(False, error=license_detail)
            return
        if not license_ok:
            yield step_event("license", "failed", license_detail)
            yield complete_event(False, error=license_detail)
            return
        yield step_event("license", "done", license_detail)

        # Step 7: Upload job configuration
        yield step_event("config", "running", "Uploading job configuration...")
        try:
            remote_job_dir = runner.upload_job()
        except Exception as exc:
            detail = _safe_preflight_error(exc, remote_config)
            yield step_event("config", "failed", detail)
            yield complete_event(False, error=detail)
            return
        yield step_event("config", "done", "Job configuration uploaded")

        yield step_event("start", "running", "Starting remote worker...")
        try:
            runner.start_remote_detached()
            remote_status = runner.remote_status()
        except Exception as exc:
            detail = _safe_preflight_error(exc, remote_config)
            yield step_event("start", "failed", detail)
            yield complete_event(False, error=detail)
            return
        yield step_event("start", "done", f"Worker started at {remote_job_dir}")

        job_id = f"remote_{remote_job_dir.split('/')[-1]}"

        if remote_config.lazy_upload and remote_config.neuroflow_enabled:
            try:
                source_paths = runner.lazy_source_paths()
            except Exception:
                source_paths = {}
            self._start_lazy_uploads(
                job_id,
                runner,
                source_paths=source_paths,
                max_concurrent=int(remote_config.neuroflow_max_concurrent_tasks),
            )

        if self.register_remote_job is not None:
            try:
                self.register_remote_job(
                    job_id=job_id,
                    remote_job_dir=remote_job_dir,
                    state=str(remote_status.get("state", "running")),
                    ssh_config={
                        "host": remote_config.ssh.host,
                        "port": remote_config.ssh.port,
                        "username": remote_config.ssh.username,
                        "password": remote_config.ssh.password,
                        "key_path": remote_config.ssh.key_path,
                    },
                    run_request=run_request,
                    started_at=float(remote_status.get("started_at", 0) or 0) or None,
                    pid=remote_status.get("pid"),
                )
            except Exception:
                pass

        from app_backend.jobs import _make_run_request_summary

        yield complete_event(True, job={
            "job_id": job_id,
            "target": "Server",
            "state": remote_status.get("state", "running"),
            "remote_job_dir": remote_job_dir,
            "job_dir": remote_job_dir,
            "started_at": float(remote_status.get("started_at", 0) or 0) or None,
            "pid": remote_status.get("pid"),
            "output_dir": remote_config.output_dir or str(run_request.get("output_dir", "")),
            "effective_output_dir": remote_config.output_dir or str(run_request.get("effective_output_dir", run_request.get("output_dir", ""))),
            "download_subdir": remote_config.download_subdir or str(run_request.get("download_subdir", "")),
            "input_files": list(run_request.get("input_files") or ([run_request["input_file"]] if run_request.get("input_file") else [])),
            "run_request_summary": _make_run_request_summary(run_request),
        })

    def stream_download_outputs(self, data: dict[str, object]) -> Iterator[SSEEvent]:
        local_target_dir = str(data.get("local_target_dir", "") or "").strip()
        if not local_target_dir:
            yield step_event("connect", "failed", "local_target_dir is required")
            yield complete_event(False, error="local_target_dir is required")
            return
        if "\x00" in local_target_dir:
            yield step_event("connect", "failed", "Invalid local target path")
            yield complete_event(False, error="Invalid local target path")
            return

        remote_job_dir = str(data.get("remote_job_dir", "") or "").strip()
        if not remote_job_dir:
            yield step_event("connect", "failed", "remote_job_dir is required")
            yield complete_event(False, error="remote_job_dir is required")
            return
        if "\x00" in remote_job_dir:
            yield step_event("connect", "failed", "Invalid remote job path")
            yield complete_event(False, error="Invalid remote job path")
            return

        remote_output_dir = str(data.get("remote_output_dir", "") or "").strip()
        download_subdir = str(data.get("download_subdir", "") or "").strip()
        job_id = str(data.get("job_id", "") or "").strip()

        # Compute final local job folder: <local_target_dir>/<safe_job_folder>
        safe_job_folder = _safe_job_folder(job_id, remote_job_dir)
        final_local_dir = str(Path(local_target_dir) / safe_job_folder)

        yield step_event("connect", "running", "Connecting to server...")
        parsed = parse_remote_config(data)
        if parsed.get("errors"):
            yield step_event("connect", "failed", "; ".join(str(e) for e in parsed["errors"]))
            yield complete_event(False, errors=parsed["errors"])
            return
        config: RemoteRunConfig = parsed["config"]  # type: ignore[assignment]

        try:
            runner = self.runner_factory(config)
            if hasattr(runner, "attach_job"):
                runner.attach_job(remote_job_dir, remote_output_dir)
            elif hasattr(runner, "remote_job_dir"):
                runner.remote_job_dir = remote_job_dir.rstrip("/")
                runner.remote_output_dir = remote_output_dir or remote_job_dir.rstrip("/") + "/outputs"
            yield step_event("connect", "done", f"Connected to {config.ssh.host}")
        except Exception as exc:
            yield step_event("connect", "failed", _safe_error_message(exc, config))
            yield complete_event(False, error=_safe_error_message(exc, config))
            return

        total_files = 0
        yield step_event("count", "running", "Counting remote files...")
        try:
            if hasattr(runner, "count_download_files"):
                total_files = runner.count_download_files()
            yield step_event("count", "done", f"Found {total_files} file(s)")
        except Exception as exc:
            yield step_event("count", "done", f"Could not count files: {_safe_error_message(exc, config)}")

        download_config = RemoteRunConfig(
            ssh=config.ssh,
            remote_workspace=config.remote_workspace,
            remote_python=config.remote_python,
            output_dir=final_local_dir,
            download_subdir=download_subdir,
        )

        download_runner = self.runner_factory(download_config)
        if hasattr(download_runner, "attach_job"):
            download_runner.attach_job(remote_job_dir, remote_output_dir)
        elif hasattr(download_runner, "remote_job_dir"):
            download_runner.remote_job_dir = remote_job_dir.rstrip("/")
            download_runner.remote_output_dir = remote_output_dir or remote_job_dir.rstrip("/") + "/outputs"

        copied_files = 0
        progress_queue: Queue[dict[str, object]] = Queue()
        download_error: list[Exception | None] = [None]

        def on_log(line: str) -> None:
            nonlocal copied_files
            if line.startswith("Downloading file:"):
                copied_files += 1
                pct = round(copied_files / total_files * 100) if total_files > 0 else 0
                progress_queue.put({
                    "step": "copy",
                    "status": "running",
                    "detail": line,
                    "copied_files": copied_files,
                    "total_files": total_files,
                    "pct": pct,
                })

        download_runner.on_log = on_log  # type: ignore[union-attr]

        def run_download() -> None:
            try:
                download_runner.download_outputs(final_local_dir)
            except Exception as exc:
                download_error[0] = exc
            finally:
                progress_queue.put(None)

        download_thread = threading.Thread(target=run_download, daemon=True)
        download_thread.start()

        yield {"event": "step", "data": {"step": "copy", "status": "running", "detail": "Copying outputs...", "copied_files": 0, "total_files": total_files, "pct": 0}}

        while True:
            try:
                event_data = progress_queue.get(timeout=0.5)
            except Empty:
                continue
            if event_data is None:
                break
            yield {"event": "step", "data": event_data}  # type: ignore[dict-item]

        download_thread.join(timeout=5)

        # Drain any remaining events
        while True:
            try:
                event_data = progress_queue.get_nowait()
            except Empty:
                break
            if event_data is not None:
                yield {"event": "step", "data": event_data}  # type: ignore[dict-item]

        if download_error[0] is not None:
            yield step_event("copy", "failed", _safe_error_message(download_error[0], config))
            yield complete_event(False, error=_safe_error_message(download_error[0], config))
        else:
            pct = round(copied_files / total_files * 100) if total_files > 0 else 100
            yield {"event": "step", "data": {"step": "copy", "status": "done", "detail": f"Copied {copied_files} file(s)", "copied_files": copied_files, "total_files": total_files, "pct": pct}}
            yield complete_event(True, local_path=final_local_dir, copied_files=copied_files, total_files=total_files)


def _safe_job_folder(job_id: str, remote_job_dir: str) -> str:
    """Derive a filesystem-safe folder name for a job download."""
    raw = job_id if job_id else Path(remote_job_dir).name if remote_job_dir else "server_job_outputs"
    sanitized = re.sub(r"[/\\:*?\"<>|]", "_", raw).strip("_")
    return sanitized or "server_job_outputs"


_IMAGE_EXTENSIONS = {".nii", ".nii.gz", ".mgz", ".mgh", ".dcm", ".dicom", ".ima"}
_DICOM_EXTENSIONS = (".dcm", ".dicom", ".ima")
_BROWSE_ENTRY_LIMIT = 500
_BATCH_CANDIDATE_LIMIT = 1000
_BATCH_MAX_DEPTH = 6


def _is_image_file(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(ext) for ext in _IMAGE_EXTENSIONS)


def _is_dicom_filename(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(ext) for ext in _DICOM_EXTENSIONS)


def _sftp_check_dicom_dir(client: object, dir_path: str) -> tuple[bool, int, int]:
    """Check if remote dir contains DICOM files. Returns (is_dicom, slice_count, total_size)."""
    import stat as _stat
    try:
        children = client.sftp.listdir_attr(dir_path)  # type: ignore[attr-defined]
    except OSError:
        return False, 0, 0
    dicom_children = [
        c for c in children
        if c.filename and not _stat.S_ISDIR(c.st_mode or 0) and _is_dicom_filename(c.filename)
    ]
    if dicom_children:
        total_size = sum(int(c.st_size or 0) for c in dicom_children)
        return True, len(dicom_children), total_size
    return False, 0, 0


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
            if is_entry_dir:
                is_dcm, slice_cnt, total_sz = _sftp_check_dicom_dir(client, entry_path)
                if is_dcm:
                    image_count += 1
                row: dict[str, JsonValue] = {
                    "name": entry_name,
                    "path": entry_path,
                    "kind": "directory",
                    "size": total_sz if is_dcm else None,
                    "modified_at": int(entry.st_mtime or 0) if entry.st_mtime else None,
                    "selectable": True,
                    "is_dicom_series": is_dcm,
                    "slice_count": slice_cnt if is_dcm else None,
                }
                dirs.append(row)
            else:
                is_img = _is_image_file(entry_name)
                if is_img:
                    image_count += 1
                row = {
                    "name": entry_name,
                    "path": entry_path,
                    "kind": "file",
                    "size": int(entry.st_size or 0),
                    "modified_at": int(entry.st_mtime or 0) if entry.st_mtime else None,
                    "selectable": is_img,
                    "is_dicom_series": False,
                }
                files.append(row)
        dirs.sort(key=lambda e: str(e["name"]).lower())
        files.sort(key=lambda e: str(e["name"]).lower())
        return {
            "ok": True,
            "path": browse_dir,
            "parent": parent,
            "dirs": dirs,
            "files": files,
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

        is_root_dcm, root_slice_count, root_total_size = _sftp_check_dicom_dir(client, scan_root)
        if is_dir and is_root_dcm:
            name = posixpath.basename(scan_root)
            candidates.append({
                "name": name,
                "path": scan_root,
                "kind": "file",
                "size": root_total_size,
                "modified_at": int(attr.st_mtime or 0) if attr.st_mtime else None,
                "selectable": True,
                "relative_path": name,
                "subject_label": name,
                "depth": 0,
                "parent": posixpath.dirname(scan_root),
                "is_dicom_series": True,
                "slice_count": root_slice_count,
            })
            return {
                "ok": True,
                "path": scan_root,
                "parent": posixpath.dirname(scan_root),
                "dirs": [],
                "files": candidates,
                "entries": candidates,
                "image_count": 1,
                "is_batch_scan": True,
                "has_multi_subject_conflict": False,
            }

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
                    is_dcm, slice_count, dcm_size = _sftp_check_dicom_dir(client, entry_path)
                    if is_dcm:
                        rel = entry_path[len(scan_root):].lstrip("/")
                        label = entry.filename if depth == 0 else (subject_hint or posixpath.basename(current_dir))
                        candidates.append({
                            "name": entry.filename,
                            "path": entry_path,
                            "kind": "file",
                            "size": dcm_size,
                            "modified_at": int(entry.st_mtime or 0) if entry.st_mtime else None,
                            "selectable": True,
                            "relative_path": rel,
                            "subject_label": label,
                            "depth": depth,
                            "parent": current_dir,
                            "is_dicom_series": True,
                            "slice_count": slice_count,
                        })
                    elif depth < max_depth:
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
                            label = _file_stem(entry.filename)
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
                            "is_dicom_series": False,
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
            "dirs": [],
            "files": candidates,
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
        return "An error occurred"
    if config is not None:
        for secret in (config.ssh.password, config.ssh.key_path):
            if secret:
                message = message.replace(secret, "[redacted]")
    if isinstance(exc, (FileNotFoundError, PermissionError, ValueError, KeyError)) or "Permission denied" in message:
        return message
    return f"SSH connection failed: {message}"


def _safe_preflight_error(exc: Exception, config: RemoteRunConfig) -> str:
    """Redact connection secrets without mislabeling a preflight failure as SSH."""
    message = str(exc).strip() or "Preflight check failed"
    for secret in (config.ssh.password, config.ssh.key_path):
        if secret:
            message = message.replace(secret, "[redacted]")
    return message


def _hardware_summary(hardware: dict[str, object]) -> dict[str, JsonValue]:
    summary: dict[str, JsonValue] = {
        "hostname": str(hardware.get("hostname", "") or ""),
        "logical_cores": _int_or_none(hardware.get("logical_cores")),
        "total_ram_bytes": _int_or_none(hardware.get("total_ram_bytes")),
    }
    gpus = hardware.get("gpus")
    if isinstance(gpus, list):
        summary["gpus"] = [
            {
                "name": str(gpu.get("name", "")) if isinstance(gpu, dict) else "",
                "total_memory_mib": _int_or_none(gpu.get("total_memory_mib")) if isinstance(gpu, dict) else None,
                "free_memory_mib": _int_or_none(gpu.get("free_memory_mib")) if isinstance(gpu, dict) else None,
            }
            for gpu in gpus
            if isinstance(gpu, dict)
        ]
    return summary


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
    job_id = _remote_job_id(job.get("job_id"), remote_dir)
    run_req = job.get("run_request_summary")
    req_dict = run_req if isinstance(run_req, dict) else {}
    from app_backend.jobs import _make_run_request_summary
    summary = {
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
    if isinstance(job.get("batch_summary"), dict):
        summary["batch_summary"] = _json_value(job["batch_summary"])
    return summary


def _remote_job_id(raw_job_id: object, remote_dir: str) -> str:
    job_id = str(raw_job_id or "").strip()
    if job_id.startswith("remote_"):
        return job_id
    folder = Path(remote_dir).name if remote_dir else job_id
    return f"remote_{folder}" if folder else "remote-job"
