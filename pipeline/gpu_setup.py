"""Allowlisted NVIDIA toolkit repair. Package transactions finish safely."""
from __future__ import annotations

import json
import os
import subprocess

from .gpu_readiness import check_gpu, cli_request, execution_target, privileged_prefix

# This fixed, self-contained helper also works through sudo and a verified WSL bridge.
# No executable text, repository URL, file path, or package name comes from the UI.
INSTALLER_SCRIPT = r'''
import fcntl
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time

# A lost SSH terminal must not interrupt a live dpkg transaction.
signal.signal(signal.SIGHUP, signal.SIG_IGN)

def emit(phase, detail):
    print("GPU_SETUP:" + json.dumps({"phase": phase, "detail": detail}), flush=True)

def run(args, timeout=None):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                            env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"})
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "Command failed")[-1800:])
    return result.stdout.strip()

try:
    data = json.load(sys.stdin)
    if os.geteuid() != 0 or data["action"] not in {"install_toolkit", "configure_runtime"}:
        raise RuntimeError("The requested GPU repair is not authorized.")
    endpoint = data["endpoint"]
    if endpoint not in {"unix:///var/run/docker.sock", "unix:///run/docker.sock"}:
        raise RuntimeError("Only a verified local Unix Docker endpoint can be configured.")
    if pathlib.Path("/etc/machine-id").read_text().strip() != data["machine_id"]:
        raise RuntimeError("The execution host changed. Run preflight again.")
    os.environ.pop("DOCKER_CONTEXT", None)
    os.environ.pop("DOCKER_HOST", None)
    docker = ["docker", "--host", endpoint]
    if run(docker + ["info", "--format", "{{.ID}}"], 10) != data["engine_id"]:
        raise RuntimeError("The Docker engine changed. Run preflight again.")
    distro = {}
    for line in pathlib.Path("/etc/os-release").read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            distro[key] = value.strip('"')
    if distro.get("ID") not in {"ubuntu", "debian"}:
        raise RuntimeError("Automatic setup supports Ubuntu and Debian.")
    if "rootless" in run(docker + ["info", "--format", "{{json .SecurityOptions}}"], 10):
        raise RuntimeError("Rootless Docker requires manual setup.")
    lock = open("/run/lock/neuroflow-gpu-setup.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("Another GPU setup is running. Wait for it to finish.")
    service = run(["systemctl", "show", "docker", "--property=ExecStart", "--value"], 10)
    if "--config-file" in service:
        raise RuntimeError("A custom Docker service configuration requires manual setup.")
    if run(docker + ["ps", "-q"], 10):
        raise RuntimeError("Stop running containers before GPU setup; Docker must restart.")
    if data["action"] == "install_toolkit":
        emit("repository", "Preparing the signed NVIDIA package repository")
        with tempfile.TemporaryDirectory(prefix="neuroflow-gpu-setup-") as folder:
            folder = pathlib.Path(folder)
            key = folder / "nvidia.asc"
            run(["curl", "-fsSL", "--connect-timeout", "15", "--max-time", "60",
                 "https://nvidia.github.io/libnvidia-container/gpgkey", "-o", str(key)], 70)
            fingerprints = run(["gpg", "--batch", "--show-keys", "--with-colons", str(key)], 10)
            if "C95B321B61E88C1809C4F759DDCAE044F796ECB0" not in fingerprints:
                raise RuntimeError("The NVIDIA signing key changed. Use the official setup guide.")
            keyring = folder / "nvidia.gpg"
            run(["gpg", "--batch", "--yes", "--dearmor", "--output", str(keyring), str(key)], 10)
            source = folder / "nvidia.list"
            run(["curl", "-fsSL", "--connect-timeout", "15", "--max-time", "60",
                 "https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list",
                 "-o", str(source)], 70)
            text = source.read_text()
            if "https://nvidia.github.io/libnvidia-container/" not in text:
                raise RuntimeError("Unexpected NVIDIA repository.")
            text = text.replace("deb https://", "deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://")
            source.write_text(text)
            for path in ("/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg",
                         "/etc/apt/sources.list.d/nvidia-container-toolkit.list"):
                if pathlib.Path(path).exists():
                    shutil.copy2(path, path + ".neuroflow-backup-" + str(time.time_ns()))
            run(["install", "-m", "0644", str(keyring), "/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg"], 10)
            run(["install", "-m", "0644", str(source), "/etc/apt/sources.list.d/nvidia-container-toolkit.list"], 10)
        emit("installing", "Installing NVIDIA Container Toolkit")
        apt_options = ["-o", "Acquire::http::Timeout=30", "-o", "Acquire::https::Timeout=30",
                       "-o", "Acquire::Retries=1", "-o", "Dpkg::Use-Pty=0"]
        run(["apt-get", *apt_options, "update",
             "-o", "Dir::Etc::sourcelist=sources.list.d/nvidia-container-toolkit.list",
             "-o", "Dir::Etc::sourceparts=-", "-o", "APT::Get::List-Cleanup=0"])
        names = ["nvidia-container-toolkit", "nvidia-container-toolkit-base",
                 "libnvidia-container-tools", "libnvidia-container1"]
        packages = [name + "=1.20.1-1" for name in names]
        preview = run(["apt-get", "--simulate", "install", "--no-install-recommends", *packages])
        for line in preview.splitlines():
            if line.startswith("Remv ") or (line.startswith("Inst ") and line.split()[1].split(":")[0] not in names):
                raise RuntimeError("Setup would change unrelated packages. Use the manual setup guide.")
        # Do not impose a process-kill deadline on a live dpkg transaction.
        run(["apt-get", *apt_options, "install", "-y", "--no-install-recommends", *packages])
    emit("configuring", "Configuring the NVIDIA runtime for Docker")
    for path in ("/etc/docker/daemon.json", "/etc/nvidia-container-runtime/config.toml"):
        if pathlib.Path(path).exists():
            shutil.copy2(path, path + ".neuroflow-backup-" + str(time.time_ns()))
    run(["nvidia-ctk", "runtime", "configure", "--runtime=docker", "--dry-run"], 15)
    run(["nvidia-ctk", "runtime", "configure", "--runtime=docker"], 15)
    if run(docker + ["ps", "-q"], 10):
        raise RuntimeError("Toolkit configured. Containers started during setup; restart Docker manually when they finish.")
    emit("restarting", "Restarting Docker to apply GPU support")
    run(["systemctl", "restart", "docker"], 45)
    for attempt in range(20):
        try:
            if run(docker + ["info", "--format", "{{.ID}}"], 3) == data["engine_id"]:
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        raise RuntimeError("Docker did not become ready after restart.")
    emit("configured", "NVIDIA toolkit and Docker configuration completed")
except Exception as exc:
    emit("failed", str(exc))
    sys.exit(1)
'''


