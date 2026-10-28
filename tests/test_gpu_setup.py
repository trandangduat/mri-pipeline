from __future__ import annotations

import io
import json
import threading
from types import SimpleNamespace

import pytest

from app_backend import gpu_setup as service_module
from pipeline import gpu_setup as setup
from tests.test_gpu_readiness import TARGET, REQUEST

DIAGNOSTIC = {
    "ready": False, "code": "GPU_TOOLKIT_MISSING", "summary": "Toolkit missing",
    "target": TARGET, "solutions": [{"can_execute": True, "action_id": "install_toolkit"}],
}


def test_repair_rejects_unknown_actions_before_any_probe(monkeypatch):
    monkeypatch.setattr(setup, "check_gpu", lambda request: pytest.fail("Unexpected probe"))
    with pytest.raises(ValueError, match="Unsupported"):
        setup.repair_gpu(REQUEST, "target", "run_arbitrary_command", lambda item: None)


def test_repair_rejects_changed_target_before_privileged_process(monkeypatch):
    monkeypatch.setattr(setup, "check_gpu", lambda request: {**DIAGNOSTIC, "target": {**TARGET, "fingerprint": "changed"}})
    monkeypatch.setattr(setup.subprocess, "Popen", lambda *a, **k: pytest.fail("Must not elevate"))
    with pytest.raises(ValueError, match="target changed"):
        setup.repair_gpu(REQUEST, "target", "install_toolkit", lambda item: None)


def test_already_ready_repair_never_reinstalls(monkeypatch):
    monkeypatch.setattr(setup, "check_gpu", lambda request: {"ready": True, "target": TARGET})
    monkeypatch.setattr(setup.subprocess, "Popen", lambda *a, **k: pytest.fail("Must not install"))
    assert setup.repair_gpu(REQUEST, "target", "install_toolkit", lambda item: None)["ok"]


def test_no_longer_eligible_repair_returns_instructions(monkeypatch):
    monkeypatch.setattr(setup, "check_gpu", lambda request: {**DIAGNOSTIC, "solutions": []})
    assert not setup.repair_gpu(REQUEST, "target", "install_toolkit", lambda item: None)["ok"]


@pytest.mark.parametrize("verified", [False, True])
def test_install_success_is_not_gpu_success_without_probe_verification(monkeypatch, verified):
    results = iter([DIAGNOSTIC, {"ready": verified, "target": TARGET}])
    monkeypatch.setattr(setup, "check_gpu", lambda request: next(results))
    monkeypatch.setattr(setup, "execution_target", lambda: TARGET)
    monkeypatch.setattr(setup, "privileged_prefix", lambda *a, **k: ["sudo", "-n"])
    class Process:
        def __init__(self):
            self.stdin = io.StringIO()
            self.stdout = iter(['GPU_SETUP:{"phase":"configuring","detail":"configured"}\n'])
        def wait(self):
            return 0
    commands = []
    def popen(command, **kwargs):
        commands.append(command)
        return Process()
    monkeypatch.setattr(setup.subprocess, "Popen", popen)
    phases = []
    result = setup.repair_gpu(REQUEST, "target", "install_toolkit", phases.append)
    assert result["ok"] == verified
    assert commands[0][:4] == ["sudo", "-n", "python3", "-u"]
    assert commands[0][-1] == setup.INSTALLER_SCRIPT
    assert any(item["phase"] == "verifying" for item in phases)


def test_repair_service_tickets_bind_request_and_deduplicate(monkeypatch):
    service = service_module.GPUSetupService()
    called = []
    release = threading.Event()
    def repair(request, expected, action, emit):
        called.append((request, expected, action))
        release.wait(3)
        return {"ok": True, "result": {"ready": True}}
    monkeypatch.setattr(setup, "repair_gpu", repair)
    registered = service.register(DIAGNOSTIC, REQUEST)
    operation = service.start(registered["ticket"], "install_toolkit")
    assert service.start(registered["ticket"], "install_toolkit") is operation
    another = service.register(DIAGNOSTIC, REQUEST)
    with pytest.raises(ValueError, match="Another GPU setup"):
        service.start(another["ticket"], "install_toolkit")
    release.set()
    assert operation.done.wait(3)
    assert len(called) == 1 and called[0] == (REQUEST, "target", "install_toolkit")
    assert service.status(registered["ticket"])["state"] == "repaired"
    assert service.start(registered["ticket"], "install_toolkit") is operation


def test_readonly_check_does_not_install_and_produces_ticket(monkeypatch):
    monkeypatch.setattr(service_module, "check_gpu", lambda *args: DIAGNOSTIC)
    monkeypatch.setattr(setup, "repair_gpu", lambda *a: pytest.fail("Unexpected install"))
    service = service_module.GPUSetupService()
    events = list(service.check_events(REQUEST))
    assert events[-1]["data"]["ok"] is False
    failure = events[-2]["data"]
    assert failure["step"] == "gpu" and failure["status"] == "failed"
    ticket = failure["gpu_solutions"]["ticket"]
    assert service.status(ticket)["state"] == "available"


def test_gpu_off_skips_entire_service(monkeypatch):
    monkeypatch.setattr(service_module, "check_gpu", lambda *a: pytest.fail("Unexpected GPU probe"))
    assert list(service_module.GPUSetupService().check_events({"device": "cpu"})) == []


