from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def _is_own_backend_process(cmdline: list[str] | None, cwd: str | None, backend_root: Path) -> bool:
    if not cmdline:
        return False

    cmd_str = " ".join(cmdline)
    matches_cmd = "app_backend.server" in cmd_str or any(arg.endswith("app_backend/server.py") for arg in cmdline)
    if not matches_cmd:
        return False

    if cwd:
        try:
            cwd_path = Path(cwd).resolve()
            resolved_root = backend_root.resolve()
            if cwd_path != resolved_root and resolved_root not in cwd_path.parents and cwd_path not in resolved_root.parents:
                return False
        except OSError:
            pass

    return True


def cleanup_stale_backend(host: str = "127.0.0.1", port: int = 8765, backend_root: Path | None = None) -> dict[str, JsonValue]:
    try:
        import psutil
    except ImportError:
        return {
            "killed": [],
            "skipped": [],
            "errors": ["psutil is missing. Install with `python3 -m pip install psutil`."],
        }

    root = (backend_root or Path(__file__).resolve().parent.parent).resolve()
    current_pid = os.getpid()

    killed_pids: list[int] = []
    skipped: list[str] = []
    errors: list[str] = []

    for proc in psutil.process_iter(["pid", "name", "cmdline", "cwd"]):
        try:
            if proc.pid == current_pid:
                continue
            connections = proc.net_connections(kind="inet")
            listening = False
            for conn in connections:
                if getattr(conn, "laddr", None) and getattr(conn.laddr, "port", None) == port:
                    listening = True
                    break
            if not listening:
                continue

            info = proc.info if hasattr(proc, "info") and isinstance(proc.info, dict) else {}
            cmdline = info.get("cmdline") or getattr(proc, "cmdline", lambda: [])()
            cwd = info.get("cwd") or getattr(proc, "cwd", lambda: "")()

            if _is_own_backend_process(cmdline, cwd, root):
                try:
                    proc.terminate()
                    gone, _alive = psutil.wait_procs([proc], timeout=1.5)
                    if not gone:
                        proc.kill()
                    killed_pids.append(proc.pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                    errors.append(f"Failed to kill backend PID {proc.pid}: {exc}")
            else:
                errors.append(f"Port {port} is occupied by non-NeuroFlow process PID {proc.pid} ({info.get('name')}).")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return {
        "killed": killed_pids,
        "skipped": skipped,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean up stale MRI Pipeline backend server processes.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--backend-root", type=str, default="")
    args = parser.parse_args(argv)

    root = Path(args.backend_root).resolve() if args.backend_root else None
    result = cleanup_stale_backend(args.host, args.port, root)

    if result["errors"]:
        for err in result["errors"]:
            print(f"Cleanup note: {err}", file=sys.stderr)
        if any("occupied by non-NeuroFlow" in str(err) for err in result["errors"]):
            return 1
    if result["killed"]:
        print(f"Cleaned up stale backend PID(s): {result['killed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
