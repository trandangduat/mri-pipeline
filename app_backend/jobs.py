from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, TypeAlias

from app_backend import paths
from app_backend.redaction import redact_secrets
from app_backend.sse_utils import step_event, complete_event, SSEEvent
from pipeline.docker_ops import check_freesurfer_license
from pipeline.config import PROJECT_ROOT
from pipeline.jobs import read_json, write_json
from pipeline.win_process import detached_worker_flags

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True)
class ProcessHandle:
    pid: int
    create_time: float | None = None
    terminate: Callable[[], None] | None = None


ProcessRunner = Callable[[list[str]], ProcessHandle]
Clock = Callable[[], float]


class LocalJobService:
    def __init__(
        self,
        jobs_root: str | Path | None = None,
        process_runner: ProcessRunner | None = None,
        clock: Clock | None = None,
        process_checker: Callable[[int, float | None], bool] | None = None,
        startup_timeout: float = 15.0,
    ) -> None:
        self.jobs_root = Path(jobs_root) if jobs_root is not None else paths.jobs_root()
        self.registry_path = self.jobs_root / "job_registry.json"
        self.process_runner = process_runner or _default_process_runner
        self.process_checker = process_checker or (_worker_is_alive if process_runner is None else None)
        self.wait_for_readiness = process_runner is None
        self.startup_timeout = startup_timeout
        self.clock = clock or time.time
        self._registry_lock = threading.RLock()

    def start_local_job(self, run_request: dict[str, object]) -> dict[str, JsonValue]:
        job_dir = self._create_job_dir()
        request = _json_dict(run_request)
        request["job_dir"] = str(job_dir)
        request["run_target"] = "Local"
        config_path = job_dir / "job_config.json"
        write_json(config_path, request)

        now = self.clock()
        # The parent initializes status before the worker can publish its result.
        write_json(job_dir / "job_status.json", {
            "state": "running", "job_dir": str(job_dir),
            "output_dir": str(request.get("output_dir", "")),
            "started_at": now, "updated_at": now,
        })
        command = paths.worker_command(str(config_path))
        try:
            process = self.process_runner(command)
        except Exception as exc:
            _record_worker_exit(job_dir, 1, f"Could not start the local worker: {exc}")
            return {"ok": False, "error": str(exc)}
        write_json(job_dir / "launcher_status.json", {
            "pid": process.pid, "create_time": process.create_time,
            "started_at": now, "command": command,
        })
        entry = self._registry_entry_for_local_job(job_dir, request, process.pid, now, "running")
        self._upsert_registry(entry)
        if self.wait_for_readiness:
            deadline = time.monotonic() + self.startup_timeout
            while True:
                entry = self._refresh_local_job(entry)
                if entry["state"] in {"failed", "stopped"}:
                    self._upsert_registry(entry)
                    return {"ok": False, "error": str(entry.get("error") or "The local worker exited during startup."), "job": _job_summary(entry)}
                if entry["state"] == "completed" or _worker_ready(job_dir, process.pid):
                    break
                if time.monotonic() >= deadline:
                    message = "The local worker did not become ready. See launcher.log for details."
                    _record_worker_exit(job_dir, 1, message)
                    _terminate_worker(process)
                    return {"ok": False, "error": message}
                time.sleep(0.05)
        entry = self._refresh_local_job(entry)
        self._upsert_registry(entry)
        return {"ok": True, "job": _job_summary(entry)}

    def list_local_jobs(self) -> dict[str, JsonValue]:
        with self._registry_lock:
            registry = self._load_registry()
            changed = False
            local_jobs: list[dict[str, JsonValue]] = []
            for entry in registry:
                if entry.get("target") == "Local":
                    refreshed = self._refresh_local_job(entry)
                    if (
                        refreshed.get("state") != entry.get("state")
                        or refreshed.get("exit_code") != entry.get("exit_code")
                    ):
                        changed = True
                    local_jobs.append(refreshed)
            if changed:
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
        with self._registry_lock:
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
        result = prepare_run_request({**payload, "run_target": "Local"}, validate_license=False)
        if not result.get("ok"):
            errors = result.get("errors", [])
            yield step_event("validate", "failed", "; ".join(str(e) for e in errors))
            yield complete_event(False, errors=errors)
            return
        request = result["request"]
        yield step_event("validate", "done", "Configuration valid")

        from app_backend.local_runtime import local_runtime_checks
        for event in local_runtime_checks(request):
            yield event
            if event["event"] == "complete":
                return

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
            "run_request": redact_secrets(run_request),
            "ssh_config": redact_secrets(ssh_config),
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
        launcher = read_json(job_dir / "launcher_status.json", {})
        pid_file = job_dir / "pid.txt"
        worker_pid = None
        if pid_file.exists():
            try:
                worker_pid = int(pid_file.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                pass
        pid = worker_pid or int(launcher.get("pid") or entry.get("pid") or 0)
        child_worker = worker_pid is not None and worker_pid != launcher.get("pid")
        create_time = (_child_worker_create_time(job_dir, pid, status) if child_worker
                       else launcher.get("create_time"))
        if (self.process_checker is not None and _exit_code(job_dir, status) is None
                and status.get("state") not in {"completed", "failed", "stopped"}
                and ((child_worker and create_time is None) or not self.process_checker(pid, create_time))):
            _record_worker_exit(job_dir, None)
            status = read_json(job_dir / "job_status.json", {})
        if status.get("error"):
            entry["error"] = str(status["error"])
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
        normalized = [_json_dict(job) for job in jobs if isinstance(job, dict)]
        migrated = [_redact_registry_entry(entry) for entry in normalized]
        if migrated != normalized:
            self._save_registry(migrated)
        return migrated

    def _save_registry(self, jobs: list[dict[str, JsonValue]]) -> None:
        jobs.sort(key=lambda item: float(item.get("updated_at") or item.get("started_at") or 0), reverse=True)
        write_json(self.registry_path, {"version": 1, "jobs": jobs})

    def _upsert_registry(self, entry: dict[str, JsonValue]) -> None:
        with self._registry_lock:
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


def _worker_is_alive(pid: int, create_time: float | None = None) -> bool:
    import psutil
    try:
        process = psutil.Process(pid)
        return (process.is_running() and process.status() != psutil.STATUS_ZOMBIE
                and (create_time is None or abs(process.create_time() - create_time) < 0.1))
    except (psutil.NoSuchProcess, ValueError):
        return False
    except psutil.AccessDenied:
        return True


def _worker_ready(job_dir: Path, pid: int) -> bool:
    try:
        worker_pid = int((job_dir / "pid.txt").read_text(encoding="utf-8").strip())
        if worker_pid == pid:
            return True
        created = _child_worker_create_time(job_dir, worker_pid, read_json(job_dir / "job_status.json", {}))
        return created is not None and _worker_is_alive(worker_pid, created)
    except (OSError, ValueError):
        return False


def _child_worker_create_time(job_dir: Path, pid: int, status: dict) -> float | None:
    identity = read_json(job_dir / "worker_identity.json", {})
    created = identity.get("create_time")
    if identity.get("pid") == pid and isinstance(created, (int, float)) and created > 0:
        return float(created)

    # Older local workers did not publish identity. Their status timestamp
    # still rejects a process that started after the original worker did.
    started = status.get("started_at")
    if status.get("pid") != pid or not isinstance(started, (int, float)):
        return None
    import psutil
    try:
        created = psutil.Process(pid).create_time()
    except psutil.Error:
        return None
    return created if created <= started else None


def _record_worker_exit(job_dir: Path, code: int | None, message: str = "") -> None:
    # Re-read after observing process exit; the worker may have just committed status.
    status = read_json(job_dir / "job_status.json", {})
    if status.get("state") in {"completed", "failed", "stopped"}:
        if not (job_dir / "exit_code.txt").exists():
            (job_dir / "exit_code.txt").write_text(str(status.get("exit_code", code or 0)), encoding="utf-8")
        return
    stopped = (job_dir / "stop_requested").exists()
    status.update(
        state="stopped" if stopped else "failed", exit_code=0 if stopped else (code or 1),
        finished_at=time.time(), updated_at=time.time(),
    )
    if not stopped:
        status["error"] = message or "The worker exited before writing its final status. See launcher.log for details."
    write_json(job_dir / "job_status.json", status)
    (job_dir / "exit_code.txt").write_text(str(status["exit_code"]), encoding="utf-8")


def _terminate_worker(handle: ProcessHandle) -> None:
    # Keep the original Popen handle; never terminate an arbitrary reused PID.
    if handle.terminate is not None:
        try:
            handle.terminate()
        except OSError:
            pass


def _default_process_runner(command: list[str]) -> ProcessHandle:
    import psutil
    config_path = Path(command[command.index("--job-config") + 1]).resolve()
    job_dir = config_path.parent
    kwargs: dict[str, object] = {
        "cwd": str(paths.backend_cwd()), "stdin": subprocess.DEVNULL,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        kwargs["creationflags"] = detached_worker_flags()
    else:
        kwargs["start_new_session"] = True
    with (job_dir / "launcher.log").open("ab") as output:
        process = subprocess.Popen(command, stdout=output, **kwargs)
    try:
        created = psutil.Process(process.pid).create_time()
    except psutil.Error:
        created = None

    def collect_exit() -> None:
        _record_worker_exit(job_dir, process.wait())

    threading.Thread(target=collect_exit, daemon=True).start()
    return ProcessHandle(pid=int(process.pid), create_time=created, terminate=process.terminate)


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
        "error": str(entry.get("error") or ""),
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


@dataclass
class _BatchSummaryCacheEntry:
    mtime: float
    st_size: int
    byte_offset: int
    states: dict[str, str]
    event_total: int
    summary: dict[str, int]


class BatchSummaryCache:
    """In-memory dirty-state cache for batch summary calculation with incremental file scans."""

    def __init__(self) -> None:
        self._cache: dict[str, _BatchSummaryCacheEntry] = {}

    def get_or_update(self, job_dir: Path, input_files: list[JsonValue]) -> dict[str, int]:
        sum_file = job_dir / "job_summary.json"
        if sum_file.exists():
            try:
                s_data = read_json(sum_file, {})
                if isinstance(s_data, dict) and "total" in s_data:
                    return {
                        "total": int(s_data.get("total", 0)),
                        "success": int(s_data.get("success", 0)),
                        "failed": int(s_data.get("failed", 0)),
                        "running": int(s_data.get("running", 0)),
                        "stopped": int(s_data.get("stopped", 0)),
                        "interrupted": int(s_data.get("stopped", 0)),
                        "pending": int(s_data.get("pending", 0)),
                    }
            except Exception:
                pass

        events_path = job_dir / "events.jsonl"
        if not events_path.exists():
            total = len(input_files)
            return {"total": total, "success": 0, "failed": 0, "running": 0, "pending": total}

        try:
            stat_res = events_path.stat()
        except OSError:
            total = len(input_files)
            return {"total": total, "success": 0, "failed": 0, "running": 0, "pending": total}

        key = str(job_dir.resolve())
        cached = self._cache.get(key)
        if cached is not None and cached.mtime == stat_res.st_mtime and cached.st_size == stat_res.st_size:
            return cached.summary

        # Incremental file growth check
        if cached is not None and stat_res.st_size >= cached.st_size and cached.byte_offset <= stat_res.st_size:
            states = dict(cached.states)
            event_total = cached.event_total
            offset = cached.byte_offset
        else:
            states = {}
            event_total = 0
            offset = 0

        new_offset = offset
        try:
            with events_path.open("r", encoding="utf-8") as handle:
                handle.seek(offset)
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
                    ev_status = str(event.get("status", "")).lower()
                    if ev_status == "stopped":
                        states[input_file] = "stopped"
                    else:
                        states[input_file] = "running" if kind == "image_start" else (
                            "success" if bool(event.get("success")) else "failed"
                        )
                new_offset = handle.tell()
        except OSError:
            pass

        total = max(len(input_files), event_total, len(states))
        success = sum(state == "success" for state in states.values())
        failed = sum(state == "failed" for state in states.values())
        running = sum(state == "running" for state in states.values())
        stopped = sum(state == "stopped" for state in states.values())
        summary = {
            "total": total,
            "success": success,
            "failed": failed,
            "running": running,
            "pending": max(0, total - success - failed - running - stopped),
        }
        if stopped > 0:
            summary["stopped"] = stopped
            summary["interrupted"] = stopped

        self._cache[key] = _BatchSummaryCacheEntry(
            mtime=stat_res.st_mtime,
            st_size=stat_res.st_size,
            byte_offset=new_offset,
            states=states,
            event_total=event_total,
            summary=summary,
        )
        return summary


_BATCH_SUMMARY_CACHE = BatchSummaryCache()


def _read_batch_summary(job_dir: Path, input_files: list[JsonValue]) -> dict[str, int]:
    """Summarize image events using the dirty-state cache with O(1) validation."""
    return _BATCH_SUMMARY_CACHE.get_or_update(job_dir, input_files)


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


def _redact_registry_entry(entry: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return _json_dict(redact_secrets(entry))