def test_remote_check_and_repair_use_only_selected_server(monkeypatch):
    service = service_module.GPUSetupService()
    monkeypatch.setattr(service_module, "check_gpu", lambda *a: pytest.fail("Must not inspect desktop GPU"))
    calls = []
    class Runner:
        def check_gpu(self, request, cancel):
            calls.append("server-check")
            return DIAGNOSTIC
        def repair_gpu(self, request, target, action, emit):
            calls.append("server-repair")
            return {"ok": True, "result": {"ready": True}}
    events = list(service.check_events(REQUEST, Runner()))
    ticket = events[-2]["data"]["gpu_solutions"]["ticket"]
    operation = service.start(ticket, "install_toolkit")
    assert operation.done.wait(3)
    assert calls == ["server-check", "server-repair"]


def test_ticket_cannot_be_reused_to_supply_an_unadvertised_action():
    service = service_module.GPUSetupService()
    ticket = service.register(DIAGNOSTIC, REQUEST)["ticket"]
    with pytest.raises(ValueError, match="not available"):
        service.start(ticket, "configure_runtime")
    with pytest.raises(ValueError, match="expired"):
        service.start("made-up-ticket", "install_toolkit")


@pytest.mark.parametrize("active", [False, True])
@pytest.mark.parametrize("action", ["configure_runtime", "install_toolkit"])
def test_fixed_installer_preserves_config_and_never_restarts_active_containers(tmp_path, monkeypatch, capsys, active, action):
    import builtins
    import fcntl
    import pathlib
    import shutil
    import sys
    import signal
    real_path = pathlib.Path
    real_open = builtins.open
    def mapped(path):
        path = str(path)
        if path.startswith(("/etc/", "/run/", "/usr/share/")):
            return tmp_path / path.lstrip("/")
        return real_path(path)
    for directory in ("etc/docker", "etc/nvidia-container-runtime", "run/lock", "etc/apt/sources.list.d", "usr/share/keyrings"):
        (tmp_path / directory).mkdir(parents=True)
    mapped("/etc/machine-id").write_text("machine")
    mapped("/etc/os-release").write_text('ID=ubuntu\n')
    configuration = '{"default-runtime":"runc","log-driver":"local","runtimes":{"custom":{"path":"custom"}}}'
    mapped("/etc/docker/daemon.json").write_text(configuration)
    original_copy = shutil.copy2
    monkeypatch.setattr(shutil, "copy2", lambda src, dst, **kwargs: original_copy(mapped(src), mapped(dst), **kwargs))
    monkeypatch.setattr(pathlib, "Path", mapped)
    monkeypatch.setattr(builtins, "open", lambda path, *a, **k: real_open(mapped(path), *a, **k))
    monkeypatch.setattr(setup.os, "geteuid", lambda: 0)
    monkeypatch.setattr(fcntl, "flock", lambda *args: None)
    monkeypatch.setattr(signal, "signal", lambda *args: None)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({
        "action": action, "endpoint": TARGET["endpoint"],
        "machine_id": "machine", "engine_id": "engine",
    })))
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        output = ""
        if args[0] == "docker":
            if "{{.ID}}" in args:
                output = "engine"
            elif "{{json .SecurityOptions}}" in args:
                output = "[]"
            elif "ps" in args:
                output = "busy-container" if active else ""
        elif args[0] == "curl":
            destination = mapped(args[args.index("-o") + 1])
            destination.write_text("deb https://nvidia.github.io/libnvidia-container/stable/deb/amd64 /"
                                   if any("nvidia-container-toolkit.list" in arg for arg in args) else "key")
        elif args[0] == "gpg":
            if "--show-keys" in args:
                output = "fpr:::::::::C95B321B61E88C1809C4F759DDCAE044F796ECB0:"
            else:
                mapped(args[args.index("--output") + 1]).write_bytes(b"key")
        elif args[0] == "install":
            original_copy(mapped(args[-2]), mapped(args[-1]))
        elif args[0] == "apt-get" and "--simulate" in args:
            output = "Inst nvidia-container-toolkit (1.20.1-1)"
        return SimpleNamespace(returncode=0, stdout=output, stderr="")
    monkeypatch.setattr(setup.subprocess, "run", run)
    if active:
        with pytest.raises(SystemExit):
            exec(compile(setup.INSTALLER_SCRIPT, "<gpu-installer>", "exec"), {})
        assert not any(args[0] == "nvidia-ctk" for args in calls)
        assert not any(args[:2] == ["systemctl", "restart"] for args in calls)
    else:
        exec(compile(setup.INSTALLER_SCRIPT, "<gpu-installer>", "exec"), {})
        assert ["nvidia-ctk", "runtime", "configure", "--runtime=docker", "--dry-run"] in calls
        assert ["systemctl", "restart", "docker"] in calls
        if action == "install_toolkit":
            installs = [args for args in calls if args[0] == "apt-get" and "-y" in args]
            assert len(installs) == 1
            assert len([arg for arg in installs[0] if arg.endswith("=1.20.1-1")]) == 4
            assert not any("upgrade" == arg or "cuda-drivers" in arg for arg in installs[0])
        backups = list(mapped("/etc/docker/daemon.json").parent.glob("*.neuroflow-backup-*"))
        assert len(backups) == 1 and backups[0].read_text() == configuration
    assert mapped("/etc/docker/daemon.json").read_text() == configuration
