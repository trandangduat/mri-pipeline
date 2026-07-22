from __future__ import annotations

import tkinter as tk
import pytest
from unittest.mock import MagicMock
from ui.gui_progress import ProgressController

def test_progress_title_for_job(mocker):
    mocker.patch("tkinter.StringVar")
    mocker.patch("tkinter.DoubleVar")
    gui_mock = MagicMock()
    ctrl = ProgressController(gui_mock)
    
    assert ctrl._progress_title_for_job(None) == "Run progress"
    assert ctrl._progress_title_for_job(None, fallback="Custom fallback") == "Custom fallback"
    
    job_local = {"target": "Local", "job_dir": "/path/to/my_job_123", "state": "running"}
    assert ctrl._progress_title_for_job(job_local) == "Local: my_job_123 (running)"
    
    job_remote = {"run_target": "Server", "remote_job_dir": "/remote/job_456", "state": "done"}
    assert ctrl._progress_title_for_job(job_remote) == "Server: job_456 (done)"
    
    job_unknown = {"job_id": "job_789"}
    # fallback to "Job" if no target is specified, and "job_789" is used
    assert ctrl._progress_title_for_job(job_unknown) == "Job: job_789"

def test_unique_progress_title(mocker):
    mocker.patch("tkinter.StringVar")
    mocker.patch("tkinter.DoubleVar")
    gui_mock = MagicMock()
    ctrl = ProgressController(gui_mock)
    
    # Mock progress contexts
    ctrl.progress_contexts = {
        "ctx1": {"title": "Local: my_job_123 (running)"},
        "ctx2": {"title": "Local: my_job_123 (running) #2"},
    }
    
    # New identical title gets #3
    assert ctrl._unique_progress_title("Local: my_job_123 (running)") == "Local: my_job_123 (running) #3"
    
    # If the context is updating its own title, it doesn't conflict with itself
    assert ctrl._unique_progress_title("Local: my_job_123 (running)", context_id="ctx1") == "Local: my_job_123 (running)"
    
    # Different title gets returned as is
    assert ctrl._unique_progress_title("Server: other_job (done)") == "Server: other_job (done)"


def test_append_log_ignores_destroyed_context_widget(mocker) -> None:
    mocker.patch("tkinter.StringVar")
    mocker.patch("tkinter.DoubleVar")
    ctrl = ProgressController(MagicMock())
    widget = MagicMock()
    widget.winfo_exists.return_value = False
    ctrl.progress_contexts = {"ctx": {"log_text": widget}}
    ctrl.active_progress_context_id = "ctx"
    ctrl.log_text = widget

    ctrl._append_log("download started")

    widget.configure.assert_not_called()
    assert ctrl.progress_contexts["ctx"]["log_text"] is None
    assert ctrl.log_text is None


def test_append_log_clears_stale_widget_after_tk_error(mocker) -> None:
    mocker.patch("tkinter.StringVar")
    mocker.patch("tkinter.DoubleVar")
    ctrl = ProgressController(MagicMock())
    widget = MagicMock()
    widget.winfo_exists.return_value = True
    widget.configure.side_effect = tk.TclError("invalid command name")
    ctrl.progress_contexts = {"ctx": {"log_text": widget}}
    ctrl.active_progress_context_id = "ctx"
    ctrl.log_text = widget

    ctrl._append_log("download started")

    assert ctrl.progress_contexts["ctx"]["log_text"] is None
    assert ctrl.log_text is None
