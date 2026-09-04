from __future__ import annotations

import os
import posixpath
import random
import stat
import threading
import time
from dataclasses import dataclass

from pathlib import Path
from typing import Callable, NamedTuple


LogCallback = Callable[[str], None]

# Max concurrent SSH channels (exec + sftp) per pooled transport. OpenSSH
# defaults to MaxSessions 10; staying at 4 leaves headroom for the server-side
# session itself and hardened servers with lower limits.
MAX_CHANNELS_PER_CONNECTION = 4


class PoolKey(NamedTuple):
    host: str
    port: int
    username: str


@dataclass
class _PooledConnection:
    client: object
    semaphore: threading.BoundedSemaphore
    created_at: float
    op_count: int


def _is_transport_usable(client: object) -> bool:
    try:
        transport = getattr(client, "get_transport", lambda: None)()
    except Exception:
        return False
    if transport is None:
        return False
    try:
        if not transport.is_active():
            return False
    except Exception:
        return False
    is_auth = getattr(transport, "is_authenticated", None)
    if callable(is_auth):
        try:
            if not is_auth():
                return False
        except Exception:
            return False
    return True


class SSHConnectionPool:
    """Connection pool maintaining persistent Paramiko SSHClient instances with keepalive and recycling."""

    def __init__(self) -> None:
        self._pool: dict[PoolKey, _PooledConnection] = {}
        self._lock = threading.Lock()
        # Per-host single-flight locks: only one thread performs the TCP+auth
        # handshake for a given server at a time. Without this, N concurrent
        # API requests all miss the cache and open N connections at once,
        # tripping sshd MaxStartups ("Error reading SSH protocol banner").
        self._connect_locks: dict[PoolKey, threading.Lock] = {}

    def _connect_lock_for(self, key: PoolKey) -> threading.Lock:
        with self._lock:
            lock = self._connect_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._connect_locks[key] = lock
            return lock

    def _get_live_entry(self, key: PoolKey) -> _PooledConnection | None:
        with self._lock:
            entry = self._pool.get(key)
            if entry is None:
                return None
            # Recycle if inactive, unauthenticated, older than 1800s (30m), or executed > 300 operations
            if (
                _is_transport_usable(entry.client)
                and (time.time() - entry.created_at < 1800)
                and (entry.op_count < 300)
            ):
                entry.op_count += 1
                return entry
            self._pool.pop(key, None)
        self._cleanup_entry(entry)
        return None

    def acquire(self, config: SSHConfig, on_log: LogCallback | None = None) -> tuple[object, threading.BoundedSemaphore]:
        key = PoolKey(config.host, config.port, config.username)
        entry = self._get_live_entry(key)
        if entry is not None:
            return entry.client, entry.semaphore

        # Single-flight: concurrent threads queue here instead of each
        # opening their own TCP connection to sshd.
        connect_lock = self._connect_lock_for(key)
        with connect_lock:
            entry = self._get_live_entry(key)
            if entry is not None:
                return entry.client, entry.semaphore
            client, semaphore = self._create_connection_with_retry(config, on_log)
            with self._lock:
                self._pool.pop(key, None)
                new_entry = _PooledConnection(client, semaphore, time.time(), 1)
                self._pool[key] = new_entry
            return client, semaphore

    def _create_connection_with_retry(
        self, config: SSHConfig, on_log: LogCallback | None = None
    ) -> tuple[object, threading.BoundedSemaphore]:
        # Auth errors must fail fast; handshake/banner throttling is retried
        # with backoff so a busy sshd is not hammered by an immediate storm.
        try:
            max_attempts = max(1, int(config.connect_attempts))
        except (TypeError, ValueError):
            max_attempts = 4
        delays = (0.5, 1.5, 3.0)[: max(0, max_attempts - 1)]
        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            try:
                return self._create_connection(config, on_log)
            except Exception as exc:  # noqa: BLE001 - mapped below
                if _is_auth_failure(exc):
                    raise
                last_exc = exc
                if attempt < len(delays):
                    wait = delays[attempt] + random.uniform(0, 0.5)
                    if on_log:
                        try:
                            on_log(f"SSH connect attempt {attempt + 1} failed ({exc}); retrying in {wait:.1f}s...")
                        except Exception:
                            pass
                    time.sleep(wait)
        assert last_exc is not None
        raise last_exc

    def _create_connection(self, config: SSHConfig, on_log: LogCallback | None = None) -> tuple[object, threading.BoundedSemaphore]:
        try:
            import paramiko
        except ImportError as exc:
            raise RuntimeError("Missing dependency: install with `python3 -m pip install paramiko`") from exc

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs = {
            "hostname": config.host,
            "port": config.port,
            "username": config.username,
            "timeout": config.timeout,
            "banner_timeout": config.timeout,
            "auth_timeout": config.timeout,
        }
        prepared_key = None
        if config.key_path:
            from remote.ssh_key import prepare_ssh_key_for_paramiko
            prepared_key = prepare_ssh_key_for_paramiko(config.key_path)
            kwargs["key_filename"] = prepared_key.key_path
            if prepared_key.warning and on_log:
                on_log(prepared_key.warning)
        if config.password:
            kwargs["password"] = config.password

        if on_log:
            on_log(f"Connecting pooled SSH {config.username}@{config.host}:{config.port}...")
        try:
            client.connect(**kwargs)
        except Exception:
            if prepared_key:
                prepared_key.cleanup()
            raise

        transport = client.get_transport()
        if transport is not None:
            try:
                transport.set_keepalive(15)
            except Exception:
                pass
        semaphore = threading.BoundedSemaphore(MAX_CHANNELS_PER_CONNECTION)
        if on_log:
            on_log("SSH pooled connection established.")
        return client, semaphore

    def release(self, config: SSHConfig, client: object, sftp: object | None = None) -> None:
        pass

    def remove(self, config: SSHConfig) -> None:
        key = PoolKey(config.host, config.port, config.username)
        with self._lock:
            entry = self._pool.pop(key, None)
        if entry:
            self._cleanup_entry(entry)

    def remove_if_current(self, config: SSHConfig, client: object) -> None:
        """Evict the pooled entry only if it is still the failing client.

        Prevents one thread's transient channel error from destroying a fresh
        healthy connection created concurrently by another thread.
        """
        key = PoolKey(config.host, config.port, config.username)
        with self._lock:
            entry = self._pool.get(key)
            if entry is None or entry.client is not client:
                return
            self._pool.pop(key, None)
        self._cleanup_entry(entry)

    def close_all(self) -> None:
        with self._lock:
            items = list(self._pool.values())
            self._pool.clear()
        for entry in items:
            self._cleanup_entry(entry)

    @staticmethod
    def _cleanup_entry(entry: _PooledConnection) -> None:
        if entry.semaphore is not None and hasattr(entry.semaphore, "close"):
            try:
                getattr(entry.semaphore, "close")()
            except Exception:
                pass
        if entry.client is not None:
            try:
                getattr(entry.client, "close")()
            except Exception:
                pass


