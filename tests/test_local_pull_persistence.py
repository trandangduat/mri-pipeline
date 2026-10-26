from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app_backend.paths import pulls_root
from app_backend.pull_stream import (
    local_pull_paths,
    pull_image_events,
    read_local_pull_state,
    write_local_pull_state,
)
from app_backend.tools import CommandResult, LocalToolService


class MockProc:
    def __init__(self, chunks: list[bytes], returncode: int = 0, pid: int = 99999):
        self.chunks = list(chunks)
        self.returncode = returncode
        self.pid = pid
        self.stdout = self

    def read(self, _size: int = 4096) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""

    def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        pass


def test_pull_image_events_writes_persistent_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEUROFLOW_PULLS_ROOT", str(tmp_path / "pulls"))
    image = "test/test-image:latest"
    paths = local_pull_paths(image)

    proc = MockProc([b"Layer 1: Pull complete\n", b"Status: Downloaded\n"], returncode=0, pid=12345)
    events = list(pull_image_events(image, popen=lambda *a, **k: proc))

    assert events[-1] == {"event": "complete", "data": {"ok": True}}
    assert paths["json"].is_file()
    assert paths["log"].is_file()

    state = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert state["status"] == "success"
    assert state["exit_code"] == 0
    assert state["pid"] == 12345

    log_content = paths["log"].read_text(encoding="utf-8")
    assert "Layer 1: Pull complete" in log_content


def test_image_status_reports_local_pulling_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEUROFLOW_PULLS_ROOT", str(tmp_path / "pulls"))
    image = "mkdayyyy/mri-fs8-all:latest"

    # Mock process is alive
    monkeypatch.setattr("app_backend.jobs._worker_is_alive", lambda pid: True)

    # Write an active pulling state
    write_local_pull_state(
        image,
        {
            "image": image,
            "status": "pulling",
            "pid": 54321,
            "started_at": 1000.0,
            "updated_at": 1005.0,
        },
    )

    service = LocalToolService(
        command_runner=lambda cmd: CommandResult(returncode=1),  # Not installed
        download_size_provider=lambda img: 1000000,
    )

    res = service.image_status(target="Local")
    assert res["ok"] is True
    images = res.get("images", [])
    fs8_entry = next((item for item in images if item["image"] == image), None)
    assert fs8_entry is not None
    assert fs8_entry["status"] == "Missing"
    assert fs8_entry["pull_status"] == "pulling"
    assert fs8_entry["pull_pid"] == 54321
    assert fs8_entry["pull_started_at"] == 1000.0


def test_local_pull_status_reads_log_with_offset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEUROFLOW_PULLS_ROOT", str(tmp_path / "pulls"))
    monkeypatch.setattr("app_backend.jobs._worker_is_alive", lambda pid: True)
    image = "test/test-image:latest"
    paths = local_pull_paths(image)
    paths["dir"].mkdir(parents=True, exist_ok=True)
    paths["json"].write_text(json.dumps({"image": image, "status": "pulling", "pid": 111}), encoding="utf-8")
    paths["log"].write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

    service = LocalToolService()
    res1 = service.local_pull_status(image, log_offset=0)
    assert res1["ok"] is True
    assert res1["status"] == "pulling"
    assert "line 1" in str(res1["log_text"])
    next_offset = res1["next_offset"]
    assert isinstance(next_offset, int) and next_offset > 0

    # Next poll with offset gets empty or new text
    res2 = service.local_pull_status(image, log_offset=next_offset)
    assert res2["log_text"] == ""

    # Append new log
    with open(paths["log"], "a", encoding="utf-8") as f:
        f.write("line 4\n")

    res3 = service.local_pull_status(image, log_offset=next_offset)
    assert "line 4" in str(res3["log_text"])


class PausedPull(MockProc):
    def __init__(self, release: threading.Event, returncode: int = 0):
        super().__init__([b"Layer 1: Pull complete\n"], returncode=returncode)
        self.release = release

    def read(self, _size: int = 4096) -> bytes:
        assert self.release.wait(timeout=5)
        return super().read(_size)


