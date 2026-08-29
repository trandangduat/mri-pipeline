from __future__ import annotations

import json
import posixpath
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from remote.remote_runner import RemoteRunConfig, RemoteRunner
from remote.ssh_client import RemoteSSHClient, SSHConfig


class DummyStat:
    def __init__(self, st_size: int):
        self.st_size = st_size


def test_local_code_signature_ignores_atlas_files(monkeypatch, tmp_path):
    # Setup dummy project root with code and atlas
    fake_project = tmp_path / "project"
    fake_project.mkdir()
    (fake_project / "pipeline_runner.py").write_text("print('hello')", encoding="utf-8")
    pipeline_dir = fake_project / "pipeline"
    pipeline_dir.mkdir()
    (pipeline_dir / "worker.py").write_text("def run(): pass", encoding="utf-8")
    
    atlas_dir = fake_project / "assets" / "atlases" / "surface"
    atlas_dir.mkdir(parents=True)
    (atlas_dir / "lh.atlas.gcs").write_bytes(b"atlas data 1")

    import remote.remote_runner as rr
    monkeypatch.setattr(rr, "PROJECT_ROOT", fake_project)
    monkeypatch.setattr(rr, "_neuroflow_source_dir", lambda: None)

    runner = RemoteRunner(RemoteRunConfig(ssh=SSHConfig(host="localhost")))
    sig1 = runner._local_code_signature()

    # Modify atlas file -> signature must stay identical
    (atlas_dir / "lh.atlas.gcs").write_bytes(b"atlas data modified with 100MB of data")
    (atlas_dir / "new_atlas.annot").write_bytes(b"another atlas")
    sig2 = runner._local_code_signature()
    assert sig1 == sig2

    # Modify python code -> signature must change
    (pipeline_dir / "worker.py").write_text("def run(): print('changed')", encoding="utf-8")
    sig3 = runner._local_code_signature()
    assert sig1 != sig3


def test_upload_dir_skips_matching_size_files(tmp_path):
    local_dir = tmp_path / "local_atlas"
    local_dir.mkdir()
    file_same = local_dir / "same.gcs"
    file_same.write_bytes(b"12345")
    file_diff = local_dir / "diff.gcs"
    file_diff.write_bytes(b"12345678")

    client = RemoteSSHClient(SSHConfig(host="localhost"))
    mock_sftp = MagicMock()
    
    def fake_stat(remote_path):
        if "same.gcs" in remote_path:
            return DummyStat(st_size=5)
        elif "diff.gcs" in remote_path:
            return DummyStat(st_size=999)
        raise OSError("File not found")

    mock_sftp.stat.side_effect = fake_stat
    client._sftp = mock_sftp

    client.upload_dir(local_dir, "/remote/atlas", skip_existing_matching_size=True)

    # same.gcs (size 5 matches local size 5) should be skipped
    # diff.gcs (size 999 differs from local size 8) should be put
    put_calls = [call[0][1] for call in mock_sftp.put.call_args_list]
    assert any("diff.gcs" in p for p in put_calls)
    assert not any("same.gcs" in p for p in put_calls)


def test_ensure_shared_code_reads_manifest_directly_and_skips_upload(monkeypatch):
    runner = RemoteRunner(RemoteRunConfig(ssh=SSHConfig(host="localhost"), remote_workspace="/home/user/workspace"))
    sig = runner._local_code_signature()

    mock_ssh = MagicMock()
    mock_ssh.expand_path.side_effect = lambda p: p
    # Manifest returns matching signature
    manifest_content = json.dumps({"signature": sig, "updated_at": 12345.0})
    mock_ssh.read_text.return_value = (0, manifest_content)

    upload_mock = MagicMock()
    monkeypatch.setattr(runner, "_upload_code", upload_mock)

    remote_code = runner._ensure_shared_code(mock_ssh)
    assert remote_code == "/home/user/workspace/code"
    upload_mock.assert_not_called()


def test_ensure_shared_code_uploads_when_manifest_mismatches(monkeypatch):
    runner = RemoteRunner(RemoteRunConfig(ssh=SSHConfig(host="localhost"), remote_workspace="/home/user/workspace"))
    
    mock_ssh = MagicMock()
    mock_ssh.expand_path.side_effect = lambda p: p
    # Manifest returns different signature
    manifest_content = json.dumps({"signature": "old_signature_123", "updated_at": 12345.0})
    mock_ssh.read_text.return_value = (0, manifest_content)

    upload_mock = MagicMock()
    monkeypatch.setattr(runner, "_upload_code", upload_mock)

    remote_code = runner._ensure_shared_code(mock_ssh)
    assert remote_code == "/home/user/workspace/code"
    upload_mock.assert_called_once_with(mock_ssh, "/home/user/workspace/code")
    mock_ssh.write_text_file.assert_called_once()
