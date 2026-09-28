from __future__ import annotations

import os
import sys
from pathlib import Path

from pipeline.config import PROJECT_ROOT


def resource_root() -> Path:
    """Return immutable application resources.

    Cross-platform contract (PyInstaller 6 one-directory + Tauri):
    specs keep `COLLECT(contents_directory="_internal")`, so static `a.datas`
    land under `backend/_internal/`. The native shell must set
    `NEUROFLOW_RESOURCE_ROOT` to that `_internal` directory - not the
    backend executable's parent. Using the parent would make packaged atlases
    and configs resolve incorrectly even when the bundle builds successfully.

    When the env var is unset, a frozen process falls back to `sys._MEIPASS`
    (the same contents directory). Source launches retain the repository root.
    """
    raw = os.environ.get("NEUROFLOW_RESOURCE_ROOT")
    if raw:
        return Path(raw).expanduser()
    if is_frozen():
        return Path(sys._MEIPASS)
    # Legacy portable launchers supplied one root for both code and mutable
    # state. Preserve that source-compatible behaviour; packaged launches use
    # the explicit immutable resource root above.
    root = portable_root()
    return root if root is not None else PROJECT_ROOT


def portable_root() -> Path | None:
    raw = os.environ.get("NEUROFLOW_PORTABLE_ROOT")
    if raw:
        return Path(raw)
    return None


def data_root() -> Path:
    """Return the writable per-user state root.

    NEUROFLOW_PORTABLE_ROOT remains a compatibility alias for the opt-in
    portable layout; installed applications always receive DATA_ROOT from the
    native shell and never write into signed resources.
    """
    raw = os.environ.get("NEUROFLOW_DATA_ROOT")
    if raw:
        return Path(raw).expanduser()
    root = portable_root()
    if root is not None:
        return root
    return PROJECT_ROOT


def config_root() -> Path:
    raw = os.environ.get("NEUROFLOW_CONFIG_ROOT")
    if raw:
        return Path(raw)
    root = data_root()
    return root / ("config" if portable_root() is not None or os.environ.get("NEUROFLOW_DATA_ROOT") else "configs")


def jobs_root() -> Path:
    raw = os.environ.get("NEUROFLOW_JOBS_ROOT")
    if raw:
        return Path(raw)
    return data_root() / "outputs" / "jobs"


def license_root() -> Path:
    raw = os.environ.get("NEUROFLOW_LICENSE_ROOT")
    if raw:
        return Path(raw)
    return data_root() / "licenses"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def worker_command(job_config_path: str) -> list[str]:
    if is_frozen():
        return [sys.executable, "worker", "--job-config", job_config_path]
    return [sys.executable, "-m", "pipeline.job_worker", "--job-config", job_config_path]


def backend_cwd() -> Path:
    # Portable launchers historically use their root as the working directory,
    # even before it has been created.  Keep that contract ahead of the
    # installed layout, where the native shell supplies RESOURCE_ROOT.
    portable = portable_root()
    if portable is not None:
        return portable
    root = resource_root()
    if root.exists():
        return root
    if is_frozen():
        return Path(sys.executable).parent
    return PROJECT_ROOT
