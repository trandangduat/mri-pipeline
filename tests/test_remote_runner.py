import pytest
from pathlib import Path
from remote.remote_runner import RemoteRunner, RemoteRunConfig
from remote.ssh_client import SSHConfig

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
    
    # We expect a ValueError before SSH is even attempted due to the local guardrail
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
