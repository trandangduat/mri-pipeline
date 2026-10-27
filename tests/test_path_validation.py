from __future__ import annotations

from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from pipeline.path_validation import validate_input_paths, validate_writable_directory
from remote.remote_runner import RemoteRunConfig, RemoteRunner
from remote.ssh_client import SSHConfig


@pytest.mark.parametrize("mode", ["file", "files", "dir"])
def test_missing_input_is_rejected_in_each_mode(tmp_path, mode):
    missing = str(tmp_path / "missing.nii.gz")
    with pytest.raises(ValueError, match="does not exist"):
        validate_input_paths(mode, missing, [missing] if mode == "files" else [])


def test_batch_checks_every_selected_file_and_not_unselected_files(tmp_path):
    good = tmp_path / "good.nii.gz"
    good.write_bytes(b"volume")
    validate_input_paths("dir", str(tmp_path / "irrelevant-root"), [str(good)])
    with pytest.raises(ValueError, match="missing.nii.gz"):
        validate_input_paths("files", str(tmp_path), [str(good), str(tmp_path / "missing.nii.gz")])


@pytest.mark.parametrize("mode", ["file", "files", "dir"])
def test_dicom_inputs_are_accepted(tmp_path, mode):
    series = tmp_path / "series"
    series.mkdir()
    (series / "001.dcm").write_bytes(b"dicom")
    validate_input_paths(mode, str(series), [str(series)] if mode == "files" else [])
    validate_input_paths("file", str(series / "001.dcm"), [])


def test_dicom_without_extension_is_accepted(tmp_path):
    series = tmp_path / "series"
    series.mkdir()
    (series / "001").write_bytes(b"\0" * 128 + b"DICM")
    validate_input_paths("file", str(series), [])


