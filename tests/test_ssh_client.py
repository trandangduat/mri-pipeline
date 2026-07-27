from __future__ import annotations

import stat
from dataclasses import dataclass

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
