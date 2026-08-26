from __future__ import annotations

import stat
from dataclasses import dataclass
from unittest.mock import MagicMock

from remote.ssh_client import RemoteSSHClient, SSHConfig


@dataclass
class FakeSFTPAttr:
    filename: str
    st_mode: int


class FakeSFTP:
    def __init__(self) -> None:
        self.downloaded: list[tuple[str, str]] = []

    def listdir_attr(self, remote_dir: str):
        assert remote_dir == "/remote/output"
        return [
            FakeSFTPAttr("fsaverage", stat.S_IFLNK),
            FakeSFTPAttr("aseg.stats", stat.S_IFREG),
        ]

    def get(self, remote_path: str, local_path: str) -> None:
        if remote_path.endswith("/fsaverage"):
            raise FileNotFoundError(remote_path)
        self.downloaded.append((remote_path, local_path))


def test_download_dir_recursive_skips_remote_symlinks(tmp_path) -> None:
    logs: list[str] = []
    client = RemoteSSHClient(SSHConfig(host="example"), logs.append)
    fake_sftp = FakeSFTP()
    client._sftp = fake_sftp

    client.download_dir("/remote/output", tmp_path)

    assert fake_sftp.downloaded == [
        ("/remote/output/aseg.stats", str(tmp_path / "aseg.stats"))
    ]
    assert "Skipping symlink: /remote/output/fsaverage" in logs


def test_run_applies_command_timeout() -> None:
    client = RemoteSSHClient(SSHConfig(host="example"))
    transport = MagicMock()
    stdout = MagicMock()
    stderr = MagicMock()
    stderr.read.return_value = b""
    stdout.channel.recv_exit_status.return_value = 0
    transport.exec_command.return_value = (MagicMock(), stdout, stderr)
    client._client = transport

    assert client.run("touch /tmp/stop", stream=False, timeout=15) == 0

    transport.exec_command.assert_called_once_with("touch /tmp/stop", get_pty=False, timeout=15)
