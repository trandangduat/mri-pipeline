from __future__ import annotations

from app_backend.remote import RemoteJobService
from pipeline.presets import PRESET_CONFIGS
from remote.remote_runner import RemoteRunConfig


class FakeRunner:
    def __init__(self, jobs: list[dict[str, object]], fail_connect: bool = False) -> None:
        self.jobs = jobs
        self.fail_connect = fail_connect
        self.calls: list[str] = []

    def list_background_jobs(self) -> list[dict[str, object]]:
        return self.jobs

    def test_ssh(self) -> None:
        if self.fail_connect:
            raise RuntimeError("auth failed for secret")

    def remote_hardware_info(self) -> dict[str, object]:
        return {
            "hostname": "server",
            "logical_cores": 32,
            "total_ram_bytes": 128_000_000_000,
            "gpus": [{"name": "NVIDIA A100", "total_memory_mib": 40960, "free_memory_mib": 39321}],
        }

    def check_image_statuses(self, image_names: list[str]) -> dict[str, bool]:
        return {image: True for image in image_names}

    def upload_job(self) -> str:
        self.calls.append("upload_job")
        return "/workspace/job_1"

    def stage_freesurfer_license(self) -> None:
        self.calls.append("stage_freesurfer_license")

    def check_freesurfer_license(self) -> tuple[bool, str]:
        self.calls.append("check_freesurfer_license")
        return True, "FreeSurfer license check passed."

    def start_remote_detached(self) -> str:
        self.calls.append("start_remote_detached")
        return "/workspace/job_1"

    def remote_status(self) -> dict[str, object]:
        self.calls.append("remote_status")
        return {"state": "running", "pid": "123"}


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
        "hardware": {
            "hostname": "server",
            "logical_cores": 32,
            "total_ram_bytes": 128_000_000_000,
            "gpus": [{"name": "NVIDIA A100", "total_memory_mib": 40960, "free_memory_mib": 39321}],
        },
    }
    assert calls == [{"host": "server.example.edu", "password": "secret"}]


def test_validate_remote_config_tolerates_hardware_without_gpus() -> None:
    class NoGpuRunner(FakeRunner):
        def remote_hardware_info(self) -> dict[str, object]:
            return {"hostname": "server", "logical_cores": 32, "total_ram_bytes": 128_000_000_000}

    service = RemoteJobService(runner_factory=lambda _config: NoGpuRunner([]))

    result = service.validate_config(
        {"host": "server.example.edu", "port": 22, "username": "alice", "password": "secret"}
    )

    assert result["ok"] is True
    assert "gpus" not in result["hardware"]


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


def test_validate_remote_config_wsl_windows_mount_no_warning(tmp_path, monkeypatch) -> None:
    key_path = tmp_path / "duat"
    key_path.write_text("private key", encoding="utf-8")
    key_path.chmod(0o777)

    monkeypatch.setattr("remote.ssh_key._is_wsl_windows_mount", lambda _p: True)

    service = RemoteJobService(runner_factory=lambda _config: FakeRunner([]))
    result = service.validate_config({"host": "server", "username": "alice", "key_path": str(key_path)})

    assert result["ok"] is True
    assert result["connected"] is True
    assert "warnings" not in result


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
    assert job["job_id"] == "remote_job_1"
    assert "run_request_summary" in job
    assert calls == [{"host": "server", "password": "secret"}]


def test_list_remote_jobs_returns_safe_error_without_secret() -> None:
    def runner_factory(_config: RemoteRunConfig) -> FakeRunner:
        raise RuntimeError("auth failed for secret")

    service = RemoteJobService(runner_factory=runner_factory)
    result = service.list_jobs({"host": "server", "username": "alice", "password": "secret"})

    assert result == {"ok": False, "error": "Remote job listing failed"}


