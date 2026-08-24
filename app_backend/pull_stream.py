"""Streaming docker pull with stall watchdog for the Tools page.

Extracted from server.py so the watchdog behavior is unit-testable.
"""

from __future__ import annotations

import queue
import subprocess
import threading
from collections.abc import Iterator
from typing import Any, Callable

DEFAULT_STALL_TIMEOUT_S = 30

_NETWORK_HINTS = (
    "timeout",
    "timed out",
    "unreachable",
    "tls handshake",
    "connection refused",
    "connection reset",
    "connection closed",
    "network",
    "no such host",
    "i/o timeout",
    "proxy",
)


def friendly_pull_error(tail: list[str], exit_code: int) -> str:
    joined = "\n".join(tail).lower()
    if any(hint in joined for hint in _NETWORK_HINTS):
        return "Network connection lost during pull. Check your internet connection and try again."
    last_line = tail[-1] if tail else ""
    return last_line or f"Pull failed (exit {exit_code})"


def pull_image_events(
    image: str,
    *,
    stall_timeout_s: int = DEFAULT_STALL_TIMEOUT_S,
    popen: Callable[..., Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield SSE-style ``{"event": ..., "data": ...}`` dicts for a docker pull.

    If the pull produces no output for ``stall_timeout_s`` seconds (typical
    when the network connection drops mid-download), the process is killed
    and a clear failure event is emitted instead of hanging forever.
    """
    popen_fn = popen or subprocess.Popen
    try:
        proc = popen_fn(
            ["docker", "pull", image],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as exc:
        yield {"event": "step", "data": {"step": "pull", "status": "failed", "detail": str(exc)}}
        yield {"event": "complete", "data": {"ok": False, "error": str(exc)}}
        return

    lines: queue.Queue = queue.Queue()

    def reader() -> None:
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    threading.Thread(target=reader, daemon=True).start()

    yield {"event": "step", "data": {"step": "pull", "status": "running", "detail": f"Pulling {image}..."}}

    tail: list[str] = []
    timed_out = False
    while True:
        try:
            item = lines.get(timeout=stall_timeout_s)
        except queue.Empty:
            timed_out = True
            break
        if item is None:
            break
        line = item.strip()
        if not line:
            continue
        tail.append(line)
        tail = tail[-5:]
        yield {"event": "step", "data": {"step": "pull", "status": "running", "detail": line}}

    if timed_out:
        try:
            proc.kill()
        except Exception:
            pass
        proc.wait()
        message = (
            f"Network connection lost during pull (no output for {stall_timeout_s}s). "
            "Check your internet connection and try again."
        )
        yield {"event": "step", "data": {"step": "pull", "status": "failed", "detail": message}}
        yield {"event": "complete", "data": {"ok": False, "error": message}}
        return

    proc.wait()
    if proc.returncode == 0:
        yield {"event": "complete", "data": {"ok": True}}
    else:
        error = friendly_pull_error(tail, int(proc.returncode))
        yield {"event": "step", "data": {"step": "pull", "status": "failed", "detail": error}}
        yield {"event": "complete", "data": {"ok": False, "error": error}}
