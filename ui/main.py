"""Tkinter GUI for the MRI Docker pipeline.

Features:
- Single file, multiple files, or batch folder input.
- Tool selection for every pipeline stage.
- Live log output.
- Live Docker container CPU/RAM chart via pipeline_runner.on_metrics.
"""

from __future__ import annotations

import json
import os
import posixpath
import queue
import stat
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from pipeline.config import PROJECT_ROOT, STAT_VECTOR_DEFS
from pipeline.registry import (
    STAGE_ORDER,
    TOOL_DEFS,
    enabled_tools_for_stage,
    is_tool_enabled,
    tool_display_name,
    tool_key_from_display,
)
from pipeline.presets import (
    PIPELINE_MODES,
    PIPELINE_MODE_ALIASES,
    VOLUME_SKIPPED_STAGES,
    PRESET_CONFIGS,
    VOLUME_STATS,
    THICKNESS_STATS,
)
from pipeline.discovery import _is_supported_mri_input
from remote.remote_runner import RemoteRunner
from remote.ssh_client import RemoteSSHClient, SSHConfig
from ui.gui_remote import RemoteController
from ui.job_registry import JobRegistryController
from ui.gui_config import ConfigController
from ui.gui_jobs import JobsController
from ui.gui_pipeline import PipelineController
from ui.gui_progress import ProgressController
from ui.gui_tools import ToolsController
from ui.state import AppState
from ui.styles import configure_windows_dpi_awareness, setup_styles
from ui.tabs.config_tab import build_configuration_tab
from ui.tabs.tools_tab import build_tools_tab
from ui.components.tooltip import Tooltip