def test_stream_start_job_blocks_when_selected_tool_image_missing() -> None:
    class FakeRunnerMissingImage(FakeRunner):
        def __init__(self) -> None:
            super().__init__([])
            self.start_remote_detached_called = False

        def check_image_statuses(self, image_names: list[str]) -> dict[str, bool]:
            return {image: False for image in image_names}

        def start_remote_detached(self) -> str:
            self.start_remote_detached_called = True
            return "/workspace/job_1"

    fake = FakeRunnerMissingImage()

    def runner_factory(config: RemoteRunConfig) -> FakeRunnerMissingImage:
        return fake

    service = RemoteJobService(runner_factory=runner_factory)

    events = list(
        service.stream_start_job(
            {
                "host": "server",
                "username": "alice",
                "password": "secret",
                "run_request": {
                    "input_source": "Server",
                    "run_target": "Server",
                    "input_mode": "file",
                    "input_path": "/data/image.nii.gz",
                    "output_dir": "/out",
                    "pipeline_mode": "Custom",
                    "selected_tools": {"reorientation": "fastsurfer_reorientation", "segmentation": "fastsurfer_segmentation"},
                    "license_dir": "/license",
                },
            }
        )
    )

    step_events = [e for e in events if e.get("event") == "step"]
    images_failed = [e for e in step_events if e["data"].get("step") == "images" and e["data"].get("status") == "failed"]
    assert len(images_failed) == 1
    assert "Tools Configuration" in images_failed[0]["data"]["detail"]

    assert events[-1]["event"] == "complete"
    assert events[-1]["data"]["ok"] is False
    assert "Tools Configuration" in str(events[-1]["data"].get("error", ""))
    assert fake.start_remote_detached_called is False


def test_stream_start_job_passes_license_path_to_remote_config(tmp_path) -> None:
    license_file = tmp_path / "license.txt"
    license_file.write_text("license", encoding="utf-8")
    configs: list[RemoteRunConfig] = []

    def runner_factory(config: RemoteRunConfig) -> FakeRunner:
        configs.append(config)
        return FakeRunner([])

    service = RemoteJobService(runner_factory=runner_factory)

    events = list(
        service.stream_start_job(
            {
                "host": "server",
                "username": "alice",
                "password": "secret",
                "run_request": {
                    "input_source": "Server",
                    "run_target": "Server",
                    "input_mode": "file",
                    "input_path": "/data/image.nii.gz",
                    "output_dir": "/out",
                    "pipeline_mode": "Custom",
                    "selected_tools": {"reorientation": "fastsurfer_reorientation", "segmentation": "fastsurfer_segmentation"},
                    "license_dir": str(license_file),
                },
            }
        )
    )

    assert events[-1]["event"] == "complete"
    assert events[-1]["data"]["ok"] is True
    assert configs[-1].license_dir == str(license_file)


def test_stream_start_job_reports_missing_license_as_license_failure() -> None:
    class MissingLicenseRunner(FakeRunner):
        def stage_freesurfer_license(self) -> None:
            self.calls.append("stage_freesurfer_license")
            raise FileNotFoundError("License not found locally: /tmp/license.txt")

    fake = MissingLicenseRunner([])
    service = RemoteJobService(runner_factory=lambda _config: fake)

    events = list(
        service.stream_start_job(
            {
                "host": "server",
                "username": "alice",
                "password": "secret",
                "run_request": {
                    "input_source": "Server",
                    "run_target": "Server",
                    "input_mode": "file",
                    "input_path": "/data/image.nii.gz",
                    "output_dir": "/out",
                    "pipeline_mode": "Custom",
                    "selected_tools": {
                        "reorientation": "fastsurfer_reorientation",
                        "segmentation": "fastsurfer_segmentation",
                    },
                    "license_dir": "/tmp/license.txt",
                },
            }
        )
    )

    step_events = [event for event in events if event.get("event") == "step"]
    license_failed = [
        event for event in step_events if event["data"].get("step") == "license" and event["data"].get("status") == "failed"
    ]
    assert len(license_failed) == 1
    assert license_failed[0]["data"]["detail"] == "License not found locally: /tmp/license.txt"
    assert "SSH connection failed" not in license_failed[0]["data"]["detail"]
    assert fake.calls == ["stage_freesurfer_license"]
    assert events[-1]["data"]["ok"] is False


