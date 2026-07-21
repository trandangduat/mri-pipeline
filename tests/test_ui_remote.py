from __future__ import annotations

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


def test_invalidate_remote_thread_max_uses_gui_request_state() -> None:
    gui_mock = MagicMock()
    gui_mock.state.run_target.get.return_value = "Server"
    gui_mock.state.remote_host.get.return_value = "new-host"
    gui_mock.state.remote_username.get.return_value = "user"
    gui_mock.state.remote_workspace.get.return_value = "~/mri-remote-jobs"
    gui_mock.state.remote_port.get.return_value = "22"
    gui_mock.state.remote_key_path.get.return_value = ""
    gui_mock._connected_remote_signature = ("old-host", 22, "user", "", "~/mri-remote-jobs")
    gui_mock._thread_max_request_id = 7
    gui_mock.tools_ctrl.image_statuses = {"Server": {"image": "Installed"}}
    gui_mock.tools_ctrl.image_installed_sizes = {"Server": {"image": "1 GB"}}
    gui_mock.tools_ctrl.checked_tools = set()

    ctrl = RemoteController(gui_mock)
    ctrl._cancel_remote_health_check = MagicMock()
    ctrl._set_remote_status_icon = MagicMock()
    ctrl._sync_remote_connection_controls = MagicMock()

    ctrl._invalidate_remote_thread_max()

    assert gui_mock._thread_max_request_id == 8
    gui_mock._set_thread_max.assert_called_once_with(None)
    gui_mock.validation_ctrl._validate_configuration.assert_called_once_with()