class PipelineGUI:

    def _normalize_pipeline_mode(self, mode: str) -> str:
        normalized = PIPELINE_MODE_ALIASES.get(mode, mode)
        normalized = PIPELINE_MODE_ALIASES.get(normalized, normalized)
        return normalized if normalized in PIPELINE_MODES else "Custom"

    def _cortical_thickness_enabled(self) -> bool:
        var = self.state.stat_vector_enabled_vars.get("cortical_thickness")
        return bool(var is not None and var.get())

    def _apply_custom_tool_defaults(self, force_reset: bool = False) -> None:
        thickness_on = self._cortical_thickness_enabled()
        for stage in STAGE_ORDER:
            current = self.state.tool_vars[stage].get().strip() if stage in self.state.tool_vars else ""
            # Keep any existing choice (including explicit skips) unless force-resetting into Custom.
            if not force_reset and current:
                continue
            tools = enabled_tools_for_stage(stage)
            if stage in VOLUME_SKIPPED_STAGES and not thickness_on:
                self.state.tool_vars[stage].set("Not available")
            elif tools:
                self.state.tool_vars[stage].set(tool_display_name(tools[0]))
            else:
                self.state.tool_vars[stage].set("Not available")

    def _sync_surface_stages_with_stats(self) -> None:
        """Steps 7-8 track cortical thickness: off => skipped, on => restore a tool if needed."""
        thickness_on = self._cortical_thickness_enabled()
        for stage in VOLUME_SKIPPED_STAGES:
            if stage not in self.state.tool_vars:
                continue
            tools = enabled_tools_for_stage(stage)
            if not thickness_on or not tools:
                self.state.tool_vars[stage].set("Not available")
                continue
            current = self.state.tool_vars[stage].get().strip()
            if not current or current == "Not available":
                self.state.tool_vars[stage].set(tool_display_name(tools[0]))

    def _sync_tool_combo_states(self) -> None:
        """Enable tool dropdowns for active stages; dim/disable skipped ones."""
        thickness_on = self._cortical_thickness_enabled()
        for stage, combo in getattr(self, "tool_combos", {}).items():
            tools = enabled_tools_for_stage(stage)
            value = self.state.tool_vars[stage].get() if stage in self.state.tool_vars else ""
            surface_skipped = stage in VOLUME_SKIPPED_STAGES and not thickness_on
            if not tools or value == "Not available" or surface_skipped:
                combo.configure(state=tk.DISABLED, style="Skipped.TCombobox")
            else:
                combo.configure(state="readonly", style="TCombobox")

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MRI Pipeline GUI")
        self.root.geometry("1200x800+80+60")
        self.root.minsize(1180, 760)

        # Initialize State
        self.state = AppState()
        self.local_max_threads = max(1, os.cpu_count() or 1)
        self.max_threads: int | None = self.local_max_threads
        self.thread_max_text = tk.StringVar(value=f"/ {self.local_max_threads} max")
        self.thread_spinbox: ttk.Spinbox | None = None
        self._thread_max_request_id = 0
        if int(self.state.threads.get()) > self.local_max_threads:
            self.state.threads.set(self.local_max_threads)
        
        # Apply Styles

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.metrics_queue: queue.Queue[tuple[float | None, int | None, float | None, str]] = queue.Queue()
        
        self.run_target_combo: ttk.Combobox | None = None
        self.remote_key_browse_button: ttk.Button | None = None
        self.remote_workspace_entry: ttk.Entry | None = None
        self.input_location_label_var = tk.StringVar(value="Input Location")
        self.input_browse_button: ttk.Button | None = None
        self.upload_input_row: ttk.Frame | None = None
        self.upload_input_button: ttk.Button | None = None
        self.output_dir_row: ttk.Frame | None = None

        self.tool_combos: dict[str, ttk.Combobox] = {}
        self.pipeline_tools_body: ttk.Frame | None = None
        self.pipeline_tools_visible = tk.BooleanVar(value=False)
        self.pipeline_tools_toggle_text = tk.StringVar(value="▶ View tools")
        self._preserve_pipeline_tools_visibility = False
        self.stat_vector_checkbuttons: dict[str, ttk.Checkbutton] = {}
        self.stat_atlas_combos: dict[str, ttk.Combobox] = {}
        self.notebook: ttk.Notebook | None = None
        self.config_tab: ttk.Frame | None = None
        self.toolbar_icons: dict[str, tk.PhotoImage] = {}
        self._spinner_frames = self._load_spinner_frames("running")
        self._spinner_frames_light = self._load_spinner_frames("running_light")
        self._spinner_idx = 0
        self._busy_buttons: dict[ttk.Button, dict[str, str]] = {}
        self.python_env_check_button: ttk.Button | None = None
        self.python_env_install_button: ttk.Button | None = None
        self.python_env_hint = tk.StringVar(value=sys.executable or "")
        self.python_env_status_icon_label: ttk.Label | None = None
        self.python_env_status_label: ttk.Label | None = None
        self._last_input_source = self.state.input_source.get()
        self._input_source_paths: dict[str, str] = {"Local": "", "Server": "~"}
        self._input_source_selected_files: dict[str, list[str]] = {"Local": [], "Server": []}
        self._connected_remote_signature: tuple | None = None
        self._remote_thread_max_signature: tuple | None = None
        self._remote_health_check_timer = None

        self.tools_ctrl = ToolsController(self)
        self.pipeline_ctrl = PipelineController(self)
        self.jobs_ctrl = JobsController(self)
        self.progress_ctrl = ProgressController(self)
        from ui.gui_validation import ValidationController
        self.validation_ctrl = ValidationController(self)
        self.config_ctrl = ConfigController(self)
        self.registry_ctrl = JobRegistryController(self)
        self.remote_ctrl = RemoteController(self)
        self._build_ui()
        self._update_python_env_hint()
        self.validation_ctrl._setup_validation_traces()
        self.validation_ctrl._validate_configuration()
        self.progress_ctrl._poll_queues()
        if self._spinner_frames or self._spinner_frames_light:
            self.root.after(120, self._animate_spinner)

    def _load_spinner_frames(self, icon_name: str, size: int = 16) -> list[tk.PhotoImage]:
        icon_path = Path(__file__).parent / "icons" / f"{icon_name}.png"
        if not icon_path.exists():
            return []
        try:
            from PIL import Image, ImageTk

            resample = getattr(getattr(Image, "Resampling", Image), "BICUBIC")
            image = Image.open(icon_path).convert("RGBA").resize((size, size), resample=resample)
            return [ImageTk.PhotoImage(image.rotate(-angle, resample=resample)) for angle in range(0, 360, 30)]
        except Exception:
            try:
                return [tk.PhotoImage(file=str(icon_path))]
            except tk.TclError:
                return []

    def _spinner_frame(self, light: bool = False) -> tk.PhotoImage | None:
        frames = self._spinner_frames_light if light and self._spinner_frames_light else self._spinner_frames
        if not frames:
            return None
        return frames[self._spinner_idx % len(frames)]

    def _button_uses_light_spinner(self, button: ttk.Button) -> bool:
        try:
            return "Accent" in str(button.cget("style"))
        except tk.TclError:
            return False

    def _is_busy_status(self, status: str) -> bool:
        return status in {"Checking", "Downloading", "Deleting"}

    def _is_button_busy(self, button: ttk.Button | None) -> bool:
        return button is not None and button in getattr(self, "_busy_buttons", {})

    def _set_button_busy(self, button: ttk.Button | None, busy: bool, text: str | None = None) -> None:
        if button is None:
            return
        busy_buttons = getattr(self, "_busy_buttons", None)
        if busy_buttons is None:
            self._busy_buttons = {}
            busy_buttons = self._busy_buttons
        try:
            if busy:
                if button not in busy_buttons:
                    busy_buttons[button] = {
                        "text": str(button.cget("text")),
                        "image": str(button.cget("image")),
                        "compound": str(button.cget("compound")),
                        "state": str(button.cget("state")),
                        "light_spinner": self._button_uses_light_spinner(button),
                    }
                busy_buttons[button]["busy_text"] = text or busy_buttons[button]["text"].strip() or "Working"
                button.configure(image=self._spinner_frame(bool(busy_buttons[button].get("light_spinner"))) or "", text=f" {busy_buttons[button]['busy_text']}", compound=tk.LEFT, state=tk.DISABLED)
                return
            original = busy_buttons.pop(button, None)
            if original is not None and button.winfo_exists():
                button.configure(
                    text=original.get("text", ""),
                    image=original.get("image", ""),
                    compound=original.get("compound", tk.NONE),
                    state=original.get("state", tk.NORMAL),
                )
        except tk.TclError:
            if not busy:
                busy_buttons.pop(button, None)

    def _animate_busy_buttons(self, frame: str) -> None:
        for button, state in list(getattr(self, "_busy_buttons", {}).items()):
            try:
                if not button.winfo_exists():
                    self._busy_buttons.pop(button, None)
                    continue
                icon = self._spinner_frame(bool(state.get("light_spinner")))
                button.configure(image=icon if icon is not None else "", text=f" {state.get('busy_text', 'Working')}", compound=tk.LEFT, state=tk.DISABLED)
            except tk.TclError:
                self._busy_buttons.pop(button, None)

    def _animate_spinner(self):
        frame_count = max(len(self._spinner_frames), len(self._spinner_frames_light))
        if not frame_count:
            return
        self._spinner_idx = (self._spinner_idx + 1) % frame_count
        frame = self._spinner_frame()
        self._animate_busy_buttons(frame)

        if getattr(self, "remote_connecting", False) and getattr(self, "remote_status_icon_label", None) is not None:
            try:
                self.pipeline_ctrl.remote_status_icon_label.configure(image=frame if frame is not None else "", text="", foreground="#2563eb")
            except Exception:
                pass

        py_status = getattr(getattr(self, "python_env_status", None), "get", lambda: "")()
        if ("checking" in py_status.lower() or "installing" in py_status.lower()) and getattr(self, "python_env_status_icon_label", None) is not None:
            try:
                self.python_env_status_icon_label.configure(image=frame if frame is not None else "", text="", foreground="#2563eb")
            except Exception:
                pass

        attach_spinner = getattr(self, "_attach_loading_spinner_label", None)
        if attach_spinner is not None:
            try:
                if attach_spinner.winfo_exists():
                    attach_spinner.configure(image=frame if frame is not None else "", text="")
            except Exception:
                pass

        remote_upload_spinner = getattr(self, "_remote_upload_spinner_label", None)
        if remote_upload_spinner is not None:
            try:
                if remote_upload_spinner.winfo_exists():
                    remote_upload_spinner.configure(image=frame if frame is not None else "", text="")
            except Exception:
                pass

        if hasattr(self, "tools_status_icon_labels") and hasattr(self, "image_statuses"):
            for tool_key, label in self.tools_ctrl.status_icon_labels.items():
                status = self.tools_ctrl._tool_status(tool_key)
                if self._is_busy_status(status):
                    try:
                        label.configure(image=frame if frame is not None else "", text=f"  {status}", compound=tk.LEFT)
                    except Exception:
                        pass

        if hasattr(self, "status_labels") and hasattr(self, "image_statuses"):
            for stage, label in self.tools_ctrl.status_labels.items():
                tool_var = self.state.tool_vars.get(stage)
                tool_key = tool_key_from_display(tool_var.get()) if tool_var is not None else ""
                status = self.tools_ctrl._tool_status(tool_key)
                if self._is_busy_status(status):
                    try:
                        label.configure(image=frame if frame is not None else "", text=f" {self.tools_ctrl._status_label_text(status)}", compound=tk.LEFT)
                    except Exception:
                        pass

        if hasattr(self, "image_rows"):
            for key, row in self.progress_ctrl.image_rows.items():
                run_state = getattr(self, "image_runs", {}).get(key, {})
                if row.get("status") and run_state.get("status") == "Running":
                    try:
                        if row.get("icon"):
                            row["icon"].configure(image=frame if frame is not None else "", text="")
                    except Exception:
                        pass

        run = getattr(self, "image_runs", {}).get(getattr(self, "current_image_key", ""))
        if run and hasattr(self, "step_summary_rows"):
            for stage, step in run.get("steps", {}).items():
                if step.get("status") == "Running" and stage in self.progress_ctrl.step_summary_rows:
                    try:
                        self.progress_ctrl.step_summary_rows[stage]["icon"].configure(image=frame if frame is not None else "", text="")
                    except Exception:
                        pass

        self.root.after(120, self._animate_spinner)

    def _build_ui(self) -> None:
        root_frame = ttk.Frame(self.root)
        root_frame.pack(fill=tk.BOTH, expand=True)

        self._build_app_toolbar(root_frame)
        self._build_status_bar(root_frame)
        self._build_tabs(root_frame)

    def _make_icon(self, name: str, color: str | None = None) -> tk.PhotoImage | None:
        icon_key = f"{name}_{color}" if color else name
        if icon_key in self.toolbar_icons:
            return self.toolbar_icons[icon_key]
        try:
            import os
            icon_path = os.path.join(os.path.dirname(__file__), "icons", f"{name}.png")
            if os.path.exists(icon_path):
                if color:
                    try:
                        from PIL import Image, ImageTk

                        hex_color = color.lstrip("#")
                        rgb = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
                        image = Image.open(icon_path).convert("RGBA")
                        alpha = image.getchannel("A")
                        tinted = Image.new("RGBA", image.size, (*rgb, 0))
                        tinted.putalpha(alpha)
                        img = ImageTk.PhotoImage(tinted)
                    except Exception:
                        source = tk.PhotoImage(file=icon_path)
                        img = tk.PhotoImage(width=source.width(), height=source.height())
                        for x in range(source.width()):
                            for y in range(source.height()):
                                try:
                                    if source.transparency_get(x, y):
                                        img.transparency_set(x, y, True)
                                    else:
                                        img.put(color, (x, y))
                                except tk.TclError:
                                    img.put(color, (x, y))
                else:
                    img = tk.PhotoImage(file=icon_path)
                self.toolbar_icons[icon_key] = img
                return img
        except Exception:
            pass
        return None

    def _get_status_icon(self, status: str) -> tk.PhotoImage | None:
        s = status.lower()
        if "pending" in s: name = "pending"
        elif "running" in s: name = "running"
        elif "paused" in s: name = "pause"
        elif "fail" in s: name = "failed"
        elif "done" in s or "success" in s or "ok" in s: name = "success"
        else: return None
        
        icon_key = f"status_{name}"
        if icon_key in self.toolbar_icons:
            return self.toolbar_icons[icon_key]
        
        try:
            import os
            icon_path = os.path.join(os.path.dirname(__file__), "icons", f"{name}.png")
            if os.path.exists(icon_path):
                img = tk.PhotoImage(file=icon_path)
                self.toolbar_icons[icon_key] = img
                return img
        except Exception:
            pass
        return None


    def _toolbar_button(self, parent: ttk.Frame, key: str, label: str, command, icon_color: str | None = None) -> ttk.Button:
        icon = self._make_icon(key, icon_color)
        options = {"text": f" {label} ", "command": command}
        if icon is not None:
            options.update({"image": icon, "compound": tk.LEFT})
        button = ttk.Button(parent, **options)
        button.pack(side=tk.LEFT, padx=3)
        return button

    def _build_app_toolbar(self, parent: ttk.Frame) -> None:
        toolbar = ttk.Frame(parent)
        # Sửa padding để nút không bị cropped ở phía trên (thêm top padding)
        toolbar.pack(fill=tk.X, padx=8, pady=(12, 8))

        self.save_button = self._toolbar_button(toolbar, "save", "Save Workspace", self.config_ctrl._save_workspace)
        self.load_button = self._toolbar_button(toolbar, "load", "Load Workspace", self.config_ctrl._load_workspace)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12, pady=4)
        
        self.run_button = self._toolbar_button(toolbar, "run", "Run", lambda: self.pipeline_ctrl._start_pipeline(resume=False, restart=False), icon_color="#ffffff")
        self.run_button.configure(style="Accent.TButton")
        self.run_tooltip = Tooltip(self.run_button, "")
        self.pipeline_ctrl.resume_button = self._toolbar_button(toolbar, "resume", "Resume", self.jobs_ctrl._resume_pipeline)
        self.pipeline_ctrl.restart_button = self._toolbar_button(toolbar, "restart", "Restart", lambda: self.pipeline_ctrl._start_pipeline(resume=False, restart=True))
        self.pipeline_ctrl.restart_tooltip = Tooltip(self.pipeline_ctrl.restart_button, "")
        self.pipeline_ctrl.stop_button = self._toolbar_button(toolbar, "pause", "Stop After Current Step", self.progress_ctrl._request_stop)
        self.pipeline_ctrl.stop_button.configure(state=tk.DISABLED)
        self.attach_button = self._toolbar_button(toolbar, "load", "Attach Job", self.jobs_ctrl._attach_job_dialog)

    def _build_tabs(self, parent: ttk.Frame) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.config_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.config_tab, text="Pipeline configuration")
        self.tools_ctrl.tab_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.tools_ctrl.tab_frame, text="Tools / Docker Images")
        self.notebook.bind("<<NotebookTabChanged>>", self.progress_ctrl._on_notebook_tab_changed)
        self.notebook.bind("<Button-1>", self.progress_ctrl._on_notebook_click)

        build_configuration_tab(self.config_tab, self)
        build_tools_tab(self.tools_ctrl.tab_frame, self.tools_ctrl)

    def _build_status_bar(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent, padding=(10, 5))
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Separator(bar, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(0, 5))
        left = ttk.Frame(bar)
        left.pack(fill=tk.X)
        ttk.Label(left, text="Status", font=("Inter", 9, "bold")).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(left, textvariable=self.state.config_status, foreground="#334155").pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # We add some styling and spacing to the status texts to make them look like a cohesive modern status badge
        ttk.Label(left, textvariable=self.state.overall_progress_text, width=4, anchor=tk.E).pack(side=tk.RIGHT, padx=(0, 0))
        ttk.Separator(left, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, pady=2, padx=8)
        ttk.Label(left, textvariable=self.state.server_text, foreground="#475569").pack(side=tk.RIGHT, padx=0)
        ttk.Separator(left, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, pady=2, padx=8)
        ttk.Label(left, textvariable=self.state.status_text, foreground="#64748b").pack(side=tk.RIGHT, padx=0)

    def _set_widget_tree_state(self, widget: tk.Widget, state: str) -> None:
        for child in widget.winfo_children():
            try:
                if "state" in child.keys():
                    child.configure(state=state)
            except tk.TclError:
                pass
            self._set_widget_tree_state(child, state)




    def _set_pipeline_tools_visible(self, visible: bool) -> None:
        body = getattr(self, "pipeline_tools_body", None)
        if body is None:
            return
        self.pipeline_tools_visible.set(visible)
        if visible:
            body.grid()
            self.pipeline_tools_toggle_text.set("▲ Hide tools")
        else:
            body.grid_remove()
            self.pipeline_tools_toggle_text.set("▶ View tools")

    def _toggle_pipeline_tools(self) -> None:
        self._set_pipeline_tools_visible(not self.pipeline_tools_visible.get())

    def _set_thread_max(self, max_threads: int | None, pending: bool = False) -> None:
        self.max_threads = max_threads if max_threads and max_threads > 0 else None
        max_value = self.max_threads if self.max_threads is not None else 9999
        if self.max_threads is not None:
            self.thread_max_text.set(f"/ {self.max_threads} max")
        elif self.state.run_target.get() == "Server":
            self.thread_max_text.set("/ checking max" if pending else "Connect Server to edit threads")
        else:
            self.thread_max_text.set("/ _ max")
        spinbox = getattr(self, "thread_spinbox", None)
        if spinbox is not None:
            spinbox_state = tk.NORMAL if self.state.run_target.get() != "Server" or self.remote_ctrl._server_thread_max_known() else tk.DISABLED
            spinbox.configure(to=max_value, state=spinbox_state)
        self.validation_ctrl._clamp_threads()
        self.validation_ctrl._validate_configuration()

















    def _refresh_thread_max_for_target(self) -> None:
        if self.state.run_target.get() != "Server":
            self._thread_max_request_id += 1
            self.remote_ctrl._cancel_remote_health_check()
            self.remote_ctrl._reset_remote_tool_image_state()
            self._set_thread_max(self.local_max_threads)
            return

        self._thread_max_request_id += 1
        if self.remote_ctrl._server_connected():
            self._set_thread_max(self.max_threads)
            return
        self._set_thread_max(None)


    def _update_python_env_hint(self) -> None:
        if self.state.run_target.get() == "Server":
            self.tools_ctrl.python_env_hint.set(self.remote_ctrl._remote_venv_display_path() if self.state.remote_workspace.get().strip() else "")
        else:
            self.tools_ctrl.python_env_hint.set(sys.executable or "")

    def _on_run_target_changed(self) -> None:
        if self.pipeline_ctrl.remote_body is None:
            return
        enabled = self.state.run_target.get() == "Server"
        if not enabled:
            self.remote_ctrl._cancel_remote_health_check()
            if self.state.input_source.get() != "Local":
                self._switch_input_source("Local")
        self.state.server_text.set("Server: remote" if enabled else "Server: local")
        if self.pipeline_ctrl.remote_frame is not None:
            if enabled:
                try:
                    self.pipeline_ctrl.remote_frame.pack(**(self.pipeline_ctrl.remote_pack_options or {"fill": tk.X, "pady": (0, 32)}))
                except tk.TclError:
                    pass
            else:
                self.pipeline_ctrl.remote_frame.pack_forget()
        self._set_widget_tree_state(self.pipeline_ctrl.remote_body, tk.NORMAL if enabled else tk.DISABLED)
        if enabled:
            self.state.remote_status.set("Remote: connected" if self.remote_ctrl._server_connected() else "Remote: disconnected")
        else:
            self.state.remote_status.set("")
        self._update_python_env_hint()
        self._refresh_thread_max_for_target()
        self.tools_ctrl._set_python_env_status("Not checked")
        self._sync_input_source_controls()
        self.remote_ctrl._sync_remote_connection_controls()
        self.tools_ctrl._refresh_tree()
        self.tools_ctrl._update_config_status_labels()
        self.validation_ctrl._validate_configuration()

    def _switch_input_source(self, new_source: str) -> None:
        old_source = getattr(self, "_last_input_source", "Local")
        if old_source != new_source:
            self._input_source_paths[old_source] = self.state.input_path.get().strip()
            self._input_source_selected_files[old_source] = list(self.state.selected_files)
            next_path = self._input_source_paths.get(new_source, "")
            if new_source == "Server" and not next_path:
                next_path = "~"
            self.state.input_path.set(next_path)
            self.state.selected_files = list(self._input_source_selected_files.get(new_source, [])) if next_path else []
            self.state.input_source.set(new_source)
            self._last_input_source = new_source
        self._sync_input_source_controls()
        self._refresh_input_label()

    def _sync_input_source_controls(self) -> None:
        server_run = self.state.run_target.get() == "Server"
        connected = self.remote_ctrl._server_connected()
        
        if hasattr(self, "input_source_row"):
            if server_run:
                self.input_source_row.grid()
            else:
                self.input_source_row.grid_remove()
            
        self.input_location_label_var.set("Server Input Location" if self.state.input_source.get() == "Server" else "Input Location")
        if self.input_browse_button is not None:
            self.input_browse_button.configure(text="Browse Server" if self.state.input_source.get() == "Server" else "Browse")
            if self.state.input_source.get() == "Server" and not connected:
                self.input_browse_button.configure(state=tk.DISABLED)
            else:
                self.input_browse_button.configure(state=tk.NORMAL)
        if hasattr(self, "upload_input_button") and self.upload_input_button is not None:
            if self.state.input_source.get() == "Local" and connected:
                self.upload_input_button.configure(state=tk.NORMAL)
            else:
                self.upload_input_button.configure(state=tk.DISABLED)
        if hasattr(self, "server_output_dir_row"):
            if server_run:
                self.server_output_dir_row.grid()
                self.server_output_browse_button.configure(state=tk.NORMAL if connected else tk.DISABLED)
            else:
                self.server_output_dir_row.grid_remove()
        if self.output_dir_row is not None:
            if server_run:
                self.output_dir_row.grid_remove()
            else:
                self.output_dir_row.grid()

    def _ask_upload_overwrite(self, remote_path: str) -> str:
        dialog = tk.Toplevel(self.root)
        dialog.title("Overwrite server file?")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        result = {"value": "cancel"}

        body = ttk.Frame(dialog, padding=14)
        body.pack(fill=tk.BOTH, expand=True)
        ttk.Label(body, text="File already exists on server:", font=("Inter", 10, "bold")).pack(anchor=tk.W)
        ttk.Label(body, text=remote_path, wraplength=560, foreground="#475569").pack(anchor=tk.W, pady=(4, 12))
        buttons = ttk.Frame(body)
        buttons.pack(fill=tk.X)

        def choose(value: str) -> None:
            result["value"] = value
            dialog.destroy()

        ttk.Button(buttons, text="Yes", style="Accent.TButton", command=lambda: choose("yes")).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(buttons, text="No", command=lambda: choose("no")).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Yes to all", command=lambda: choose("yes_all")).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="No to all", command=lambda: choose("no_all")).pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Cancel", command=lambda: choose("cancel")).pack(side=tk.RIGHT)
        dialog.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))
        self.root.wait_window(dialog)
        return result["value"]


    def _browse_input(self) -> None:
        if self.state.input_source.get() == "Server":
            self.remote_ctrl._browse_remote_input()
            return
        mode = self.state.input_mode.get()
        if mode == "file":
            path = filedialog.askopenfilename(title="Select MRI file", filetypes=self._mri_filetypes())
            if path:
                self.state.selected_files = [path]
                self.state.input_path.set(path)
        elif mode == "files":
            paths = filedialog.askopenfilenames(title="Select MRI files", filetypes=self._mri_filetypes())
            if paths:
                self.state.selected_files = list(paths)
                self.state.input_path.set("; ".join(self.state.selected_files))
        elif mode == "dir":
            path = filedialog.askdirectory(title="Select Input Directory")
            if path:
                self.state.input_path.set(path)
        self._input_source_paths[self.state.input_source.get()] = self.state.input_path.get().strip()
        self._input_source_selected_files[self.state.input_source.get()] = list(self.state.selected_files)
        self._refresh_input_label()



    def _mri_filetypes(self) -> tuple[tuple[str, str], tuple[str, str]]:
        return (("MRI files", "*.nii *.nii.gz *.mgz *.mgh *.dcm *.dicom *.ima"), ("All files", "*.*"))

    def _browse_directory(self, variable: tk.StringVar) -> None:
        path = filedialog.askdirectory(title="Select directory")
        if path:
            variable.set(path)


    def _apply_stats_preset_for_mode(self, mode: str, force_reset: bool = False) -> None:
        if mode == "Custom":
            if not force_reset:
                return
            self._is_applying_preset = True
            try:
                for stat, var in self.state.stat_vector_enabled_vars.items():
                    var.set(False)
                    first_atlas = next(iter(self.state.stat_atlas_vars.get(stat, {})), "")
                    if first_atlas:
                        self.state.set_stat_atlas_choice(stat, first_atlas)
            finally:
                self._is_applying_preset = False
            return
            
        preset = PRESET_CONFIGS.get(mode)
        if preset is None:
            return
        enabled = set(preset["stats"])

        self._is_applying_preset = True
        try:
            for stat, var in self.state.stat_vector_enabled_vars.items():
                var.set(stat in enabled)
            for stat in enabled:
                if not self.state.selected_atlases_for_stat(stat):
                    first_atlas = next(iter(self.state.stat_atlas_vars.get(stat, {})), "")
                    if first_atlas:
                        self.state.set_stat_atlas_choice(stat, first_atlas)
        finally:
            self._is_applying_preset = False

    def _update_stats_vector_controls(self, mode: str) -> None:
        self._is_applying_preset = True
        try:
            for stat, check in getattr(self, "stat_vector_checkbuttons", {}).items():
                check.configure(state=tk.NORMAL)
            for stat, combo in getattr(self, "stat_atlas_combos", {}).items():
                var = self.state.stat_vector_enabled_vars.get(stat)
                choice_var = self.state.stat_atlas_choice_vars.get(stat)
                is_enabled = var is not None and var.get()
                
                if is_enabled:
                    combo.configure(state="readonly")
                    if choice_var and choice_var.get() == "Not available":
                        first_atlas = next(iter(self.state.stat_atlas_vars.get(stat, {})), "")
                        if first_atlas:
                            self.state.set_stat_atlas_choice(stat, first_atlas)
                else:
                    combo.configure(state=tk.DISABLED)
                    if choice_var:
                        if mode == "Custom":
                            if choice_var.get() == "Not available" or not choice_var.get():
                                first_atlas = next(iter(self.state.stat_atlas_vars.get(stat, {})), "")
                                if first_atlas:
                                    self.state.set_stat_atlas_choice(stat, first_atlas)
                        else:
                            choice_var.set("Not available")
        finally:
            self._is_applying_preset = False

    def _apply_pipeline_mode(self, apply_stats_preset: bool = True, show_custom_tools: bool = True, update_tools_visibility: bool = True) -> None:
        if getattr(self, "_preserve_pipeline_tools_visibility", False):
            update_tools_visibility = False
        mode = self._normalize_pipeline_mode(self.state.pipeline_mode.get())
        if mode != self.state.pipeline_mode.get():
            self.state.pipeline_mode.set(mode)
            return
            
        is_programmatic = getattr(self, "_is_applying_preset", False)
        if apply_stats_preset:
            self._apply_stats_preset_for_mode(mode, force_reset=not is_programmatic)

        preset = PRESET_CONFIGS.get(mode)
        self._is_applying_preset = True
        try:
            if preset is not None:
                fixed_tools = preset["tools"]
                for stage, tool in fixed_tools.items():
                    if stage in self.state.tool_vars:
                        if not tool:
                            self.state.tool_vars[stage].set("Not available")
                        else:
                            self.state.tool_vars[stage].set(tool_display_name(tool))
                stats = set(preset["stats"])
                if stats == VOLUME_STATS:
                    self.state.pipeline_note.set(f"{mode}: cortical and subcortical volume vectors are selected. Surface steps 7-8 are skipped.")
                elif stats == THICKNESS_STATS:
                    suffix = " FastSurfer presets use FastSurferVINN for segmentation and FreeSurfer surface steps for thickness."
                    self.state.pipeline_note.set(f"{mode}: cortical thickness vector is selected with FreeSurfer aparc by default. Surface steps 7-8 are enabled." + (suffix if mode.startswith("FastSurfer") else ""))
                else:
                    suffix = " FastSurfer presets use FastSurferVINN for segmentation and FreeSurfer surface steps for thickness."
                    self.state.pipeline_note.set(f"{mode}: volume vectors and cortical thickness are selected. Surface steps 7-8 are enabled." + (suffix if mode.startswith("FastSurfer") else ""))
            else:
                self._apply_custom_tool_defaults(force_reset=not is_programmatic)
                self.state.pipeline_note.set("Custom mode: choose tools freely for each stage.")
                if update_tools_visibility:
                    self._set_pipeline_tools_visible(show_custom_tools)
            # Surface steps always follow cortical thickness, including Custom.
            self._sync_surface_stages_with_stats()
            self._update_stats_vector_controls(mode)
        finally:
            self._is_applying_preset = False

        self._sync_tool_combo_states()
        self.tools_ctrl._update_config_status_labels()

    def _selected_tools(self) -> dict[str, str]:
        if self._normalize_pipeline_mode(self.state.pipeline_mode.get()) != "Custom":
            self._apply_pipeline_mode(apply_stats_preset=False)
        return self.state.get_selected_tools()










    def _refresh_input_label(self, *_args) -> None:
        if self.state.input_mode.get() == "files":
            self.file_count_label.configure(text=f"Selected: {len(self.state.selected_files)} files")
        else:
            self.file_count_label.configure(text="")
            
        if hasattr(self, 'btn_config_batch'):
            if self.state.input_mode.get() == "dir" and self.state.input_path.get().strip() != "":
                self.btn_config_batch.configure(state=tk.NORMAL)
            else:
                self.btn_config_batch.configure(state=tk.DISABLED)
                
        self.validation_ctrl._validate_configuration()





