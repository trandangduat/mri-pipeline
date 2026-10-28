from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import gpu_resource_metrics as gpu
from pipeline.executor import DockerResourceMetrics, ExecutionRequest, LocalDockerExecutor

CID = "a" * 64


def collector(monkeypatch, records, *, changed=False, mig="Disabled"):
    reads = []
    identities = []
    def query(command):
        reads.append(command)
        if command[:2] == ["docker", "inspect"]:
            return json.dumps([{"Id": CID, "State": {"Running": True, "Pid": 10},
                                "HostConfig": {"PidMode": ""}}])
        if command[:2] == ["docker", "top"]:
            return "PID\n10\n11"
        if "--query-gpu=uuid,mig.mode.current" in command:
            return f"GPU-one, {mig}"
        return records
    def identity(pid, container_id):
        assert container_id == CID
        identities.append(pid)
        return str(pid + (100 if changed and len(identities) > 2 else 0))
    monkeypatch.setattr(gpu, "_query", query)
    monkeypatch.setattr(gpu, "_process_identity", identity)
    return gpu.ContainerGPUMemoryCollector("container", "1"), reads


@pytest.mark.parametrize("records,expected", [
    ("GPU-one, 10, 100, python\nGPU-one, 11, 200, python", 300),
    ("GPU-one, 10, 0, python", 0),
    ("GPU-one, 10, 100, python\nGPU-two, 11, 500, python\nGPU-one, 99, 900, python", 100),
])
def test_sample_sums_only_owned_processes_on_selected_gpu(monkeypatch, records, expected):
    monitor, reads = collector(monkeypatch, records)
    value, info = monitor.sample()
    assert value == expected
    assert info["gpu_uuid"] == "GPU-one"
    assert info["container_id"] == CID
    assert info["valid_samples"] == 1
    assert not info["reason"]
    assert any(command[:2] == ["docker", "top"] for command in reads)


@pytest.mark.parametrize("records,reason", [
    ("", "No measured"),
    ("GPU-two, 10, 500, python", "No measured"),
    ("GPU-one, 99, 100, python", "No measured"),
    ("GPU-one, 10, N/A, python", "invalid literal"),
    ("GPU-one, 10, 100, python\nGPU-one, 11, N/A, python", "invalid literal"),
    ("GPU-one, 10, 100, python\nGPU-one, 10, 100, python", "Duplicate"),
    ("GPU-one, 10, -1, python", "Negative"),
    ("GPU-one, 10, 200, nvidia-cuda-mps-server", "MPS"),
    ("incomplete", "Incomplete"),
])
def test_unknown_or_partial_samples_are_not_zero_or_partial_totals(monkeypatch, records, reason):
    monitor, _ = collector(monkeypatch, records)
    value, info = monitor.sample()
    assert value is None
    assert reason in info["reason"]
    assert info["valid_samples"] == 0


def test_pid_reuse_invalidates_sample(monkeypatch):
    monitor, _ = collector(monkeypatch, "GPU-one, 10, 100, python", changed=True)
    value, info = monitor.sample()
    assert value is None
    assert "changed" in info["reason"]


def test_mig_is_not_misreported_as_physical_gpu_memory(monkeypatch):
    monitor, _ = collector(monkeypatch, "GPU-one, 10, 100, python", mig="Enabled")
    assert monitor.sample()[0] is None


@pytest.mark.parametrize("failure", ["missing", "timeout", "failed"])
def test_query_failures_produce_missing_metric(monkeypatch, failure):
    import subprocess
    from types import SimpleNamespace
    def run(*args, **kwargs):
        assert kwargs["timeout"] == 1
        if failure == "missing":
            raise FileNotFoundError("nvidia-smi missing")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args[0], 1)
        return SimpleNamespace(returncode=1, stdout="")
    monkeypatch.setattr(gpu.subprocess, "run", run)
    value, info = gpu.ContainerGPUMemoryCollector("container", "1").sample()
    assert value is None and info["reason"]


