from __future__ import annotations

import pytest
from pathlib import Path
from remote.remote_runner import RemoteRunner, RemoteRunConfig
from remote.ssh_client import SSHConfig


class FakeRemoteSSHClient:
    commands: list[str] = []

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
        return 0, ""

    def run(self, command: str, stream: bool = True, check: bool = False) -> int:
        self.commands.append(command)
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
