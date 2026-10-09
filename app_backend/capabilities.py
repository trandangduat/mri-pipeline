from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from typing import Any


REQUIRED_DEPENDENCIES = (
    ("paramiko", "Paramiko"),
    ("yaml", "PyYAML"),
)


def runtime_capabilities(import_module: Callable[[str], Any] = importlib.import_module) -> dict[str, Any]:
    """Return safe application-runtime capability information for the desktop UI."""
    components: list[dict[str, str | bool]] = []
    for module, label in REQUIRED_DEPENDENCIES:
        try:
            import_module(module)
        except Exception as exc:
            import traceback
            traceback.print_exc(file=sys.stderr)
            components.append(
                {
                    "id": module,
                    "label": label,
                    "ok": False,
                    "reason": f"{label} is unavailable: {type(exc).__name__}: {exc}",
                }
            )
        else:
            components.append({"id": module, "label": label, "ok": True, "reason": ""})

    missing = [component for component in components if not component["ok"]]
    ssh_ok = not any(component["id"] == "paramiko" for component in missing)
    return {
        "ok": not missing,
        "state": "ready" if not missing else "attention",
        "components": components,
        "ssh": {
            "ok": ssh_ok,
            "reason": "" if ssh_ok else "Paramiko is unavailable in the application backend.",
        },
        "diagnostics": {
            "python_executable": sys.executable,
            "runtime_source": "bundled" if getattr(sys, "frozen", False) else "development",
        },
    }
