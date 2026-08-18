from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from app_backend import paths
from app_backend.config_store import ConfigStore
from app_backend.jobs import LocalJobService, ProcessHandle
from app_backend.licenses import LicenseStore


class TestPortablePathsModule:
    def test_portable_root_returns_none_when_unset(self, tmp_path: Path) -> None:
        env_keys = ["NEUROFLOW_PORTABLE_ROOT", "NEUROFLOW_CONFIG_ROOT", "NEUROFLOW_JOBS_ROOT", "NEUROFLOW_LICENSE_ROOT"]
        clean_env = {k: "" for k in env_keys}
        with patch.dict("os.environ", clean_env, clear=False):
            for key in env_keys:
                __import__("os").environ.pop(key, None)
            result = paths.portable_root()
            assert result is None

    def test_portable_root_returns_path_from_env(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {"NEUROFLOW_PORTABLE_ROOT": str(tmp_path / "portable")}, clear=False):
            result = paths.portable_root()
            assert result == tmp_path / "portable"

    def test_config_root_from_env(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {"NEUROFLOW_CONFIG_ROOT": str(tmp_path / "my-config")}, clear=False):
            assert paths.config_root() == tmp_path / "my-config"

    def test_config_root_from_portable_root(self, tmp_path: Path) -> None:
        env = {"NEUROFLOW_PORTABLE_ROOT": str(tmp_path / "portable"), "NEUROFLOW_CONFIG_ROOT": ""}
        with patch.dict("os.environ", env, clear=False):
            assert paths.config_root() == tmp_path / "portable" / "config"

    def test_jobs_root_from_env(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {"NEUROFLOW_JOBS_ROOT": str(tmp_path / "my-jobs")}, clear=False):
            assert paths.jobs_root() == tmp_path / "my-jobs"

    def test_jobs_root_from_portable_root(self, tmp_path: Path) -> None:
        env = {"NEUROFLOW_PORTABLE_ROOT": str(tmp_path / "portable"), "NEUROFLOW_JOBS_ROOT": ""}
        with patch.dict("os.environ", env, clear=False):
            assert paths.jobs_root() == tmp_path / "portable" / "outputs" / "jobs"

    def test_license_root_from_env(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {"NEUROFLOW_LICENSE_ROOT": str(tmp_path / "my-licenses")}, clear=False):
            assert paths.license_root() == tmp_path / "my-licenses"

    def test_license_root_from_portable_root(self, tmp_path: Path) -> None:
        env = {"NEUROFLOW_PORTABLE_ROOT": str(tmp_path / "portable"), "NEUROFLOW_LICENSE_ROOT": ""}
        with patch.dict("os.environ", env, clear=False):
            assert paths.license_root() == tmp_path / "portable" / "licenses"

    def test_worker_command_uses_sys_executable_in_dev(self) -> None:
        with patch.object(paths, "is_frozen", return_value=False):
            cmd = paths.worker_command("/tmp/job_config.json")
            assert cmd == [sys.executable, "-m", "pipeline.job_worker", "--job-config", "/tmp/job_config.json"]

    def test_worker_command_uses_exe_when_frozen(self) -> None:
        with patch.object(paths, "is_frozen", return_value=True):
            with patch.object(sys, "executable", r"C:\NeuroFlow\backend\neuroflow-backend.exe"):
                cmd = paths.worker_command(r"C:\jobs\job1\job_config.json")
                assert cmd == [
                    r"C:\NeuroFlow\backend\neuroflow-backend.exe",
                    "worker",
                    "--job-config",
                    r"C:\jobs\job1\job_config.json",
                ]

    def test_backend_cwd_returns_portable_root_when_set(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {"NEUROFLOW_PORTABLE_ROOT": str(tmp_path / "portable")}, clear=False):
            paths._ENV_CACHE = {}
            assert paths.backend_cwd() == tmp_path / "portable"

    def test_is_frozen_false_in_normal_python(self) -> None:
        assert paths.is_frozen() is False


class TestConfigStorePortable:
    def test_respects_config_root_env(self, tmp_path: Path) -> None:
        custom_root = tmp_path / "custom-configs"
        store = ConfigStore(config_root=custom_root)

        saved = store.save_workspace("test", {"key": "value"})
        assert saved["ok"] is True
        assert (custom_root / "workspaces" / "test.json").exists()

    def test_uses_portable_config_root_from_env(self, tmp_path: Path) -> None:
        env = {"NEUROFLOW_CONFIG_ROOT": str(tmp_path / "portable-configs")}
        with patch.dict("os.environ", env, clear=False):
            store = ConfigStore()

            saved = store.save_workspace("test", {"key": "value"})
            assert saved["ok"] is True
            assert (tmp_path / "portable-configs" / "workspaces" / "test.json").exists()


class TestLocalJobServicePortable:
    def test_respects_jobs_root_env(self, tmp_path: Path) -> None:
        custom_root = tmp_path / "custom-jobs"
        runner = _FakeProcessRunner()
        service = LocalJobService(jobs_root=custom_root, process_runner=runner, clock=lambda: 100.0)

        result = service.start_local_job(_simple_request(tmp_path))
        assert result["ok"] is True
        assert (custom_root / "job_registry.json").exists()

    def test_uses_portable_jobs_root_from_env(self, tmp_path: Path) -> None:
        env = {"NEUROFLOW_JOBS_ROOT": str(tmp_path / "portable-jobs")}
        with patch.dict("os.environ", env, clear=False):
            runner = _FakeProcessRunner()
            service = LocalJobService(process_runner=runner, clock=lambda: 100.0)

            result = service.start_local_job(_simple_request(tmp_path))
            assert result["ok"] is True
            assert (tmp_path / "portable-jobs" / "job_registry.json").exists()

    def test_uses_worker_command_for_frozen_mode(self, tmp_path: Path) -> None:
        runner = _FakeProcessRunner()
        service = LocalJobService(jobs_root=tmp_path / "jobs", process_runner=runner, clock=lambda: 100.0)

        with patch.object(paths, "is_frozen", return_value=True):
            with patch.object(sys, "executable", r"C:\backend\neuroflow-backend.exe"):
                service.start_local_job(_simple_request(tmp_path))

        cmd = runner.commands[0]
        assert cmd[0] == r"C:\backend\neuroflow-backend.exe"
        assert cmd[1] == "worker"
        assert "--job-config" in cmd


class TestLicenseStorePortable:
    def test_respects_license_root_env(self, tmp_path: Path) -> None:
        custom_root = tmp_path / "custom-licenses"
        store = LicenseStore(root=custom_root)

        assert store.root == custom_root

    def test_uses_portable_license_root_from_env(self, tmp_path: Path) -> None:
        env = {"NEUROFLOW_LICENSE_ROOT": str(tmp_path / "portable-licenses")}
        with patch.dict("os.environ", env, clear=False):
            store = LicenseStore()

            assert store.root == tmp_path / "portable-licenses"


class _FakeProcessRunner:
    def __init__(self, pid: int = 4321) -> None:
        self.pid = pid
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> ProcessHandle:
        self.commands.append(command)
        return ProcessHandle(pid=self.pid)


def _simple_request(tmp_path: Path) -> dict[str, object]:
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
