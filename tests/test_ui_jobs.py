from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ui.gui_jobs import JobsController
from ui.gui_progress import ProgressController
from ui.gui_tools import ToolsController


def test_ensure_remote_auth_for_job_action():
    mock_gui = MagicMock()
    mock_gui.state.remote_password.get.return_value = ""
    mock_gui.state.remote_key_path.get.return_value = "/invalid/path/key.pem"
    mock_gui.notebook = MagicMock()
    mock_gui.config_tab = MagicMock()

    ctrl = JobsController(mock_gui)

    with patch("ui.gui_jobs.messagebox.showwarning") as mock_msg:
        with patch.object(ctrl, "_remote_key_file_exists", return_value=False):
            result = ctrl._ensure_remote_auth_for_job_action("test action")

            assert result is False
            mock_gui.state.remote_key_path.set.assert_called_with("")
            mock_gui.notebook.select.assert_called_with(mock_gui.config_tab)
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


def test_register_job_monitor_uses_active_progress_context() -> None:
    gui = SimpleNamespace(
        progress_ctrl=SimpleNamespace(active_progress_context_id="ctx-fast"),
        pipeline_ctrl=SimpleNamespace(remote_runner=None),
    )
    ctrl = JobsController(gui)
    ctrl.active_job = {"target": "Local", "job_dir": "/tmp/job-fast"}
    ctrl.job_log_offset = 42

    ctrl._register_job_monitor_for_active_context()

    assert ctrl.job_monitors["ctx-fast"]["active_job"] is ctrl.active_job
    assert ctrl.job_monitors["ctx-fast"]["job_log_offset"] == 42


def test_activate_progress_context_loads_jobs_controller_monitor(mocker) -> None:
    mocker.patch("tkinter.StringVar", side_effect=lambda **kwargs: MagicMock())
    gui = SimpleNamespace()
    gui.state = SimpleNamespace()
    gui.jobs_ctrl = SimpleNamespace(
        active_job=None,
        job_log_offset=0,
        remote_poll_in_flight=False,
        job_poll_after_id=None,
        job_monitors={
            "ctx-fs7": {
                "active_job": {"target": "Local", "job_dir": "/tmp/job-fs7"},
                "remote_runner": "runner-fs7",
                "job_log_offset": 99,
                "remote_poll_in_flight": True,
                "after_id": "after-fs7",
            }
        },
    )
    gui.pipeline_ctrl = SimpleNamespace(remote_runner=None)
    ctrl = ProgressController(gui)
    mocker.patch.object(ctrl, "_save_active_progress_context")
    mocker.patch.object(ctrl, "_sync_progress_context_to_state")
    mocker.patch.object(ctrl, "_sync_runtime_settings_panel")
    ctrl.progress_contexts = {"ctx-fs7": {"tab": MagicMock()}}

    ctrl._activate_progress_context("ctx-fs7")

    assert gui.jobs_ctrl.active_job == {"target": "Local", "job_dir": "/tmp/job-fs7"}
    assert gui.pipeline_ctrl.remote_runner == "runner-fs7"
    assert gui.jobs_ctrl.job_log_offset == 99
    assert gui.jobs_ctrl.remote_poll_in_flight is True
    assert gui.jobs_ctrl.job_poll_after_id == "after-fs7"


def test_poll_active_job_restores_previously_active_context(mocker) -> None:
    class FakeProgressController:
        def __init__(self) -> None:
            self.active_progress_context_id = "ctx-fast"
            self.progress_contexts = {"ctx-fast": {}, "ctx-fs7": {}}

        def _activate_progress_context(self, context_id: str) -> dict:
            self.active_progress_context_id = context_id
            return self.progress_contexts[context_id]

        def _save_active_progress_context(self) -> None:
            return None

    progress_ctrl = FakeProgressController()
    gui = SimpleNamespace(
        progress_ctrl=progress_ctrl,
        pipeline_ctrl=SimpleNamespace(remote_runner="runner-fast", running=True),
        root=SimpleNamespace(after=MagicMock(return_value="after-new"), after_cancel=MagicMock()),
    )
    ctrl = JobsController(gui)
    ctrl.active_job = {"target": "Local", "job_dir": "/tmp/job-fast"}
    ctrl.job_log_offset = 5
    ctrl.job_poll_after_id = "after-fast"
    ctrl.job_monitors["ctx-fs7"] = {
        "context_id": "ctx-fs7",
        "active_job": {"target": "Local", "job_dir": "/tmp/job-fs7"},
        "remote_runner": None,
        "job_log_offset": 12,
        "after_id": "after-fs7",
        "remote_poll_in_flight": False,
    }
    mocker.patch.object(ctrl, "_poll_local_background_job", return_value=False)

    ctrl._poll_active_job("ctx-fs7")

    assert progress_ctrl.active_progress_context_id == "ctx-fast"
    assert ctrl.active_job == {"target": "Local", "job_dir": "/tmp/job-fast"}
    assert ctrl.job_log_offset == 5
    assert ctrl.job_poll_after_id == "after-fast"
    assert ctrl.job_monitors["ctx-fs7"]["job_log_offset"] == 12
