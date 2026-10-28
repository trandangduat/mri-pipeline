from __future__ import annotations

import json
import subprocess
import threading
from types import SimpleNamespace

import pytest

from pipeline import gpu_readiness as gpu

TARGET = {"fingerprint": "target", "label": "host", "engine_id": "engine",
          "machine_id": "machine", "endpoint": "unix:///var/run/docker.sock",
          "native": True, "runtimes": ["runc"]}
REQUEST = {"device": "cuda", "threads": 4, "selected_tools": {"segmentation": "fastsurfer_segmentation"}}


@pytest.fixture
def ready(monkeypatch):
    monkeypatch.setattr(gpu, "execution_target", lambda: dict(TARGET))
    card = SimpleNamespace(available=True, gpu_id="gpu_1", free_memory_mib=8000,
                           total_memory_mib=8192, device_class="generic_cuda",
                           metadata=(("uuid", "GPU-one"), ("host_index", "1")))
    monkeypatch.setattr(gpu, "gpu_inventory", lambda: (card,))
    monkeypatch.setattr(gpu, "_documents", lambda *args: None)
    calls = []
    def probe(*args):
        calls.append(args)
        return 0, "GPU_CHECK_OK"
    monkeypatch.setattr(gpu, "_probe", probe)
    return calls


def test_gpu_off_has_no_gpu_or_privilege_subprocesses(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("GPU check must not run")
    monkeypatch.setattr(gpu, "execution_target", unexpected)
    monkeypatch.setattr(gpu, "repair_capability", unexpected)
    assert gpu.check_gpu({"device": "cpu"})["code"] == "GPU_NOT_REQUIRED"


def test_cuda_ready_does_not_require_vram_metrics(ready, monkeypatch):
    monkeypatch.setattr(gpu, "repair_capability", lambda *a, **k: pytest.fail("Ready paths must not inspect installers"))
    result = gpu.check_gpu(REQUEST)
    assert result["ready"] and result["code"] == "GPU_READY"
    assert ready[0][0:3] == ("duattran05/mri-fastsurfervinn:latest", "torch", "1")
    assert "peak_gpu_memory_mib" not in result


@pytest.mark.parametrize("present", [False, True])
def test_toolkit_failure_has_executable_solution_only_with_verified_authority(ready, monkeypatch, present):
    monkeypatch.setattr(gpu, "_probe", lambda *a: (125, "failed to discover GPU vendor from CDI"))
    monkeypatch.setattr(gpu.shutil, "which", lambda name: "/bin/nvidia-ctk" if present else None)
    monkeypatch.setattr(gpu, "repair_capability", lambda *a, **k: (True, ""))
    result = gpu.check_gpu(REQUEST)
    assert result["code"] == ("GPU_RUNTIME_UNCONFIGURED" if present else "GPU_TOOLKIT_MISSING")
    solution = result["solutions"][0]
    assert solution["can_execute"]
    assert solution["action_id"] == ("configure_runtime" if present else "install_toolkit")
    assert solution["requires_admin"] and solution["requires_docker_restart"]


def test_no_admin_means_instructions_without_install_button(ready, monkeypatch):
    monkeypatch.setattr(gpu, "_probe", lambda *a: (125, "could not select device driver with capabilities: [[gpu]]"))
    monkeypatch.setattr(gpu.shutil, "which", lambda name: None)
    monkeypatch.setattr(gpu, "repair_capability", lambda *a, **k: (False, "Administrative access is unavailable"))
    solution = gpu.check_gpu(REQUEST)["solutions"][0]
    assert not solution["can_execute"] and solution["action_id"] is None
    assert solution["instructions"] and "Administrative" in solution["unavailable_reason"]


def test_desktop_does_not_offer_linux_toolkit_installation(ready, monkeypatch):
    monkeypatch.setattr(gpu, "execution_target", lambda: {**TARGET, "native": False})
    monkeypatch.setattr(gpu, "_probe", lambda *a: (125, "failed to discover GPU vendor from CDI"))
    monkeypatch.setattr(gpu, "repair_capability", lambda *a, **k: pytest.fail("Must not install into a neighboring host"))
    result = gpu.check_gpu(REQUEST)
    assert result["code"] == "GPU_IMAGE_RUNTIME_FAILED"
    assert result["solutions"][0]["action_id"] is None
    assert gpu.DESKTOP_URL in result["solutions"][0]["instructions"]


def test_memory_pressure_does_not_offer_software_installation(ready, monkeypatch):
    monkeypatch.setattr(gpu, "_probe", lambda *a: (1, "CUDA out of memory"))
    assert gpu.check_gpu(REQUEST)["code"] == "GPU_RESOURCES_BUSY"


def test_unknown_probe_failure_is_not_called_missing_toolkit(ready, monkeypatch):
    monkeypatch.setattr(gpu, "_probe", lambda *a: (1, "unknown library failure"))
    result = gpu.check_gpu(REQUEST)
    assert result["code"] == "GPU_IMAGE_RUNTIME_FAILED"
    assert result["solutions"][0]["action_id"] is None


def test_no_gpu_stops_before_probes(ready, monkeypatch):
    monkeypatch.setattr(gpu, "gpu_inventory", lambda: ())
    assert gpu.check_gpu(REQUEST)["code"] == "GPU_NOT_FOUND"
    assert not ready


def test_incompatible_profile_fails_before_container(ready, monkeypatch):
    def invalid(*args):
        raise RuntimeError("class mismatch")
    monkeypatch.setattr(gpu, "_documents", invalid)
    assert gpu.check_gpu(REQUEST)["code"] == "GPU_CONFIG_INCOMPATIBLE"
    assert not ready


def test_timeout_is_reported_separately(ready, monkeypatch):
    def expired(*args):
        raise subprocess.TimeoutExpired("probe", 30)
    monkeypatch.setattr(gpu, "_probe", expired)
    assert gpu.check_gpu(REQUEST)["code"] == "GPU_PROBE_TIMEOUT"


def test_probe_specs_deduplicate_and_do_not_require_torch_for_cpu_tools():
    specs = gpu.probe_specs({"selected_tools": {
        "reorientation": "fastsurfer_reorientation", "segmentation": "fastsurfer_segmentation",
        "statistics": "fastsurfer_volume_stats_extraction"}})
    assert len(specs) == 2
    assert {kind for image, kind in specs} == {"access", "torch"}
    assert gpu.probe_specs({"selected_tools": {"reorientation": "mri_convert_fs7"}})[0][1] == "access"


def test_unknown_supported_runtime_produces_manual_guidance(ready):
    result = gpu.check_gpu({**REQUEST, "selected_tools": {"segmentation": "synthseg_standalone"}})
    assert result["code"] == "GPU_PROBE_UNSUPPORTED"
    assert not ready


@pytest.mark.parametrize("cancel", [False, True])
def test_probe_uses_exact_device_no_pull_and_cleans_only_its_container(mocker, cancel):
    stop = threading.Event()
    if cancel:
        stop.set()
    process = mocker.Mock()
    process.communicate.return_value = ("GPU_CHECK_OK", None)
    process.returncode = 0
    process.poll.return_value = None if cancel else 0
    popen = mocker.patch.object(gpu.subprocess, "Popen", return_value=process)
    run = mocker.patch.object(gpu, "_run")
    if cancel:
        with pytest.raises(InterruptedError):
            gpu._probe("image", "torch", "GPU-one", stop, 1)
        process.kill.assert_called_once()
    else:
        assert gpu._probe("image", "torch", "GPU-one", stop, 1)[0] == 0
    command = popen.call_args.args[0]
    assert command[command.index("--gpus") + 1] == "device=GPU-one"
    assert "--pull=never" in command
    assert command[command.index("--cpus") + 1] == "1"
    name = command[command.index("--name") + 1]
    assert name.startswith("neuroflow-gpu-check-")
    run.assert_called_once_with(["docker", "rm", "-f", name], timeout=3)


def test_stock_fastsurfer_profile_validates_with_generic_cuda(ready):
    request = {**REQUEST, "neuroflow_enabled": True, "pipeline_mode": "FastSurfer + Volume",
               "runtime_ram_bytes": 16 * 1024**3}
    # Use actual stock documents, not a mocked validator.
    from pipeline import neuroflow_adapter as adapter
    adapter._ensure_neuroflow_import_path()
    from neuroflow import GPUResource
    from unittest.mock import patch
    card = GPUResource("gpu_0", True, 8192, 8192, "generic_cuda",
                       (("uuid", "GPU-zero"), ("host_index", "0")))
    with patch.object(adapter, "_gpu_resources", return_value=(card,)):
        # The fixture patched _documents; retrieve the original from the module source
        # through an unpatched reference kept below.
        DOCUMENTS(request, (card,))


DOCUMENTS = gpu._documents


def test_repair_authority_rejects_a_different_machine_or_daemon(mocker):
    mocker.patch.object(gpu.os, "geteuid", return_value=0)
    mocker.patch.object(gpu, "_run", return_value=SimpleNamespace(returncode=0, stdout="other"))
    assert gpu.privileged_prefix(TARGET) is None


def test_unsupported_automatic_setup_returns_manual_reason(monkeypatch):
    assert gpu.repair_capability({**TARGET, "native": False})[0] is False
    monkeypatch.setattr(gpu.platform, "freedesktop_os_release", lambda: {"ID": "fedora"})
    assert not gpu.repair_capability(TARGET)[0]


def test_new_gpu_helpers_are_in_packaged_pipeline_sources():
    from pathlib import Path
    from packaging_resources import collect_python_source_datas
    root = Path(gpu.__file__).resolve().parent
    sources = {Path(source).name for source, destination in collect_python_source_datas(root, "pipeline")}
    assert {"gpu_readiness.py", "gpu_setup.py"}.issubset(sources)
