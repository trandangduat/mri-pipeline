from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from pipeline.executor import LocalDockerExecutor, ExecutionRequest

def test_executor_command_generation(mocker):
    # Mock subprocess.Popen
    mock_popen = mocker.patch("pipeline.executor.subprocess.Popen")
    
    # Configure mock object to simulate a successful process execution
    mock_process = MagicMock()
    mock_process.communicate.return_value = ("Success output", "")
    mock_process.returncode = 0
    mock_popen.return_value = mock_process
    
    # Also mock threading to avoid the background monitor thread doing anything
    mocker.patch("pipeline.executor.threading.Thread.start")
    mocker.patch("pipeline.executor.threading.Thread.join")
    
    req = ExecutionRequest(
        image="freesurfer/freesurfer:7.4.1",
        args=["-sd", "/out", "-s", "sub-01", "-all"],
        mounts=[("/home/user/data", "/data"), ("/home/user/out", "/out")],
        command=["recon-all"],
        entrypoint="/bin/bash",
        env={"FS_LICENSE": "/license.txt"},
        gpus=True,
        memory_bytes=8000000000, # ~8GB
        container_name="mri-test-container"
    )
    
    executor = LocalDockerExecutor()
    result = executor.execute(req)
    
    assert result.success is True
    assert result.output == "Success output"
    
    # Check that Popen was called with the correct command array
    mock_popen.assert_called_once()
    cmd_called = mock_popen.call_args[0][0]
    
    # Verify standard docker run arguments
    assert cmd_called[0:3] == ["docker", "run", "--rm"]
    
    # Check for container name
    assert "--name" in cmd_called
    assert cmd_called[cmd_called.index("--name") + 1] == "mri-test-container"
    
    # Check GPUs
    assert "--gpus" in cmd_called
    assert cmd_called[cmd_called.index("--gpus") + 1] == "all"
    
    # Check memory
    assert "--memory" in cmd_called
    assert cmd_called[cmd_called.index("--memory") + 1] == "8000000000b"
    
    # Check mounts
    assert "-v" in cmd_called
    # Path might be abspath'd, so just check if it contains the mapping
    mounts = [cmd_called[i+1] for i, x in enumerate(cmd_called) if x == "-v"]
    assert any(m.endswith(":/data") for m in mounts)
    assert any(m.endswith(":/out") for m in mounts)
    
    # Check env
    assert "-e" in cmd_called
    assert cmd_called[cmd_called.index("-e") + 1] == "FS_LICENSE=/license.txt"
    
    # Check entrypoint
    assert "--entrypoint" in cmd_called
    assert cmd_called[cmd_called.index("--entrypoint") + 1] == "/bin/bash"
    
    # Check image and command and args (they should be at the end in order)
    image_index = cmd_called.index("freesurfer/freesurfer:7.4.1")
    assert cmd_called[image_index + 1] == "recon-all"
    assert cmd_called[image_index + 2:] == ["-sd", "/out", "-s", "sub-01", "-all"]
