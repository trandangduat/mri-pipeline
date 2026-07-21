import pytest
from unittest.mock import MagicMock
from ui.gui_remote import RemoteController

def test_current_remote_connection_signature():
    gui_mock = MagicMock()
    
    # Missing host
    gui_mock.state.remote_host.get.return_value = ""
    gui_mock.state.remote_username.get.return_value = "user"
    gui_mock.state.remote_workspace.get.return_value = "/remote"
    ctrl = RemoteController(gui_mock)
    assert ctrl._current_remote_connection_signature() is None
    
    # Valid
    gui_mock.state.remote_host.get.return_value = "10.0.0.1"
    gui_mock.state.remote_username.get.return_value = "admin"
    gui_mock.state.remote_workspace.get.return_value = ""
    gui_mock.state.remote_port.get.return_value = "2222"
    gui_mock.state.remote_key_path.get.return_value = "/path/to/key.pem"
    
    assert ctrl._current_remote_connection_signature() == (
        "10.0.0.1", 
        2222, 
        "admin", 
        "/path/to/key.pem", 
        "~/mri-remote-jobs" # fallback if workspace is empty
    )
    
    # Invalid port
    gui_mock.state.remote_port.get.return_value = "invalid"
    assert ctrl._current_remote_connection_signature() is None

def test_ssh_config_from_current_remote():
    gui_mock = MagicMock()
    
    gui_mock.state.remote_host.get.return_value = "10.0.0.1"
    gui_mock.state.remote_username.get.return_value = "admin"
    gui_mock.state.remote_port.get.return_value = "22"
    gui_mock.state.remote_password.get.return_value = "secret"
    gui_mock.state.remote_key_path.get.return_value = "/path/to/key.pem"
    
    ctrl = RemoteController(gui_mock)
    
    config = ctrl._ssh_config_from_current_remote()
    assert config is not None
    assert config.host == "10.0.0.1"
    assert config.port == 22
    assert config.username == "admin"
    assert config.password == "secret"
    assert config.key_path == "/path/to/key.pem"
