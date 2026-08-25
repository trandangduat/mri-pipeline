from __future__ import annotations

import json
import shlex
import subprocess

import pytest
from pathlib import Path
from remote.remote_runner import RemoteRunner, RemoteRunConfig, _neuroflow_source_dir
from remote.ssh_client import SSHConfig


class FakeRemoteSSHClient:
    commands: list[str] = []
    versions: dict[str, tuple[int, str]] = {}
    dependency_check: tuple[int, str] = (0, "")
    downloaded_dirs: list[tuple[str, Path]] = []
    downloaded_files: list[tuple[str, Path]] = []
    uploaded_dirs: list[tuple[Path, str]] = []
    uploaded_files: list[tuple[Path, str]] = []
    existing_download_files: set[str] = set()
    managed_python_installed: bool = False

    def __init__(self, _config, _on_log=None) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        pass

    def expand_path(self, remote_path: str) -> str:
        return remote_path.replace("~", "/home/tester", 1) if remote_path.startswith("~") else remote_path

    def read_text(self, command: str) -> tuple[int, str]:
        if command == 'printf %s "$HOME"':
            return 0, "/home/tester"
        if "import yaml, jsonschema" in command:
            return self.dependency_check
        if "test -x /home/tester/mri-remote-jobs/.venv/bin/python" in command:
            return 0, ""
        if "/home/tester/mri-remote-jobs/python311/bin/python -c " in command:
            return (0, "3.11\n") if self.managed_python_installed else (1, "")
        for python_cmd, response in self.versions.items():
            if f"{python_cmd} -c " in command:
                return response
        return 0, ""

    def run(self, command: str, stream: bool = True, check: bool = False) -> int:
        self.commands.append(command)
        if "micro.mamba.pm" in command and "python=3.11" in command:
            self.managed_python_installed = True
        return 0

    def mkdir_p(self, remote_path: str) -> None:
        self.commands.append(f"mkdir -p {remote_path}")

    def download_dir(self, remote_dir: str, local_dir: str | Path) -> None:
        self.downloaded_dirs.append((remote_dir, Path(local_dir)))

    def download_file_if_exists(self, remote_file: str, local_file: str | Path) -> bool:
        if remote_file not in self.existing_download_files:
            return False
        self.downloaded_files.append((remote_file, Path(local_file)))
        return True

    def upload_file(self, local_file: str | Path, remote_file: str) -> None:
        self.uploaded_files.append((Path(local_file), remote_file))

    def upload_dir(
        self,
        local_dir: str | Path,
        remote_dir: str,
        skip_dirs: set[str] | None = None,
        allowed_extensions: set[str] | None = None,
    ) -> None:
        self.uploaded_dirs.append((Path(local_dir), remote_dir))


class ExecPythonListSSHClient(FakeRemoteSSHClient):
    def read_text(self, command: str) -> tuple[int, str]:
        if command.startswith("python3 -c "):
            stripped = command.removesuffix(" 2>/dev/null")
            parts = shlex.split(stripped)
            result = subprocess.run(parts, check=False, capture_output=True, text=True)
            return result.returncode, result.stdout + result.stderr
        return super().read_text(command)


class MissingNeuroflowSSHClient(FakeRemoteSSHClient):
    def run(self, command: str, stream: bool = True, check: bool = False) -> int:
        self.commands.append(command)
        if "import yaml, jsonschema" in command:
            return 0
        if "import neuroflow" in command:
            return 1
        if "test -f" in command and "NeuroFLOW-private" in command:
            return 1
        return 0


def test_remote_runner_clean_guardrail(dummy_ssh_server):
    ssh_config = SSHConfig(
        host=dummy_ssh_server["host"], 
        port=dummy_ssh_server["port"], 
        username=dummy_ssh_server["username"], 
        password=dummy_ssh_server["password"]
    )
    
    run_config = RemoteRunConfig(
        ssh=ssh_config,
        remote_workspace="/home/tester/mri_workspace",
        input_file="input.nii.gz",
        output_dir="outputs"
    )
    runner = RemoteRunner(run_config)
    
    # Intentionally set the remote_job_dir to something dangerous outside the workspace
    runner.remote_job_dir = "/etc"
    
    # We expect a ValueError before the destructive rm command is attempted.
    with pytest.raises(ValueError, match="outside of designated workspace"):
        runner.clean_remote()