@pytest.mark.parametrize("ownership", ["valid", "other-container", "namespace", "missing"])
def test_process_identity_requires_full_container_cgroup_and_host_pid(tmp_path, monkeypatch, ownership):
    proc = tmp_path / "proc"
    process = proc / "10"
    process.mkdir(parents=True)
    (process / "cgroup").write_text(f"0::/system.slice/docker-{CID if ownership != 'other-container' else 'b'*64}.scope\n")
    (process / "status").write_text(f"NSpid:\t{10 if ownership != 'namespace' else 1}\n")
    (process / "stat").write_text("10 (a process (name)) S " + " ".join(str(i) for i in range(4, 53)))
    original_path = Path
    monkeypatch.setattr(gpu, "Path", lambda _: proc)
    if ownership == "missing":
        (process / "cgroup").unlink()
    if ownership == "valid":
        assert gpu._process_identity(10, CID) == "22"
    else:
        with pytest.raises((ValueError, OSError)):
            gpu._process_identity(10, CID)
    assert original_path(proc).is_dir()


def test_executor_tracks_maximum_sampled_total_and_cpu_ram(mocker):
    import threading
    from types import SimpleNamespace
    from pipeline import executor
    ready = threading.Event()
    values = iter([100, 300, 250])
    def sample():
        value = next(values)
        if value == 250:
            ready.set()
        return value, {"valid_samples": 3, "gpu_uuid": "GPU-one"}
    mocker.patch.object(executor, "ContainerGPUMemoryCollector",
                        return_value=SimpleNamespace(sample=sample))
    process = mocker.Mock(returncode=0)
    def communicate(**kwargs):
        assert ready.wait(8)
        return "done", None
    process.communicate.side_effect = communicate
    mocker.patch.object(executor.subprocess, "Popen", return_value=process)
    mocker.patch.object(executor.subprocess, "run",
                        return_value=SimpleNamespace(returncode=0, stdout="25%|10MiB / 20MiB"))
    result = LocalDockerExecutor().execute(ExecutionRequest(
        "image", [], [], gpus=True, gpu_device_id="1", container_name="container"))
    assert result.metrics.peak_gpu_memory_mib == 300
    assert result.metrics.peak_ram_bytes == 10 * 1024**2
    assert result.metrics.peak_cpu_pct == 25
    assert result.metrics.gpu_telemetry["gpu_uuid"] == "GPU-one"


def test_executor_discards_pending_sample_before_return(mocker):
    import threading
    from types import SimpleNamespace
    from pipeline import executor
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    def sample():
        entered.set()
        release.wait(6)
        done.set()
        return 500, {"valid_samples": 1}
    mocker.patch.object(executor, "ContainerGPUMemoryCollector",
                        return_value=SimpleNamespace(sample=sample))
    process = mocker.Mock(returncode=0)
    def communicate(**kwargs):
        assert entered.wait(3)
        return "done", None
    process.communicate.side_effect = communicate
    mocker.patch.object(executor.subprocess, "Popen", return_value=process)
    result = LocalDockerExecutor().execute(ExecutionRequest(
        "image", [], [], gpus=True, gpu_device_id="1", container_name="container"))
    try:
        assert result.metrics.peak_gpu_memory_mib is None
    finally:
        release.set()
    assert done.wait(3)
    assert result.metrics.peak_gpu_memory_mib is None


def test_cpu_execution_does_not_probe_gpu(mocker):
    from pipeline import executor
    monitor = mocker.patch.object(executor, "ContainerGPUMemoryCollector")
    process = mocker.Mock(returncode=0)
    process.communicate.return_value = ("done", None)
    mocker.patch.object(executor.subprocess, "Popen", return_value=process)
    result = LocalDockerExecutor().execute(ExecutionRequest("image", [], []))
    monitor.assert_not_called()
    assert result.metrics.peak_gpu_memory_mib is None
    assert DockerResourceMetrics().peak_gpu_memory_mib is None



