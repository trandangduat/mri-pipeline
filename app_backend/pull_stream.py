"""Streaming docker pull events for the Tools page.

Extracted from server.py so streaming and optional watchdog behavior are unit-testable.
"""

from __future__ import annotations

import json
import queue
import re
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Callable
from pipeline.win_process import no_window_kwargs

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


def local_pull_paths(image: str) -> dict[str, Path]:
    from app_backend.paths import pulls_root

    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", image)
    root = pulls_root()
    return {
        "dir": root,
        "json": root / f"{safe}.json",
        "log": root / f"{safe}.log",
    }


def read_local_pull_state(image: str) -> dict[str, Any] | None:
    p = local_pull_paths(image)
    if not p["json"].is_file():
        return None
    try:
        data = json.loads(p["json"].read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    status = str(data.get("status", "")).lower()
    pid = data.get("pid")
    if status == "pulling" and isinstance(pid, int):
        from app_backend.jobs import _worker_is_alive

        if not _worker_is_alive(pid):
            data["status"] = "failed"
            data["error"] = "Pull process terminated unexpectedly"
            try:
                p["json"].write_text(json.dumps(data, indent=2), encoding="utf-8")
            except OSError:
                pass
            return data
    return data


def write_local_pull_state(image: str, state: dict[str, Any]) -> None:
    p = local_pull_paths(image)
    try:
        p["dir"].mkdir(parents=True, exist_ok=True)
        p["json"].write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass


def pull_image_events(
    image: str,
    *,
    stall_timeout_s: int | None = DEFAULT_STALL_TIMEOUT_S,
    popen: Callable[..., Any] | None = None,
) -> Iterator[dict[str, Any]]:
    paths = local_pull_paths(image)
    try:
        paths["dir"].mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    # Check if a pull for this image is already actively running
    existing = read_local_pull_state(image)
    if existing and str(existing.get("status", "")).lower() == "pulling":
        yield {
            "event": "step",
            "data": {"step": "pull", "status": "running", "detail": f"Pulling {image}..."},
        }
        offset = 0
        if paths["log"].is_file():
            try:
                initial_lines = paths["log"].read_text(encoding="utf-8", errors="replace").splitlines()
                for line in initial_lines[-5:]:
                    if line.strip():
                        yield {"event": "step", "data": {"step": "pull", "status": "running", "detail": line.strip()}}
                offset = paths["log"].stat().st_size
            except OSError:
                pass
        while True:
            time.sleep(0.3)
            if paths["log"].is_file():
                try:
                    cur_size = paths["log"].stat().st_size
                    if cur_size > offset:
                        with open(paths["log"], "r", encoding="utf-8", errors="replace") as lf:
                            lf.seek(offset)
                            new_data = lf.read()
                            offset = lf.tell()
                            for line in new_data.splitlines():
                                if line.strip():
                                    yield {"event": "step", "data": {"step": "pull", "status": "running", "detail": line.strip()}}
                except OSError:
                    pass
            cur_state = read_local_pull_state(image)
            if not cur_state or str(cur_state.get("status", "")).lower() != "pulling":
                ok = bool(cur_state and str(cur_state.get("status", "")).lower() == "success")
                err = cur_state.get("error") if cur_state else "Pull ended"
                if ok:
                    yield {"event": "complete", "data": {"ok": True}}
                else:
                    yield {"event": "step", "data": {"step": "pull", "status": "failed", "detail": str(err)}}
                    yield {"event": "complete", "data": {"ok": False, "error": str(err)}}
                return

    popen_fn = popen or subprocess.Popen
    try:
        proc = popen_fn(
            ["docker", "pull", image],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            **(no_window_kwargs() if popen_fn is subprocess.Popen else {}),
        )
    except Exception as exc:
        yield {"event": "step", "data": {"step": "pull", "status": "failed", "detail": str(exc)}}
        yield {"event": "complete", "data": {"ok": False, "error": str(exc)}}
        return

    pid = getattr(proc, "pid", None)
    now = time.time()
    state_record = {
        "image": image,
        "status": "pulling",
        "pid": pid,
        "started_at": now,
        "updated_at": now,
        "log_path": str(paths["log"]),
    }
    write_local_pull_state(image, state_record)
    try:
        paths["log"].write_text(f"Starting pull for {image}\n", encoding="utf-8")
    except OSError:
        pass

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
    last_state_write = time.monotonic()

    def _append_log(msg: str) -> None:
        try:
            with open(paths["log"], "a", encoding="utf-8", errors="replace") as lf:
                lf.write(msg + "\n")
        except OSError:
            pass

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
        _append_log(line)

        now_mono = time.monotonic()
        if (now_mono - last_state_write) >= 2.0:
            last_state_write = now_mono
            state_record["updated_at"] = time.time()
            write_local_pull_state(image, state_record)

        if _ALWAYS_EMIT_RE.search(line):
            yield {"event": "step", "data": {"step": "pull", "status": "running", "detail": line}}
            continue
        if (now_mono - last_progress_emit) >= PROGRESS_EMIT_INTERVAL_S:
            last_progress_emit = now_mono
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
        _append_log(f"TIMEOUT: {message}")
        state_record["status"] = "failed"
        state_record["exit_code"] = 1
        state_record["error"] = message
        state_record["updated_at"] = time.time()
        write_local_pull_state(image, state_record)

        yield {"event": "step", "data": {"step": "pull", "status": "failed", "detail": message}}
        yield {"event": "complete", "data": {"ok": False, "error": message}}
        return

    proc.wait()
    if proc.returncode == 0:
        state_record["status"] = "success"
        state_record["exit_code"] = 0
        state_record["updated_at"] = time.time()
        write_local_pull_state(image, state_record)
        _append_log("Pull completed successfully.")
        yield {"event": "complete", "data": {"ok": True}}
    else:
        error = friendly_pull_error(tail, int(proc.returncode))
        state_record["status"] = "failed"
        state_record["exit_code"] = int(proc.returncode)
        state_record["error"] = error
        state_record["updated_at"] = time.time()
        write_local_pull_state(image, state_record)
        _append_log(f"FAILED: {error}")
        yield {"event": "step", "data": {"step": "pull", "status": "failed", "detail": error}}
        yield {"event": "complete", "data": {"ok": False, "error": error}}
