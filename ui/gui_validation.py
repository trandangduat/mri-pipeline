from __future__ import annotations

from ui.events import ui_events, EVENT_LOG_MESSAGE
import tkinter as tk
import os
from dataclasses import dataclass
from pathlib import Path

# Imports for validation
from pipeline.config import STAT_VECTOR_DEFS
from pipeline.registry import STAGE_ORDER, TOOL_DEFS, enabled_tools_for_stage, is_tool_enabled, tool_display_name
from pipeline.presets import VOLUME_SKIPPED_STAGES
from pipeline.discovery import _is_supported_mri_input


@dataclass(frozen=True)
class RunReadinessCondition:
    key: str
    name: str
    location: str
    status: str
    status_kind: str
    details: str
    required: bool = True
    failure: str = ""

    @property
    def ok(self) -> bool:
        return self.status_kind == "ok"

    @property
    def failure_message(self) -> str:
        return self.failure if self.required and not self.ok else ""


class ValidationController:
    def __init__(self, gui):
        self.gui = gui

    def _setup_validation_traces(self) -> None:
        variables = [
            self.gui.state.input_source,
            self.gui.state.input_mode,
            self.gui.state.input_path,
            self.gui.state.output_dir,
            self.gui.state.license_dir,
            self.gui.state.device,
            self.gui.state.threads,
            self.gui.state.ram_percent,
            self.gui.state.non_recursive,
            self.gui.state.run_target,
            self.gui.state.remote_host,
            self.gui.state.remote_port,
            self.gui.state.remote_username,
            self.gui.state.remote_key_path,
            self.gui.state.remote_workspace,
            self.gui.state.remote_python,
            self.gui.state.pipeline_mode,
            self.gui.state.export_outputs_enabled,
            self.gui.state.export_default_format,
        ]
        for var in variables:
            var.trace_add("write", lambda *_args: self._validate_configuration())
    
        self.gui.state.run_target.trace_add("write", lambda *_args: self.gui._update_python_env_hint())
        self.gui.state.remote_workspace.trace_add("write", lambda *_args: self.gui._update_python_env_hint())
        self.gui.state.threads.trace_add("write", lambda *_args: self._clamp_threads())
        for var in (
            self.gui.state.remote_host,
            self.gui.state.remote_port,
            self.gui.state.remote_username,
            self.gui.state.remote_password,
            self.gui.state.remote_key_path,
            self.gui.state.remote_workspace,
        ):
            var.trace_add("write", lambda *_args: self.gui.remote_ctrl._invalidate_remote_thread_max())
    
        self.gui.state.input_path.trace_add("write", self.gui._refresh_input_label)
    
        def _on_tool_selection_changed(*_args):
            if getattr(self.gui, "_is_applying_preset", False) or getattr(self, "_is_applying_preset", False):
                self._validate_configuration()
                self.gui.tools_ctrl._update_config_status_labels()
                return
            mode = self.gui._normalize_pipeline_mode(self.gui.state.pipeline_mode.get())
            if mode != "Custom":
                self._is_applying_preset = True
                try:
                    # Switching to Custom keeps the tool the user just picked.
                    self.gui.state.pipeline_mode.set("Custom")
                finally:
                    self._is_applying_preset = False
            self._validate_configuration()
            self.gui.tools_ctrl._update_config_status_labels()
    
        for tool_var in self.gui.state.tool_vars.values():
            tool_var.trace_add("write", _on_tool_selection_changed)
    
        for var in [*self.gui.state.export_name_vars.values(), *self.gui.state.export_format_vars.values()]:
            var.trace_add("write", lambda *_args: self._validate_configuration())
    
        def _on_stat_vector_changed(*_args):
            if getattr(self.gui, "_is_applying_preset", False) or getattr(self, "_is_applying_preset", False):
                return
            mode = self.gui._normalize_pipeline_mode(self.gui.state.pipeline_mode.get())
            self._is_applying_preset = True
            try:
                if mode != "Custom":
                    self.gui.state.pipeline_mode.set("Custom")
                    # Nested apply clears the flag; restore before syncing tools.
                    self._is_applying_preset = True
                # Keep steps 7-8 skipped unless cortical thickness is selected.
                self.gui._sync_surface_stages_with_stats()
            finally:
                self._is_applying_preset = False
            self.gui._sync_tool_combo_states()
            self.gui.tools_ctrl._update_config_status_labels()
            self._validate_configuration()
    
        for var in self.gui.state.stat_vector_enabled_vars.values():
            var.trace_add("write", _on_stat_vector_changed)
        for var in self.gui.state.stat_atlas_choice_vars.values():
            var.trace_add("write", lambda *_args: self._validate_configuration())
    
    def run_readiness_conditions(self) -> list[RunReadinessCondition]:
        conditions: list[RunReadinessCondition] = []
        input_source = self.gui.state.input_source.get()
        target = self.gui.state.run_target.get()

        def add(
            key: str,
            name: str,
            location: str,
            ok: bool,
            failure: str,
            details: str,
            required: bool = True,
            not_required: bool = False,
        ) -> None:
            if not_required:
                return
            elif ok:
                status = "OK"
                status_kind = "ok"
            else:
                status = "Not done"
                status_kind = "not_done"
            conditions.append(RunReadinessCondition(key, name, location, status, status_kind, details, required, failure))

        remote_errors: list[str] = []
        if self.gui.state.run_target.get() == "Server":
            if not self.gui.state.remote_host.get().strip():
                remote_errors.append("Remote Host/IP is required.")
            if not self.gui.state.remote_username.get().strip():
                remote_errors.append("Remote Username is required.")
            try:
                port = int(self.gui.state.remote_port.get())
                if port < 1 or port > 65535:
                    remote_errors.append("Remote port must be between 1 and 65535.")
            except (tk.TclError, ValueError):
                remote_errors.append("Remote port must be a valid integer.")
            if not self.gui.state.remote_workspace.get().strip():
                remote_errors.append("Remote workspace is required.")
            elif self.gui.remote_ctrl._current_remote_connection_signature() is not None and not self.gui.remote_ctrl._server_connected():
                remote_errors.append("Connect to the server before running.")
        add(
            "server_connection",
            "Server connection",
            "Pipeline configuration > Server",
            not remote_errors,
            remote_errors[0] if remote_errors else "Server connection is not ready.",
            "What: enter server host, username, port, workspace, then connect.\nWhere: Pipeline configuration > Server.",
            not_required=target != "Server",
        )
    
        mode = self.gui.state.input_mode.get()
        raw_input = self.gui.state.input_path.get().strip()
        input_errors: list[str] = []
        if not raw_input:
            input_errors.append("Choose an input MRI file or folder.")
        elif self.gui.state.run_target.get() != "Server" and input_source != "Local":
            input_errors.append("Local runs can only use local input data.")
        elif input_source == "Server" and self.gui.state.run_target.get() != "Server":
            input_errors.append("Server input requires Run on = Server.")
        elif input_source == "Local" and mode == "file":
            path = self.gui.state.selected_files[0] if self.gui.state.selected_files else raw_input
            if not _is_supported_mri_input(path):
                input_errors.append("Input file or DICOM folder does not exist.")
        elif input_source == "Local" and mode == "files":
            files = self.gui.state.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
            if not files:
                input_errors.append("Choose at least one input file.")
            elif any(not _is_supported_mri_input(p) for p in files):
                input_errors.append("One or more selected input files or DICOM folders do not exist.")
        elif input_source == "Local":
            if not Path(raw_input).is_dir():
                input_errors.append("Input folder does not exist.")
        elif input_source == "Server":
            files = self.gui.state.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
            if mode == "file" and raw_input == "~" and not self.gui.state.selected_files:
                input_errors.append("Choose a server MRI file or upload input to server first.")
            elif mode == "files" and (not files or files == ["~"]):
                input_errors.append("Choose server MRI files or upload input to server first.")
            elif mode == "dir" and raw_input == "~" and not self.gui.state.selected_files:
                input_errors.append("Choose a server MRI folder or upload input to server first.")
        add(
            "input",
            "Input selected",
            "Pipeline configuration > Input",
            not input_errors,
            input_errors[0] if input_errors else "Input is not ready.",
            "What: choose a supported MRI file, files, DICOM folder, or batch folder.\nWhere: Pipeline configuration > Input.",
        )
    
        output_errors: list[str] = []
        if self.gui.state.run_target.get() != "Server" and not self.gui.state.output_dir.get().strip():
            output_errors.append("Choose an output directory.")
        add(
            "output",
            "Output directory",
            "Pipeline configuration > Output",
            not output_errors,
            output_errors[0] if output_errors else "Output directory is not ready.",
            "What: choose where local pipeline outputs will be written.\nWhere: Pipeline configuration > Output.",
            not_required=target == "Server",
        )

        export_errors: list[str] = []
        if self.gui.state.export_outputs_enabled.get():
            invalid_names = [name.get().strip() for name in self.gui.state.export_name_vars.values() if not name.get().strip() or any(sep in name.get() for sep in ("/", "\\"))]
            if invalid_names:
                export_errors.append("Export file names cannot be empty or contain path separators.")
        add(
            "export_names",
            "Export names",
            "Pipeline configuration > Export",
            not export_errors,
            export_errors[0] if export_errors else "Export names are not ready.",
            "What: keep export file names non-empty and without path separators.\nWhere: Pipeline configuration > Export.",
            not_required=not self.gui.state.export_outputs_enabled.get(),
        )

        stats_errors: list[str] = []
        for stat, stat_def in STAT_VECTOR_DEFS.items():
            if self.gui.state.stat_vector_enabled_vars.get(stat) and self.gui.state.stat_vector_enabled_vars[stat].get():
                if stat_def.get("atlases") and not self.gui.state.selected_atlases_for_stat(stat):
                    stats_errors.append(f"Choose at least one atlas for {stat_def['label']}.")
        add(
            "stats_vectors",
            "Stats vector atlases",
            "Pipeline configuration > Stats vectors",
            not stats_errors,
            stats_errors[0] if stats_errors else "Stats vector atlases are not ready.",
            "What: select an atlas for each enabled stats vector that requires one.\nWhere: Pipeline configuration > Stats vectors.",
            not_required=not any(var.get() for var in self.gui.state.stat_vector_enabled_vars.values()),
        )

        runtime_errors: list[str] = []
        try:
            threads = int(self.gui.state.threads.get())
            if threads < 1:
                runtime_errors.append("Threads must be at least 1.")
            elif self.gui.state.run_target.get() == "Server" and self.gui.remote_ctrl._server_connected() and not self.gui.remote_ctrl._server_thread_max_known():
                runtime_errors.append("Connect Server could not read the server CPU thread limit.")
            elif self.gui.max_threads is not None and threads > self.gui.max_threads:
                runtime_errors.append(f"Threads cannot exceed max CPU threads ({self.gui.max_threads}).")
        except (tk.TclError, ValueError):
            runtime_errors.append("Threads must be a valid integer.")
    
        try:
            ram_percent = int(self.gui.state.ram_percent.get())
            if ram_percent < 1 or ram_percent > 100:
                runtime_errors.append("RAM % must be between 1 and 100.")
        except (tk.TclError, ValueError):
            runtime_errors.append("RAM % must be a valid integer.")
        add(
            "runtime",
            "Threads and RAM",
            "Pipeline configuration > Advanced Settings",
            not runtime_errors,
            runtime_errors[0] if runtime_errors else "Runtime settings are not ready.",
            "What: keep threads within the available CPU limit and RAM between 1 and 100%.\nWhere: Pipeline configuration > Advanced Settings.",
        )
    
        selected_tools = self.gui.state.get_selected_tools()
        missing_stages = [
            stage for stage in STAGE_ORDER
            if stage not in VOLUME_SKIPPED_STAGES and enabled_tools_for_stage(stage) and not selected_tools.get(stage)
        ]
        tool_errors: list[str] = []
        if missing_stages:
            tool_errors.append("Select one tool for every pipeline stage.")
        disabled_tools = [tool for tool in selected_tools.values() if tool and not is_tool_enabled(tool)]
        if disabled_tools:
            tool_errors.append(f"Disabled tools selected: {', '.join(tool_display_name(tool) for tool in disabled_tools)}")
        add(
            "pipeline_tools",
            "Pipeline tools",
            "Pipeline configuration > Pipeline Tools",
            not tool_errors,
            tool_errors[0] if tool_errors else "Pipeline tools are not ready.",
            "What: choose one enabled tool for every required pipeline stage.\nWhere: Pipeline configuration > Pipeline Tools.",
        )
    
        image_statuses = self.gui.tools_ctrl.image_statuses.setdefault(target, {})
        required_images: list[str] = []
        for tool in selected_tools.values():
            image = str(TOOL_DEFS.get(tool, {}).get("image", ""))
            if tool and is_tool_enabled(tool) and image and image not in required_images:
                required_images.append(image)
        image_check_required = bool(required_images and (target != "Server" or self.gui.remote_ctrl._server_connected()))
        unknown = [image for image in required_images if image_statuses.get(image, "Unknown") == "Unknown"] if image_check_required else []
        not_installed = [image for image in required_images if image_statuses.get(image, "Unknown") not in {"Installed", "Unknown"}] if image_check_required else []
        add(
            "docker_checked",
            "Docker images checked",
            "Tools / Docker Images > Refresh",
            image_check_required and not unknown,
            "Check Docker images before running.",
            "What: verify selected Docker images on the selected target.\nWhere: Tools / Docker Images > Refresh.",
            not_required=not image_check_required,
        )
        missing_names = ", ".join(not_installed[:2]) + ("..." if len(not_installed) > 2 else "")
        add(
            "docker_installed",
            "Docker images installed",
            "Tools / Docker Images > Download",
            image_check_required and not unknown and not not_installed,
            f"Install selected Docker images before running{': ' + missing_names if missing_names else '.'}",
            "What: download every selected tool image that is missing.\nWhere: Tools / Docker Images > Select Missing > Download.",
            not_required=not image_check_required,
        )
    
        needs_license = any(TOOL_DEFS.get(tool, {}).get("needs_license") for tool in selected_tools.values())
        add(
            "freesurfer_license",
            "FreeSurfer license",
            "Pipeline configuration > FreeSurfer license",
            not needs_license or Path(self.gui.state.license_dir.get().strip()).exists(),
            "FreeSurfer license directory is required for selected tools.",
            "What: choose a folder containing the FreeSurfer license file.\nWhere: Pipeline configuration > FreeSurfer license.",
            not_required=not needs_license,
        )

        return conditions

    def _validate_configuration(self) -> bool:
        conditions = self.run_readiness_conditions()
        errors = [condition.failure_message for condition in conditions if condition.failure_message]
    
    
    
        ok = not errors
        status_msg = "Configuration complete. Ready to run." if ok else errors[0]
    
        if getattr(self.gui, "run_button", None) is not None:
            if not self.gui._is_button_busy(self.gui.run_button):
                self.gui.run_button.configure(state=tk.NORMAL)
            if getattr(self.gui, "run_tooltip", None) is not None:
                self.gui.run_tooltip.update_text(status_msg)
        if getattr(self.gui.pipeline_ctrl, "restart_button", None) is not None:
            self.gui.pipeline_ctrl.restart_button.configure(state=tk.NORMAL if ok else tk.DISABLED)
            if getattr(self.gui.pipeline_ctrl, "restart_tooltip", None) is not None:
                self.gui.pipeline_ctrl.restart_tooltip.update_text(status_msg)
        
        self.gui.state.config_status.set(status_msg)
        
        # Check server connection state for specific buttons
        server_ok = self.gui.state.run_target.get() != "Server" or self.gui.remote_ctrl._server_connected()
        server_msg = "Please connect to the server first" if not server_ok else ""
        
        if self.gui.upload_input_button:
            self.gui.upload_input_button.configure(state=tk.NORMAL if server_ok else tk.DISABLED)
            if getattr(self.gui, "upload_input_tooltip", None) is not None:
                self.gui.upload_input_tooltip.update_text(server_msg)
                
        if self.gui.server_output_browse_button:
            self.gui.server_output_browse_button.configure(state=tk.NORMAL if server_ok else tk.DISABLED)
            if getattr(self.gui, "server_output_tooltip", None) is not None:
                self.gui.server_output_tooltip.update_text(server_msg)
                
        if self.gui.tools_ctrl.refresh_button:
            self.gui.tools_ctrl.refresh_button.configure(state=tk.NORMAL if server_ok else tk.DISABLED)
            if getattr(self.gui.tools_ctrl, "tools_refresh_tooltip", None) is not None:
                self.gui.tools_ctrl.tools_refresh_tooltip.update_text(server_msg)
                
        if self.gui.input_browse_button:
            if getattr(self.gui, "input_browse_tooltip", None) is not None:
                self.gui.input_browse_tooltip.update_text(server_msg)
    
        return ok
    


    def _validate_thread_input(self, proposed: str) -> bool:
        if self.gui.state.run_target.get() == "Server" and not self.gui.remote_ctrl._server_thread_max_known():
            return proposed == ""
        if proposed == "":
            return True
        try:
            value = int(proposed)
        except ValueError:
            return False
        if value < 1:
            return False
        return self.gui.max_threads is None or value <= self.gui.max_threads

    def _validate_ram_percent_input(self, proposed: str) -> bool:
        if proposed == "":
            return True
        try:
            value = int(proposed)
        except ValueError:
            return False
        return 1 <= value <= 100

    def _clamp_threads(self) -> None:
        if self.gui.max_threads is None:
            return
        try:
            value = int(self.gui.state.threads.get())
        except (tk.TclError, ValueError):
            return
        clamped = min(max(value, 1), self.gui.max_threads)

        if clamped != value:

            self.gui.state.threads.set(clamped)
