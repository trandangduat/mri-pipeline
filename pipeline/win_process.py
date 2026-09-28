"""Windows-safe subprocess helpers for GUI hosts.

NeuroFlow's packaged backend and Tauri shell are PE Windows (GUI) subsystem
binaries (``console=False`` / ``windows_subsystem = "windows"``). Spawning a
console-subsystem child such as ``docker.exe`` or ``nvidia-smi.exe`` without
``CREATE_NO_WINDOW`` allocates a visible console that flashes briefly.

Prefer ``no_window_kwargs()`` on every ``subprocess.run`` / ``Popen`` that can
run under the GUI. Do **not** combine ``CREATE_NO_WINDOW`` with
``DETACHED_PROCESS`` — MSDN documents that ``CREATE_NO_WINDOW`` is ignored when
paired with ``DETACHED_PROCESS``.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

# Present on Python 3.7+ Windows; hardcode the Win32 value for other platforms
# so imports stay safe in tests.
CREATE_NO_WINDOW: int = int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
CREATE_NEW_PROCESS_GROUP: int = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200))


def no_window_kwargs() -> dict[str, Any]:
    """Return ``creationflags=CREATE_NO_WINDOW`` on Windows; empty elsewhere."""
    if os.name != "nt":
        return {}
    return {"creationflags": CREATE_NO_WINDOW}


def detached_worker_flags() -> int:
    """Flags for long-lived worker children spawned from the GUI backend.

    Uses ``CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`` (not ``DETACHED_PROCESS``)
    so the console stays hidden on Windows.
    """
    if os.name != "nt":
        return 0
    return CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
