from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from ui.job_registry import JobRegistryController
from ui.gui_config import ConfigController
from ui.gui_pipeline import PipelineController

def test_job_registry_identity_and_merge():
    # JobRegistryController just needs a mock gui
    ctrl = JobRegistryController(MagicMock())
    
    job1 = {"job_id": "123", "state": "running", "target": "Local"}
    job2 = {"job_dir": "/path/to/job", "state": "completed"}
    job3 = {"remote_job_dir": "/remote/job", "state": "failed"}
    
    # Test _job_identity
    assert ctrl._job_identity(job1) == "123"
    assert ctrl._job_identity(job2) == "/path/to/job"
    assert ctrl._job_identity(job3) == "/remote/job"
    
    # Test _merge_job_lists
    # list 1 has an older state for job1, list 2 has newer state
    list1 = [job1, job2]
    list2 = [{"job_id": "123", "state": "completed", "extra": "data"}, job3]
    
    merged = ctrl._merge_job_lists(list1, list2)
    
    assert len(merged) == 3
    # Check that job1 was updated with data from list2
    merged_job1 = next(j for j in merged if ctrl._job_identity(j) == "123")
    assert merged_job1["state"] == "completed"
    assert merged_job1["extra"] == "data"
    assert merged_job1["target"] == "Local" # Retained from list1

def test_config_controller_collect_run_config():
    mock_gui = MagicMock()
    # Setup the state mock to return predictable values
    mock_gui.state.pipeline_mode.get.return_value = "FreeSurfer 7"
    mock_gui.state.get_selected_tools.return_value = {"segmentation": "recon-all"}
    mock_gui.state.get_stats_vector_config.return_value = {"enable": True}
    
    ctrl = ConfigController(mock_gui)
    
    config = ctrl._collect_run_config()
    
    assert config["version"] == 1
    assert config["type"] == "mri-pipeline-preset"
    assert config["pipeline_mode"] == "FreeSurfer 7"
    assert config["tools"]["segmentation"] == "recon-all"
    assert config["stats_vectors"]["enable"] is True

def test_config_controller_apply_run_config(mocker):
    mock_gui = MagicMock()
    mock_gui._normalize_pipeline_mode.side_effect = lambda x: x # pass-through mock
    
    # Setup mock tool variables in state
    mock_tool_var = MagicMock()
    mock_gui.state.tool_vars = {"segmentation": mock_tool_var}
    
    ctrl = ConfigController(mock_gui)
    
    # Mock registry functions to simulate tool validation
    mocker.patch("ui.gui_config.tool_key_from_display", return_value="freesurfer-7.4.1")
    mocker.patch("ui.gui_config.is_tool_enabled", return_value=True)
    mocker.patch("ui.gui_config.tool_display_name", return_value="FreeSurfer 7.4.1")
    
    config = {
        "pipeline_mode": "Custom",
        "tools": {"segmentation": "FreeSurfer 7.4.1"},
        "stats_vectors": {"enable": False}
    }
    
    ctrl._apply_run_config(config)
    
    # Verify pipeline mode was set
    mock_gui.state.pipeline_mode.set.assert_called_with("Custom")
    
    # Verify the tool variable was set to the display name
    mock_tool_var.set.assert_called_with("FreeSurfer 7.4.1")
    
    # Verify stats vector was applied
    mock_gui.state.apply_stats_vector_config.assert_called_with({"enable": False})
    
    # Verify downstream UI update methods were called
    mock_gui._apply_pipeline_mode.assert_called_with(apply_stats_preset=False)
    mock_gui.validation_ctrl._validate_configuration.assert_called_once()


def test_configure_batch_opens_batch_window_with_gui_root(mocker) -> None:
    mock_gui = MagicMock()
    ctrl = ConfigController(mock_gui)
    batch_window = mocker.patch("ui.batch_window.BatchConfigWindow")

    ctrl._configure_batch()

    batch_window.assert_called_once_with(mock_gui.root, mock_gui)


def test_upload_remote_job_dialog_receives_runner(mocker) -> None:
    mock_gui = MagicMock()
    ctrl = PipelineController(mock_gui)
    runner = MagicMock()
    dialog = mocker.patch("ui.dialogs.job_dialogs.show_upload_remote_job_dialog", return_value=True)

    assert ctrl._upload_remote_job_with_dialog(runner) is True

    dialog.assert_called_once_with(ctrl, runner)


def test_delete_active_registry_job_stops_jobs_controller_monitor(mocker) -> None:
    mock_gui = MagicMock()
    active_job = {"job_id": "active", "state": "completed", "target": "Local"}
    mock_gui.jobs_ctrl.active_job = active_job
    ctrl = JobRegistryController(mock_gui)
    mocker.patch("ui.job_registry.load_job_registry", return_value=[active_job])
    mocker.patch("ui.job_registry.save_job_registry")

    assert ctrl._delete_registry_job(active_job) is True

    mock_gui.jobs_ctrl.stop_current_job_monitor.assert_called_once_with()
    mock_gui.jobs_ctrl.delete_local_job_folders.assert_called_once_with(active_job)


def test_remote_jobs_for_current_server_uses_jobs_controller_auth(mocker) -> None:
    mock_gui = MagicMock()
    mock_gui.remote_ctrl._require_remote_connection.return_value = True
    mock_gui.jobs_ctrl.ensure_remote_auth_for_job_action.return_value = True
    ssh_config = MagicMock(host="host", port=22, username="user", key_path="")
    mock_gui.jobs_ctrl.build_ssh_config.return_value = ssh_config
    mock_gui.state.remote_workspace.get.return_value = "~/mri-remote-jobs"
    mock_gui.state.remote_python.get.return_value = "python3"
    mock_gui.state.output_dir.get.return_value = "/tmp/out"
    runner = MagicMock()
    runner.list_background_jobs.return_value = []
    remote_runner = mocker.patch("ui.job_registry.RemoteRunner", return_value=runner)
    mocker.patch("ui.job_registry.load_job_registry", return_value=[])
    ctrl = JobRegistryController(mock_gui)

    assert ctrl._remote_jobs_for_current_server() == []

    mock_gui.jobs_ctrl.ensure_remote_auth_for_job_action.assert_called_once_with("Resume or Attach job")
    mock_gui.jobs_ctrl.build_ssh_config.assert_called_once_with()
    remote_runner.assert_called_once()


def test_pipeline_gui_validate_configuration_facade(mocker) -> None:
    mocker.patch.dict("sys.modules", {"sv_ttk": MagicMock()})
    from ui.main import PipelineGUI

    gui = PipelineGUI.__new__(PipelineGUI)
    gui.validation_ctrl = MagicMock()
    gui.validation_ctrl._validate_configuration.return_value = True

    assert gui._validate_configuration() is True
    gui.validation_ctrl._validate_configuration.assert_called_once_with()
