"""Client-side lazy-upload orchestrator for Server-target + Local-input jobs.

Watches the remote ``events.jsonl`` for ``image_awaiting_input`` events
(emitted when the NeuroFLOW scheduler schedules an image's first stage),
uploads that image's local data to its staging path via SFTP, then publishes
it atomically and writes a ``<staged>.ready`` marker the server-side worker
blocks on. At most ``max_concurrent`` uploads run at once, mirroring the
scheduler's concurrency so images upload exactly when they are needed.
"""

from __future__ import annotations

import posixpath
import threading
import time
from pathlib import Path

from .ssh_client import RemoteSSHClient


UPLOAD_POLL_INTERVAL_SEC = 2.0
PROGRESS_THROTTLE_SEC = 0.25

TERMINAL_STATES = {"ready", "failed", "cancelled"}


class _UploadHandle:
    def __init__(self) -> None:
        self.cancelled = threading.Event()
        self.thread: threading.Thread | None = None
        self.error = ""


class LazyUploadOrchestrator:
    """Drives per-image uploads for one running remote job."""

    def __init__(
        self,
        runner,
        *,
        source_paths: dict[str, str],
        max_concurrent: int = 2,
        on_log=None,
    ) -> None:
        # staging_path -> local_path
        self.source_paths = dict(source_paths)
        self.max_concurrent = max(1, int(max_concurrent))
        self.on_log = on_log or (lambda _line: None)
        self._runner = runner
        self._ssh_config = runner.config.ssh
        self._lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._done_event = threading.Event()
        self._semaphore = threading.BoundedSemaphore(self.max_concurrent)
        self._handles: dict[str, _UploadHandle] = {}
        self._state: dict[str, dict[str, object]] = {
            staging: {"subject": Path(local).name, "pct": 0.0, "state": "pending", "error": ""}
            for staging, local in self.source_paths.items()
        }
        self._thread = threading.Thread(target=self._run, name="lazy-upload", daemon=True)

    # ------------------------------------------------------------------ API
    def start(self) -> None:
        self._thread.start()

    def cancel(self) -> None:
        """Abort all in-flight uploads and delete partial files on the server."""
        self._cancel_event.set()
        with self._lock:
            handles = list(self._handles.items())
        if handles:
            self._abort_handles(handles)
        self._done_event.set()

    def snapshot(self) -> list[dict[str, object]]:
        with self._lock:
            return [
                {"staging_path": staging, **state}
                for staging, state in sorted(self._state.items())
            ]

    def is_terminal(self) -> bool:
        with self._lock:
            states = [str(entry["state"]) for entry in self._state.values()]
        return all(state in TERMINAL_STATES for state in states) if states else True

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout=timeout)

    # ---------------------------------------------------------------- loop
    def _run(self) -> None:
        offset = 0
        last_progress = 0.0
        try:
            while not self._cancel_event.is_set():
                now = time.monotonic()
                if now - last_progress >= PROGRESS_THROTTLE_SEC:
                    last_progress = now
                    self._drain_finished()
                events, offset = self._read_events(offset)
                for event in events:
                    if self._cancel_event.is_set():
                        break
                    kind = event.get("kind")
                    if kind == "image_awaiting_input":
                        self._schedule_for_subject(str(event.get("input_file", "")))
                    elif kind in {"batch_done", "job_exit"}:
                        self._drain_finished()
                        return
                pending = self._pending_count()
                if pending == 0 and self._all_scheduled() and self.is_terminal():
                    return
                time.sleep(UPLOAD_POLL_INTERVAL_SEC)
        finally:
            self._done_event.set()

    def _read_events(self, offset: int) -> tuple[list[dict], int]:
        try:
            result = self._runner.read_remote_events(offset=offset)
            if isinstance(result, dict):
                return list(result.get("events", [])), int(result.get("next_offset", offset))
        except Exception as exc:  # transient SSH failures keep polling
            self.on_log(f"Lazy upload event poll failed: {exc}")
        return [], offset

    def _schedule_for_subject(self, staged_input: str) -> None:
        local = self.source_paths.get(staged_input)
        if not local:
            return
        with self._lock:
            state = self._state.get(staged_input)
            if not state or state["state"] != "pending" or staged_input in self._handles:
                return
            state["state"] = "uploading"
            handle = _UploadHandle()
            self._handles[staged_input] = handle
        self._semaphore.acquire()
        if self._cancel_event.is_set():
            self._semaphore.release()
            return
        handle.thread = threading.Thread(
            target=self._upload_one,
            args=(staged_input, local, handle),
            daemon=True,
        )
        handle.thread.start()

    def _upload_one(self, staging: str, local: str, handle: _UploadHandle) -> None:
        part = staging + ".part"
        try:
            with RemoteSSHClient(self._ssh_config, self.on_log) as ssh:
                parent = posixpath.dirname(staging)
                if parent:
                    ssh.mkdir_p(parent)
                self._upload_path(ssh, local, part, staging, handle)
                if handle.cancelled.is_set():
                    raise RuntimeError("cancelled")
                self._publish(ssh, part, staging)
                with ssh.sftp.open(staging + ".ready", "w") as marker:
                    marker.write(local)
            with self._lock:
                self._state[staging] = {**self._state[staging], "pct": 100.0, "state": "ready"}
            self.on_log(f"Uploaded: {local} -> {staging}")
        except Exception as exc:
            message = str(exc)
            with self._lock:
                state = dict(self._state[staging])
                cancelled = handle.cancelled.is_set()
                state["state"] = "cancelled" if cancelled else "failed"
                state["error"] = "" if cancelled else message
                self._state[staging] = state
            if not cancelled:
                self.on_log(f"Upload FAILED for {local}: {message}")
        finally:
            self._semaphore.release()

    def _set_pct(self, staging: str, pct: float) -> None:
        with self._lock:
            self._state[staging] = {**self._state[staging], "pct": round(min(pct, 99.9), 1)}

    def _upload_path(self, ssh: RemoteSSHClient, local: str, part: str, staging: str, handle: _UploadHandle) -> None:
        """Upload a file or DICOM series directory into `<part>`, reporting %."""
        source = Path(local)
        if source.is_file():
            total = source.stat().st_size or 1

            def progress(transferred: int, _total: int) -> None:
                self._set_pct(staging, transferred / total * 100.0)

            ssh.upload_file_with_progress(source, part, callback=progress)
            return

        files = [path for path in sorted(source.rglob("*")) if path.is_file()]
        total_bytes = sum(path.stat().st_size for path in files) or 1
        completed_bytes = {"value": 0}
        ssh.mkdir_p(part)
        for file_path in files:
            if handle.cancelled.is_set():
                raise RuntimeError("cancelled")
            relative = file_path.relative_to(source).as_posix()
            destination = posixpath.join(part, relative)
            ssh.mkdir_p(posixpath.dirname(destination))
            base = completed_bytes["value"]

            def progress(transferred: int, _total: int, _base: int = base) -> None:
                self._set_pct(staging, (_base + transferred) / total_bytes * 100.0)

            ssh.upload_file_with_progress(file_path, destination, callback=progress)
            completed_bytes["value"] += file_path.stat().st_size

    def _publish(self, ssh: RemoteSSHClient, part: str, staging: str) -> None:
        """Atomically move `.part` into place; fallback to remove+rename."""
        try:
            ssh.sftp.posix_rename(part, staging)
        except OSError:
            try:
                ssh.sftp.remove(staging)
            except OSError:
                pass
            ssh.sftp.rename(part, staging)

    def _abort_handles(self, handles: list[tuple[str, _UploadHandle]]) -> None:
        for staging, handle in handles:
            handle.cancelled.set()
        for staging, handle in handles:
            thread = handle.thread
            if thread and thread.is_alive():
                thread.join(timeout=5)
        try:
            with RemoteSSHClient(self._ssh_config, lambda _line: None) as ssh:
                for staging in self.source_paths:
                    for candidate in (staging + ".part",):
                        try:
                            ssh.sftp.remove(candidate)
                        except OSError:
                            pass
        except Exception as exc:
            self.on_log(f"Partial cleanup failed: {exc}")

    def _pending_count(self) -> int:
        with self._lock:
            return sum(1 for entry in self._state.values() if entry["state"] in {"pending", "uploading"})

    def _all_scheduled(self) -> bool:
        with self._lock:
            return all(entry["state"] != "pending" for entry in self._state.values())

    def _drain_finished(self) -> None:
        with self._lock:
            finished = [
                (staging, handle)
                for staging, handle in self._handles.items()
                if handle.thread and not handle.thread.is_alive()
            ]
            for staging, _handle in finished:
                self._handles.pop(staging, None)
