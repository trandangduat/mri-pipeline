"""Streaming docker pull events for the Tools page.

Extracted from server.py so streaming and optional watchdog behavior are unit-testable.
"""

from __future__ import annotations

import queue
import re
import subprocess
import threading
import time
from collections.abc import Iterator
from typing import Any, Callable

DEFAULT_STALL_TIMEOUT_S: int | None = None
PROGRESS_EMIT_INTERVAL_S = 0.2

# docker pull sends per-layer progress frames separated by carriage returns;
# these keywords mark meaningful transitions that should always be emitted.
_ALWAYS_EMIT_RE = re.compile(
    r"(Pull complete|Download complete|Extracting complete|Already exists|"
    r"Status:|Digest:|Pulling from|Error|error)",
)

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


def _split_stream_segments(buffer: str) -> tuple[list[str], str]:
    """Split decoded chunks on both newlines and carriage returns."""
    parts = re.split(r"[\r\n]", buffer)
    remaining = parts.pop() if parts else ""
    return [part for part in parts if part], remaining


def pull_image_events(
    image: str,
    *,
    stall_timeout_s: int | None = DEFAULT_STALL_TIMEOUT_S,
    popen: Callable[..., Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield SSE-style ``{"event": ..., "data": ...}`` dicts for a docker pull.

    - Per-layer progress frames (separated by ``\\r``) are streamed with light
      throttling so the UI can show download/extract progress per layer.
    - By default, Docker controls pull retries and failures without an
      application-level inactivity deadline. If ``stall_timeout_s`` is set,
      the process is killed after that many seconds without output.
    """
    popen_fn = popen or subprocess.Popen
    try:
        proc = popen_fn(
            ["docker", "pull", image],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
    except Exception as exc:
        yield {"event": "step", "data": {"step": "pull", "status": "failed", "detail": str(exc)}}
        yield {"event": "complete", "data": {"ok": False, "error": str(exc)}}
        return

    segments: queue.Queue = queue.Queue()

    def reader() -> None:
        assert proc.stdout is not None
        buffer = ""
        read1 = getattr(proc.stdout, "read1", None)
        read_chunk = read1 if callable(read1) else proc.stdout.read
        try:
            while True:
                chunk = read_chunk(4096)
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else chunk
                buffer += text
                parts, buffer = _split_stream_segments(buffer)
                for part in parts:
                    segments.put(part)
        finally:
            if buffer.strip():
                segments.put(buffer)
            segments.put(None)

    threading.Thread(target=reader, daemon=True).start()

    yield {"event": "step", "data": {"step": "pull", "status": "running", "detail": f"Pulling {image}..."}}

    tail: list[str] = []
    timed_out = False
    last_progress_emit = 0.0
    while True:
        try:
            item = segments.get(timeout=stall_timeout_s)
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
        if _ALWAYS_EMIT_RE.search(line):
            yield {"event": "step", "data": {"step": "pull", "status": "running", "detail": line}}
            continue
        now = time.monotonic()
        if (now - last_progress_emit) >= PROGRESS_EMIT_INTERVAL_S:
            last_progress_emit = now
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
