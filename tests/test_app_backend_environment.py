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


def test_hardware_status_includes_local_gpu_probe(monkeypatch) -> None:
    from app_backend import environment as env_module

    monkeypatch.setattr(env_module, "_host_info", lambda: {
        "hostname": "local",
        "logical_cores": 8,
        "physical_cores": 4,
        "total_ram_bytes": 16_000_000_000,
        "gpus": [{"name": "RTX 4090", "total_memory_mib": 25568, "free_memory_mib": 24000}],
    })

    status = env_module._hardware_status()
    assert status["gpus"] == [{"name": "RTX 4090", "total_memory_mib": 25568, "free_memory_mib": 24000}]


def test_gpu_info_returns_empty_when_nvidia_smi_missing(monkeypatch) -> None:
    from pipeline import hardware

    def raise_os_error(*_args, **_kwargs):
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(hardware.subprocess, "run", raise_os_error)
    assert hardware._gpu_info() == []
