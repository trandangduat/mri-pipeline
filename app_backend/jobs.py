from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeAlias

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
        self.jobs_root = Path(jobs_root) if jobs_root is not None else PROJECT_ROOT / "outputs" / "jobs"
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

        command = [sys.executable, "-m", "pipeline.job_worker", "--job-config", str(config_path)]
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
        if exit_code is not None or status.get("state") in {"completed", "failed"}:
            entry["state"] = "completed" if exit_code == 0 else "failed"
            entry["exit_code"] = exit_code
        elif status.get("state"):
            entry["state"] = str(status.get("state"))
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
        "cwd": str(PROJECT_ROOT),
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


def _job_summary(entry: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "job_id": str(entry.get("job_id", "")),
        "target": "Local",
        "state": str(entry.get("state", "unknown")),
        "job_dir": str(entry.get("job_dir", "")),
        "pid": int(entry.get("pid", 0) or 0),
        "exit_code": entry.get("exit_code") if isinstance(entry.get("exit_code"), int) else None,
        "started_at": float(entry.get("started_at", 0.0) or 0.0),
        "updated_at": float(entry.get("updated_at", 0.0) or 0.0),
        "output_dir": str(entry.get("output_dir", "")),
        "effective_output_dir": str(entry.get("effective_output_dir", "")),
    }


def _input_files_for_request(request: dict[str, JsonValue]) -> list[str]:
    mode = request.get("mode")
    if mode == "file" and request.get("input_file"):
        return [str(request.get("input_file"))]
    if mode == "files" and isinstance(request.get("input_files"), list):
        return [str(path) for path in request.get("input_files", [])]
    if request.get("input_dir"):
        return [str(request.get("input_dir"))]
    return []


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