def main() -> None:
    import sys
    import os
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("ERROR: No Linux GUI display detected.", file=sys.stderr)
        sys.exit(1)

    try:
        configure_windows_dpi_awareness()
        root = tk.Tk()
        setup_styles(root)
    except tk.TclError as exc:
        print(f"ERROR: Could not start Tkinter GUI: {exc}", file=sys.stderr)
        sys.exit(1)

    if "--probe-window" in sys.argv:
        probe = tk.Toplevel(root)
        probe.title("MRI Pipeline Probe Window")
        probe.geometry("640x360+120+90")
        probe.minsize(640, 360)
        probe.configure(bg="#dc2626")
        tk.Label(
            probe,
            text="Tkinter / WSLg probe window\\nIf you can see this, GUI display works.",
            font=("Inter", 16, "bold"),
        ).pack(fill=tk.BOTH, expand=True, padx=24, pady=24)
        probe.deiconify()
        probe.lift()
        print(f"Probe window is running on DISPLAY={os.environ.get('DISPLAY', '')}.", flush=True)

    root.title("MRI Pipeline GUI - Tkinter")
    root.geometry("1200x800+80+60")
    root.minsize(1180, 700)
    PipelineGUI(root)
    root.update_idletasks()
    root.deiconify()
    root.title("MRI Pipeline GUI")
    root.lift()
    print(f"MRI Pipeline GUI is running on DISPLAY={os.environ.get('DISPLAY', '')}.", flush=True)
    root.mainloop()

if __name__ == "__main__":
    main()