def test_remote_runner_clean_safe_integration(dummy_ssh_server):
    ssh_config = SSHConfig(
        host=dummy_ssh_server["host"], 
        port=dummy_ssh_server["port"], 
        username=dummy_ssh_server["username"], 
        password=dummy_ssh_server["password"]
    )
    run_config = RemoteRunConfig(
        ssh=ssh_config,
        remote_workspace="/home/tester/mri_workspace",
        input_file="input.nii.gz",
        output_dir="outputs"
    )
    runner = RemoteRunner(run_config)
    
    # Set a safe directory within the workspace that actually exists on the dummy server
    runner.remote_job_dir = "/home/tester/mri_workspace/job_123"
    
    # Should connect to the dummy server, execute rm -rf, and not raise exception
    runner.clean_remote()


def test_remote_runner_clean_allows_expanded_default_workspace(mocker) -> None:
    FakeRemoteSSHClient.commands = []
    mocker.patch("remote.remote_runner.RemoteSSHClient", FakeRemoteSSHClient)
    run_config = RemoteRunConfig(
        ssh=SSHConfig(host="example", username="tester"),
        remote_workspace="~/mri-remote-jobs",
    )
    runner = RemoteRunner(run_config)
    runner.remote_job_dir = "/home/tester/mri-remote-jobs/job_123"

    runner.clean_remote()

    assert FakeRemoteSSHClient.commands == ["rm -rf /home/tester/mri-remote-jobs/job_123"]


def test_remote_runner_clean_rejects_workspace_root(mocker) -> None:
    mocker.patch("remote.remote_runner.RemoteSSHClient", FakeRemoteSSHClient)
    run_config = RemoteRunConfig(
        ssh=SSHConfig(host="example", username="tester"),
        remote_workspace="~/mri-remote-jobs",
    )
    runner = RemoteRunner(run_config)
    runner.remote_job_dir = "/home/tester/mri-remote-jobs"

    with pytest.raises(ValueError, match="workspace root"):
        runner.clean_remote()


def test_remote_runner_upload_creates_output_outside_workspace(mocker) -> None:
    """User-supplied output roots are no longer workspace-contained: mkdir instead."""
    mocker.patch("remote.remote_runner.RemoteSSHClient", FakeRemoteSSHClient)
    run_config = RemoteRunConfig(
        ssh=SSHConfig(host="example", username="tester"),
        remote_workspace="~/mri-remote-jobs",
        server_output_dir="/tmp/outside",
    )
    runner = RemoteRunner(run_config)
    for step_name in (
        "_upload_export_config",
        "_upload_stats_vector_config",
        "_upload_subject_id_map",
        "_ensure_shared_code",
        "_upload_license",
        "_write_job_config",
        "_write_job_metadata",
    ):
        mocker.patch.object(runner, step_name, lambda *_args, **_kwargs: None)

    job_dir = runner.upload_job()

    assert job_dir
    assert runner.remote_output_dir == "/tmp/outside"
    assert any("mkdir -p /tmp/outside" in command for command in FakeRemoteSSHClient.commands)


def test_remote_runner_upload_rejects_missing_license(mocker, tmp_path) -> None:
    mocker.patch("remote.remote_runner.RemoteSSHClient", FakeRemoteSSHClient)
    run_config = RemoteRunConfig(
        ssh=SSHConfig(host="example", username="tester"),
        remote_workspace="~/mri-remote-jobs",
        license_dir=str(tmp_path / "missing-license.txt"),
    )
    runner = RemoteRunner(run_config)
    runner.remote_job_dir = "/home/tester/mri-remote-jobs/job_123"

    with FakeRemoteSSHClient(None) as ssh:
        with pytest.raises(FileNotFoundError, match="License not found locally"):
            runner._upload_license(ssh)