def test_stream_start_job_stops_after_invalid_license_check(tmp_path) -> None:
    license_file = tmp_path / "license.txt"
    license_file.write_text("invalid", encoding="utf-8")

    class InvalidLicenseRunner(FakeRunner):
        def check_freesurfer_license(self) -> tuple[bool, str]:
            self.calls.append("check_freesurfer_license")
            return False, "FreeSurfer license check failed on the remote server."

    fake = InvalidLicenseRunner([])
    service = RemoteJobService(runner_factory=lambda _config: fake)
    events = list(
        service.stream_start_job(
            {
                "host": "server",
                "username": "alice",
                "password": "secret",
                "run_request": {
                    "input_source": "Server",
                    "run_target": "Server",
                    "input_mode": "file",
                    "input_path": "/data/image.nii.gz",
                    "output_dir": "/out",
                    "pipeline_mode": "Custom",
                    "selected_tools": {
                        "reorientation": "fastsurfer_reorientation",
                        "segmentation": "fastsurfer_segmentation",
                    },
                    "license_dir": str(license_file),
                },
            }
        )
    )

    step_events = [event for event in events if event.get("event") == "step"]
    assert [(event["data"]["step"], event["data"]["status"]) for event in step_events[-2:]] == [
        ("license", "running"),
        ("license", "failed"),
    ]
    assert fake.calls == ["stage_freesurfer_license", "check_freesurfer_license"]
    assert events[-1]["data"]["ok"] is False


def test_stream_start_job_orders_license_config_and_worker(tmp_path) -> None:
    license_file = tmp_path / "license.txt"
    license_file.write_text("license", encoding="utf-8")
    fake = FakeRunner([])
    service = RemoteJobService(runner_factory=lambda _config: fake)

    events = list(
        service.stream_start_job(
            {
                "host": "server",
                "username": "alice",
                "password": "secret",
                "run_request": {
                    "input_source": "Server",
                    "run_target": "Server",
                    "input_mode": "file",
                    "input_path": "/data/image.nii.gz",
                    "output_dir": "/out",
                    "pipeline_mode": "Custom",
                    "selected_tools": {
                        "reorientation": "fastsurfer_reorientation",
                        "segmentation": "fastsurfer_segmentation",
                    },
                    "license_dir": str(license_file),
                },
            }
        )
    )

    assert fake.calls == [
        "stage_freesurfer_license",
        "check_freesurfer_license",
        "upload_job",
        "start_remote_detached",
        "remote_status",
    ]
    steps = [event["data"]["step"] for event in events if event.get("event") == "step"]
    assert steps[-6:] == ["license", "license", "config", "config", "start", "start"]


def test_stream_start_job_infers_preset_mode_for_neuroflow_custom_tools() -> None:
    configs: list[RemoteRunConfig] = []

    def runner_factory(config: RemoteRunConfig) -> FakeRunner:
        configs.append(config)
        return FakeRunner([])

    service = RemoteJobService(runner_factory=runner_factory)

    events = list(
        service.stream_start_job(
            {
                "host": "server",
                "username": "alice",
                "password": "secret",
                "run_request": {
                    "input_source": "Server",
                    "run_target": "Server",
                    "input_mode": "file",
                    "input_path": "/data/image.nii.gz",
                    "output_dir": "/out",
                    "pipeline_mode": "Custom",
                    "selected_tools": dict(PRESET_CONFIGS["FreeSurfer 8 + Volume + Cortical Thickness"]["tools"]),
                    "neuroflow_enabled": True,
                    "license_dir": "/license",
                },
            }
        )
    )

    assert events[-1]["event"] == "complete"
    assert events[-1]["data"]["ok"] is True
    assert configs[-1].pipeline_mode == "FreeSurfer 8 + Volume + Cortical Thickness"
    assert events[-1]["data"]["job"]["run_request_summary"]["pipeline_mode"] == "FreeSurfer 8 + Volume + Cortical Thickness"


def test_stream_start_job_succeeds_when_local_remote_registry_update_fails() -> None:
    def register_remote_job(**_kwargs: object) -> None:
        raise ValueError("local registry is malformed")

    service = RemoteJobService(
        runner_factory=lambda _config: FakeRunner([]),
        register_remote_job=register_remote_job,
    )

    events = list(
        service.stream_start_job(
            {
                "host": "server",
                "username": "alice",
                "password": "secret",
                "run_request": {
                    "input_source": "Server",
                    "run_target": "Server",
                    "input_mode": "file",
                    "input_path": "/data/image.nii.gz",
                    "output_dir": "/out",
                    "pipeline_mode": "Custom",
                    "selected_tools": {"reorientation": "fastsurfer_reorientation", "segmentation": "fastsurfer_segmentation"},
                    "license_dir": "/license",
                },
            }
        )
    )

    assert events[-1]["event"] == "complete"
    assert events[-1]["data"]["ok"] is True
    assert events[-1]["data"]["job"]["state"] == "running"


