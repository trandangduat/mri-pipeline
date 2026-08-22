from __future__ import annotations

import json
from pathlib import Path

from app_backend.jobs import LocalJobService, ProcessHandle
from pipeline.jobs import read_json


class FakeProcessRunner:
    def __init__(self, pid: int = 4321) -> None:
        self.pid = pid
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> ProcessHandle:
        self.commands.append(command)
        return ProcessHandle(pid=self.pid)


def _request(tmp_path: Path) -> dict[str, object]:
    image = tmp_path / "image.nii.gz"
    image.write_text("fake", encoding="utf-8")
    return {
        "mode": "file",
        "input_file": str(image),
        "output_dir": str(tmp_path / "outputs"),
        "effective_output_dir": str(tmp_path / "outputs"),
        "is_batch": False,
        "batch_output_name": "",
        "selected_tools": {"segmentation": "synthseg_freesurfer_fs7"},
        "pipeline_mode": "Custom",
        "license_dir": str(tmp_path / "license.txt"),
        "threads": 4,
        "device": "cpu",
    }


def test_start_local_job_writes_worker_files_and_registry(tmp_path: Path) -> None:
    runner = FakeProcessRunner(pid=9876)
    service = LocalJobService(jobs_root=tmp_path / "jobs", process_runner=runner, clock=lambda: 123.0)

    result = service.start_local_job(_request(tmp_path))

    assert result["ok"] is True
    job = result["job"]
    assert isinstance(job, dict)
    job_dir = Path(str(job["job_dir"]))
    assert job["state"] == "running"
    assert job["pid"] == 9876
    assert job["target"] == "Local"
    assert "run_request" not in job
    assert "run_request_summary" in job
    assert isinstance(job["run_request_summary"], dict)
    assert job["run_request_summary"]["mode"] == "file"
    assert job["run_request_summary"]["pipeline_mode"] == "Custom"
    assert "input_files" in job
    assert "download_subdir" in job
    assert (job_dir / "job_config.json").exists()
    saved_config = json.loads((job_dir / "job_config.json").read_text(encoding="utf-8"))
    assert saved_config["job_dir"] == str(job_dir)
    assert saved_config["license_dir"] == str(tmp_path / "license.txt")
    assert json.loads((job_dir / "launcher_status.json").read_text(encoding="utf-8"))["pid"] == 9876
    assert json.loads((job_dir / "job_status.json").read_text(encoding="utf-8"))["state"] == "running"
    assert json.loads((tmp_path / "jobs" / "job_registry.json").read_text(encoding="utf-8"))["jobs"][0]["job_id"] == job["job_id"]
    assert runner.commands[0][1:] == ["-m", "pipeline.job_worker", "--job-config", str(job_dir / "job_config.json")]


def test_stream_start_job_reports_license_failure_before_worker_start(tmp_path: Path, mocker) -> None:
    request = _request(tmp_path)
    Path(str(request["license_dir"])).write_text("license", encoding="utf-8")
    request["input_path"] = request["input_file"]
    request["input_mode"] = "file"
    runner = FakeProcessRunner()
    service = LocalJobService(jobs_root=tmp_path / "jobs", process_runner=runner)
    mocker.patch(
        "app_backend.jobs.check_freesurfer_license",
        return_value=(False, "FreeSurfer license check failed."),
    )

    events = list(service.stream_start_job(request))

    assert [(event["event"], event["data"].get("status")) for event in events] == [
        ("step", "running"),
        ("step", "done"),
        ("step", "running"),
        ("step", "failed"),
        ("complete", None),
    ]
    assert events[2]["data"]["step"] == "license"
    assert events[3]["data"]["detail"] == "FreeSurfer license check failed."
    assert events[-1]["data"]["ok"] is False
    assert runner.commands == []



def test_list_local_jobs_refreshes_status_from_exit_code(tmp_path: Path) -> None:
    service = LocalJobService(jobs_root=tmp_path / "jobs", process_runner=FakeProcessRunner(), clock=lambda: 123.0)
    started = service.start_local_job(_request(tmp_path))
    job = started["job"]
    assert isinstance(job, dict)
    job_dir = Path(str(job["job_dir"]))
    (job_dir / "exit_code.txt").write_text("0", encoding="utf-8")

    result = service.list_local_jobs()

    assert result["ok"] is True
    jobs = result["jobs"]
    assert isinstance(jobs, list)
    assert jobs[0]["job_id"] == job["job_id"]
    assert jobs[0]["state"] == "completed"
    assert jobs[0]["exit_code"] == 0


def test_list_local_jobs_preserves_non_local_registry_entries(tmp_path: Path) -> None:
    service = LocalJobService(jobs_root=tmp_path / "jobs", process_runner=FakeProcessRunner(), clock=lambda: 123.0)
    service.start_local_job(_request(tmp_path))
    registry_path = tmp_path / "jobs" / "job_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["jobs"].append({"job_id": "remote-1", "target": "Server", "state": "running", "updated_at": 999.0})
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    result = service.list_local_jobs()

    assert result["ok"] is True
    saved = json.loads(registry_path.read_text(encoding="utf-8"))
    assert any(job.get("job_id") == "remote-1" for job in saved["jobs"])


def test_stop_local_job_writes_stop_marker_inside_job_dir(tmp_path: Path) -> None:
    service = LocalJobService(jobs_root=tmp_path / "jobs", process_runner=FakeProcessRunner(), clock=lambda: 123.0)
    started = service.start_local_job(_request(tmp_path))
    job = started["job"]
    assert isinstance(job, dict)

    result = service.stop_local_job(str(job["job_id"]))

    assert result["ok"] is True
    assert result["accepted"] is True
    assert Path(str(job["job_dir"]), "stop_requested").read_text(encoding="utf-8") == "stop requested\n"
    status = json.loads(Path(str(job["job_dir"]), "job_status.json").read_text(encoding="utf-8"))
    assert status["state"] == "running"


def test_stop_local_job_rejects_symlink_stop_marker(tmp_path: Path) -> None:
    service = LocalJobService(jobs_root=tmp_path / "jobs", process_runner=FakeProcessRunner(), clock=lambda: 123.0)
    started = service.start_local_job(_request(tmp_path))
    job = started["job"]
    assert isinstance(job, dict)
    outside = tmp_path / "outside"
    outside.write_text("do not touch", encoding="utf-8")
    Path(str(job["job_dir"]), "stop_requested").symlink_to(outside)

    result = service.stop_local_job(str(job["job_id"]))

    assert result == {"ok": False, "error": "Stop marker path is not safe"}
    assert outside.read_text(encoding="utf-8") == "do not touch"


def test_stop_local_job_rejects_unknown_id(tmp_path: Path) -> None:
    service = LocalJobService(jobs_root=tmp_path / "jobs", process_runner=FakeProcessRunner(), clock=lambda: 123.0)

    result = service.stop_local_job("missing")

    assert result == {"ok": False, "error": "Local job not found"}


def test_read_json_returns_default_for_malformed_registry(tmp_path: Path) -> None:
    path = tmp_path / "job_registry.json"
    path.write_text('{"jobs": [\n  {"job_id" "missing colon"}\n]}', encoding="utf-8")

    assert read_json(path, {"jobs": []}) == {"jobs": []}