@pytest.mark.parametrize("code,expected", [(0, "success"), (1, "failed")])
def test_disconnected_pull_keeps_logs_and_final_result(tmp_path, monkeypatch, code, expected):
    monkeypatch.setenv("NEUROFLOW_PULLS_ROOT", str(tmp_path))
    release = threading.Event()
    proc = PausedPull(release, returncode=code)
    image = "test/disconnected:latest"
    stream = pull_image_events(image, popen=lambda *a, **k: proc)
    try:
        assert next(stream)["event"] == "step"
        stream.close()
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = read_local_pull_state(image)
        if state and state.get("status") == expected:
            break
        time.sleep(0.01)
    else:
        pytest.fail("Disconnected pull did not save its final result")
    assert state["exit_code"] == code
    assert "Layer 1: Pull complete" in local_pull_paths(image)["log"].read_text()


def test_concurrent_pull_requests_share_one_process(tmp_path, monkeypatch):
    monkeypatch.setenv("NEUROFLOW_PULLS_ROOT", str(tmp_path))
    release = threading.Event()
    start = threading.Barrier(2)
    proc = PausedPull(release)
    calls = []

    def popen(*args, **kwargs):
        calls.append(args[0])
        return proc

    def subscribe(_):
        start.wait(timeout=5)
        stream = pull_image_events("test/shared:latest", popen=popen)
        assert next(stream)["event"] == "step"
        return stream

    streams = []
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            streams = list(pool.map(subscribe, range(2)))
        assert len(calls) == 1
        streams[0].close()
        release.set()
        assert list(streams[1])[-1] == {"event": "complete", "data": {"ok": True}}
    finally:
        release.set()
        for stream in streams:
            stream.close()


def test_status_reader_waits_for_active_producer_to_record_exit(tmp_path, monkeypatch):
    monkeypatch.setenv("NEUROFLOW_PULLS_ROOT", str(tmp_path))
    # Simulate the Docker process exiting before its producer saves success.
    monkeypatch.setattr("app_backend.jobs._worker_is_alive", lambda pid: False)
    waiting = threading.Event()
    release = threading.Event()

    class ExitedPull(MockProc):
        def wait(self):
            waiting.set()
            assert release.wait(timeout=5)
            return 0

    stream = pull_image_events("test/exited:latest", popen=lambda *a, **k: ExitedPull([]))
    try:
        next(stream)
        assert waiting.wait(timeout=5)
        assert read_local_pull_state("test/exited:latest")["status"] == "pulling"
        release.set()
        assert list(stream)[-1]["data"]["ok"] is True
    finally:
        release.set()
        stream.close()


def test_http_disconnect_detaches_subscriber_without_stopping_pull(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app_backend import pull_stream
    from app_backend.server import AppBackendRequestHandler, ClientDisconnectedError

    monkeypatch.setenv("NEUROFLOW_PULLS_ROOT", str(tmp_path))
    release = threading.Event()
    proc = PausedPull(release)
    image = "test/http-disconnect:latest"
    original = pull_stream.pull_image_events
    monkeypatch.setattr(pull_stream, "pull_image_events", lambda img: original(img, popen=lambda *a, **k: proc))

    def disconnected(*args):
        raise ClientDisconnectedError("client closed")

    handler = SimpleNamespace(_write_sse_headers=lambda: None, _send_sse_event=disconnected)
    try:
        AppBackendRequestHandler._handle_tools_pull_stream(handler, image)
        assert handler.close_connection is True
        with pull_stream._PULL_LOCK:
            assert not pull_stream._ACTIVE_PULLS[pull_stream._pull_key(image)].subscribers
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        state = read_local_pull_state(image)
        if state and state.get("status") == "success":
            break
        time.sleep(0.01)
    else:
        pytest.fail("HTTP disconnect stopped pull completion")