def test_batch_uses_the_worker_recursion_rules(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    (nested / "scan.nii.gz").write_bytes(b"volume")
    with pytest.raises(ValueError, match="No MRI files"):
        validate_input_paths("dir", str(tmp_path), [], recursive=False)
    validate_input_paths("dir", str(tmp_path), [], recursive=True)


def test_single_rejects_directory_of_nifti_files(tmp_path):
    (tmp_path / "scan.nii.gz").write_bytes(b"volume")
    with pytest.raises(ValueError, match="MRI file or DICOM folder"):
        validate_input_paths("file", str(tmp_path), [])


def test_existing_unreadable_file_is_rejected(tmp_path, monkeypatch):
    image = tmp_path / "scan.nii.gz"
    image.write_bytes(b"volume")
    original = Path.open
    def open_file(path, *args, **kwargs):
        if path == image:
            raise PermissionError("permission denied")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", open_file)
    with pytest.raises(ValueError, match="Cannot read input.*scan.nii.gz"):
        validate_input_paths("file", str(image), [])


def test_unreadable_batch_directory_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.path_validation.os.access", lambda *_: False)
    with pytest.raises(ValueError, match="Cannot read input folder"):
        validate_input_paths("dir", str(tmp_path), [])


def test_output_probe_does_not_create_output_tree_or_leave_files(tmp_path):
    target = tmp_path / "new" / "output"
    validate_writable_directory(str(target))
    assert list(tmp_path.iterdir()) == []


def test_output_probe_rejects_a_file_in_the_parent_chain(tmp_path):
    parent = tmp_path / "file"
    parent.write_bytes(b"data")
    with pytest.raises(ValueError, match="not a directory"):
        validate_writable_directory(str(parent / "output"))


def test_unwritable_output_is_rejected(tmp_path, monkeypatch):
    def denied(**kwargs):
        raise PermissionError("permission denied")
    monkeypatch.setattr("pipeline.path_validation.tempfile.TemporaryFile", denied)
    with pytest.raises(ValueError, match="Cannot write output directory"):
        validate_writable_directory(str(tmp_path))


@pytest.mark.skipif(sys.platform == "win32", reason="Remote worker uses Linux")
@pytest.mark.parametrize("case", ["valid", "missing", "batch_missing", "empty_batch", "upload", "bad_output", "bad_staging", "large_batch"])
def test_remote_path_probe_executes_shared_validator(tmp_path, monkeypatch, case):
    from pipeline.config import SOURCE_ROOT
    image = tmp_path / "scan; literal ' name.nii.gz"
    image.write_bytes(b"volume")
    source = str(image) if case != "missing" else str(tmp_path / "missing.nii.gz")
    output = str(image) if case == "bad_output" else str(tmp_path / "new-output")
    staging = str(image) if case == "bad_staging" else str(tmp_path / "new-staging")
    empty = tmp_path / "empty"
    empty.mkdir()
    class SSH:
        def __init__(self, *_args):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            pass
        def expand_path(self, value):
            return value
        def read_text(self, command, timeout=None, input_text=None):
            assert timeout == 35
            assert "literal" not in command
            outer = shlex.split(command)
            assert outer[:3] == ["cd", str(SOURCE_ROOT), "&&"]
            args = shlex.split(outer[-1])
            result = subprocess.run(args, cwd=SOURCE_ROOT, input=input_text, capture_output=True, text=True, timeout=timeout)
            return result.returncode, result.stdout + result.stderr
    monkeypatch.setattr("remote.remote_runner.RemoteSSHClient", SSH)
    monkeypatch.setattr(RemoteRunner, "_remote_code_dir", lambda *_: str(SOURCE_ROOT))
    monkeypatch.setattr(RemoteRunner, "_remote_venv_python", lambda *_: sys.executable)
    config = RemoteRunConfig(ssh=SSHConfig(host="test", username="test"), input_file=source,
        server_output_dir=output, input_server_dir=staging,
        input_source="Local" if case in {"upload", "bad_staging"} else "Server")
    if case in {"batch_missing", "empty_batch"}:
        config.input_mode = "dir"
        config.input_dir = str(empty)
        config.input_files = [str(image), str(tmp_path / "missing.nii.gz")] if case == "batch_missing" else []
    if case == "large_batch":
        config.input_mode = "files"
        config.input_files = [str(image)] * 2000
    if case == "upload":
        config.input_file = "/local-only/does-not-exist-on-server.nii.gz"
    runner = RemoteRunner(config)
    if case in {"valid", "upload", "large_batch"}:
        runner.validate_paths()
    else:
        with pytest.raises(RuntimeError):
            runner.validate_paths()
    assert not Path(staging).is_dir()
    assert not Path(output).is_dir()


@pytest.mark.parametrize("result", [(1, ""), (0, "invalid JSON"), (0, '{"ok": false}'), (1, '{"ok": true}')])
def test_remote_probe_never_accepts_failed_or_invalid_response(monkeypatch, result):
    class SSH:
        def __init__(self, *_args):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            pass
        def expand_path(self, value):
            return value
        def read_text(self, *_args, **_kwargs):
            return result
    monkeypatch.setattr("remote.remote_runner.RemoteSSHClient", SSH)
    runner = RemoteRunner(RemoteRunConfig(ssh=SSHConfig(host="test", username="test"), remote_workspace="/workspace"))
    with pytest.raises(RuntimeError):
        runner.validate_paths()


def test_remote_path_probe_timeout_is_not_accepted(monkeypatch):
    class SSH:
        def __init__(self, *_args):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            pass
        def expand_path(self, value):
            return value
        def read_text(self, *_args, **_kwargs):
            raise TimeoutError("Path validation timed out")
    monkeypatch.setattr("remote.remote_runner.RemoteSSHClient", SSH)
    runner = RemoteRunner(RemoteRunConfig(ssh=SSHConfig(host="test", username="test"), remote_workspace="/workspace"))
    with pytest.raises(TimeoutError):
        runner.validate_paths()