def test_remote_runner_checks_uploaded_license_before_start(mocker) -> None:
    FakeRemoteSSHClient.commands = []
    mocker.patch("remote.remote_runner.RemoteSSHClient", FakeRemoteSSHClient)
    run_config = RemoteRunConfig(
        ssh=SSHConfig(host="example", username="tester"),
        remote_workspace="~/mri-remote-jobs",
        selected_tools={"segmentation": "fs7_recon_style_segmentation"},
    )
    runner = RemoteRunner(run_config)
    runner.remote_job_dir = "/home/tester/mri-remote-jobs/job_123"

    ok, detail = runner.check_freesurfer_license()

    assert ok is True
    assert detail == "FreeSurfer license check passed."
    assert "docker run --rm --entrypoint /bin/bash" in FakeRemoteSSHClient.commands[0]
    assert "recon-all -version" in FakeRemoteSSHClient.commands[0]


def test_remote_runner_downloads_job_level_neuroflow_artifacts(mocker, tmp_path) -> None:
    FakeRemoteSSHClient.downloaded_dirs = []
    FakeRemoteSSHClient.downloaded_files = []
    FakeRemoteSSHClient.existing_download_files = {
        "/home/tester/mri-remote-jobs/job_123/neuroflow_observations.tsv",
        "/home/tester/mri-remote-jobs/job_123/run.log",
    }
    mocker.patch("remote.remote_runner.RemoteSSHClient", FakeRemoteSSHClient)
    run_config = RemoteRunConfig(
        ssh=SSHConfig(host="example", username="tester"),
        remote_workspace="~/mri-remote-jobs",
        output_dir=str(tmp_path),
        download_subdir="batch_123",
    )
    runner = RemoteRunner(run_config)
    runner.remote_job_dir = "/home/tester/mri-remote-jobs/job_123"
    runner.remote_output_dir = "/home/tester/mri-remote-jobs/job_123/outputs"

    local_path = runner.download_outputs()

    assert local_path == tmp_path / "batch_123"
    assert FakeRemoteSSHClient.downloaded_dirs == [
        ("/home/tester/mri-remote-jobs/job_123/outputs", tmp_path / "batch_123")
    ]
    assert (
        "/home/tester/mri-remote-jobs/job_123/neuroflow_observations.tsv",
        tmp_path / "batch_123" / "neuroflow_observations.tsv",
    ) in FakeRemoteSSHClient.downloaded_files
    assert (
        "/home/tester/mri-remote-jobs/job_123/run.log",
        tmp_path / "batch_123" / "run.log",
    ) in FakeRemoteSSHClient.downloaded_files
    FakeRemoteSSHClient.existing_download_files = set()


