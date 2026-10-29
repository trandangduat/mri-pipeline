from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app_backend import jobs, local_runtime
from pipeline import docker_runtime
from pipeline.docker_runtime import DockerRuntime
from pipeline.jobs import read_json, write_json

GIB = 1024 ** 3


def test_docker_capacity_uses_engine_limits(mocker):
    mocker.patch.object(docker_runtime.os, "cpu_count", return_value=16)
    mocker.patch.object(docker_runtime, "_total_ram_bytes", return_value=64 * GIB)
    run = mocker.patch.object(docker_runtime.subprocess, "run", return_value=SimpleNamespace(
        returncode=0, stdout=json.dumps({"OSType": "linux", "NCPU": 4, "MemTotal": 8 * GIB})))
    assert docker_runtime.inspect_docker_runtime() == DockerRuntime(4, 8 * GIB)
    assert run.call_args.args[0] == ["docker", "info", "--format", "{{json .}}"]


@pytest.mark.parametrize("result", [
    SimpleNamespace(returncode=1, stdout=""),
    SimpleNamespace(returncode=0, stdout='{"OSType":"windows","NCPU":4,"MemTotal":1000}'),
    SimpleNamespace(returncode=0, stdout='{"OSType":"linux","NCPU":0,"MemTotal":1000}'),
    SimpleNamespace(returncode=0, stdout='invalid json'),
])
def test_docker_inspection_rejects_unusable_engine(mocker, result):
    mocker.patch.object(docker_runtime.subprocess, "run", return_value=result)
    with pytest.raises(RuntimeError):
        docker_runtime.inspect_docker_runtime()


@pytest.mark.parametrize("error", [FileNotFoundError(), subprocess.TimeoutExpired("docker", 15)])
def test_docker_inspection_reports_missing_or_unresponsive_docker(mocker, error):
    mocker.patch.object(docker_runtime.subprocess, "run", side_effect=error)
    with pytest.raises(RuntimeError):
        docker_runtime.inspect_docker_runtime()


@pytest.fixture
def ready_runtime(mocker):
    mocker.patch.object(local_runtime, "inspect_docker_runtime", return_value=DockerRuntime(4, 8 * GIB))
    mocker.patch.object(local_runtime, "check_scheduler_runtime")
    mocker.patch.object(local_runtime, "get_profile_peak_ram_mib", return_value=1024)
    mocker.patch.object(local_runtime, "image_exists", return_value=True)
    return {
        "threads": 4,
        "ram_percent": 50,
        "selected_tools": {"segmentation": "cat12_volume_segmentation"},
        "export_config": {"enabled": False},
    }


def test_preflight_persists_only_engine_capacity(ready_runtime):
    request = {**ready_runtime, "runtime_ram_bytes": 999 * GIB}
    events = list(local_runtime.local_runtime_checks(request))
    assert events[-1]["data"]["status"] == "done"
    assert request["runtime_ram_bytes"] == 8 * GIB
    assert request["runtime_cpu_threads"] == 4
    assert [e["data"]["step"] for e in events if e["data"]["status"] == "done"] == ["runtime", "resources", "images"]


@pytest.mark.parametrize("fault,step", [("runtime", "runtime"), ("cpu", "resources"), ("ram", "resources"), ("image", "images")])
def test_preflight_stops_before_worker_for_runtime_faults(mocker, ready_runtime, fault, step):
    if fault == "runtime":
        mocker.patch.object(local_runtime, "inspect_docker_runtime", side_effect=RuntimeError("Docker is offline"))
    elif fault == "cpu":
        ready_runtime["threads"] = 5
    elif fault == "ram":
        mocker.patch.object(local_runtime, "get_profile_peak_ram_mib", return_value=9000)
    else:
        mocker.patch.object(local_runtime, "image_exists", return_value=False)
    events = list(local_runtime.local_runtime_checks(ready_runtime))
    assert events[-1]["event"] == "complete"
    assert events[-1]["data"]["ok"] is False
    assert events[-2]["data"]["step"] == step
    assert events[-2]["data"]["status"] == "failed"


