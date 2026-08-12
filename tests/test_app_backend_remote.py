from __future__ import annotations

from app_backend.remote import RemoteJobService
from remote.remote_runner import RemoteRunConfig


class FakeRunner:
    def __init__(self, jobs: list[dict[str, object]], fail_connect: bool = False) -> None:
        self.jobs = jobs
        self.fail_connect = fail_connect

    def list_background_jobs(self) -> list[dict[str, object]]:
        return self.jobs

    def test_ssh(self) -> None:
        if self.fail_connect:
            raise RuntimeError("auth failed for secret")

    def remote_hardware_info(self) -> dict[str, object]:
        return {"hostname": "server", "logical_cores": 32, "total_ram_bytes": 128_000_000_000}


def test_validate_remote_config_connects_and_redacts_secrets() -> None:
    calls: list[dict[str, object]] = []

    def runner_factory(config: RemoteRunConfig) -> FakeRunner:
        calls.append({"host": config.ssh.host, "password": config.ssh.password})
        return FakeRunner([])

    service = RemoteJobService(runner_factory=runner_factory)

    result = service.validate_config(
        {
            "host": "server.example.edu",
            "port": 2222,
            "username": "alice",
            "password": "secret",
            "workspace": "~/mri-remote-jobs",
        }
    )

    assert result == {
        "ok": True,
        "connected": True,
        "config": {
            "host": "server.example.edu",
            "port": 2222,
            "username": "alice",
            "auth_method": "password",
            "workspace": "~/mri-remote-jobs",
            "python": "python3",
        },
        "hardware": {"hostname": "server", "logical_cores": 32, "total_ram_bytes": 128_000_000_000},
    }
    assert calls == [{"host": "server.example.edu", "password": "secret"}]


def test_validate_remote_config_returns_safe_connection_error_without_secret() -> None:
    service = RemoteJobService(runner_factory=lambda _config: FakeRunner([], fail_connect=True))

    result = service.validate_config({"host": "server", "username": "alice", "password": "secret"})

    assert result == {
        "ok": False,
        "connected": False,
            "error": "SSH connection failed: auth failed for [redacted]",
        "config": {
            "host": "server",
            "port": 22,
            "username": "alice",
            "auth_method": "password",
            "workspace": "~/mri-remote-jobs",
            "python": "python3",
        },
    }


def test_validate_remote_config_rejects_key_with_open_permissions(tmp_path) -> None:
    key_path = tmp_path / "id_rsa"
    key_path.write_text("private key", encoding="utf-8")
    key_path.chmod(0o777)
    service = RemoteJobService(runner_factory=lambda _config: FakeRunner([]))

    result = service.validate_config({"host": "server", "username": "alice", "key_path": str(key_path)})

    assert result["ok"] is False
    assert result["connected"] is False
    assert "SSH key file permissions are too open" in str(result["error"])


def test_validate_remote_config_wsl_windows_mount_adds_warning(tmp_path, monkeypatch) -> None:
    key_path = tmp_path / "duat"
    key_path.write_text("private key", encoding="utf-8")
    key_path.chmod(0o777)

    monkeypatch.setattr("remote.ssh_key._is_wsl_windows_mount", lambda _p: True)

    service = RemoteJobService(runner_factory=lambda _config: FakeRunner([]))
    result = service.validate_config({"host": "server", "username": "alice", "key_path": str(key_path)})

    assert result["ok"] is True
    assert result["connected"] is True
    assert "warnings" in result
    assert any("Windows-mounted WSL path" in w for w in result["warnings"])


def test_validate_remote_config_rejects_invalid_required_fields() -> None:
    service = RemoteJobService()

    assert service.validate_config({"host": "", "port": 70000, "username": ""}) == {
        "ok": False,
        "errors": ["Remote host is required.", "Remote username is required.", "Remote port must be between 1 and 65535."],
    }


def test_list_remote_jobs_uses_injected_runner_and_normalizes_response() -> None:
    calls: list[dict[str, object]] = []

    def runner_factory(config: RemoteRunConfig) -> FakeRunner:
        calls.append({"host": config.ssh.host, "password": config.ssh.password})
        return FakeRunner([{"job_id": "job_1", "state": "running", "pid": "123", "remote_job_dir": "/workspace/job_1"}])

    service = RemoteJobService(runner_factory=runner_factory)
    result = service.list_jobs({"host": "server", "username": "alice", "password": "secret"})

    assert result["ok"] is True
    assert isinstance(result.get("jobs"), list)
    job = result["jobs"][0]
    assert job["target"] == "Server"
    assert job["state"] == "running"
    assert job["pid"] == "123"
    assert job["remote_job_dir"] == "/workspace/job_1"
    assert job["job_id"] == "job_1"
    assert "run_request_summary" in job
    assert calls == [{"host": "server", "password": "secret"}]


def test_list_remote_jobs_returns_safe_error_without_secret() -> None:
    def runner_factory(_config: RemoteRunConfig) -> FakeRunner:
        raise RuntimeError("auth failed for secret")

    service = RemoteJobService(runner_factory=runner_factory)
    result = service.list_jobs({"host": "server", "username": "alice", "password": "secret"})

    assert result == {"ok": False, "error": "Remote job listing failed"}

