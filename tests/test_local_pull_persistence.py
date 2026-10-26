from __future__ import annotations

import json
import time
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
