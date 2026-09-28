from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

from pipeline.win_process import (
    CREATE_NEW_PROCESS_GROUP,
    CREATE_NO_WINDOW,
    detached_worker_flags,
    no_window_kwargs,
)


def test_no_window_kwargs_empty_off_windows() -> None:
    with patch("pipeline.win_process.os.name", "posix"):
        assert no_window_kwargs() == {}


def test_no_window_kwargs_sets_create_no_window_on_windows() -> None:
    with patch("pipeline.win_process.os.name", "nt"):
        assert no_window_kwargs() == {"creationflags": CREATE_NO_WINDOW}


def test_detached_worker_flags_prefer_create_no_window_not_detached() -> None:
    """DETACHED_PROCESS must not be combined with CREATE_NO_WINDOW (MSDN)."""
    with patch("pipeline.win_process.os.name", "nt"):
        flags = detached_worker_flags()
    assert flags & CREATE_NO_WINDOW
    assert flags & CREATE_NEW_PROCESS_GROUP
    detached = int(getattr(subprocess, "DETACHED_PROCESS", 0x00000008))
    assert flags & detached == 0


def test_jobs_default_runner_uses_detached_worker_flags(monkeypatch) -> None:
    from app_backend import jobs

    captured: dict[str, object] = {}

    class FakeProc:
        pid = 4242

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeProc()

    monkeypatch.setattr(jobs.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(jobs.os, "name", "nt")
    monkeypatch.setattr(jobs, "detached_worker_flags", lambda: CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP)

    handle = jobs._default_process_runner(["neuroflow-backend.exe", "worker", "--job-config", "x.json"])
    assert handle.pid == 4242
    assert captured["kwargs"]["creationflags"] == CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    assert "DETACHED_PROCESS" not in str(captured["kwargs"])