def test_scheduler_missing_is_reported_before_start(mocker):
    mocker.patch("pipeline.neuroflow_adapter._ensure_neuroflow_import_path")
    mocker.patch.object(local_runtime.importlib, "import_module", side_effect=ImportError("neuroflow"))
    with pytest.raises(RuntimeError, match="scheduler is unavailable"):
        local_runtime.check_scheduler_runtime({"neuroflow_enabled": True})


def request(tmp_path):
    return {"mode": "file", "input_file": "sample.mgz", "output_dir": str(tmp_path / "output")}


def test_fast_worker_status_is_not_overwritten(tmp_path):
    def runner(command):
        folder = Path(command[-1]).parent
        write_json(folder / "job_status.json", {"state": "failed", "exit_code": 42, "error": "fast failure"})
        (folder / "exit_code.txt").write_text("42", encoding="utf-8")
        return jobs.ProcessHandle(123)
    service = jobs.LocalJobService(jobs_root=tmp_path / "jobs", process_runner=runner)
    result = service.start_local_job(request(tmp_path))
    status = read_json(Path(result["job"]["job_dir"]) / "job_status.json")
    assert status["state"] == "failed"
    assert status["error"] == "fast failure"
    assert result["job"]["state"] == "failed"


def test_dead_worker_is_failed_without_exit_file(tmp_path):
    service = jobs.LocalJobService(jobs_root=tmp_path / "jobs", process_runner=lambda command: jobs.ProcessHandle(123), process_checker=lambda *_: False)
    result = service.start_local_job(request(tmp_path))
    assert result["job"]["state"] == "failed"
    assert service.list_local_jobs()["jobs"][0]["state"] == "failed"
    assert "exited" in result["job"]["error"]


def test_exit_recovery_preserves_a_just_completed_worker(tmp_path):
    write_json(tmp_path / "job_status.json", {"state": "completed", "exit_code": 0})
    jobs._record_worker_exit(tmp_path, None)
    assert read_json(tmp_path / "job_status.json")["state"] == "completed"
    assert (tmp_path / "exit_code.txt").read_text() == "0"


def test_real_python_import_failure_is_logged_and_reported(tmp_path, mocker):
    mocker.patch.object(jobs.paths, "backend_cwd", return_value=tmp_path)
    mocker.patch.object(jobs.paths, "worker_command", side_effect=lambda config: [
        sys.executable, "-c", "raise RuntimeError('audit startup failure')", "--job-config", config])
    service = jobs.LocalJobService(jobs_root=tmp_path / "jobs", startup_timeout=5)
    result = service.start_local_job(request(tmp_path))
    assert result["ok"] is False
    folder = next((tmp_path / "jobs").glob("job_*"))
    assert "audit startup failure" in (folder / "launcher.log").read_text()
    assert service.list_local_jobs()["jobs"][0]["state"] == "failed"


def test_process_identity_rejects_reused_pid():
    import psutil
    created = psutil.Process(os.getpid()).create_time()
    assert jobs._worker_is_alive(os.getpid(), created)
    assert not jobs._worker_is_alive(os.getpid(), created - 100)


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("reused", [False, True])
def test_packaged_worker_identity_survives_backend_restart(tmp_path, legacy, reused):
    import psutil
    import time
    pid = os.getpid()
    created = psutil.Process(pid).create_time()
    (tmp_path / "pid.txt").write_text(str(pid))
    write_json(tmp_path / "launcher_status.json", {"pid": 99999999, "create_time": created - 2000})
    write_json(tmp_path / "job_status.json", {
        "state": "running", "pid": pid,
        "started_at": created - 1000 if reused else time.time(),
    })
    if not legacy:
        write_json(tmp_path / "worker_identity.json", {
            "pid": pid, "create_time": created - 1000 if reused else created,
        })
    assert jobs._worker_ready(tmp_path, 99999999) is not reused
    service = jobs.LocalJobService(jobs_root=tmp_path)
    result = service._refresh_local_job({"job_dir": str(tmp_path), "state": "running"})
    assert result["state"] == ("failed" if reused else "running")


