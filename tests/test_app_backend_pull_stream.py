from __future__ import annotations

import threading

from app_backend.pull_stream import pull_image_events


class FakeStdout:
    def __init__(self, chunks: list[bytes], hold: threading.Event | None = None) -> None:
        self.chunks = list(chunks)
        self._hold = hold

    def read(self, _size: int) -> bytes:
        if self.chunks:
            return self.chunks.pop(0)
        if self._hold is not None:
            self._hold.wait(timeout=5)
        return b""


class FakeProc:
    def __init__(self, chunks: list[bytes], returncode: int = 0, hold: bool = False) -> None:
        self.returncode = returncode
        self.killed = False
        self._release = threading.Event()
        self.stdout = FakeStdout(chunks, hold=self._release if hold else None)

    def kill(self):
        self.killed = True
        self._release.set()

    def wait(self):
        return self.returncode


def test_pull_success_streams_lines_and_completes():
    proc = FakeProc(
        [
            b"Pulling from library \n",
            b"Digest: sha256:abc \n",
            b"Status: Downloaded newer image \n",
        ],
        returncode=0,
    )
    events = list(pull_image_events("hello:latest", popen=lambda *a, **k: proc))

    assert events[0] == {"event": "step", "data": {"step": "pull", "status": "running", "detail": "Pulling hello:latest..."}}
    assert [e["data"]["detail"] for e in events[1:-1]] == [
        "Pulling from library",
        "Digest: sha256:abc",
        "Status: Downloaded newer image",
    ]
    assert events[-1] == {"event": "complete", "data": {"ok": True}}
    assert proc.killed is False


def test_pull_streams_carriage_return_progress_frames():
    proc = FakeProc(
        [
            b"latest: Pulling from library/hello\n",
            b"abc123: Downloading [==>]  10MB/20MB\r"
            b"abc123: Extracting [==> ]  12MB/20MB\r"
            b"abc123: Pull complete\n",
            b"Status: Downloaded newer image for hello:latest\n",
        ],
        returncode=0,
    )
    events = list(pull_image_events("hello:latest", popen=lambda *a, **k: proc))

    details = [e["data"]["detail"] for e in events[1:-1]]
    # \r-separated progress frames are split; the "Pull complete" transition is always emitted
    assert "abc123: Downloading [==>]  10MB/20MB" in details
    assert "abc123: Pull complete" in details
    assert "Status: Downloaded newer image for hello:latest" in details
    assert events[-1] == {"event": "complete", "data": {"ok": True}}


def test_pull_stall_kills_process_and_reports_network_error():
    proc = FakeProc([], returncode=1, hold=True)
    events = list(pull_image_events("hello:latest", stall_timeout_s=1, popen=lambda *a, **k: proc))

    assert proc.killed is True
    complete = events[-1]
    assert complete["event"] == "complete"
    assert complete["data"]["ok"] is False
    assert "Network connection lost during pull" in complete["data"]["error"]
    assert any(
        e["event"] == "step" and e["data"].get("status") == "failed" and "Network connection lost" in e["data"]["detail"]
        for e in events
    )


def test_pull_failure_with_network_keyword_is_classified():
    proc = FakeProc(
        [b"Get \"https://registry-1.docker.io/v2/\": net/http: connection refused\n"],
        returncode=1,
    )
    events = list(pull_image_events("hello:latest", popen=lambda *a, **k: proc))

    complete = events[-1]["data"]
    assert complete["ok"] is False
    assert "Network connection lost during pull" in complete["error"]


def test_pull_failure_generic_uses_last_output_line():
    proc = FakeProc([b"Error response from daemon: manifest for hello:latest not found\n"], returncode=1)
    events = list(pull_image_events("hello:latest", popen=lambda *a, **k: proc))

    complete = events[-1]["data"]
    assert complete["ok"] is False
    assert complete["error"] == "Error response from daemon: manifest for hello:latest not found"
