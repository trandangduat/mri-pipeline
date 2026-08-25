from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, TypeAlias

from app_backend import paths
from app_backend.sse_utils import step_event, complete_event, SSEEvent
from pipeline.docker_ops import check_freesurfer_license
from pipeline.config import PROJECT_ROOT
from pipeline.jobs import read_json, write_json

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True)
class ProcessHandle:
    pid: int


ProcessRunner = Callable[[list[str]], ProcessHandle]
Clock = Callable[[], float]


class LocalJobService:
    def __init__(
        self,
        jobs_root: str | Path | None = None,
        process_runner: ProcessRunner | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.jobs_root = Path(jobs_root) if jobs_root is not None else paths.jobs_root()
        self.registry_path = self.jobs_root / "job_registry.json"
        self.process_runner = process_runner or _default_process_runner
        self.clock = clock or time.time

    def start_local_job(self, run_request: dict[str, object]) -> dict[str, JsonValue]:
        job_dir = self._create_job_dir()
        request = _json_dict(run_request)
        request["job_dir"] = str(job_dir)
        request["run_target"] = "Local"
        config_path = job_dir / "job_config.json"
        write_json(config_path, request)

        command = paths.worker_command(str(config_path))
        process = self.process_runner(command)
        now = self.clock()
        write_json(job_dir / "launcher_status.json", {"pid": process.pid, "started_at": now, "command": command})
        write_json(
            job_dir / "job_status.json",
            {
                "state": "running",
                "pid": process.pid,
                "job_dir": str(job_dir),
                "output_dir": str(request.get("output_dir", "")),
                "started_at": now,
                "updated_at": now,
            },
        )
        entry = self._registry_entry_for_local_job(job_dir, request, process.pid, now, "running")
        self._upsert_registry(entry)
        return {"ok": True, "job": _job_summary(entry)}

    def list_local_jobs(self) -> dict[str, JsonValue]:
        registry = self._load_registry()
        local_jobs = [self._refresh_local_job(entry) for entry in registry if entry.get("target") == "Local"]
        other_jobs = [entry for entry in registry if entry.get("target") != "Local"]
        self._save_registry([*local_jobs, *other_jobs])
        return {"ok": True, "jobs": [_job_summary(job) for job in local_jobs]}

    def stop_local_job(self, job_id: str) -> dict[str, JsonValue]:
        entry = self._find_local_job(job_id)
        if entry is None:
            return {"ok": False, "error": "Local job not found"}
        job_dir = Path(str(entry.get("job_dir", ""))).resolve()
        if not job_dir.exists() or not _is_relative_to(job_dir, self.jobs_root.resolve()):
            return {"ok": False, "error": "Local job not found"}

        if not _write_stop_marker(job_dir / "stop_requested"):
            return {"ok": False, "error": "Stop marker path is not safe"}
        return {"ok": True, "accepted": True, "job": _job_summary(entry)}

    def delete_local_job(self, job_id: str) -> dict[str, JsonValue]:
        jobs = self._load_registry()
        entry = next((job for job in jobs if job.get("target") == "Local" and job.get("job_id") == job_id), None)
        if entry is None:
            return {"ok": False, "error": "Local job not found"}
        if str(entry.get("state", "")).lower() == "running":
            return {"ok": False, "error": "Stop the job before deleting it"}

        job_dir = Path(str(entry.get("job_dir", ""))).resolve()
        if not _is_relative_to(job_dir, self.jobs_root.resolve()):
            return {"ok": False, "error": "Local job path is not safe"}
        if job_dir.exists():
            if not job_dir.is_dir() or job_dir.is_symlink():
                return {"ok": False, "error": "Local job path is not safe"}
            shutil.rmtree(job_dir)

        self._save_registry([job for job in jobs if job is not entry])
        return {"ok": True, "job_id": job_id}

    def stream_start_job(self, payload: dict[str, object]) -> Iterator[SSEEvent]:
        from app_backend.run_request import prepare_run_request

        yield step_event("validate", "running", "Validating configuration...")
        result = prepare_run_request(payload)
        if not result.get("ok"):
            errors = result.get("errors", [])
            yield step_event("validate", "failed", "; ".join(str(e) for e in errors))
            yield complete_event(False, errors=errors)
            return
        request = result["request"]
        yield step_event("validate", "done", "Configuration valid")

        yield step_event("license", "running", "Checking FreeSurfer license...")
        license_ok, license_detail = check_freesurfer_license(
            request.get("selected_tools"),
            str(request.get("license_dir", "")),
        )
        if not license_ok:
            yield step_event("license", "failed", license_detail)
            yield complete_event(False, error=license_detail)
            return
        yield step_event("license", "done", license_detail)

        yield step_event("config", "running", "Preparing job configuration...")
        yield step_event("config", "done", "Job configuration ready")

        yield step_event("start", "running", "Starting local worker...")
        try:
            start_result = self.start_local_job(request)
            if start_result.get("ok"):
                yield step_event("start", "done", "Worker started")
                yield complete_event(True, job=start_result.get("job"))
            else:
                yield step_event("start", "failed", str(start_result.get("error", "Unknown error")))
                yield complete_event(False, error=str(start_result.get("error", "Unknown error")))
        except Exception as exc:
            yield step_event("start", "failed", str(exc))
            yield complete_event(False, error=str(exc))

    def upsert_remote_job(
        self,
        job_id: str,
        remote_job_dir: str,
        state: str,
        ssh_config: dict[str, JsonValue],
        run_request: dict[str, JsonValue],
        started_at: float | None = None,
        pid: str | int | None = None,
    ) -> dict[str, JsonValue]:
        now = self.clock()
        entry: dict[str, JsonValue] = {
            "job_id": job_id,
            "target": "Server",
            "state": state,
            "job_dir": remote_job_dir,
            "remote_job_dir": remote_job_dir,
            "pid": pid or 0,
            "started_at": started_at or now,
            "updated_at": now,
            "output_dir": str(run_request.get("output_dir", "")),
            "effective_output_dir": str(run_request.get("effective_output_dir", run_request.get("output_dir", ""))),
            "download_subdir": str(run_request.get("batch_output_name", "")) if run_request.get("is_batch") else "",
            "input_files": _input_files_for_request(run_request),
            "run_request": run_request,
            "ssh_config": ssh_config,
        }
        self._upsert_registry(entry)
        return _job_summary(entry)

    def _create_job_dir(self) -> Path:
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        for _attempt in range(100):
            job_id = f"job_{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}_{int(self.clock() * 1000)}_{_attempt}"
            job_dir = self.jobs_root / job_id
            try:
                job_dir.mkdir(parents=True, exist_ok=False)
                return job_dir
            except FileExistsError:
                time.sleep(0.001)
        raise RuntimeError("Could not create a unique local job directory")

    def _registry_entry_for_local_job(
        self,
        job_dir: Path,
        request: dict[str, JsonValue],
        pid: int,
        now: float,
        state: str,
    ) -> dict[str, JsonValue]:
        return {
            "job_id": job_dir.name,
            "target": "Local",
            "state": state,
            "job_dir": str(job_dir),
            "pid": pid,
            "started_at": now,
            "updated_at": now,
            "output_dir": str(request.get("output_dir", "")),
            "effective_output_dir": str(request.get("effective_output_dir", request.get("output_dir", ""))),
            "download_subdir": str(request.get("batch_output_name", "")) if request.get("is_batch") else "",
            "input_files": _input_files_for_request(request),
            "run_request": request,
        }

    def _refresh_local_job(self, entry: dict[str, JsonValue]) -> dict[str, JsonValue]:
        entry = dict(entry)
        job_dir = Path(str(entry.get("job_dir", "")))
        if not job_dir.exists():
            entry["state"] = "missing"
            entry["updated_at"] = self.clock()
            return entry

        status = read_json(job_dir / "job_status.json", {})
        exit_code = _exit_code(job_dir, status)
        stop_requested = (job_dir / "stop_requested").exists()
        if status.get("state") == "stopped" or (stop_requested and (exit_code is not None or status.get("state") in {"completed", "failed", "stopped"})):
            entry["state"] = "stopped"
            entry["exit_code"] = exit_code
        elif exit_code is not None or status.get("state") in {"completed", "failed"}:
            entry["state"] = "completed" if exit_code == 0 else "failed"
            entry["exit_code"] = exit_code
        elif status.get("state"):
            entry["state"] = str(status.get("state"))
        elif stop_requested:
            entry["state"] = "stopped"
        entry["updated_at"] = self.clock()
        return entry

    def _find_local_job(self, job_id: str) -> dict[str, JsonValue] | None:
        for entry in self._load_registry():
            if entry.get("target") != "Local":
                continue
            if entry.get("job_id") == job_id or entry.get("job_dir") == job_id:
                return entry
        return None

    def _load_registry(self) -> list[dict[str, JsonValue]]:
        data = read_json(self.registry_path, {"jobs": []})
        jobs = data.get("jobs", [])
        if not isinstance(jobs, list):
            return []
        return [_json_dict(job) for job in jobs if isinstance(job, dict)]

    def _save_registry(self, jobs: list[dict[str, JsonValue]]) -> None:
        jobs.sort(key=lambda item: float(item.get("updated_at") or item.get("started_at") or 0), reverse=True)
        write_json(self.registry_path, {"version": 1, "jobs": jobs})

    def _upsert_registry(self, entry: dict[str, JsonValue]) -> None:
        jobs = self._load_registry()
        entry_id = entry.get("job_id") or entry.get("job_dir")
        for idx, existing in enumerate(jobs):
            existing_id = existing.get("job_id") or existing.get("job_dir")
            if existing_id == entry_id:
                merged = dict(existing)
                merged.update(entry)
                jobs[idx] = merged
                self._save_registry(jobs)
                return
        jobs.append(entry)
        self._save_registry(jobs)


def _default_process_runner(command: list[str]) -> ProcessHandle:
    kwargs: dict[str, object] = {
        "cwd": str(paths.backend_cwd()),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)
    return ProcessHandle(pid=int(process.pid))


SAFE_RUN_REQUEST_KEYS = (
    "mode",
    "input_file",
    "input_files",
    "input_dir",
    "recursive",
    "output_dir",
    "effective_output_dir",
    "pipeline_mode",
    "device",
    "threads",
    "ram_percent",
    "resume",
    "restart",
    "lazy_watch",
    "neuroflow_enabled",
    "neuroflow_max_concurrent_tasks",
    "neuroflow_machine_profile_id",
    "selected_tools",
    "is_batch",
    "batch_output_name",
)


def _make_run_request_summary(request: dict[str, JsonValue]) -> dict[str, JsonValue]:
    summary: dict[str, JsonValue] = {}
    for key in SAFE_RUN_REQUEST_KEYS:
        if key in request:
            summary[key] = _json_value(request[key])
    return summary


def _job_summary(entry: dict[str, JsonValue]) -> dict[str, JsonValue]:
    run_req = entry.get("run_request")
    req_dict = run_req if isinstance(run_req, dict) else {}
    input_files = entry.get("input_files")
    if not isinstance(input_files, list):
        input_files = _input_files_for_request(req_dict)
    batch_summary = entry.get("batch_summary")
    if not isinstance(batch_summary, dict) and str(entry.get("target", "Local")) == "Local":
        batch_summary = _read_batch_summary(Path(str(entry.get("job_dir", ""))), input_files)
    summary = {
        "job_id": str(entry.get("job_id", "")),
        "target": str(entry.get("target", "Local")),
        "state": str(entry.get("state", "unknown")),
        "job_dir": str(entry.get("job_dir", "")),
        "pid": int(entry.get("pid", 0) or 0),
        "exit_code": entry.get("exit_code") if isinstance(entry.get("exit_code"), int) else None,
        "started_at": float(entry.get("started_at", 0.0) or 0.0),
        "updated_at": float(entry.get("updated_at", 0.0) or 0.0),
        "output_dir": str(entry.get("output_dir", "")),
        "effective_output_dir": str(entry.get("effective_output_dir", "")),
        "download_subdir": str(entry.get("download_subdir", "")),
        "input_files": _json_value(input_files),
        "run_request_summary": _make_run_request_summary(req_dict),
    }
    if isinstance(batch_summary, dict):
        summary["batch_summary"] = _json_value(batch_summary)
    return summary



def _input_files_for_request(request: dict[str, JsonValue]) -> list[str]:
    mode = request.get("mode")
    if mode == "file" and request.get("input_file"):
        return [str(request.get("input_file"))]
    if mode == "files" and isinstance(request.get("input_files"), list):
        return [str(path) for path in request.get("input_files", [])]
    if request.get("input_dir"):
        return [str(request.get("input_dir"))]
    return []


def _read_batch_summary(job_dir: Path, input_files: list[JsonValue]) -> dict[str, int]:
    """Summarize image events without inferring failures from job state."""
    states: dict[str, str] = {}
    event_total = 0
    events_path = job_dir / "events.jsonl"
    try:
        with events_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = _json_dict(json.loads(line))
                except (json.JSONDecodeError, OSError):
                    continue
                kind = str(event.get("kind", ""))
                if kind not in {"image_start", "image_done"}:
                    continue
                try:
                    event_total = max(event_total, int(event.get("total", 0) or 0))
                except (TypeError, ValueError):
                    pass
                input_file = str(event.get("input_file", ""))
                if not input_file:
                    continue
                states[input_file] = "running" if kind == "image_start" else (
                    "success" if bool(event.get("success")) else "failed"
                )
    except OSError:
        pass

    total = max(len(input_files), event_total, len(states))
    success = sum(state == "success" for state in states.values())
    failed = sum(state == "failed" for state in states.values())
    running = sum(state == "running" for state in states.values())
    return {
        "total": total,
        "success": success,
        "failed": failed,
        "running": running,
        "pending": max(0, total - success - failed - running),
    }


def _exit_code(job_dir: Path, status: dict) -> int | None:
    code = status.get("exit_code")
    if code is None:
        exit_path = job_dir / "exit_code.txt"
        if exit_path.exists():
            code = exit_path.read_text(encoding="utf-8", errors="replace").strip()
    try:
        return int(code) if code is not None and str(code).strip() != "" else None
    except (TypeError, ValueError):
        return None


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _write_stop_marker(path: Path) -> bool:
    if path.is_symlink():
        return False
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o644)
    except OSError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as marker:
        marker.write("stop requested\n")
    return True


def _json_dict(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _json_value(item) for key, item in value.items()}


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
