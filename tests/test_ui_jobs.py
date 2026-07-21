from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from ui.gui_jobs import JobsController
from ui.gui_tools import ToolsController

def test_ensure_remote_auth_for_job_action():
    mock_gui = MagicMock()
    # Setup state
    mock_gui.state.remote_password.get.return_value = ""
    mock_gui.state.remote_key_path.get.return_value = "/invalid/path/key.pem"
    
    # Notebook should be accessed through gui
    mock_gui.notebook = MagicMock()
    mock_gui.config_tab = MagicMock()
    
    ctrl = JobsController(mock_gui)
    
    # Mock messagebox to prevent popups and check if it was called
    with patch("ui.gui_jobs.messagebox.showwarning") as mock_msg:
        with patch.object(ctrl, "_remote_key_file_exists", return_value=False):
            result = ctrl._ensure_remote_auth_for_job_action("test action")
            
            assert result is False
            # Verify the key path was cleared
            mock_gui.state.remote_key_path.set.assert_called_with("")
            
            # Verify notebook selection was triggered (this fails if getattr uses 'self')
            mock_gui.notebook.select.assert_called_with(mock_gui.config_tab)
            
            # Verify warning was shown
            mock_msg.assert_called_once()


def test_set_image_status_validates_through_validation_controller(mocker) -> None:
    mocker.patch("ui.gui_tools.tk.StringVar", side_effect=lambda **kwargs: MagicMock())
    mock_gui = MagicMock()
    ctrl = ToolsController(mock_gui)
    ctrl._refresh_tree = MagicMock()
    ctrl._update_config_status_labels = MagicMock()

    ctrl._set_image_status("Server", "image:latest", "Installed")

    assert ctrl.image_statuses["Server"]["image:latest"] == "Installed"
    mock_gui.validation_ctrl._validate_configuration.assert_called_once_with()
