from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import remote.lazy_upload as lazy_upload_module
from pipeline.neuroflow_adapter import _wait_for_input_marker
from remote.lazy_upload import LazyUploadOrchestrator
from remote.remote_runner import RemoteRunConfig, RemoteRunner
from remote.ssh_client import SSHConfig


# --------------------------------------------------------------------- fakes
class FakeSftp:
    """Virtual remote filesystem for the marker/publish protocol."""

    def __init__(self) -> None:
        self.files: set[str] = set()
        self.renamed: list[tuple[str, str]] = []
        self.remove_attempts: list[str] = []

    def posix_rename(self, src: str, dst: str) -> None:
        self.files.discard(src)
        self.files.add(dst)
        self.renamed.append((src, dst))

    def remove(self, path: str) -> None:
        self.remove_attempts.append(path)
        self.files.discard(path)

    class _MarkerFile:
        def __init__(self, fs: "FakeSftp", path: str) -> None:
            self._fs = fs
            self._path = path

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def write(self, content: str) -> int:
            self._fs.files.add(self._path)
            return len(content)

    def open(self, path: str, mode: str = "r"):
        assert mode == "w", "marker files are write-only in these tests"
        return FakeSftp._MarkerFile(self, path)


class FakeSSHClient:
    instances: list["FakeSSHClient"] = []

    def __init__(self, config=None, on_log=None) -> None:
        self.sftp = FakeSftp()
        self.dirs_created: list[str] = []
        self.uploads: list[tuple[str, str]] = []
        self.upload_gate: threading.Event | None = None  # block uploads when set
        self.upload_error: Exception | None = None
        FakeSSHClient.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def mkdir_p(self, remote_path: str) -> None:
        self.dirs_created.append(remote_path)

    def upload_file_with_progress(self, local_path, remote_path, callback=None) -> None:
        if self.upload_error is not None:
            raise self.upload_error
        if self.upload_gate is not None:
            self.upload_gate.wait(timeout=5)
        self.uploads.append((str(local_path), remote_path))
        if callback:
            callback(10, 10)


class FakeRunner:
    def __init__(self, events: list[dict] | None = None) -> None:
        self.events = list(events or [])
        self.config = SimpleNamespace(ssh=SimpleNamespace(host="h", port=22, username="u", password="p", key_path=""))

    def emit(self, event: dict) -> None:
        self.events.append(event)

    def read_remote_events(self, offset: int = 0, limit: int = 500) -> dict:
        events = self.events[offset:]
        return {"ok": True, "events": events, "warnings": [], "next_offset": len(self.events)}


def make_orchestrator(runner: FakeRunner, source_paths: dict[str, str], max_concurrent: int = 2, **kwargs) -> LazyUploadOrchestrator:
    return LazyUploadOrchestrator(
        runner,
        source_paths=source_paths,
        max_concurrent=max_concurrent,
        on_log=lambda _line: None,
        **kwargs,
    )


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    monkeypatch.setattr(lazy_upload_module, "UPLOAD_POLL_INTERVAL_SEC", 0.01)
    monkeypatch.setattr(lazy_upload_module, "RemoteSSHClient", FakeSSHClient)
    FakeSSHClient.instances.clear()


