from __future__ import annotations

import json
from pathlib import Path
from typing import TypeAlias

from app_backend import paths
from pipeline.jobs import read_json

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

MAX_EVENT_BYTES = 1_000_000
MAX_EVENT_LINE_BYTES = 262_144
MAX_FILTERED_METRICS_BYTES = 100_000_000


class LocalJobProgressService:
    def __init__(self, jobs_root: str | Path | None = None) -> None:
        self.jobs_root = Path(jobs_root) if jobs_root is not None else paths.jobs_root()
        self.registry_path = self.jobs_root / "job_registry.json"

    def read_events(self, job_id: str, offset: int = 0, limit: int = 500) -> dict[str, JsonValue]:
        job_dir = self._job_dir(job_id)
        if job_dir is None:
            return {"ok": False, "error": "Local job not found"}

        events_path = _safe_child_file(job_dir, "events.jsonl")
        if events_path is None:
            return {"ok": False, "error": "Progress file is not safe"}
        if not events_path.exists():
            return {"ok": True, "events": [], "warnings": [], "next_offset": max(0, offset)}

        start = max(0, int(offset))
        max_events = max(1, min(int(limit), 5000))
        events: list[JsonValue] = []
        warnings: list[JsonValue] = []
        next_offset = start
        scanned = 0
        with events_path.open("rb") as handle:
            handle.seek(start)
            while len(events) < max_events and scanned < MAX_EVENT_BYTES:
                raw_line = handle.readline(MAX_EVENT_LINE_BYTES + 1)
                if not raw_line:
                    break
                scanned += len(raw_line)
                next_offset = handle.tell()
                if len(raw_line) > MAX_EVENT_LINE_BYTES:
                    warnings.append("Stopped at oversized event line")
                    break
                if len(events) >= max_events:
                    break
                text = raw_line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    event = json.loads(text)
                except json.JSONDecodeError:
                    warnings.append("Skipped malformed event line")
                    continue
                if isinstance(event, dict):
                    events.append(_json_value(event))
                else:
                    warnings.append("Skipped non-object event line")
        return {"ok": True, "events": events, "warnings": warnings, "next_offset": next_offset}

    def read_metrics(
        self,
        job_id: str,
        offset: int = 0,
        limit: int = 500,
        subject_id: str = "",
        input_file: str = "",
    ) -> dict[str, JsonValue]:
        job_dir = self._job_dir(job_id)
        if job_dir is None:
            return {"ok": False, "error": "Local job not found"}

        for fname in ("metrics.jsonl", "events.jsonl"):
            metrics_path = _safe_child_file(job_dir, fname)
            if metrics_path is None or not metrics_path.exists():
                continue
            start = max(0, int(offset))
            max_events = max(1, min(int(limit), 5000))
            filtered = bool(subject_id or input_file)
            events: list[JsonValue] = []
            warnings: list[JsonValue] = []
            next_offset = start
            scanned = 0
            with metrics_path.open("rb") as handle:
                handle.seek(start)
                scan_limit = MAX_FILTERED_METRICS_BYTES if filtered else MAX_EVENT_BYTES
                while len(events) < max_events and scanned < scan_limit:
                    raw_line = handle.readline(MAX_EVENT_LINE_BYTES + 1)
                    if not raw_line:
                        break
                    scanned += len(raw_line)
                    next_offset = handle.tell()
                    if len(raw_line) > MAX_EVENT_LINE_BYTES:
                        warnings.append("Stopped at oversized metric line")
                        break
                    text = raw_line.decode("utf-8", errors="replace").strip()
                    if not text:
                        continue
                    try:
                        event = json.loads(text)
                    except json.JSONDecodeError:
                        warnings.append("Skipped malformed metric line")
                        continue
                    if isinstance(event, dict):
                        if fname != "metrics.jsonl" and event.get("kind") != "metrics":
                            continue
                        if filtered and not _metric_matches(event, subject_id, input_file):
                            continue
                        events.append(_json_value(event))
                    else:
                        warnings.append("Skipped non-object metric line")
            return {"ok": True, "events": events, "warnings": warnings, "next_offset": next_offset}

        return {"ok": True, "events": [], "warnings": [], "next_offset": max(0, offset)}

    def read_log(self, job_id: str, offset: int = 0, max_bytes: int = 65536) -> dict[str, JsonValue]:
        job_dir = self._job_dir(job_id)
        if job_dir is None:
            return {"ok": False, "error": "Local job not found"}

        log_path = _safe_child_file(job_dir, "run.log")
        if log_path is None:
            return {"ok": False, "error": "Progress file is not safe"}
        if not log_path.exists():
            return {"ok": True, "text": "", "next_offset": max(0, offset), "truncated": False}

        start = max(0, int(offset))
        byte_limit = max(1, min(int(max_bytes), 1_000_000))
        with log_path.open("rb") as handle:
            handle.seek(start)
            data = handle.read(byte_limit)
            extra = handle.read(1)
            next_offset = handle.tell() - len(extra)
        return {
            "ok": True,
            "text": data.decode("utf-8", errors="replace"),
            "next_offset": next_offset,
            "truncated": bool(extra),
        }

    def _job_dir(self, job_id: str) -> Path | None:
        registry = read_json(self.registry_path, {"jobs": []})
        jobs = registry.get("jobs", [])
        if not isinstance(jobs, list):
            return None
        for entry in jobs:
            if not isinstance(entry, dict) or entry.get("target") != "Local":
                continue
            if entry.get("job_id") != job_id:
                continue
            job_dir = Path(str(entry.get("job_dir", ""))).resolve()
            jobs_root = self.jobs_root.resolve()
            if job_dir.exists() and _is_relative_to(job_dir, jobs_root):
                return job_dir
        return None


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _safe_child_file(job_dir: Path, name: str) -> Path | None:
    path = job_dir / name
    if path.is_symlink():
        return None
    try:
        resolved = path.resolve(strict=False)
        resolved.relative_to(job_dir.resolve())
    except ValueError:
        return None
    return path


def _metric_matches(event: dict[str, object], subject_id: str, input_file: str) -> bool:
    """Match either stable subject identity used by new and legacy jobs."""
    return bool(
        (subject_id and str(event.get("subject_id", "")) == subject_id)
        or (input_file and str(event.get("input_file", "")) == input_file)
    )


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