class FakeSFTPAttr:
    def __init__(self, filename: str, is_dir: bool, size: int = 100, mtime: int = 1700000000) -> None:
        import stat as _stat
        self.filename = filename
        self.st_mode = (_stat.S_IFDIR | 0o755) if is_dir else (_stat.S_IFREG | 0o644)
        self.st_size = size
        self.st_mtime = mtime


class FakeSFTPClient:
    def __init__(self, tree: dict[str, list[FakeSFTPAttr]]) -> None:
        self.tree = tree

    def normalize(self, path: str) -> str:
        return path

    def stat(self, path: str) -> FakeSFTPAttr:
        if path in self.tree:
            return FakeSFTPAttr(path.split("/")[-1] or "root", is_dir=True)
        return FakeSFTPAttr(path.split("/")[-1], is_dir=False)

    def listdir_attr(self, path: str) -> list[FakeSFTPAttr]:
        return self.tree.get(path, [])


def test_browse_path_detects_remote_dicom_series_directory(monkeypatch) -> None:
    tree = {
        "/data": [
            FakeSFTPAttr("sub-01", is_dir=True),
            FakeSFTPAttr("notes.txt", is_dir=False, size=50),
        ],
        "/data/sub-01": [
            FakeSFTPAttr("slice_001.dcm", is_dir=False, size=500),
            FakeSFTPAttr("slice_002.dcm", is_dir=False, size=500),
        ],
    }

    class FakeSSH:
        def __init__(self, _config) -> None:
            self.sftp = FakeSFTPClient(tree)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("remote.ssh_client.RemoteSSHClient", FakeSSH)

    service = RemoteJobService()
    result = service.browse_path(
        {
            "host": "server",
            "username": "alice",
            "password": "secret",
            "path": "/data",
            "purpose": "browse",
        }
    )

    assert result["ok"] is True
    dirs = [e for e in result["entries"] if e["kind"] == "directory"]
    assert len(dirs) == 1
    sub01 = dirs[0]
    assert sub01["name"] == "sub-01"
    assert sub01["is_dicom_series"] is True
    assert sub01["slice_count"] == 2
    assert sub01["size"] == 1000


def test_scan_batch_via_sftp_groups_dicom_series_and_computes_metadata(monkeypatch) -> None:
    tree = {
        "/dataset": [
            FakeSFTPAttr("sub-01", is_dir=True),
            FakeSFTPAttr("sub-02", is_dir=True),
        ],
        "/dataset/sub-01": [
            FakeSFTPAttr("T1w.nii.gz", is_dir=False, size=1500),
        ],
        "/dataset/sub-02": [
            FakeSFTPAttr(f"IM{i:03d}.dcm", is_dir=False, size=200) for i in range(10)
        ],
    }

    class FakeSSH:
        def __init__(self, _config) -> None:
            self.sftp = FakeSFTPClient(tree)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("remote.ssh_client.RemoteSSHClient", FakeSSH)

    service = RemoteJobService()
    result = service.browse_path(
        {
            "host": "server",
            "username": "alice",
            "password": "secret",
            "path": "/dataset",
            "purpose": "batch",
            "max_depth": 1,
        }
    )

    assert result["ok"] is True
    assert result["image_count"] == 2
    assert result["has_multi_subject_conflict"] is False

    entries = {e["subject_label"]: e for e in result["entries"]}

    sub1 = entries["sub-01"]
    assert sub1["name"] == "T1w.nii.gz"
    assert sub1["is_dicom_series"] is False

    sub2 = entries["sub-02"]
    assert sub2["name"] == "sub-02"
    assert sub2["is_dicom_series"] is True
    assert sub2["slice_count"] == 10
    assert sub2["size"] == 2000
