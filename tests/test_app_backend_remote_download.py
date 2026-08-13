from __future__ import annotations

from pathlib import Path
from typing import Iterator

from app_backend.remote import RemoteJobService
from app_backend.sse_utils import SSEEvent
from remote.remote_runner import RemoteRunConfig


class FakeRunner:
    def __init__(self, config: RemoteRunConfig, on_log=None) -> None:
        self.config = config
        self.on_log = on_log or (lambda _line: None)
        self.remote_job_dir = ""
        self.remote_output_dir = ""

    def test_ssh(self) -> None:
        pass

    def remote_hardware_info(self) -> dict[str, object]:
        return {"hostname": "fake", "logical_cores": 4, "total_ram_bytes": 8_000_000_000}

    def list_background_jobs(self) -> list[dict[str, object]]:
        return []

    def attach_job(self, remote_job_dir: str, remote_output_dir: str = "") -> None:
        self.remote_job_dir = remote_job_dir.rstrip("/")
        self.remote_output_dir = remote_output_dir or self.remote_job_dir + "/outputs"

    def count_download_files(self) -> int:
        return 5

    def download_outputs(self, local_target_dir: str | Path | None = None) -> Path:
        self.on_log("Downloading file: /remote/outputs/a.nii.gz -> /local/outputs/a.nii.gz")
        self.on_log("Downloading file: /remote/outputs/b.nii.gz -> /local/outputs/b.nii.gz")
        return Path(local_target_dir or "/tmp/outputs")


def _make_service() -> RemoteJobService:
    def factory(config: RemoteRunConfig) -> FakeRunner:
        return FakeRunner(config)

    return RemoteJobService(runner_factory=factory)


def _collect_events(service: RemoteJobService, payload: dict[str, object]) -> list[SSEEvent]:
    return list(service.stream_download_outputs(payload))


def test_stream_download_outputs_valid_payload() -> None:
    service = _make_service()
    payload: dict[str, object] = {
        "host": "server",
        "port": 22,
        "username": "tester",
        "password": "",
        "key_path": "",
        "workspace": "~/mri-remote-jobs",
        "remote_python": "python3",
        "remote_job_dir": "/home/tester/mri-remote-jobs/job_123",
        "remote_output_dir": "/home/tester/mri-remote-jobs/job_123/outputs",
        "local_target_dir": "/tmp/outputs",
        "download_subdir": "",
    }
    events = _collect_events(service, payload)

    step_steps = [e for e in events if e.get("event") == "step"]
    completes = [e for e in events if e.get("event") == "complete"]

    assert len(step_steps) >= 3
    assert len(completes) == 1
    assert completes[0]["data"]["ok"] is True
    assert completes[0]["data"]["local_path"] == "/tmp/outputs"
    assert completes[0]["data"]["copied_files"] == 2
    assert completes[0]["data"]["total_files"] == 5


def test_stream_download_outputs_missing_local_target() -> None:
    service = _make_service()
    payload: dict[str, object] = {
        "host": "server",
        "port": 22,
        "username": "tester",
        "password": "",
        "key_path": "",
        "workspace": "~/mri-remote-jobs",
        "remote_python": "python3",
        "remote_job_dir": "/home/tester/mri-remote-jobs/job_123",
    }
    events = _collect_events(service, payload)

    completes = [e for e in events if e.get("event") == "complete"]
    assert len(completes) == 1
    assert completes[0]["data"]["ok"] is False
    assert "local_target_dir" in str(completes[0]["data"].get("error", ""))


def test_stream_download_outputs_missing_remote_job_dir() -> None:
    service = _make_service()
    payload: dict[str, object] = {
        "host": "server",
        "port": 22,
        "username": "tester",
        "password": "",
        "key_path": "",
        "workspace": "~/mri-remote-jobs",
        "remote_python": "python3",
        "local_target_dir": "/tmp/outputs",
    }
    events = _collect_events(service, payload)

    completes = [e for e in events if e.get("event") == "complete"]
    assert len(completes) == 1
    assert completes[0]["data"]["ok"] is False
    assert "remote_job_dir" in str(completes[0]["data"].get("error", ""))


def test_stream_download_outputs_with_download_subdir() -> None:
    service = _make_service()
    payload: dict[str, object] = {
        "host": "server",
        "port": 22,
        "username": "tester",
        "password": "",
        "key_path": "",
        "workspace": "~/mri-remote-jobs",
        "remote_python": "python3",
        "remote_job_dir": "/home/tester/mri-remote-jobs/job_123",
        "remote_output_dir": "/home/tester/mri-remote-jobs/job_123/outputs",
        "local_target_dir": "/tmp/outputs",
        "download_subdir": "batch_456",
    }
    events = _collect_events(service, payload)

    completes = [e for e in events if e.get("event") == "complete"]
    assert len(completes) == 1
    assert completes[0]["data"]["ok"] is True
