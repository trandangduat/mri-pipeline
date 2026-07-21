import tkinter as tk
import os
from pathlib import Path

# Imports for validation
from pipeline.config import STAT_VECTOR_DEFS, STAGE_ORDER, TOOL_DEFS, enabled_tools_for_stage, is_tool_enabled, tool_display_name, VOLUME_SKIPPED_STAGES
from pipeline.discovery import _is_supported_mri_input

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
            var.trace_add("write", lambda *_args: self.gui._validate_configuration())
    
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
            var.trace_add("write", lambda *_args: self._invalidate_remote_thread_max())
    
        self.gui.state.input_path.trace_add("write", self.gui._refresh_input_label)
    
        def _on_tool_selection_changed(*_args):
            if getattr(self, "_is_applying_preset", False):
                self.gui._validate_configuration()
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
            self.gui._validate_configuration()
            self.gui.tools_ctrl._update_config_status_labels()
    
        for tool_var in self.gui.state.tool_vars.values():
            tool_var.trace_add("write", _on_tool_selection_changed)
    
        for var in [*self.gui.state.export_name_vars.values(), *self.gui.state.export_format_vars.values()]:
            var.trace_add("write", lambda *_args: self.gui._validate_configuration())
    
        def _on_stat_vector_changed(*_args):
            if getattr(self, "_is_applying_preset", False):
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
            self.gui._validate_configuration()
    
        for var in self.gui.state.stat_vector_enabled_vars.values():
            var.trace_add("write", _on_stat_vector_changed)
        for var in self.gui.state.stat_atlas_choice_vars.values():
            var.trace_add("write", lambda *_args: self.gui._validate_configuration())
    
    def _validate_configuration(self) -> bool:
        errors: list[str] = []
        input_source = self.gui.state.input_source.get()
        if self.gui.state.run_target.get() == "Server":
            if not self.gui.state.remote_host.get().strip():
                errors.append("Remote Host/IP is required.")
            if not self.gui.state.remote_username.get().strip():
                errors.append("Remote Username is required.")
            try:
                port = int(self.gui.state.remote_port.get())
                if port < 1 or port > 65535:
                    errors.append("Remote port must be between 1 and 65535.")
            except (tk.TclError, ValueError):
                errors.append("Remote port must be a valid integer.")
            if not self.gui.state.remote_workspace.get().strip():
                errors.append("Remote workspace is required.")
            elif self.gui._current_remote_connection_signature() is not None and not self.gui._server_connected():
                errors.append("Connect to the server before running.")
    
        mode = self.gui.state.input_mode.get()
        raw_input = self.gui.state.input_path.get().strip()
        if not raw_input:
            errors.append("Choose an input MRI file or folder.")
        elif self.gui.state.run_target.get() != "Server" and input_source != "Local":
            errors.append("Local runs can only use local input data.")
        elif input_source == "Server" and self.gui.state.run_target.get() != "Server":
            errors.append("Server input requires Run on = Server.")
        elif input_source == "Local" and mode == "file":
            path = self.gui.state.selected_files[0] if self.gui.state.selected_files else raw_input
            if not _is_supported_mri_input(path):
                errors.append("Input file or DICOM folder does not exist.")
        elif input_source == "Local" and mode == "files":
            files = self.gui.state.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
            if not files:
                errors.append("Choose at least one input file.")
            elif any(not _is_supported_mri_input(p) for p in files):
                errors.append("One or more selected input files or DICOM folders do not exist.")
        elif input_source == "Local":
            if not Path(raw_input).is_dir():
                errors.append("Input folder does not exist.")
        elif input_source == "Server":
            files = self.gui.state.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
            if mode == "file" and raw_input == "~" and not self.gui.state.selected_files:
                errors.append("Choose a server MRI file or upload input to server first.")
            elif mode == "files" and (not files or files == ["~"]):
                errors.append("Choose server MRI files or upload input to server first.")
            elif mode == "dir" and raw_input == "~" and not self.gui.state.selected_files:
                errors.append("Choose a server MRI folder or upload input to server first.")
    
        if self.gui.state.run_target.get() != "Server" and not self.gui.state.output_dir.get().strip():
            errors.append("Choose an output directory.")
        if self.gui.state.export_outputs_enabled.get():
            invalid_names = [name.get().strip() for name in self.gui.state.export_name_vars.values() if not name.get().strip() or any(sep in name.get() for sep in ("/", "\\"))]
            if invalid_names:
                errors.append("Export file names cannot be empty or contain path separators.")
        for stat, stat_def in STAT_VECTOR_DEFS.items():
            if self.gui.state.stat_vector_enabled_vars.get(stat) and self.gui.state.stat_vector_enabled_vars[stat].get():
                if stat_def.get("atlases") and not self.gui.state.selected_atlases_for_stat(stat):
                    errors.append(f"Choose at least one atlas for {stat_def['label']}.")
        try:
            threads = int(self.gui.state.threads.get())
            if threads < 1:
                errors.append("Threads must be at least 1.")
            elif self.gui.state.run_target.get() == "Server" and self.gui._server_connected() and not self.gui._server_thread_max_known():
                errors.append("Connect Server could not read the server CPU thread limit.")
            elif self.gui.max_threads is not None and threads > self.gui.max_threads:
                errors.append(f"Threads cannot exceed max CPU threads ({self.gui.max_threads}).")
        except (tk.TclError, ValueError):
            errors.append("Threads must be a valid integer.")
    
        try:
            ram_percent = int(self.gui.state.ram_percent.get())
            if ram_percent < 1 or ram_percent > 100:
                errors.append("RAM % must be between 1 and 100.")
        except (tk.TclError, ValueError):
            errors.append("RAM % must be a valid integer.")
    
        selected_tools = self.gui.state.get_selected_tools()
        missing_stages = [
            stage for stage in STAGE_ORDER
            if stage not in VOLUME_SKIPPED_STAGES and enabled_tools_for_stage(stage) and not selected_tools.get(stage)
        ]
        if missing_stages:
            errors.append("Select one tool for every pipeline stage.")
        disabled_tools = [tool for tool in selected_tools.values() if tool and not is_tool_enabled(tool)]
        if disabled_tools:
            errors.append(f"Disabled tools selected: {', '.join(tool_display_name(tool) for tool in disabled_tools)}")
    
        target = self.gui.state.run_target.get()
        image_statuses = self.gui.tools_ctrl.image_statuses.setdefault(target, {})
        required_images: list[str] = []
        for tool in selected_tools.values():
            image = str(TOOL_DEFS.get(tool, {}).get("image", ""))
            if tool and is_tool_enabled(tool) and image and image not in required_images:
                required_images.append(image)
        if required_images and (target != "Server" or self.gui._server_connected()):
            unknown = [image for image in required_images if image_statuses.get(image, "Unknown") == "Unknown"]
            not_installed = [image for image in required_images if image_statuses.get(image, "Unknown") not in {"Installed", "Unknown"}]
            if unknown:
                errors.append("Check Docker images before running.")
            elif not_installed:
                errors.append("Install selected Docker images before running.")
    
        needs_license = any(TOOL_DEFS.get(tool, {}).get("needs_license") for tool in selected_tools.values())
        if needs_license and not Path(self.gui.state.license_dir.get().strip()).exists():
            errors.append("FreeSurfer license directory is required for selected tools.")
    
    
    
        ok = not errors
        can_start = self.gui.jobs_ctrl._can_start_new_pipeline()
        status_msg = "Configuration complete. Ready to run." if ok else errors[0]
        if not can_start:
            status_msg = "Pipeline is already running or busy."
    
        if getattr(self, "run_button", None) is not None:
            self.gui.run_button.configure(state=tk.NORMAL if ok and can_start else tk.DISABLED)
            if getattr(self.gui, "run_tooltip", None) is not None:
                self.gui.run_tooltip.update_text(status_msg)
        if getattr(self, "restart_button", None) is not None:
            self.gui.pipeline_ctrl.restart_button.configure(state=tk.NORMAL if ok and can_start else tk.DISABLED)
            if getattr(self.gui, "restart_tooltip", None) is not None:
                self.gui.pipeline_ctrl.restart_tooltip.update_text(status_msg)
        
        self.gui.state.config_status.set(status_msg)
        
        # Check server connection state for specific buttons
        server_ok = self.gui.state.run_target.get() != "Server" or self.gui._server_connected()
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
            if getattr(self.gui, "tools_refresh_tooltip", None) is not None:
                self.gui.tools_refresh_tooltip.update_text(server_msg)
                
        if self.gui.input_browse_button:
            if getattr(self.gui, "input_browse_tooltip", None) is not None:
                self.gui.input_browse_tooltip.update_text(server_msg)
    
        return ok
    