def repair_gpu(request: dict, expected_target: str, action: str, emit) -> dict:
    if action not in {"install_toolkit", "configure_runtime"}:
        raise ValueError("Unsupported GPU repair action.")
    emit({"phase": "checking", "detail": "Rechecking GPU setup and administrative access"})
    diagnostic = check_gpu(request)
    target = diagnostic.get("target") or {}
    if target.get("fingerprint") != expected_target:
        raise ValueError("The Docker target changed. Run preflight again.")
    if diagnostic.get("ready"):
        return {"ok": True, "result": diagnostic, "detail": "GPU is already ready."}
    eligible = any(item.get("can_execute") and item.get("action_id") == action
                   for item in diagnostic.get("solutions", []))
    if not eligible:
        return {"ok": False, "result": diagnostic, "error": "Automatic repair is no longer available. Follow the setup instructions."}
    prefix = privileged_prefix(target, allow_wsl=not bool(request.get("_gpu_remote")))
    if prefix is None:
        raise ValueError("Administrative access is unavailable. Follow the setup instructions.")
    # Recheck identity just before elevating.
    if execution_target().get("fingerprint") != expected_target:
        raise ValueError("The Docker target changed. Run preflight again.")
    from .win_process import no_window_kwargs
    payload = {key: target[key] for key in ("endpoint", "machine_id", "engine_id")}
    payload["action"] = action
    process = subprocess.Popen([*prefix, "python3", "-u", "-c", INSTALLER_SCRIPT],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, start_new_session=(os.name == "posix"), **no_window_kwargs())
    process.stdin.write(json.dumps(payload))
    process.stdin.close()
    log_tail = ""
    failed_phase = ""
    for line in process.stdout:
        log_tail = (log_tail + line)[-4000:]
        if line.startswith("GPU_SETUP:"):
            item = json.loads(line.removeprefix("GPU_SETUP:"))
            if item.get("phase") == "failed":
                failed_phase = str(item.get("detail", ""))
            emit(item)
    code = process.wait()
    if code:
        return {"ok": False, "error": "GPU setup did not finish. " + (failed_phase or log_tail[-1800:]),
                "result": diagnostic}
    emit({"phase": "verifying", "detail": "Toolkit configured. Verifying GPU access in the processing image"})
    verified = check_gpu(request)
    return {"ok": bool(verified.get("ready")), "result": verified,
            "error": "" if verified.get("ready") else "Toolkit configured, but the processing image GPU check still failed."}


if __name__ == "__main__":
    try:
        payload = cli_request()
        result = repair_gpu(payload["request"], payload["expected_target"], payload["action"],
                            lambda item: print("GPU_SETUP:" + json.dumps(item), flush=True))
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    print("GPU_SETUP_RESULT:" + json.dumps(result), flush=True)
