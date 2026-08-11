from __future__ import annotations

from app_backend.environment import LocalEnvironmentService


def test_local_environment_status_reports_found_commands() -> None:
    def which(command: str) -> str | None:
        return {"python3": "/usr/bin/python3", "docker": "/usr/bin/docker", "ssh": "/usr/bin/ssh"}.get(command)

    service = LocalEnvironmentService(which=which, python_version=lambda: "3.12.3")

    result = service.status()

    assert result["ok"] is True
    assert result["python"] == {"ok": True, "path": "/usr/bin/python3", "version": "3.12.3"}
    assert result["docker"] == {"ok": True, "path": "/usr/bin/docker"}
    assert result["ssh"] == {"ok": True, "path": "/usr/bin/ssh"}
    assert isinstance(result["hardware"], dict)
    assert "logical_cores" in result["hardware"]


def test_local_environment_status_reports_missing_dependencies() -> None:
    service = LocalEnvironmentService(which=lambda _command: None, python_version=lambda: "3.12.3")

    result = service.status()

    assert result["ok"] is False
    assert result["python"] == {"ok": False, "path": "", "version": "3.12.3"}
    assert result["docker"] == {"ok": False, "path": ""}
    assert result["ssh"] == {"ok": False, "path": ""}
    assert isinstance(result["hardware"], dict)