def test_remote_runner_lists_rich_background_jobs_with_stable_remote_id(mocker, tmp_path) -> None:
    workspace = tmp_path / "mri-remote-jobs"
    incomplete_job_dir = workspace / "job_20260814_102226"
    incomplete_job_dir.mkdir(parents=True)
    (incomplete_job_dir / "job_metadata.json").write_text(
        json.dumps({"job_id": "job_20260814_102226", "created_at": 1786702969.0}),
        encoding="utf-8",
    )
    job_dir = workspace / "job_20260814_102225"
    job_dir.mkdir(parents=True)
    (job_dir / "job_metadata.json").write_text(
        json.dumps({"job_id": "job_20260814_102225", "created_at": 1786702948.0}),
        encoding="utf-8",
    )
    (job_dir / "job_status.json").write_text(
        json.dumps({"state": "running", "started_at": 1786702948.0}),
        encoding="utf-8",
    )
    (job_dir / "job_config.json").write_text(
        json.dumps(
            {
                "mode": "files",
                "input_files": ["/data/sub-001.nii.gz"],
                "output_dir": "/remote/output",
                "effective_output_dir": "/remote/output/batch_20260814_102225",
                "device": "cpu",
                "threads": 8,
                "ram_percent": 90,
                "pipeline_mode": "FreeSurfer 8 + Volume + Cortical Thickness",
                "selected_tools": {"segmentation": "freesurfer8_segmentation"},
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "events.jsonl").write_text(
        json.dumps(
            {
                "kind": "image_done",
                "input_file": "/data/sub-001.nii.gz",
                "success": True,
                "total": 1,
            }
        ),
        encoding="utf-8",
    )

    mocker.patch("remote.remote_runner.RemoteSSHClient", ExecPythonListSSHClient)
    runner = RemoteRunner(
        RemoteRunConfig(
            ssh=SSHConfig(host="example", username="tester"),
            remote_workspace=str(workspace),
        )
    )

    jobs = runner.list_background_jobs()

    assert jobs == [
        {
            "job_id": "remote_job_20260814_102225",
            "remote_job_dir": str(job_dir),
            "state": "running",
            "pid": "",
            "exit_code": None,
            "started_at": 1786702948.0,
            "finished_at": None,
            "output_dir": "/remote/output",
            "effective_output_dir": "/remote/output/batch_20260814_102225",
            "download_subdir": "",
            "input_files": ["/data/sub-001.nii.gz"],
            "batch_summary": {"total": 1, "success": 1, "failed": 0, "running": 0, "pending": 0},
            "run_request_summary": {
                "mode": "files",
                "input_files": ["/data/sub-001.nii.gz"],
                "output_dir": "/remote/output",
                "effective_output_dir": "/remote/output/batch_20260814_102225",
                "device": "cpu",
                "threads": 8,
                "ram_percent": 90,
                "pipeline_mode": "FreeSurfer 8 + Volume + Cortical Thickness",
                "selected_tools": {"segmentation": "freesurfer8_segmentation"},
            },
        }
    ]


def test_remote_runner_write_config_rejects_attached_job_outside_workspace(mocker) -> None:
    mocker.patch("remote.remote_runner.RemoteSSHClient", FakeRemoteSSHClient)
    run_config = RemoteRunConfig(
        ssh=SSHConfig(host="example", username="tester"),
        remote_workspace="~/mri-remote-jobs",
    )
    runner = RemoteRunner(run_config)
    runner.attach_job("/tmp/job_123")

    with pytest.raises(ValueError, match="remote job directory is outside"):
        runner.write_remote_job_config({})


def test_remote_runner_adds_neuroflow_src_to_worker_pythonpath(mocker) -> None:
    FakeRemoteSSHClient.commands = []
    mocker.patch("remote.remote_runner.RemoteSSHClient", FakeRemoteSSHClient)
    run_config = RemoteRunConfig(
        ssh=SSHConfig(host="example", username="tester"),
        remote_workspace="~/mri-remote-jobs",
        neuroflow_enabled=True,
    )
    runner = RemoteRunner(run_config)
    runner.remote_job_dir = "/home/tester/mri-remote-jobs/job_123"
    runner.remote_output_dir = "/home/tester/mri-remote-jobs/job_123/outputs"
    mocker.patch.object(runner, "_ensure_shared_code", return_value="/home/tester/mri-remote-jobs/code")
    mocker.patch.object(runner, "ensure_remote_venv", return_value="/home/tester/mri-remote-jobs/.venv/bin/python")
    mocker.patch.object(runner, "_ensure_neuroflow_dependencies")

    runner.start_remote_detached()

    commands = "\n".join(FakeRemoteSSHClient.commands)
    assert "/home/tester/mri-remote-jobs/code/NeuroFLOW-private/src" in commands


def test_remote_runner_fails_early_when_neuroflow_package_missing() -> None:
    ssh = MissingNeuroflowSSHClient(None)
    runner = RemoteRunner(
        RemoteRunConfig(
            ssh=SSHConfig(host="example", username="tester"),
            remote_workspace="~/mri-remote-jobs",
            neuroflow_enabled=True,
        )
    )

    with pytest.raises(RuntimeError, match="NeuroFLOW scheduler package is missing"):
        runner._ensure_neuroflow_dependencies(
            ssh,
            "/home/tester/mri-remote-jobs/.venv/bin/python",
            "/home/tester/mri-remote-jobs/code",
        )


def test_neuroflow_source_dir_uses_explicit_env(monkeypatch, tmp_path) -> None:
    source = tmp_path / "NeuroFLOW-private"
    (source / "src" / "neuroflow").mkdir(parents=True)

    monkeypatch.setenv("NEUROFLOW_SOURCE_DIR", str(source))

    assert _neuroflow_source_dir() == source


def test_remote_runner_uploads_tracked_neuroflow_configs(mocker: object) -> None:
    FakeRemoteSSHClient.commands = []
    FakeRemoteSSHClient.uploaded_dirs = []
    FakeRemoteSSHClient.uploaded_files = []
    mocker.patch("remote.remote_runner.RemoteSSHClient", FakeRemoteSSHClient)
    run_config = RemoteRunConfig(
        ssh=SSHConfig(host="example", username="tester"),
        remote_workspace="~/mri-remote-jobs",
        neuroflow_enabled=True,
    )
    runner = RemoteRunner(run_config)

    with FakeRemoteSSHClient(None) as ssh:
        runner._upload_code(ssh, "/home/tester/mri-remote-jobs/code")

    assert any(
        local.as_posix().endswith("configs/neuroflow")
        and remote == "/home/tester/mri-remote-jobs/code/configs/neuroflow"
        for local, remote in FakeRemoteSSHClient.uploaded_dirs
    )
    assert not any(
        remote.endswith("/NeuroFLOW-private/config")
        for _local, remote in FakeRemoteSSHClient.uploaded_dirs
    )


def test_remote_runner_recreates_old_venv_for_neuroflow(mocker) -> None:
    FakeRemoteSSHClient.commands = []
    FakeRemoteSSHClient.versions = {
        "python3": (0, "3.8\n"),
        "python3.12": (1, ""),
        "python3.11": (0, "3.11\n"),
        "/home/tester/mri-remote-jobs/.venv/bin/python": (0, "3.8\n"),
    }
    mocker.patch("remote.remote_runner.RemoteSSHClient", FakeRemoteSSHClient)
    run_config = RemoteRunConfig(
        ssh=SSHConfig(host="example", username="tester"),
        remote_workspace="~/mri-remote-jobs",
        neuroflow_enabled=True,
    )
    runner = RemoteRunner(run_config)

    with FakeRemoteSSHClient(None) as ssh:
        python_path = runner.ensure_remote_venv(ssh)

    assert python_path == "/home/tester/mri-remote-jobs/.venv/bin/python"
    commands = "\n".join(FakeRemoteSSHClient.commands)
    assert "rm -rf /home/tester/mri-remote-jobs/.venv" in commands
    assert "python3.11 -m venv /home/tester/mri-remote-jobs/.venv" in commands
    FakeRemoteSSHClient.versions = {}


def test_remote_runner_bootstraps_python311_for_neuroflow_when_missing(mocker) -> None:
    FakeRemoteSSHClient.commands = []
    FakeRemoteSSHClient.managed_python_installed = False
    FakeRemoteSSHClient.versions = {
        "python3": (0, "3.8\n"),
        "python3.12": (1, ""),
        "python3.11": (1, ""),
        "/home/tester/mri-remote-jobs/.venv/bin/python": (0, "3.8\n"),
    }
    mocker.patch("remote.remote_runner.RemoteSSHClient", FakeRemoteSSHClient)
    run_config = RemoteRunConfig(
        ssh=SSHConfig(host="example", username="tester"),
        remote_workspace="~/mri-remote-jobs",
        neuroflow_enabled=True,
    )
    runner = RemoteRunner(run_config)

    with FakeRemoteSSHClient(None) as ssh:
        python_path = runner.ensure_remote_venv(ssh)

    assert python_path == "/home/tester/mri-remote-jobs/.venv/bin/python"
    commands = "\n".join(FakeRemoteSSHClient.commands)
    assert "micro.mamba.pm/api/micromamba/linux-64/latest" in commands
    assert "python=3.11" in commands
    assert "/home/tester/mri-remote-jobs/python311/bin/python -m venv" in commands
    FakeRemoteSSHClient.versions = {}
    FakeRemoteSSHClient.managed_python_installed = False


def test_remote_python_version_supports_shell_command() -> None:
    FakeRemoteSSHClient.commands = []
    FakeRemoteSSHClient.versions = {
        "source ~/.bashrc && conda activate nf && python": (0, "3.11\n"),
    }
    runner = RemoteRunner(
        RemoteRunConfig(
            ssh=SSHConfig(host="example", username="tester"),
            remote_python="source ~/.bashrc && conda activate nf && python",
        )
    )
    with FakeRemoteSSHClient(None) as ssh:
        assert runner._remote_python_version(ssh, runner.config.remote_python) == (3, 11)
    FakeRemoteSSHClient.versions = {}


def test_remote_python_details_report_neuroflow_requirements() -> None:
    FakeRemoteSSHClient.versions = {
        "python3": (0, "3.8\n"),
        "python3.12": (1, ""),
        "python3.11": (1, ""),
        "/home/tester/mri-remote-jobs/.venv/bin/python": (0, "3.8\n"),
    }
    FakeRemoteSSHClient.dependency_check = (1, "No module named yaml")
    runner = RemoteRunner(
        RemoteRunConfig(
            ssh=SSHConfig(host="example", username="tester"),
            remote_workspace="~/mri-remote-jobs",
            neuroflow_enabled=True,
        )
    )
    with FakeRemoteSSHClient(None) as ssh:
        details = runner._check_python_details(ssh)

    assert details["neuroflow_python_ok"] is False
    assert details["neuroflow_dependency_ok"] is False
    assert "Remote Python=3.8" in str(details["neuroflow_python_text"])
    FakeRemoteSSHClient.versions = {}
    FakeRemoteSSHClient.dependency_check = (0, "")


def test_remote_runner_uses_preset_tools_for_cat12_volume() -> None:
    runner = RemoteRunner(
        RemoteRunConfig(
            ssh=SSHConfig(host="example", username="tester"),
            pipeline_mode="CAT12 + Volume",
            selected_tools={
                "reorientation": "fs8_reduced54_reorientation",
                "segmentation": "cat12_volume_segmentation",
                "stats_extraction": "cat12_volume_stats_extraction",
            },
        )
    )

    args = runner._tool_args()

    assert "--reorientation" not in args
    assert args == [
        "--segmentation",
        "cat12_volume_segmentation",
        "--stats-extraction",
        "cat12_volume_stats_extraction",
    ]


def test_parse_gpu_rows_parses_nvidia_smi_output() -> None:
    from remote.remote_runner import _parse_gpu_rows

    raw = "24508, 25568, NVIDIA GeForce RTX 4090|31200, 32510, NVIDIA A100-SXM4-40GB|"
    gpus = _parse_gpu_rows(raw)
    assert [g["name"] for g in gpus] == ["NVIDIA GeForce RTX 4090", "NVIDIA A100-SXM4-40GB"]
    assert gpus[0]["free_memory_mib"] == 24508
    assert gpus[0]["total_memory_mib"] == 25568


def test_parse_gpu_rows_handles_absence_and_garbage() -> None:
    from remote.remote_runner import _parse_gpu_rows

    # nvidia-smi missing -> empty payload between marker and newline.
    assert _parse_gpu_rows("") == []
    # Malformed rows are skipped.
    assert _parse_gpu_rows("not-a-number, 1234, GPU|12, 24, OK") == [
        {"name": "OK", "total_memory_mib": 24, "free_memory_mib": 12}
    ]


def test_remote_hardware_info_includes_gpus(mocker) -> None:
    from remote.remote_runner import RemoteRunner
    from remote.ssh_client import SSHConfig

    probe_output = (
        "hostname=gpu-box\n"
        "logical_cores=16\n"
        "phys_pages=33720786\n"
        "page_size=4096\n"
        "gpus=24508, 25568, NVIDIA GeForce RTX 4090|\n"
    )

    class GpuSSH:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc) -> None:
            pass

        def read_text(self, command: str) -> tuple[int, str]:
            if "nvidia-smi" in command:
                return 0, probe_output
            return 0, ""

    mocker.patch("remote.remote_runner.RemoteSSHClient", GpuSSH)
    config = type("Cfg", (), {"ssh": SSHConfig(host="h", username="u", password="p")})()
    runner = RemoteRunner(config)
    info = runner.remote_hardware_info()
    assert info["gpus"] == [
        {
            "name": "NVIDIA GeForce RTX 4090",
            "total_memory_mib": 25568,
            "free_memory_mib": 24508,
        }
    ]
    assert info["logical_cores"] == 16


def test_remote_hardware_info_without_nvidia_smi_yields_empty_gpus(mocker) -> None:
    from remote.remote_runner import RemoteRunner
    from remote.ssh_client import SSHConfig

    class NoGpuSSH:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc) -> None:
            pass

        def read_text(self, command: str) -> tuple[int, str]:
            return 0, "hostname=cpu-box\nlogical_cores=8\nphys_pages=2031616\npage_size=4096\ngpus=\n"

    mocker.patch("remote.remote_runner.RemoteSSHClient", NoGpuSSH)
    config = type("Cfg", (), {"ssh": SSHConfig(host="h", username="u", password="p")})()
    runner = RemoteRunner(config)
    info = runner.remote_hardware_info()
    assert info["gpus"] == []
