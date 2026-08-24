from __future__ import annotations

import threading

from app_backend.pull_stream import pull_image_events


class FakeProc:
    def __init__(self, lines=None, returncode=0, hold_stdout=False):
        self.lines = lines or []
        self.returncode = returncode
        self.killed = False
        self._release = threading.Event()
        self.hold_stdout = hold_stdout

    def kill(self):
        self.killed = True
        self._release.set()

    def wait(self):
        return self.returncode

    @property
    def stdout(self):
        return self._iter()

    def _iter(self):
        for line in self.lines:
            yield line
        if self.hold_stdout:
            self._release.wait(timeout=5)


def test_pull_success_streams_lines_and_completes():
    proc = FakeProc(lines=["Pulling from library \n", "Digest: sha256:abc \n", "Status: Downloaded \n"], returncode=0)
    events = list(pull_image_events("hello:latest", popen=lambda *a, **k: proc))

    assert events[0] == {"event": "step", "data": {"step": "pull", "status": "running", "detail": "Pulling hello:latest..."}}
    assert [e["data"]["detail"] for e in events[1:-1]] == ["Pulling from library", "Digest: sha256:abc", "Status: Downloaded"]
    assert events[-1] == {"event": "complete", "data": {"ok": True}}
    assert proc.killed is False


def test_pull_stall_kills_process_and_reports_network_error():
    proc = FakeProc(lines=[], returncode=1, hold_stdout=True)
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
        lines=["Get \"https://registry-1.docker.io/v2/\": net/http: connection refused\n"],
        returncode=1,
    )
    events = list(pull_image_events("hello:latest", popen=lambda *a, **k: proc))

    complete = events[-1]["data"]
    assert complete["ok"] is False
    assert "Network connection lost during pull" in complete["error"]


def test_pull_failure_generic_uses_last_output_line():
    proc = FakeProc(lines=["Error response from daemon: manifest for hello:latest not found\n"], returncode=1)
    events = list(pull_image_events("hello:latest", popen=lambda *a, **k: proc))

    complete = events[-1]["data"]
    assert complete["ok"] is False
    assert complete["error"] == "Error response from daemon: manifest for hello:latest not found"
