from __future__ import annotations

import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SSHKeyInspection:
    key_path: str
    exists: bool = False
    is_file: bool = False
    mode: int = 0
    is_too_open: bool = False
    is_wsl_windows_mount: bool = False
    error_message: str = ""
    warning_message: str = ""


class PreparedSSHKey:
    def __init__(
        self,
        key_path: str,
        original_key_path: str,
        warning: str = "",
        temp_dir: tempfile.TemporaryDirectory | None = None,
    ) -> None:
        self.key_path = key_path
        self.original_key_path = original_key_path
        self.warning = warning
        self._temp_dir = temp_dir

    def cleanup(self) -> None:
        if self._temp_dir is not None:
            try:
                self._temp_dir.cleanup()
            except OSError:
                pass
            self._temp_dir = None

    def __enter__(self) -> "PreparedSSHKey":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()


def _is_wsl() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True
    try:
        proc_ver = Path("/proc/version").read_text(encoding="utf-8", errors="replace").lower()
        return "microsoft" in proc_ver or "wsl" in proc_ver
    except OSError:
        return False


def _is_wsl_windows_mount(path: Path) -> bool:
    if not _is_wsl():
        return False
    try:
        parts = path.resolve().parts
    except OSError:
        parts = path.parts
    # Check if path starts with /mnt/<letter>/
    if len(parts) >= 3 and parts[1] == "mnt" and len(parts[2]) == 1 and parts[2].isalpha():
        return True
    return False


def inspect_ssh_key(key_path: str) -> SSHKeyInspection:
    if not key_path:
        return SSHKeyInspection(key_path="")
    path = Path(key_path).expanduser()
    if not path.exists():
        return SSHKeyInspection(
            key_path=key_path,
            exists=False,
            error_message=f"SSH key file was not found: {key_path}",
        )
    if not path.is_file():
        return SSHKeyInspection(
            key_path=key_path,
            exists=True,
            is_file=False,
            error_message=f"SSH key path is not a regular file: {key_path}",
        )
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        return SSHKeyInspection(
            key_path=key_path,
            exists=True,
            is_file=True,
            error_message=f"SSH key access error: {exc}",
        )

    is_too_open = bool(mode & 0o077)
    is_wsl_mount = _is_wsl_windows_mount(path)

    error_message = ""
    warning_message = ""

    if is_too_open:
        if is_wsl_mount:
            warning_message = (
                "SSH key is on a Windows-mounted WSL path; "
                "NeuroFlow uses a temporary secure Linux copy for this connection."
            )
        else:
            error_message = (
                f"SSH key file permissions are too open ({mode:04o}). "
                "Copy the key into the Linux filesystem, run chmod 600 on it, then use that path."
            )

    return SSHKeyInspection(
        key_path=key_path,
        exists=True,
        is_file=True,
        mode=mode,
        is_too_open=is_too_open,
        is_wsl_windows_mount=is_wsl_mount,
        error_message=error_message,
        warning_message=warning_message,
    )


def prepare_ssh_key_for_paramiko(key_path: str) -> PreparedSSHKey:
    if not key_path:
        return PreparedSSHKey(key_path="", original_key_path="")
    inspection = inspect_ssh_key(key_path)
    if inspection.error_message:
        raise ValueError(inspection.error_message)

    path = Path(key_path).expanduser()

    if inspection.is_too_open and inspection.is_wsl_windows_mount:
        # Create a secure temp directory in Linux filesystem
        temp_dir = tempfile.TemporaryDirectory(prefix="mri_ssh_key_")
        temp_dir_path = Path(temp_dir.name)
        try:
            temp_dir_path.chmod(0o700)
            target_key_file = temp_dir_path / path.name
            key_bytes = path.read_bytes()
            target_key_file.write_bytes(key_bytes)
            target_key_file.chmod(0o600)
            return PreparedSSHKey(
                key_path=str(target_key_file),
                original_key_path=key_path,
                warning=inspection.warning_message,
                temp_dir=temp_dir,
            )
        except Exception:
            temp_dir.cleanup()
            raise

    return PreparedSSHKey(
        key_path=str(path),
        original_key_path=key_path,
        warning=inspection.warning_message,
        temp_dir=None,
    )