def test_engine_ram_reaches_scheduler_and_standard_executor(mocker):
    from pipeline.neuroflow_adapter import _ram_limit_mib
    from pipeline.runner import _docker_memory_limit_bytes
    mocker.patch("pipeline.neuroflow_adapter._total_ram_bytes", return_value=64 * GIB)
    mocker.patch("pipeline.runner._total_ram_bytes", return_value=64 * GIB)
    assert _ram_limit_mib(50, 8 * GIB) == 4096
    assert _docker_memory_limit_bytes(50, 8 * GIB) == 4 * GIB
    assert _docker_memory_limit_bytes(100, 8 * GIB) == 8 * GIB
    assert _docker_memory_limit_bytes(100) is None


def test_standard_worker_receives_engine_memory(tmp_path, mocker):
    from pipeline import job_worker
    from pipeline.config import StepResult
    seen = []
    def run(config, **kwargs):
        seen.append(config.runtime_ram_bytes)
        return [StepResult("segmentation", "cat12_volume_segmentation", True, 0.01)]
    mocker.patch.object(job_worker, "run_pipeline", side_effect=run)
    mocker.patch.object(job_worker, "write_batch_reports")
    code = job_worker._run_job(tmp_path, {
        "mode": "file", "input_file": "sample.mgz", "pipeline_mode": "CAT12 + Volume",
        "output_dir": str(tmp_path / "results"), "runtime_ram_bytes": 8 * GIB,
    })
    assert code == 0
    assert seen == [8 * GIB]


def test_batch_runner_receives_engine_memory(tmp_path, mocker):
    from pipeline import runner
    from pipeline.config import StepResult
    seen = []
    def run(config, **kwargs):
        seen.append(config.runtime_ram_bytes)
        return [StepResult("segmentation", "cat12_volume_segmentation", True, 0.01)]
    mocker.patch.object(runner, "run_pipeline", side_effect=run)
    mocker.patch.object(runner, "write_batch_reports")
    mocker.patch.object(runner, "_write_batch_benchmark_reports")
    results = runner.run_batch_pipeline(
        input_dir=str(tmp_path), output_dir=str(tmp_path / "results"),
        input_files=[str(tmp_path / "sample.mgz")],
        batch_config={"runtime_ram_bytes": 8 * GIB},
    )
    assert results[0].success
    assert seen == [8 * GIB]


def test_real_python_worker_reports_readiness(tmp_path, mocker):
    script = (
        "import json, os, pathlib, sys; "
        "p=pathlib.Path(sys.argv[-1]).parent; "
        "(p/'pid.txt').write_text(str(os.getpid())); "
        "(p/'job_status.json').write_text(json.dumps({'state':'completed','exit_code':0})); "
        "(p/'exit_code.txt').write_text('0')"
    )
    mocker.patch.object(jobs.paths, "backend_cwd", return_value=tmp_path)
    mocker.patch.object(jobs.paths, "worker_command", side_effect=lambda config: [
        sys.executable, "-c", script, "--job-config", config])
    service = jobs.LocalJobService(jobs_root=tmp_path / "jobs", startup_timeout=5)
    result = service.start_local_job(request(tmp_path))
    assert result["ok"] is True
    import time
    deadline = time.monotonic() + 2
    while service.list_local_jobs()["jobs"][0]["state"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert service.list_local_jobs()["jobs"][0]["state"] == "completed"


def test_unready_worker_is_terminated_by_its_original_handle(tmp_path, mocker):
    import time
    mocker.patch.object(jobs.paths, "backend_cwd", return_value=tmp_path)
    mocker.patch.object(jobs.paths, "worker_command", side_effect=lambda config: [
        sys.executable, "-c", "import time; time.sleep(10)", "--job-config", config])
    service = jobs.LocalJobService(jobs_root=tmp_path / "jobs", startup_timeout=0.1)
    result = service.start_local_job(request(tmp_path))
    assert result["ok"] is False
    assert "did not become ready" in result["error"]
    folder = next((tmp_path / "jobs").glob("job_*"))
    launcher = read_json(folder / "launcher_status.json")
    deadline = time.monotonic() + 3
    while jobs._worker_is_alive(launcher["pid"], launcher["create_time"]) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not jobs._worker_is_alive(launcher["pid"], launcher["create_time"])
    assert service.list_local_jobs()["jobs"][0]["state"] == "failed"
