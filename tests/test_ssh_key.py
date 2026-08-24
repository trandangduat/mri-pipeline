from __future__ import annotations

import os
import stat
from pathlib import Path
import pytest

from remote.ssh_key import (
    SSHKeyInspection,
    inspect_ssh_key,
    prepare_ssh_key_for_paramiko,
    _is_wsl_windows_mount,
)


def test_inspect_ssh_key_empty() -> None:
    inspection = inspect_ssh_key("")
    assert inspection.exists is False
    assert inspection.error_message == ""
    assert inspection.warning_message == ""


def test_inspect_ssh_key_missing() -> None:
    inspection = inspect_ssh_key("/nonexistent/path/to/key")
    assert inspection.exists is False
    assert "not found" in inspection.error_message


def test_inspect_ssh_key_valid_linux_permissions(tmp_path: Path) -> None:
    key_file = tmp_path / "id_rsa"
    key_file.write_text("private-key-content", encoding="utf-8")
    key_file.chmod(0o600)

    inspection = inspect_ssh_key(str(key_file))
    assert inspection.exists is True
    assert inspection.is_too_open is False
    assert inspection.error_message == ""
    assert inspection.warning_message == ""


def test_inspect_ssh_key_too_open_linux_permissions(tmp_path: Path) -> None:
    key_file = tmp_path / "id_rsa"
    key_file.write_text("private-key-content", encoding="utf-8")
    key_file.chmod(0o777)

    # Standard Linux path (not /mnt/c/...)
    inspection = inspect_ssh_key(str(key_file))
    assert inspection.exists is True
    assert inspection.is_too_open is True
    assert "permissions are too open" in inspection.error_message


def test_inspect_ssh_key_allows_windows_permissions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key_file = tmp_path / "id_rsa"
    key_file.write_text("private-key-content", encoding="utf-8")
    key_file.chmod(0o777)

    monkeypatch.setattr("remote.ssh_key._uses_posix_key_permissions", lambda: False)

    inspection = inspect_ssh_key(str(key_file))
    assert inspection.exists is True
    assert inspection.is_too_open is False
    assert inspection.error_message == ""
    assert inspection.warning_message == ""


def test_is_wsl_windows_mount() -> None:
    path_wsl = Path("/mnt/c/Users/ADMIN/.ssh/duat")
    path_linux = Path("/home/user/.ssh/id_rsa")

    # Force WSL check true for test
    os.environ["WSL_DISTRO_NAME"] = "Ubuntu"
    try:
        assert _is_wsl_windows_mount(path_wsl) is True
        assert _is_wsl_windows_mount(path_linux) is False
    finally:
        os.environ.pop("WSL_DISTRO_NAME", None)


def test_inspect_ssh_key_wsl_windows_mount(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key_file = tmp_path / "duat"
    key_file.write_text("private-key-content", encoding="utf-8")
    key_file.chmod(0o777)

    monkeypatch.setattr("remote.ssh_key._is_wsl_windows_mount", lambda _p: True)

    inspection = inspect_ssh_key(str(key_file))
    assert inspection.exists is True
    assert inspection.is_too_open is True
    assert inspection.error_message == ""
    assert inspection.warning_message == ""


def test_prepare_ssh_key_wsl_copies_to_secure_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    key_file = tmp_path / "duat"
    key_file.write_text("private-key-content", encoding="utf-8")
    key_file.chmod(0o777)

    monkeypatch.setattr("remote.ssh_key._is_wsl_windows_mount", lambda _p: True)

    prepared = prepare_ssh_key_for_paramiko(str(key_file))
    try:
        assert prepared.key_path != str(key_file)
        assert Path(prepared.key_path).exists()
        assert Path(prepared.key_path).read_text(encoding="utf-8") == "private-key-content"
        mode = stat.S_IMODE(Path(prepared.key_path).stat().st_mode)
        assert prepared.warning == ""
    finally:
        prepared.cleanup()

    assert not Path(prepared.key_path).exists()
