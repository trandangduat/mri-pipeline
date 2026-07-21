import pytest
import subprocess
import time
import os

@pytest.fixture(scope="session")
def dummy_ssh_server():
    """Spins up a local docker container running an SSH server."""
    image_name = "mri-dummy-ssh"
    container_name = "mri_test_ssh"
    
    # Check if docker is available
    try:
        subprocess.run(["docker", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Docker not available. Skipping integration tests.")
        
    dockerfile_dir = os.path.join(os.path.dirname(__file__), "dummy_ssh")
    # Build image
    subprocess.run(["docker", "build", "-t", image_name, dockerfile_dir], check=True)
    
    # Remove existing container if any
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
    
    # Run container
    port = "2222"
    subprocess.run([
        "docker", "run", "-d", "-p", f"{port}:22", "--name", container_name, image_name
    ], check=True, capture_output=True)
    
    # Wait for SSH to be ready
    time.sleep(2)
    
    yield {"host": "127.0.0.1", "port": int(port), "username": "tester", "password": "tester"}
    
    # Teardown
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
