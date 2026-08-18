from __future__ import annotations

import os
import sys
from pathlib import Path

from pipeline.config import PROJECT_ROOT


def portable_root() -> Path | None:
    raw = os.environ.get("NEUROFLOW_PORTABLE_ROOT")
    if raw:
        return Path(raw)
    return None


def config_root() -> Path:
    raw = os.environ.get("NEUROFLOW_CONFIG_ROOT")
    if raw:
        return Path(raw)
    root = portable_root()
    if root is not None:
        return root / "config"
    return PROJECT_ROOT / "configs"


def jobs_root() -> Path:
    raw = os.environ.get("NEUROFLOW_JOBS_ROOT")
    if raw:
        return Path(raw)
    root = portable_root()
    if root is not None:
        return root / "outputs" / "jobs"
    return PROJECT_ROOT / "outputs" / "jobs"


def license_root() -> Path:
    raw = os.environ.get("NEUROFLOW_LICENSE_ROOT")
    if raw:
        return Path(raw)
    root = portable_root()
    if root is not None:
        return root / "licenses"
    return config_root() / "licenses"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def worker_command(job_config_path: str) -> list[str]:
    if is_frozen():
        return [sys.executable, "worker", "--job-config", job_config_path]
    return [sys.executable, "-m", "pipeline.job_worker", "--job-config", job_config_path]


def backend_cwd() -> Path:
    root = portable_root()
    if root is not None:
        return root
    if is_frozen():
        return Path(sys.executable).parent
    return PROJECT_ROOT
