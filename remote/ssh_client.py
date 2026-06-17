from __future__ import annotations

import os
import posixpath
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


LogCallback = Callable[[str], None]


@dataclass
class SSHConfig:
    host: str
    port: int = 22
    username: str = ""
    password: str = ""
    key_path: str = ""
    timeout: int = 15


class RemoteSSHClient:
    def __init__(self, config: SSHConfig, on_log: LogCallback | None = None) -> None:
        self.config = config
        self.on_log = on_log or (lambda _line: None)
        self._client = None
        self._sftp = None

    def __enter__(self) -> "RemoteSSHClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> None:
        try:
            import paramiko
        except ImportError as exc:
            raise RuntimeError("Missing dependency: install with `python3 -m pip install paramiko`") from exc

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs = {
            "hostname": self.config.host,
            "port": self.config.port,
            "username": self.config.username,
            "timeout": self.config.timeout,
            "banner_timeout": self.config.timeout,
            "auth_timeout": self.config.timeout,
        }
        if self.config.key_path:
            kwargs["key_filename"] = self.config.key_path
        if self.config.password:
            kwargs["password"] = self.config.password

        self.on_log(f"Connecting SSH {self.config.username}@{self.config.host}:{self.config.port}...")
        client.connect(**kwargs)
        self._client = client
        self._sftp = client.open_sftp()
        self.on_log("SSH connected.")

    def close(self) -> None:
        if self._sftp:
            self._sftp.close()
            self._sftp = None
        if self._client:
            self._client.close()
            self._client = None

    @property
    def client(self):
        if self._client is None:
            raise RuntimeError("SSH client is not connected")
        return self._client

    @property
    def sftp(self):
        if self._sftp is None:
            raise RuntimeError("SFTP client is not connected")
        return self._sftp

    def run(self, command: str, stream: bool = True, check: bool = False) -> int:
        self.on_log(f">>> {command}")
        stdin, stdout, stderr = self.client.exec_command(command, get_pty=True)
        if stream:
            for line in iter(stdout.readline, ""):
                if line:
                    self.on_log(line.rstrip())
        err_text = stderr.read().decode(errors="replace").strip()
        if err_text:
            for line in err_text.splitlines():
                self.on_log(line)
        code = stdout.channel.recv_exit_status()
        self.on_log(f"<<< exit {code}")
        if check and code != 0:
            raise RuntimeError(f"Remote command failed with exit code {code}: {command}")
        return code

    def read_text(self, command: str) -> tuple[int, str]:
        stdin, stdout, stderr = self.client.exec_command(command)
        text = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        code = stdout.channel.recv_exit_status()
        return code, text + err

    def mkdir_p(self, remote_path: str) -> None:
        parts = []
        current = self.expand_path(remote_path)
        while current not in ("", "/"):
            parts.append(current)
            current = posixpath.dirname(current)
        for path in reversed(parts):
            try:
                self.sftp.stat(path)
            except OSError:
                self.sftp.mkdir(path)

    def expand_path(self, remote_path: str) -> str:
        if remote_path.startswith("~/") or remote_path == "~":
            code, home = self.read_text("printf %s \"$HOME\"")
            if code == 0 and home.strip():
                return remote_path.replace("~", home.strip(), 1)
        return remote_path

    def upload_file(self, local_path: str | Path, remote_path: str) -> None:
        local = Path(local_path)
        remote_path = self.expand_path(remote_path)
        self.mkdir_p(posixpath.dirname(remote_path))
        self.on_log(f"Uploading file: {local} -> {remote_path}")
        self.sftp.put(str(local), remote_path)

    def upload_dir(self, local_dir: str | Path, remote_dir: str, skip_dirs: set[str] | None = None) -> None:
        local_root = Path(local_dir)
        remote_root = self.expand_path(remote_dir)
        skip_dirs = skip_dirs or set()
        self.mkdir_p(remote_root)
        for root, dirs, files in os.walk(local_root):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            rel = Path(root).relative_to(local_root)
            remote_subdir = remote_root if str(rel) == "." else posixpath.join(remote_root, rel.as_posix())
            self.mkdir_p(remote_subdir)
            for name in files:
                local_file = Path(root) / name
                remote_file = posixpath.join(remote_subdir, name)
                self.sftp.put(str(local_file), remote_file)

    def download_dir(self, remote_dir: str, local_dir: str | Path) -> None:
        remote_dir = self.expand_path(remote_dir)
        local_root = Path(local_dir)
        local_root.mkdir(parents=True, exist_ok=True)
        self._download_dir_recursive(remote_dir, local_root)

    def _download_dir_recursive(self, remote_dir: str, local_dir: Path) -> None:
        local_dir.mkdir(parents=True, exist_ok=True)
        for item in self.sftp.listdir_attr(remote_dir):
            remote_path = posixpath.join(remote_dir, item.filename)
            local_path = local_dir / item.filename
            if stat.S_ISDIR(item.st_mode):
                self._download_dir_recursive(remote_path, local_path)
            else:
                self.on_log(f"Downloading file: {remote_path} -> {local_path}")
                self.sftp.get(remote_path, str(local_path))
