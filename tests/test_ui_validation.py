from __future__ import annotations

import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import pytest
from unittest.mock import MagicMock
from ui.gui_validation import ValidationController
from pipeline.registry import STAGE_ORDER, TOOL_DEFS, enabled_tools_for_stage
from pipeline.presets import VOLUME_SKIPPED_STAGES


class Value:
    def __init__(self, value: Any) -> None:
        self.value = value

    def get(self) -> Any:
        return self.value

    def set(self, value: Any) -> None:
        self.value = value


def _selected_required_tools() -> dict[str, str]:
    selected: dict[str, str] = {}
    for stage in STAGE_ORDER:
        tools = enabled_tools_for_stage(stage)
        selected[stage] = "" if stage in VOLUME_SKIPPED_STAGES or not tools else tools[0]
    return selected


def _validation_gui(tmp_path: Path, image_status: str = "Unknown") -> SimpleNamespace:
    input_file = tmp_path / "subject.nii"
    input_file.write_bytes(b"")
    output_dir = tmp_path / "outputs"
    output_dir.mkdir()
    license_dir = tmp_path / "license"
    license_dir.mkdir()
    selected_tools = _selected_required_tools()
    image_statuses = {}
    for tool in selected_tools.values():
        image = str(TOOL_DEFS.get(tool, {}).get("image", ""))
        if image:
            image_statuses[image] = image_status

    state = SimpleNamespace(
        input_source=Value("Local"),
        input_mode=Value("file"),
        input_path=Value(str(input_file)),
        selected_files=[],
        output_dir=Value(str(output_dir)),
        license_dir=Value(str(license_dir)),
        run_target=Value("Local"),
        remote_host=Value(""),
        remote_username=Value(""),
        remote_port=Value(22),
        remote_workspace=Value("~/mri-remote-jobs"),
        export_outputs_enabled=Value(False),
        export_name_vars={},
        stat_vector_enabled_vars={},
        threads=Value(2),
        ram_percent=Value(90),
        get_selected_tools=lambda: selected_tools,
        selected_atlases_for_stat=lambda _stat: [],
        config_status=Value(""),
    )
    tools_ctrl = SimpleNamespace(
        image_statuses={"Local": image_statuses, "Server": {}},
        refresh_button=None,
        tools_refresh_tooltip=None,
    )
    remote_ctrl = SimpleNamespace(
        _current_remote_connection_signature=lambda: None,
        _server_connected=lambda: False,
        _server_thread_max_known=lambda: False,
    )
    return SimpleNamespace(
        state=state,
        tools_ctrl=tools_ctrl,
        remote_ctrl=remote_ctrl,
        max_threads=8,
        run_button=MagicMock(),
        run_tooltip=MagicMock(),
        pipeline_ctrl=SimpleNamespace(restart_button=None, restart_tooltip=None),
        upload_input_button=None,
        server_output_browse_button=None,
        input_browse_button=None,
        _is_button_busy=lambda _button: False,
    )

def test_validate_thread_input():
    mock_gui = MagicMock()
    mock_gui.state.run_target.get.return_value = "Local"
    mock_gui.max_threads = 8
    
    ctrl = ValidationController(mock_gui)
    
    # Valid inputs
    assert ctrl._validate_thread_input("") is True
    assert ctrl._validate_thread_input("1") is True
    assert ctrl._validate_thread_input("4") is True
    assert ctrl._validate_thread_input("8") is True
    
    # Invalid inputs
    assert ctrl._validate_thread_input("9") is False # exceeds max
    assert ctrl._validate_thread_input("0") is False # less than 1
    assert ctrl._validate_thread_input("-1") is False
    assert ctrl._validate_thread_input("abc") is False

def test_validate_thread_input_remote_unknown():
    mock_gui = MagicMock()
    mock_gui.state.run_target.get.return_value = "Server"
    mock_gui.remote_ctrl._server_thread_max_known.return_value = False
    
    ctrl = ValidationController(mock_gui)
    
    # When server thread max is unknown, we should only allow empty (which might revert to default or just block until known)
    assert ctrl._validate_thread_input("") is True
    assert ctrl._validate_thread_input("4") is False

def test_clamp_threads():
    mock_gui = MagicMock()
    mock_gui.max_threads = 16
    mock_gui.state.threads.get.return_value = "20"
    
    ctrl = ValidationController(mock_gui)
    ctrl._clamp_threads()
    
    # Should clamp 20 down to 16
    mock_gui.state.threads.set.assert_called_with(16)
    
    mock_gui.state.threads.get.return_value = "0"
    ctrl._clamp_threads()
    
    # Should clamp 0 up to 1
    mock_gui.state.threads.set.assert_called_with(1)


def test_docker_unknown_is_before_run_condition_but_run_button_stays_enabled(tmp_path):
    gui = _validation_gui(tmp_path, image_status="Unknown")
    ctrl = ValidationController(gui)

    by_key = {condition.key: condition for condition in ctrl.run_readiness_conditions()}

    assert by_key["docker_checked"].status_kind == "not_done"
    assert by_key["docker_installed"].status_kind == "not_done"
    assert ctrl._validate_configuration() is False
    gui.run_button.configure.assert_any_call(state=tk.NORMAL)


def test_missing_docker_image_is_before_run_condition(tmp_path):
    gui = _validation_gui(tmp_path, image_status="Installed")
    selected_image = next(iter(gui.tools_ctrl.image_statuses["Local"]))
    gui.tools_ctrl.image_statuses["Local"][selected_image] = "Missing"
    ctrl = ValidationController(gui)

    by_key = {condition.key: condition for condition in ctrl.run_readiness_conditions()}

    assert by_key["docker_checked"].status_kind == "ok"
    assert by_key["docker_installed"].status_kind == "not_done"
    assert "Install selected Docker images" in by_key["docker_installed"].failure_message


def test_validation_passes_when_required_images_are_installed(tmp_path):
    gui = _validation_gui(tmp_path, image_status="Installed")
    ctrl = ValidationController(gui)

    assert ctrl._validate_configuration() is True
    assert gui.state.config_status.get() == "Configuration complete. Ready to run."
    gui.run_button.configure.assert_any_call(state=tk.NORMAL)


def test_local_run_omits_server_only_conditions(tmp_path):
    gui = _validation_gui(tmp_path, image_status="Installed")
    ctrl = ValidationController(gui)

    keys = {condition.key for condition in ctrl.run_readiness_conditions()}

    assert "server_connection" not in keys
    assert "export_names" not in keys
    assert "stats_vectors" not in keys


def test_server_run_reflects_server_conditions(tmp_path):
    gui = _validation_gui(tmp_path, image_status="Installed")
    gui.state.run_target.set("Server")
    gui.state.remote_host.set("")
    gui.state.remote_username.set("")
    ctrl = ValidationController(gui)

    by_key = {condition.key: condition for condition in ctrl.run_readiness_conditions()}

    assert by_key["server_connection"].status_kind == "not_done"
    assert "output" not in by_key