def _is_auth_failure(exc: BaseException) -> bool:
    try:
        import paramiko  # type: ignore[import-not-found]

        if isinstance(
            exc,
            (
                paramiko.AuthenticationException,
                paramiko.BadHostKeyException,
            ),
        ):
            return True
    except ImportError:
        pass
    msg = str(exc).lower()
    return "authentication failed" in msg or "bad host key" in msg


_GLOBAL_SSH_POOL = SSHConnectionPool()


def get_ssh_connection_pool() -> SSHConnectionPool:
    return _GLOBAL_SSH_POOL


@dataclass
class SSHConfig:
    host: str
    port: int = 22
    username: str = ""
    password: str = ""
    key_path: str = ""
    timeout: int = 15
    # How many TCP/SSH handshake attempts the pool makes before giving up.
    # Background ops keep 4 (with backoff); explicit connectivity probes
    # (Connect button) pass 1 so a dead route fails fast instead of
    # stacking timeouts.
    connect_attempts: int = 4


class RemoteSSHClient:
    def __init__(self, config: SSHConfig, on_log: LogCallback | None = None, use_pool: bool = True) -> None:
        self.config = config
        self.on_log = on_log or (lambda _line: None)
        self.use_pool = use_pool
        self._client = None
        self._sftp = None
        self._semaphore: threading.BoundedSemaphore | None = None
        self._prepared_key = None
        self._is_pooled = False
        self._owns_sftp_channel = False

    def __enter__(self) -> "RemoteSSHClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
        self._prepared_key = None

    def _acquire_channel_slot(self) -> None:
        if self._semaphore is not None:
            self._semaphore.acquire()

    def _release_channel_slot(self) -> None:
        if self._semaphore is not None:
            try:
                self._semaphore.release()
            except ValueError:
                pass

    def _evict_if_transport_dead(self) -> None:
        if not self._is_pooled or self._client is None:
            return
        if _is_transport_usable(self._client):
            # Transient channel failure (e.g. MaxSessions "open failed"):
            # keep the shared transport for the other in-flight users.
            return
        _GLOBAL_SSH_POOL.remove_if_current(self.config, self._client)

    def connect(self) -> None:
        if self.use_pool:
            # No silent fallback: opening a second direct TCP connection when
            # the pool handshake fails doubles the storm on an overloaded
            # sshd (banner read errors). Surface the error so the caller can
            # report it and the pool can retry with backoff on next request.
            client, semaphore = _GLOBAL_SSH_POOL.acquire(self.config, self.on_log)
            self._client = client
            self._semaphore = semaphore
            self._is_pooled = True
            self._sftp = None
            self._owns_sftp_channel = False
            return

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
            from remote.ssh_key import prepare_ssh_key_for_paramiko
            prepared = prepare_ssh_key_for_paramiko(self.config.key_path)
            self._prepared_key = prepared
            kwargs["key_filename"] = prepared.key_path
            if prepared.warning:
                self.on_log(prepared.warning)
        if self.config.password:
            kwargs["password"] = self.config.password

        self.on_log(f"Connecting SSH {self.config.username}@{self.config.host}:{self.config.port}...")
        try:
            client.connect(**kwargs)
        except Exception:
            if self._prepared_key:
                self._prepared_key.cleanup()
                self._prepared_key = None
            raise

        self._client = client
        self._semaphore = threading.BoundedSemaphore(MAX_CHANNELS_PER_CONNECTION)
        self._sftp = None
        self._owns_sftp_channel = False
        self.on_log("SSH connected.")

    def close(self) -> None:
        if self._owns_sftp_channel and self._sftp is not None:
            try:
                self._sftp.close()
            except Exception:
                pass
            self._sftp = None
            self._owns_sftp_channel = False
            self._release_channel_slot()

        if self._is_pooled:
            _GLOBAL_SSH_POOL.release(self.config, self._client)
            self._client = None
            self._semaphore = None
            self._is_pooled = False
            return

        if self._client:
            self._client.close()
            self._client = None
            self._semaphore = None
        if self._prepared_key:
            self._prepared_key.cleanup()
            self._prepared_key = None

    @property
    def client(self):
        if self._client is None:
            raise RuntimeError("SSH client is not connected")
        return self._client

    @property
    def sftp(self):
        if self._sftp is None:
            if self._client is not None:
                self._acquire_channel_slot()
                try:
                    self._sftp = getattr(self._client, "open_sftp")()
                    self._owns_sftp_channel = True
                except Exception:
                    self._release_channel_slot()
                    self._evict_if_transport_dead()
                    raise
            else:
                raise RuntimeError("SFTP client is not connected")
        return self._sftp

    def run(self, command: str, stream: bool = True, check: bool = False, timeout: float | None = None) -> int:
        self.on_log(f">>> {command}")
        self._acquire_channel_slot()
        try:
            try:
                stdin, stdout, stderr = self.client.exec_command(command, get_pty=stream, timeout=timeout)
            except Exception:
                self._evict_if_transport_dead()
                raise

            try:
                stdin.close()
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
            finally:
                try:
                    stdout.close()
                except Exception:
                    pass
                try:
                    stderr.close()
                except Exception:
                    pass
                try:
                    stdout.channel.close()
                except Exception:
                    pass
        finally:
            self._release_channel_slot()

    def read_text(self, command: str) -> tuple[int, str]:
        self._acquire_channel_slot()
        try:
            try:
                stdin, stdout, stderr = self.client.exec_command(command)
            except Exception:
                self._evict_if_transport_dead()
                raise

            try:
                stdin.close()
                text = stdout.read().decode(errors="replace")
                err = stderr.read().decode(errors="replace")
                code = stdout.channel.recv_exit_status()
                return code, text + err
            finally:
                try:
                    stdout.close()
                except Exception:
                    pass
                try:
                    stderr.close()
                except Exception:
                    pass
                try:
                    stdout.channel.close()
                except Exception:
                    pass
        finally:
            self._release_channel_slot()

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
                try:
                    self.sftp.mkdir(path)
                except OSError as exc:
                    user_info = f" as user '{self.config.username}'" if self.config.username else ""
                    if "Permission denied" in str(exc) or getattr(exc, "errno", None) == 13:
                        raise PermissionError(
                            f"Permission denied creating remote directory '{path}'{user_info}. Please check write permissions on the server."
                        ) from exc
                    raise OSError(f"Failed creating remote directory '{path}': {exc}") from exc

    def expand_path(self, remote_path: str) -> str:
        if remote_path.startswith("~/") or remote_path == "~":
            code, home = self.read_text("printf %s \"$HOME\"")
            if code == 0 and home.strip():
                return remote_path.replace("~", home.strip(), 1)
        return remote_path

    def write_text_file(self, remote_path: str, content: str) -> None:
        remote_path = self.expand_path(remote_path)
        self.mkdir_p(posixpath.dirname(remote_path))
        try:
            with self.sftp.open(remote_path, "w") as f:
                f.write(content)
        except OSError as exc:
            user_info = f" as user '{self.config.username}'" if self.config.username else ""
            if "Permission denied" in str(exc) or getattr(exc, "errno", None) == 13:
                raise PermissionError(
                    f"Permission denied writing to remote file '{remote_path}'{user_info}. Please check write permissions on the server."
                ) from exc
            raise OSError(f"Failed writing to remote file '{remote_path}': {exc}") from exc

    def upload_file(self, local_path: str | Path, remote_path: str) -> None:
        local = Path(local_path)
        remote_path = self.expand_path(remote_path)
        self.mkdir_p(posixpath.dirname(remote_path))
        self.on_log(f"Uploading file: {local} -> {remote_path}")
        try:
            self.sftp.put(str(local), remote_path)
        except OSError as exc:
            user_info = f" as user '{self.config.username}'" if self.config.username else ""
            if "Permission denied" in str(exc) or getattr(exc, "errno", None) == 13:
                raise PermissionError(
                    f"Permission denied uploading '{local.name}' to '{remote_path}'{user_info}. Please check write permissions on the server."
                ) from exc
            raise OSError(f"Failed uploading '{local}' to '{remote_path}': {exc}") from exc

    def upload_file_with_progress(
        self,
        local_path: str | Path,
        remote_path: str,
        callback=None,
    ) -> None:
        """sftp.put with an optional paramiko progress callback(transferred, total)."""
        local = Path(local_path)
        remote_path = self.expand_path(remote_path)
        self.mkdir_p(posixpath.dirname(remote_path))
        kwargs = {"callback": callback} if callback else {}
        try:
            self.sftp.put(str(local), remote_path, **kwargs)
        except OSError as exc:
            user_info = f" as user '{self.config.username}'" if self.config.username else ""
            if "Permission denied" in str(exc) or getattr(exc, "errno", None) == 13:
                raise PermissionError(
                    f"Permission denied uploading '{local.name}' to '{remote_path}'{user_info}. Please check write permissions on the server."
                ) from exc
            raise OSError(f"Failed uploading '{local}' to '{remote_path}': {exc}") from exc

    def upload_dir(
        self,
        local_dir: str | Path,
        remote_dir: str,
        skip_dirs: set[str] | None = None,
        allowed_extensions: set[str] | None = None,
        skip_existing_matching_size: bool = False,
    ) -> None:
        local_root = Path(local_dir)
        remote_root = self.expand_path(remote_dir)
        skip_dirs = skip_dirs or set()
        self.mkdir_p(remote_root)
        for root, dirs, files in os.walk(local_root):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            rel = Path(root).relative_to(local_root)
            remote_subdir = remote_root if str(rel) == "." else posixpath.join(remote_root, rel.as_posix())
            
            files_to_upload = files
            if allowed_extensions:
                files_to_upload = [f for f in files if any(f.endswith(ext) for ext in allowed_extensions)]
            
            if not files_to_upload:
                continue

            self.mkdir_p(remote_subdir)
            for name in files_to_upload:
                local_file = Path(root) / name
                remote_file = posixpath.join(remote_subdir, name)
                if skip_existing_matching_size:
                    try:
                        remote_stat = self.sftp.stat(remote_file)
                        if remote_stat.st_size == local_file.stat().st_size:
                            continue
                    except (OSError, IOError):
                        pass
                self.on_log(f"Uploading file: {local_file} -> {remote_file}")
                try:
                    self.sftp.put(str(local_file), remote_file)
                except OSError as exc:
                    user_info = f" as user '{self.config.username}'" if self.config.username else ""
                    if "Permission denied" in str(exc) or getattr(exc, "errno", None) == 13:
                        raise PermissionError(
                            f"Permission denied uploading '{local_file.name}' to '{remote_file}'{user_info}. Please check write permissions on the server."
                        ) from exc
                    raise OSError(f"Failed uploading '{local_file}' to '{remote_file}': {exc}") from exc

    def download_dir(self, remote_dir: str, local_dir: str | Path) -> None:
        remote_dir = self.expand_path(remote_dir)
        local_root = Path(local_dir)
        local_root.mkdir(parents=True, exist_ok=True)
        self._download_dir_recursive(remote_dir, local_root)

    def download_file_if_exists(self, remote_file: str, local_file: str | Path) -> bool:
        remote_file = self.expand_path(remote_file)
        try:
            self.sftp.stat(remote_file)
        except OSError:
            return False
        local_path = Path(local_file)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self.on_log(f"Downloading file: {remote_file} -> {local_path}")
        self.sftp.get(remote_file, str(local_path))
        return True

    def _download_dir_recursive(self, remote_dir: str, local_dir: Path) -> None:
        local_dir.mkdir(parents=True, exist_ok=True)
        for item in self.sftp.listdir_attr(remote_dir):
            remote_path = posixpath.join(remote_dir, item.filename)
            local_path = local_dir / item.filename
            if stat.S_ISLNK(item.st_mode):
                self.on_log(f"Skipping symlink: {remote_path}")
            elif stat.S_ISDIR(item.st_mode):
                self._download_dir_recursive(remote_path, local_path)
            else:
                if local_path.exists() and local_path.stat().st_size == item.st_size:
                    self.on_log(f"Skipping existing file: {local_path}")
                else:
                    self.on_log(f"Downloading file: {remote_path} -> {local_path}")
                    self.sftp.get(remote_path, str(local_path))