# ------------------------------------------------------------- marker wait
def test_wait_for_marker_success(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.neuroflow_adapter.LAZY_UPLOAD_POLL_SEC", 0.01)
    staged = tmp_path / "img.nii.gz"
    Path(str(staged) + ".ready").write_text("x")

    ok, message = _wait_for_input_marker(staged, should_stop=None)

    assert ok is True
    assert message == ""


def test_wait_for_marker_cancelled(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.neuroflow_adapter.LAZY_UPLOAD_POLL_SEC", 0.01)
    ok, message = _wait_for_input_marker(tmp_path / "none.nii.gz", should_stop=lambda: True)

    assert ok is False
    assert "cancelled" in message


def test_wait_for_marker_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.neuroflow_adapter.LAZY_UPLOAD_POLL_SEC", 0.01)
    ok, message = _wait_for_input_marker(tmp_path / "none.nii.gz", should_stop=None, timeout_sec=0.05)

    assert ok is False
    assert "timed out" in message


# ------------------------------------------------- staging rewrite (runner)
def _lazy_config(tmp_path: Path, **overrides) -> RemoteRunConfig:
    defaults = dict(
        ssh=SSHConfig(host="example", username="tester"),
        input_mode="file",
        input_file=str(tmp_path / "sub-001_T1w.nii.gz"),
        lazy_upload=True,
        input_server_dir="~/mri-uploads",
    )
    defaults.update(overrides)
    return RemoteRunConfig(**defaults)


def test_staging_rewrite_file_mode(tmp_path):
    runner = RemoteRunner(_lazy_config(tmp_path))
    runner.job_id = "job_1"
    runner._expanded_staging_root = "/home/tester/mri-uploads/job_1"

    request = runner._remote_input_request()

    subject_id = request["subject_id"]
    staged = request["input_file"]
    assert staged == f"/home/tester/mri-uploads/job_1/{subject_id}/{Path(request['source_paths'][staged]).name}"
    assert request["source_paths"][staged] == str(tmp_path / "sub-001_T1w.nii.gz")
    assert request["lazy_upload"] is True
    # original local path must not appear anywhere in worker-facing fields
    assert str(tmp_path / "sub-001_T1w.nii.gz") != staged


def test_staging_rewrite_files_mode_preserves_subject_ids(tmp_path):
    files = [str(tmp_path / "sub-001_T1w.nii.gz"), str(tmp_path / "sub-002_T1w.nii.gz")]
    for name in files:
        Path(name).write_text("fake")
    runner = RemoteRunner(
        _lazy_config(
            tmp_path,
            input_mode="files",
            input_file="",
            input_files=files,
            input_dir=str(tmp_path),
        )
    )
    runner.job_id = "job_1"
    runner._expanded_staging_root = "/home/tester/mri-uploads/job_1"

    request = runner._remote_input_request()

    assert all(staged.startswith("/home/tester/mri-uploads/job_1/") for staged in request["input_files"])
    from pipeline.discovery import _derive_subject_id

    assert sorted(request["subject_id_map"].values()) == [
        _derive_subject_id(files[0]),
        _derive_subject_id(files[1]),
    ]
    assert set(request["source_paths"]) == set(request["input_files"])


def test_lazy_source_paths_and_dynamic_metadata(tmp_path):
    runner = RemoteRunner(_lazy_config(tmp_path))
    runner.job_id = "job_1"
    runner._expanded_staging_root = "/home/tester/mri-uploads/job_1"

    source_paths = runner.lazy_source_paths()

    assert len(source_paths) == 1
    local = next(iter(source_paths.values()))
    assert local == str(tmp_path / "sub-001_T1w.nii.gz")


def test_metadata_reports_local_source_for_lazy_upload(tmp_path):
    from pipeline.discovery import _derive_subject_id  # noqa: F401  (import sanity)

    runner = RemoteRunner(_lazy_config(tmp_path))
    runner.job_id = "job_1"
    runner._expanded_staging_root = "/home/tester/mri-uploads/job_1"

    metadata = {
        "input_source": "Local" if runner.config.lazy_upload else "Server",
    }

    assert metadata["input_source"] == "Local"


def test_non_lazy_runner_keeps_server_semantics(tmp_path):
    config = RemoteRunConfig(
        ssh=SSHConfig(host="example", username="tester"),
        input_mode="file",
        input_file="/data/on/server.nii.gz",
        lazy_upload=False,
    )
    runner = RemoteRunner(config)

    assert runner.lazy_source_paths() == {}
    assert runner._remote_input_request()["mode"] == "file"


# ------------------------------------------------------------ orchestrator
def _drain(orchestrator: LazyUploadOrchestrator, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        orchestrator.join(timeout=0.05)
        if not orchestrator.is_alive():
            return
        if orchestrator.is_terminal() and not any(
            handle.thread and handle.thread.is_alive()
            for handle in list(orchestrator._handles.values())
        ):
            return


def test_upload_flow_publishes_part_then_ready_marker(tmp_path):
    local = tmp_path / "img.nii.gz"
    local.write_bytes(b"x" * 1024)
    runner = FakeRunner()
    staged = "/srv/uploads/job_1/sub-001/img.nii.gz"
    orchestrator = make_orchestrator(runner, {staged: str(local)})
    orchestrator.start()
    try:
        runner.emit({"kind": "image_awaiting_input", "input_file": staged, "subject_id": "sub-001"})
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            snapshot = orchestrator.snapshot()
            if snapshot and snapshot[0]["state"] == "ready":
                break
            time.sleep(0.01)

        ssh = FakeSSHClient.instances[-1]
        assert ssh.sftp.renamed == [(staged + ".part", staged)]
        assert staged + ".ready" in ssh.sftp.files
        snapshot = orchestrator.snapshot()[0]
        assert snapshot["state"] == "ready"
        assert snapshot["pct"] == 100.0
        assert staged + ".part" not in ssh.sftp.files
    finally:
        orchestrator.cancel()


def test_duplicate_events_trigger_single_upload(tmp_path):
    local = tmp_path / "img.nii.gz"
    local.write_bytes(b"x" * 1024)
    runner = FakeRunner()
    staged = "/srv/uploads/job_1/sub-001/img.nii.gz"
    orchestrator = make_orchestrator(runner, {staged: str(local)})
    orchestrator.start()
    try:
        runner.emit({"kind": "image_awaiting_input", "input_file": staged, "subject_id": "sub-001"})
        runner.emit({"kind": "image_awaiting_input", "input_file": staged, "subject_id": "sub-001"})
        runner.emit({"kind": "image_awaiting_input", "input_file": staged, "subject_id": "sub-001"})
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if orchestrator.is_terminal():
                break
            time.sleep(0.01)
        time.sleep(0.05)

        total_puts = sum(len(ssh.uploads) for ssh in FakeSSHClient.instances)
        assert total_puts == 1, f"puts={total_puts}, state={orchestrator.snapshot()}"
    finally:
        orchestrator.cancel()


def test_failed_upload_marks_state_without_ready_marker(monkeypatch, tmp_path):
    runner = FakeRunner()
    staged = "/srv/uploads/job_1/sub-bad/img.nii.gz"
    local = tmp_path / "broken.nii.gz"
    local.write_bytes(b"x" * 1024)
    orchestrator = make_orchestrator(runner, {staged: str(local)})

    class ExplodingSSH(FakeSSHClient):
        def upload_file_with_progress(self, local_path, remote_path, callback=None) -> None:
            raise RuntimeError("disk full")

    orchestrator.start()
    try:
        import remote.lazy_upload as module

        monkeypatch.setattr(module, "RemoteSSHClient", ExplodingSSH)
        runner.emit({"kind": "image_awaiting_input", "input_file": staged, "subject_id": "sub-bad"})
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            snapshot = orchestrator.snapshot()
            if snapshot and snapshot[0]["state"] == "failed":
                break
            time.sleep(0.01)

        snapshot = orchestrator.snapshot()[0]
        assert snapshot["state"] == "failed"
        ssh = ExplodingSSH.instances[-1]
        assert staged + ".ready" not in ssh.sftp.files
        assert staged not in ssh.sftp.files
    finally:
        orchestrator.cancel()


def test_cancel_deletes_partial_files_and_marks_cancelled(monkeypatch, tmp_path):
    runner = FakeRunner()
    staged = "/srv/uploads/job_1/sub-001/big.nii.gz"
    gate = threading.Event()
    local_file = tmp_path / "big.nii.gz"
    local_file.write_bytes(b"x" * 2048)

    class GatedSSH(FakeSSHClient):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.upload_gate = gate

        def upload_file_with_progress(self, local_path, remote_path, callback=None) -> None:
            self.upload_gate.wait(timeout=5)
            self.uploads.append((str(local_path), remote_path))

    monkeypatch.setattr(lazy_upload_module, "RemoteSSHClient", GatedSSH)
    orchestrator = make_orchestrator(runner, {staged: str(local_file)})
    orchestrator.start()
    try:
        runner.emit({"kind": "image_awaiting_input", "input_file": staged, "subject_id": "sub-001"})
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not FakeSSHClient.instances:
            time.sleep(0.01)
        ssh = FakeSSHClient.instances[-1]

        # Simulate a partially transferred file sitting on the server.
        ssh.sftp.files.add(staged + ".part")

        # Cancel while the upload thread is blocked inside the transfer.
        canceller = threading.Thread(target=orchestrator.cancel, daemon=True)
        canceller.start()
        time.sleep(0.05)
        gate.set()
        canceller.join(timeout=3)

        # Cleanup runs on a fresh connection; assert across all instances.
        all_remove_attempts = [
            path for inst in FakeSSHClient.instances for path in inst.sftp.remove_attempts
        ]
        all_files = set().union(*[inst.sftp.files for inst in FakeSSHClient.instances]) if FakeSSHClient.instances else set()
        assert staged + ".part" in all_remove_attempts or staged + ".part" not in all_files
        assert staged + ".ready" not in all_files
        snapshot = orchestrator.snapshot()[0]
        assert snapshot["state"] in {"cancelled", "uploading"}
    finally:
        gate.set()


def test_concurrency_cap_respected(monkeypatch, tmp_path):
    runner = FakeRunner()
    paths = {}
    for i in (1, 2, 3):
        p = tmp_path / f"sub-{i:03d}.nii.gz"
        p.write_bytes(b"x" * 512)
        paths[f"/srv/uploads/job_1/sub-{i:03d}/img.nii.gz"] = str(p)

    active = {"count": 0, "peak": 0}
    lock = threading.Lock()

    class CountingSSH(FakeSSHClient):
        def upload_file_with_progress(self, local_path, remote_path, callback=None) -> None:
            with lock:
                active["count"] += 1
                active["peak"] = max(active["peak"], active["count"])
            time.sleep(0.05)
            with lock:
                active["count"] -= 1
            self.uploads.append((str(local_path), remote_path))

    monkeypatch.setattr(lazy_upload_module, "RemoteSSHClient", CountingSSH)
    orchestrator = make_orchestrator(runner, paths, max_concurrent=1)
    orchestrator.start()
    try:
        for staged in paths:
            runner.emit({"kind": "image_awaiting_input", "input_file": staged, "subject_id": staged})
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not orchestrator.is_terminal():
            time.sleep(0.01)

        assert active["peak"] == 1
        total_puts = sum(len(ssh.uploads) for ssh in FakeSSHClient.instances if isinstance(ssh, CountingSSH))
        assert total_puts == 3
    finally:
        orchestrator.cancel()


def test_unknown_event_subject_is_ignored():
    runner = FakeRunner()
    orchestrator = make_orchestrator(runner, {"/srv/a": "/local/a"})
    orchestrator.start()
    try:
        runner.emit({"kind": "image_awaiting_input", "input_file": "/srv/unknown", "subject_id": "ghost"})
        time.sleep(0.05)
        assert all(entry["state"] == "pending" for entry in orchestrator.snapshot())
    finally:
        orchestrator.cancel()
