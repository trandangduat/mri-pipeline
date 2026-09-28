from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from .config import PROJECT_ROOT


JOBS_ROOT = PROJECT_ROOT / "outputs" / "jobs"
REGISTRY_PATH = JOBS_ROOT / "job_registry.json"


def make_job_id(prefix: str = "job") -> str:
    return f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"


def write_json(path: str | Path, data: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # A distinct adjacent temporary file avoids one concurrent writer replacing
    # another writer's staged content. os.replace is atomic on one filesystem.
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def read_json(path: str | Path, default: dict | None = None) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else (default or {})
    except (FileNotFoundError, json.JSONDecodeError):
        return default or {}


def create_local_job_dir(output_dir: str | Path | None = None) -> Path:
    base = Path(output_dir) if output_dir else JOBS_ROOT
    if base.name != "jobs":
        base = base / "jobs"
    job_dir = base / make_job_id()
    job_dir.mkdir(parents=True, exist_ok=False)
    return job_dir


def load_job_registry() -> list[dict]:
    data = read_json(REGISTRY_PATH, {"jobs": []})
    jobs = data.get("jobs", [])
    return jobs if isinstance(jobs, list) else []


def save_job_registry(jobs: list[dict]) -> None:
    write_json(REGISTRY_PATH, {"version": 1, "jobs": jobs})


def upsert_job_registry(entry: dict) -> None:
    jobs = load_job_registry()
    job_id = entry.get("job_id") or entry.get("job_dir") or entry.get("remote_job_dir")
    updated = False
    for idx, existing in enumerate(jobs):
        existing_id = existing.get("job_id") or existing.get("job_dir") or existing.get("remote_job_dir")
        if existing_id == job_id:
            merged = dict(existing)
            merged.update(entry)
            jobs[idx] = merged
            updated = True
            break
    if not updated:
        jobs.append(entry)
    jobs.sort(key=lambda item: float(item.get("updated_at") or item.get("started_at") or 0), reverse=True)
    save_job_registry(jobs[:100])