@pytest.fixture
def execution_evidence(tmp_path):
    from types import SimpleNamespace
    from pipeline.config import PipelineConfig, StepResult
    from pipeline.gpu_execution_receipt import execution_provenance, receipt_path, save_execution
    source = tmp_path / "input.nii.gz"
    source.write_text("input")
    subject = tmp_path / "out/sub"
    subject.mkdir(parents=True)
    output = subject / "output.nii.gz"
    output.write_text("output")
    config = PipelineConfig(str(source), str(tmp_path / "out"), "sub",
                            selected_tools={"segmentation": "fastsurfer_segmentation"})
    context = SimpleNamespace(config=config, input_file=str(source), subject_dir=str(subject),
                              input_for_stage=lambda stage: None)
    launch = SimpleNamespace(task_id="sub:seg", attempt_id="attempt-1", configuration_id="gpu_1",
                             cpu_threads=1, gpu_id="gpu_1",
                             execution_mode=SimpleNamespace(value="gpu"))
    provenance = execution_provenance(context, launch, "segmentation", ("preset", "profile"))
    step = StepResult("segmentation", "fastsurfer_segmentation", True, 2,
                      output_file=str(output), peak_ram_bytes=1024**2, peak_gpu_memory_mib=321,
                      gpu_telemetry={"gpu_uuid": "GPU-one", "container_id": CID, "valid_samples": 1})
    path = receipt_path(tmp_path / "job", launch.task_id)
    save_execution(path, provenance, launch, "execution-1", step, str(output))
    return path, provenance, output, source


def test_same_execution_receipt_retains_original_metrics_and_identity(execution_evidence):
    from pipeline.config import StepResult
    from pipeline.gpu_execution_receipt import load_execution, mark_reported
    path, provenance, _, _ = execution_evidence
    evidence = load_execution(path, provenance)
    restored = StepResult(**evidence["step"])
    assert restored.peak_gpu_memory_mib == 321
    assert restored.duration_sec == 2
    assert evidence["attempt_id"] == "attempt-1"
    assert evidence["execution_id"] == "execution-1"
    assert evidence["reporting_state"] == "pending"
    mark_reported(path)
    assert load_execution(path, provenance)["reporting_state"] == "reported"


@pytest.mark.parametrize("mismatch", ["input", "configuration", "tool", "output", "missing", "source"])
def test_receipt_mismatch_cannot_authorize_reuse(execution_evidence, mismatch):
    from pipeline.gpu_execution_receipt import load_execution
    path, provenance, output, source = execution_evidence
    if mismatch == "input":
        provenance = {**provenance, "input": {"path": "/another/input"}}
    elif mismatch == "configuration":
        provenance = {**provenance, "configuration_id": "gpu_other"}
    elif mismatch == "tool":
        provenance = {**provenance, "tool": "another_tool"}
    elif mismatch == "source":
        provenance = {**provenance, "sources": ["new_preset", "new_profile"]}
    elif mismatch == "output":
        output.write_text("different output")
    else:
        output.unlink()
    with pytest.raises((ValueError, OSError)):
        load_execution(path, provenance)


def test_atomic_receipt_failure_keeps_previous_evidence(execution_evidence, monkeypatch):
    from pipeline import gpu_execution_receipt as receipts
    path, _, _, _ = execution_evidence
    original = path.read_bytes()
    def fail_replace(*args):
        raise OSError("disk error")
    monkeypatch.setattr(receipts.os, "replace", fail_replace)
    with pytest.raises(OSError):
        receipts.write_json(path, {"invalid": "new record"})
    assert path.read_bytes() == original
    assert not path.with_suffix(".tmp").exists()


def test_input_provenance_supports_dicom_directory(tmp_path):
    from pipeline.gpu_execution_receipt import _input_stamp
    folder = tmp_path / "dicom"
    folder.mkdir()
    (folder / "slice.dcm").write_text("DICOM")
    identity = _input_stamp(str(folder))
    assert identity["files"][0]["path"] == str(folder / "slice.dcm")
    assert identity["files"][0]["size"] == 5
