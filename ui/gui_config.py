from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import os
import json
from pipeline.config import PROJECT_ROOT
from pipeline.registry import tool_key_from_display, TOOL_DEFS, tool_display_name, is_tool_enabled

class ConfigController:
    def __init__(self, gui):
        self.gui = gui
        
    def _save_workspace(self) -> None:

        config_dir = PROJECT_ROOT / "configs" / "workspaces"

        config_dir.mkdir(parents=True, exist_ok=True)

        path = filedialog.asksaveasfilename(

            title="Save workspace",

            initialdir=str(config_dir),

            defaultextension=".json",

            filetypes=(("Workspace JSON", "*.json"), ("All files", "*.*")),

        )

        if not path:

            return

    

        workspace = self.gui.state.collect_workspace()

        workspace_name = Path(path).stem

        workspace["name"] = workspace_name

        self.gui.state.workspace_name = workspace_name

        try:

            with open(path, "w", encoding="utf-8") as f:

                json.dump(workspace, f, indent=2, ensure_ascii=False)

            self.gui.progress_ctrl._log(f"Saved workspace: {path}")

        except Exception as exc:

            messagebox.showerror("Save workspace failed", str(exc))

    def _load_workspace(self) -> None:

        if self.gui.pipeline_ctrl.remote_connecting:

            messagebox.showwarning("Server connecting", "Wait for the current server connection attempt to finish before loading a workspace.")

            return

        config_dir = PROJECT_ROOT / "configs" / "workspaces"

        path = filedialog.askopenfilename(

            title="Load workspace",

            initialdir=str(config_dir),

            filetypes=(("Workspace JSON", "*.json"), ("All files", "*.*")),

        )

        if not path:

            return

    

        tools_visible = self.gui.pipeline_tools_visible.get()

        self.gui._preserve_pipeline_tools_visibility = True

        try:

            with open(path, "r", encoding="utf-8") as f:

                workspace = json.load(f)

            self.gui.state.workspace_name = Path(path).stem

            self.gui.state.apply_workspace(workspace)

            self.gui._on_run_target_changed()

            self.gui._last_input_source = self.gui.state.input_source.get()

            self.gui._input_source_paths[self.gui._last_input_source] = self.gui.state.input_path.get().strip()

            self.gui._input_source_selected_files[self.gui._last_input_source] = list(self.gui.state.selected_files)

            self.gui._refresh_input_label()

            self.gui.validation_ctrl._validate_configuration()

            self.gui.progress_ctrl._log(f"Loaded workspace: {path}")

        except Exception as exc:

            messagebox.showerror("Load workspace failed", str(exc))

        finally:

            self.gui._preserve_pipeline_tools_visibility = False

            self.gui._set_pipeline_tools_visible(tools_visible)

    def _save_config(self) -> None:

        self._save_workspace()

    def _load_config(self) -> None:

        self._load_workspace()

    def _collect_run_config(self) -> dict:

        return {

            "version": 1,

            "type": "mri-pipeline-preset",

            "pipeline_mode": self.gui.state.pipeline_mode.get(),

            "tools": self.gui.state.get_selected_tools(),

            "stats_vectors": self.gui.state.get_stats_vector_config(),

        }

    def _apply_run_config(self, config: dict) -> None:

        self._is_applying_preset = True

        try:

            self.gui.state.pipeline_mode.set(self.gui._normalize_pipeline_mode(config.get("pipeline_mode", "Custom")))

    

            tools = config.get("tools", {})

            for stage, value in tools.items():

                if stage in self.gui.state.tool_vars:

                    tool_key = tool_key_from_display(value)

                    if not tool_key and value in TOOL_DEFS:

                        tool_key = value

                    self.gui.state.tool_vars[stage].set(tool_display_name(tool_key) if is_tool_enabled(tool_key) else "")

    

            self.gui.state.apply_stats_vector_config(config.get("stats_vectors", {}))

            self.gui._apply_pipeline_mode(apply_stats_preset=False)

            self.gui.tools_ctrl._update_config_status_labels()

            self.gui.validation_ctrl._validate_configuration()

        finally:

            self._is_applying_preset = False

    def _save_run_config(self) -> None:

        config_dir = PROJECT_ROOT / "configs" / "preset"

        config_dir.mkdir(parents=True, exist_ok=True)

        path = filedialog.asksaveasfilename(

            title="Save preset",

            initialdir=str(config_dir),

            defaultextension=".json",

            filetypes=(("Preset JSON", "*.json"), ("All files", "*.*")),

        )

        if not path:

            return

        data = self._collect_run_config()

        data["name"] = Path(path).stem

        try:

            with open(path, "w", encoding="utf-8") as f:

                json.dump(data, f, indent=2, ensure_ascii=False)

            self.gui.progress_ctrl._log(f"Saved preset: {path}")

        except Exception as exc:

            messagebox.showerror("Save preset failed", str(exc))

    def _load_run_config(self) -> None:

        config_dir = PROJECT_ROOT / "configs" / "preset"

        path = filedialog.askopenfilename(

            title="Load preset",

            initialdir=str(config_dir),

            filetypes=(("Preset JSON", "*.json"), ("All files", "*.*")),

        )

        if not path:

            return

        try:

            with open(path, "r", encoding="utf-8") as f:

                config = json.load(f)

            if config.get("type") not in (None, "mri-pipeline-run-config", "mri-pipeline-preset"):

                messagebox.showerror("Invalid preset", "Selected file is not an MRI pipeline preset.")

                return

            self._apply_run_config(config)

            self.gui.progress_ctrl._log(f"Loaded preset: {path}")

        except Exception as exc:

            messagebox.showerror("Load preset failed", str(exc))

    def _configure_batch(self) -> None:

        from ui.batch_window import BatchConfigWindow

        BatchConfigWindow(self.root, self)