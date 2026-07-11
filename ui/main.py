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

from pipeline_runner import (
    PROJECT_ROOT,
    STAGE_ORDER,
    TOOL_DEFS,
    STAT_VECTOR_DEFS,
    enabled_tools_for_stage,
    is_tool_enabled,
    _is_supported_mri_input,
    tool_display_name,
    tool_key_from_display,
)
from remote.remote_runner import RemoteRunner
from remote.ssh_client import RemoteSSHClient, SSHConfig
from ui.gui_jobs import JobsMixin
from ui.gui_pipeline import PipelineMixin
from ui.gui_progress import ProgressMixin
from ui.gui_tools import ToolsMixin
from ui.state import AppState
from ui.styles import configure_windows_dpi_awareness, setup_styles
from ui.tabs.config_tab import build_configuration_tab
from ui.tabs.tools_tab import build_tools_tab


class PipelineGUI(ToolsMixin, JobsMixin, PipelineMixin, ProgressMixin):
    PIPELINE_MODES = (
        "FreeSurfer 8 + Volume",
        "FreeSurfer 8 + Cortical Thickness",
        "FreeSurfer 8 + Volume + Cortical Thickness",
        "FreeSurfer 7 + Volume",
        "FreeSurfer 7 + Cortical Thickness",
        "FreeSurfer 7 + Volume + Cortical Thickness",
        "FastSurfer + Volume",
        "FastSurfer + Cortical Thickness",
        "FastSurfer + Volume + Cortical Thickness",
        "Custom",
    )
    PIPELINE_MODE_ALIASES = {
        "Custom Tools": "Custom",
        "FS7": "FreeSurfer 7 + Volume",
        "FS8": "FreeSurfer 8 + Volume",
        "FreeSurfer7": "FreeSurfer 7 + Volume",
        "FreeSurfer8": "FreeSurfer 8 + Volume",
        "FreeSurfer 7": "FreeSurfer 7 + Volume",
        "FreeSurfer 8": "FreeSurfer 8 + Volume",
        "FreeSurfer Fixed": "FreeSurfer 7 + Volume",
        "FreeSurfer Fixed (7 steps)": "FreeSurfer 7 + Volume",
        "Volume": "FreeSurfer 7 + Volume",
        "Volume & Cortical Thickness": "FreeSurfer 7 + Volume + Cortical Thickness",
    }
    OPTIONAL_STAGES = {
        "surface_reconstruction",
        "surface_registration",
    }
    FREESURFER_7_TOOLS = {
        "reorientation": "mri_convert_fs7",
        "brain_extraction": "synthstrip_fs7",
        "segmentation": "synthseg_freesurfer_fs7",
        "template_registration": "synthmorph_fs8",
        "bias_correction": "ants_n4",
        "white_matter_segmentation": "mri_binarize",
        "surface_reconstruction": "",
        "surface_registration": "",
        "stats_extraction": "freesurfer_stats_fs7",
    }
    FREESURFER_7_SURFACE_TOOLS = {
        **FREESURFER_7_TOOLS,
        "surface_reconstruction": "recon_all_fs7",
        "surface_registration": "surface_stats_fs7",
    }
    FREESURFER_8_TOOLS = {
        "reorientation": "mri_convert_fs8",
        "brain_extraction": "synthstrip_fs8",
        "segmentation": "synthseg_freesurfer_fs8",
        "template_registration": "synthmorph_fs8",
        "bias_correction": "ants_n4",
        "white_matter_segmentation": "mri_binarize_fs8",
        "surface_reconstruction": "",
        "surface_registration": "",
        "stats_extraction": "freesurfer_stats_fs8",
    }
    FREESURFER_8_SURFACE_TOOLS = {
        **FREESURFER_8_TOOLS,
        "surface_reconstruction": "recon_all_fs8",
        "surface_registration": "surface_stats_fs8",
    }
    FASTSURFER_TOOLS = {
        "reorientation": "mri_convert_fs7",
        "brain_extraction": "synthstrip_fs7",
        "segmentation": "fastsurfervinn",
        "template_registration": "synthmorph_fs8",
        "bias_correction": "ants_n4",
        "white_matter_segmentation": "mri_binarize",
        "surface_reconstruction": "",
        "surface_registration": "",
        "stats_extraction": "freesurfer_stats_fs7",
    }
    FASTSURFER_SURFACE_TOOLS = {
        **FASTSURFER_TOOLS,
        "surface_reconstruction": "recon_all_fs7",
        "surface_registration": "surface_stats_fs7",
    }
    VOLUME_STATS = {"cortical_volume", "subcortical_volume"}
    THICKNESS_STATS = {"cortical_thickness"}
    PRESET_CONFIGS = {
        "FreeSurfer 8 + Volume": {"tools": FREESURFER_8_TOOLS, "stats": VOLUME_STATS},
        "FreeSurfer 8 + Cortical Thickness": {"tools": FREESURFER_8_SURFACE_TOOLS, "stats": THICKNESS_STATS},
        "FreeSurfer 8 + Volume + Cortical Thickness": {"tools": FREESURFER_8_SURFACE_TOOLS, "stats": VOLUME_STATS | THICKNESS_STATS},
        "FreeSurfer 7 + Volume": {"tools": FREESURFER_7_TOOLS, "stats": VOLUME_STATS},
        "FreeSurfer 7 + Cortical Thickness": {"tools": FREESURFER_7_SURFACE_TOOLS, "stats": THICKNESS_STATS},
        "FreeSurfer 7 + Volume + Cortical Thickness": {"tools": FREESURFER_7_SURFACE_TOOLS, "stats": VOLUME_STATS | THICKNESS_STATS},
        "FastSurfer + Volume": {"tools": FASTSURFER_TOOLS, "stats": VOLUME_STATS},
        "FastSurfer + Cortical Thickness": {"tools": FASTSURFER_SURFACE_TOOLS, "stats": THICKNESS_STATS},
        "FastSurfer + Volume + Cortical Thickness": {"tools": FASTSURFER_SURFACE_TOOLS, "stats": VOLUME_STATS | THICKNESS_STATS},
    }

    def _normalize_pipeline_mode(self, mode: str) -> str:
        normalized = self.PIPELINE_MODE_ALIASES.get(mode, mode)
        normalized = self.PIPELINE_MODE_ALIASES.get(normalized, normalized)
        return normalized if normalized in self.PIPELINE_MODES else "Custom"

    def _apply_custom_tool_defaults(self) -> None:
        for stage in STAGE_ORDER:
            if stage in self.OPTIONAL_STAGES:
                continue
            if stage not in self.state.tool_vars or self.state.tool_vars[stage].get().strip():
                continue
            tools = enabled_tools_for_stage(stage)
            if tools:
                self.state.tool_vars[stage].set(tool_display_name(tools[0]))

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MRI Pipeline GUI")
        self.root.geometry("1400x950")
        self.root.minsize(1180, 760)

        # Initialize State
        self.state = AppState()
        self.local_max_threads = max(1, os.cpu_count() or 1)
        self.max_threads: int | None = self.local_max_threads
        self.thread_max_text = tk.StringVar(value=f"/ {self.local_max_threads} max")
        self.thread_spinbox: ttk.Spinbox | None = None
        self._thread_max_request_id = 0
        self._remote_thread_max_signature: tuple[str, int, str, str, str] | None = None
        self._connected_remote_signature: tuple[str, int, str, str, str] | None = None
        self.remote_connecting = False
        self.remote_health_after_id: str | None = None
        self.remote_health_in_flight = False
        if int(self.state.threads.get()) > self.local_max_threads:
            self.state.threads.set(self.local_max_threads)
        
        # Apply Styles

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.metrics_queue: queue.Queue[tuple[float | None, int | None, float | None, str]] = queue.Queue()
        self.running = False
        self.stop_requested = threading.Event()
        
        self.remote_runner: RemoteRunner | None = None
        self.active_job: dict | None = None
        self.job_poll_after_id: str | None = None
        self.job_log_offset = 0
        self.remote_frame: ttk.Frame | None = None
        self.remote_body: ttk.Frame | None = None
        self.remote_pack_options: dict | None = None
        self.remote_status_icon_label: ttk.Label | None = None
        self.run_target_combo: ttk.Combobox | None = None
        self.remote_host_entry: ttk.Entry | None = None
        self.remote_port_entry: ttk.Entry | None = None
        self.remote_username_entry: ttk.Entry | None = None
        self.remote_password_entry: ttk.Entry | None = None
        self.remote_key_entry: ttk.Entry | None = None
        self.remote_key_browse_button: ttk.Button | None = None
        self.remote_workspace_entry: ttk.Entry | None = None
        self.remote_connect_button: ttk.Button | None = None
        self.input_location_label_var = tk.StringVar(value="Input location")
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
        self.progress_tab: ttk.Frame | None = None
        self.progress_contexts: dict[str, dict] = {}
        self.progress_context_by_job: dict[str, str] = {}
        self.active_progress_context_id = ""
        self.toolbar_icons: dict[str, tk.PhotoImage] = {}
        self.image_runs: dict[str, dict] = {}
        self.image_rows: dict[str, dict] = {}
        self.current_image_key = ""
        self.active_image_key = ""
        self._spinner_frames = self._load_spinner_frames("running")
        self._spinner_frames_light = self._load_spinner_frames("running_light")
        self._spinner_idx = 0
        self._busy_buttons: dict[ttk.Button, dict[str, str]] = {}
        self.tools_tab: ttk.Frame | None = None
        self.tools_table_frame: ttk.Frame | None = None
        self.tools_log_text: tk.Text | None = None
        self.tools_log_body: ttk.Frame | None = None
        self.tools_log_toggle_text: tk.StringVar | None = None
        self.tools_log_visible = False
        self.tools_checked_tools: set[str] = set()
        self.tools_check_vars: dict[str, tk.BooleanVar] = {}
        self.tools_status_icon_labels: dict[str, ttk.Label] = {}
        self.python_env_check_button: ttk.Button | None = None
        self.python_env_install_button: ttk.Button | None = None
        self.tools_refresh_button: ttk.Button | None = None
        self.tools_select_all_button: ttk.Button | None = None
        self.tools_unselect_all_button: ttk.Button | None = None
        self.tools_select_missing_button: ttk.Button | None = None
        self.tools_download_button: ttk.Button | None = None
        self.tools_delete_button: ttk.Button | None = None
        self.tools_row_widgets: dict[str, dict] = {}
        self.python_env_status = tk.StringVar(value="Not checked")
        self.python_env_hint = tk.StringVar(value=sys.executable or "")
        self.python_env_status_icon_label: ttk.Label | None = None
        self.python_env_status_label: ttk.Label | None = None
        self.tool_image_statuses: dict[str, dict[str, str]] = {"Local": {}, "Server": {}}
        self.tool_image_sizes: dict[str, dict[str, str]] = {"Local": {}, "Server": {}}
        self.tool_image_installed_sizes: dict[str, dict[str, str]] = {"Local": {}, "Server": {}}
        self.tools_hub_size_loading = False
        self.tool_status_labels: dict[str, ttk.Label] = {}
        self._last_input_source = self.state.input_source.get()
        self._input_source_paths: dict[str, str] = {"Local": "", "Server": "~"}
        self._input_source_selected_files: dict[str, list[str]] = {"Local": [], "Server": []}
        self.progress_log_body: ttk.Frame | None = None
        self.progress_log_toggle_text: tk.StringVar | None = None
        self.progress_log_visible = False
        self.step_summary_rows: dict[str, dict[str, ttk.Label]] = {}
        self.progress_selected_tools: dict[str, str] = {}
        self.remote_poll_in_flight = False
        self.job_monitors: dict[str, dict] = {}

        self._build_ui()
        self._update_python_env_hint()
        self._setup_validation_traces()
        self._validate_configuration()
        self._poll_queues()
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
                self.remote_status_icon_label.configure(image=frame if frame is not None else "", text="", foreground="#2563eb")
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

        if hasattr(self, "tools_status_icon_labels") and hasattr(self, "tool_image_statuses"):
            for tool_key, label in self.tools_status_icon_labels.items():
                status = self._tool_status(tool_key)
                if self._is_busy_status(status):
                    try:
                        label.configure(image=frame if frame is not None else "", text=f"  {status}", compound=tk.LEFT)
                    except Exception:
                        pass

        if hasattr(self, "tool_status_labels") and hasattr(self, "tool_image_statuses"):
            for stage, label in self.tool_status_labels.items():
                tool_var = self.state.tool_vars.get(stage)
                tool_key = tool_key_from_display(tool_var.get()) if tool_var is not None else ""
                status = self._tool_status(tool_key)
                if self._is_busy_status(status):
                    try:
                        label.configure(image=frame if frame is not None else "", text=f" {self._status_label_text(status)}", compound=tk.LEFT)
                    except Exception:
                        pass

        if hasattr(self, "image_rows"):
            for key, row in self.image_rows.items():
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
                if step.get("status") == "Running" and stage in self.step_summary_rows:
                    try:
                        self.step_summary_rows[stage]["icon"].configure(image=frame if frame is not None else "", text="")
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

    def _set_remote_status_icon(self, icon_name: str | None) -> None:
        label = getattr(self, "remote_status_icon_label", None)
        if label is None:
            return
        if icon_name == "running":
            label.configure(image=self._spinner_frame() or "", text="", foreground="#2563eb")
            return
        icon = self._make_icon(icon_name) if icon_name else None
        label.configure(image=icon if icon is not None else "", text="")

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

        self.save_button = self._toolbar_button(toolbar, "save", "Save Workspace", self._save_workspace)
        self.load_button = self._toolbar_button(toolbar, "load", "Load Workspace", self._load_workspace)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12, pady=4)
        
        self.run_button = self._toolbar_button(toolbar, "run", "Run", lambda: self._start_pipeline(resume=False, restart=False), icon_color="#ffffff")
        self.run_button.configure(style="Accent.TButton")
        self.resume_button = self._toolbar_button(toolbar, "resume", "Resume", self._resume_pipeline)
        self.restart_button = self._toolbar_button(toolbar, "restart", "Restart", lambda: self._start_pipeline(resume=False, restart=True))
        self.stop_button = self._toolbar_button(toolbar, "pause", "Stop After Current Step", self._request_stop)
        self.stop_button.configure(state=tk.DISABLED)
        self.attach_button = self._toolbar_button(toolbar, "load", "Attach Job", self._attach_job_dialog)

    def _build_tabs(self, parent: ttk.Frame) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.config_tab = ttk.Frame(self.notebook)
        self.tools_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.config_tab, text="Pipeline configuration")
        self.notebook.add(self.tools_tab, text="Tools / Docker Images")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed)

        build_configuration_tab(self.config_tab, self)
        build_tools_tab(self.tools_tab, self)

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

    def _validate_thread_input(self, proposed: str) -> bool:
        if self.state.run_target.get() == "Server" and not self._server_thread_max_known():
            return proposed == ""
        if proposed == "":
            return True
        try:
            value = int(proposed)
        except ValueError:
            return False
        if value < 1:
            return False
        return self.max_threads is None or value <= self.max_threads

    def _clamp_threads(self) -> None:
        if self.max_threads is None:
            return
        try:
            value = int(self.state.threads.get())
        except (tk.TclError, ValueError):
            return
        clamped = min(max(value, 1), self.max_threads)
        if clamped != value:
            self.state.threads.set(clamped)

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
            spinbox_state = tk.NORMAL if self.state.run_target.get() != "Server" or self._server_thread_max_known() else tk.DISABLED
            spinbox.configure(to=max_value, state=spinbox_state)
        self._clamp_threads()
        self._validate_configuration()

    def _current_remote_thread_signature(self) -> tuple[str, int, str, str, str] | None:
        return self._current_remote_connection_signature()

    def _current_remote_connection_signature(self) -> tuple[str, int, str, str, str] | None:
        host = self.state.remote_host.get().strip()
        username = self.state.remote_username.get().strip()
        workspace = self.state.remote_workspace.get().strip() or "~/mri-remote-jobs"
        if not host or not username:
            return None
        try:
            port = int(self.state.remote_port.get())
        except (tk.TclError, ValueError):
            return None
        return (host, port, username, self.state.remote_key_path.get().strip(), workspace)

    def _server_connected(self) -> bool:
        return (
            self.state.run_target.get() == "Server"
            and self._connected_remote_signature is not None
            and self._connected_remote_signature == self._current_remote_connection_signature()
        )

    def _remote_actions_enabled(self) -> bool:
        return self.state.run_target.get() != "Server" or self._server_connected()

    def _server_thread_max_known(self) -> bool:
        if self.max_threads is None:
            return False
        return self._server_connected() and self._remote_thread_max_signature == self._current_remote_thread_signature()

    def _invalidate_remote_thread_max(self) -> None:
        if self.state.run_target.get() != "Server":
            return
        current_signature = self._current_remote_connection_signature()
        if self._connected_remote_signature is not None and current_signature == self._connected_remote_signature:
            return
        self._cancel_remote_health_check()
        self._thread_max_request_id += 1
        self._connected_remote_signature = None
        self._remote_thread_max_signature = None
        self._set_thread_max(None)
        self._reset_remote_tool_image_state()
        self.state.remote_status.set("Remote: disconnected")
        self._set_remote_status_icon("pending")
        self._set_python_env_status("Not checked")
        self._sync_remote_connection_controls()

    def _reset_remote_tool_image_state(self) -> None:
        self.tool_image_statuses["Server"] = {}
        self.tool_image_installed_sizes["Server"] = {}
        self.tools_checked_tools.clear()
        self._refresh_tools_tree()
        self._update_config_tool_status_labels()
        self._update_tools_download_button()
        self._validate_configuration()

    def _handle_remote_connection_lost(self, reason: str = "") -> None:
        if self._connected_remote_signature is None and not self.remote_connecting:
            return
        self._cancel_remote_health_check()
        self.remote_connecting = False
        self._thread_max_request_id += 1
        self._connected_remote_signature = None
        self._remote_thread_max_signature = None
        self._set_thread_max(None)
        self._reset_remote_tool_image_state()
        self.state.remote_status.set("Remote: disconnected unexpectedly")
        self._set_remote_status_icon("failed")
        self._set_python_env_status("Not checked")
        self._sync_remote_connection_controls()
        self._validate_configuration()
        detail = f"\n\n{reason}" if reason else ""
        messagebox.showwarning("Server disconnected", "The server connection was lost. Remote actions are disabled until you connect again." + detail)

    def _cancel_remote_health_check(self) -> None:
        after_id = self.remote_health_after_id
        self.remote_health_after_id = None
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass

    def _schedule_remote_health_check(self, delay_ms: int = 15000) -> None:
        self._cancel_remote_health_check()
        if not self._server_connected():
            return
        self.remote_health_after_id = self.root.after(delay_ms, self._remote_health_check)

    def _ssh_config_from_current_remote(self) -> SSHConfig | None:
        host = self.state.remote_host.get().strip()
        username = self.state.remote_username.get().strip()
        if not host or not username:
            return None
        try:
            port = int(self.state.remote_port.get())
        except (tk.TclError, ValueError):
            return None
        return SSHConfig(
            host=host,
            port=port,
            username=username,
            password=self.state.remote_password.get(),
            key_path=self.state.remote_key_path.get().strip(),
        )

    def _remote_health_check(self) -> None:
        self.remote_health_after_id = None
        if self.remote_health_in_flight or not self._server_connected():
            return
        signature = self._connected_remote_signature
        ssh_config = self._ssh_config_from_current_remote()
        if signature is None or ssh_config is None:
            self._handle_remote_connection_lost("Remote server configuration is incomplete.")
            return
        self.remote_health_in_flight = True

        def worker() -> None:
            error = ""
            try:
                with RemoteSSHClient(ssh_config, lambda _line: None) as ssh:
                    code, _text = ssh.read_text("true")
                if code != 0:
                    error = f"Health check exited with code {code}."
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"

            def finish() -> None:
                self.remote_health_in_flight = False
                if signature != self._connected_remote_signature:
                    return
                if error:
                    self._handle_remote_connection_lost(error)
                else:
                    self._schedule_remote_health_check()

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _sync_remote_connection_controls(self) -> None:
        server_mode = self.state.run_target.get() == "Server"
        editing_state = tk.NORMAL if server_mode and not self.remote_connecting else tk.DISABLED

        if self.run_target_combo is not None:
            self.run_target_combo.configure(state=tk.DISABLED if self.remote_connecting else "readonly")
        for widget in (
            self.remote_host_entry,
            self.remote_port_entry,
            self.remote_username_entry,
            self.remote_password_entry,
            self.remote_key_entry,
            self.remote_key_browse_button,
            self.remote_workspace_entry,
        ):
            if widget is not None:
                widget.configure(state=editing_state)
        if self.remote_connect_button is not None:
            if self.remote_connecting:
                self.remote_connect_button.configure(text="Connecting...", state=tk.DISABLED)
            else:
                self.remote_connect_button.configure(text="Connect Server", state=tk.NORMAL if server_mode else tk.DISABLED)

        self._refresh_tools_tree()
        self._update_config_tool_status_labels()
        self._sync_remote_action_buttons()
        self._sync_input_source_controls()
        self._set_thread_max(self.max_threads)

    def _sync_remote_action_buttons(self) -> None:
        enabled = self._remote_actions_enabled()
        state = tk.NORMAL if enabled else tk.DISABLED
        for button in (
            self.python_env_check_button,
            self.python_env_install_button,
            self.tools_refresh_button,
            self.tools_select_all_button,
            self.tools_unselect_all_button,
            self.tools_select_missing_button,
        ):
            if button is not None:
                button.configure(state=state)
        self._update_tools_action_buttons()

    def _require_remote_connection(self, action: str) -> bool:
        if self.state.run_target.get() != "Server" or self._server_connected():
            return True
        messagebox.showwarning("Server not connected", f"Connect to the server before {action}.")
        return False

    def _read_remote_thread_max(self, ssh_config) -> int | None:
        command = "getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || python3 -c 'import os; print(os.cpu_count() or 1)'"
        with RemoteSSHClient(ssh_config, lambda _line: None) as ssh:
            code, text = ssh.read_text(command)
        if code != 0:
            return None
        for token in text.replace("\n", " ").split():
            try:
                value = int(token)
            except ValueError:
                continue
            if value > 0:
                return value
        return None

    def _refresh_thread_max_for_target(self) -> None:
        if self.state.run_target.get() != "Server":
            self._thread_max_request_id += 1
            self._cancel_remote_health_check()
            self._connected_remote_signature = None
            self._remote_thread_max_signature = None
            self._reset_remote_tool_image_state()
            self._set_thread_max(self.local_max_threads)
            return

        self._thread_max_request_id += 1
        if self._server_connected():
            self._set_thread_max(self.max_threads)
            return
        self._remote_thread_max_signature = None
        self._set_thread_max(None)

    def _remote_venv_display_path(self) -> str:
        workspace = (self.state.remote_workspace.get().strip() or "~/mri-remote-jobs").rstrip("/")
        return f"{workspace}/.venv"

    def _update_python_env_hint(self) -> None:
        if self.state.run_target.get() == "Server":
            self.python_env_hint.set(self._remote_venv_display_path() if self.state.remote_workspace.get().strip() else "")
        else:
            self.python_env_hint.set(sys.executable or "")

    def _on_run_target_changed(self) -> None:
        if self.remote_body is None:
            return
        enabled = self.state.run_target.get() == "Server"
        if not enabled:
            self._cancel_remote_health_check()
            self._connected_remote_signature = None
        desired_source = "Server" if enabled else "Local"
        if self.state.input_source.get() != desired_source:
            self._switch_input_source(desired_source)
        self.state.server_text.set("Server: remote" if enabled else "Server: local")
        if self.remote_frame is not None:
            if enabled:
                try:
                    self.remote_frame.pack(**(self.remote_pack_options or {"fill": tk.X, "pady": (0, 18)}))
                except tk.TclError:
                    pass
            else:
                self.remote_frame.pack_forget()
        self._set_widget_tree_state(self.remote_body, tk.NORMAL if enabled else tk.DISABLED)
        if enabled:
            self.state.remote_status.set("Remote: connected" if self._server_connected() else "Remote: disconnected")
        else:
            self.state.remote_status.set("")
        self._update_python_env_hint()
        self._refresh_thread_max_for_target()
        self._set_python_env_status("Not checked")
        self._sync_input_source_controls()
        self._sync_remote_connection_controls()
        self._refresh_tools_tree()
        self._update_config_tool_status_labels()
        self._validate_configuration()

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
        connected = self._server_connected()
        self.input_location_label_var.set("Server Input Location" if server_run else "Input location")
        if self.input_browse_button is not None:
            self.input_browse_button.configure(text="Browse Server" if server_run else "Browse")
            if server_run and not connected:
                self.input_browse_button.configure(state=tk.DISABLED)
            else:
                self.input_browse_button.configure(state=tk.NORMAL)
        if self.upload_input_row is not None:
            if server_run:
                self.upload_input_row.grid()
                if self.upload_input_button is not None:
                    self.upload_input_button.configure(state=tk.NORMAL if connected else tk.DISABLED)
            else:
                self.upload_input_row.grid_remove()
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

    def _upload_input_to_server_placeholder(self) -> None:
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Upload input to server")
        dialog.geometry("1080x650")
        dialog.transient(self.root)
        dialog.grab_set()

        ssh_holder: dict[str, RemoteSSHClient | None] = {"ssh": None}
        local_entries: list[dict] = []
        server_entries: list[dict] = []
        upload_running = {"value": False}

        def initial_local_dir() -> str:
            raw = self.state.input_path.get().strip()
            if raw and ";" not in raw:
                path = Path(raw).expanduser()
                if path.is_file():
                    return str(path.parent)
                if path.is_dir():
                    return str(path)
            return str(PROJECT_ROOT)

        def initial_server_dir() -> str:
            raw = self.state.input_path.get().strip()
            if self.state.input_source.get() == "Server" and raw:
                first = raw.split(";", 1)[0].strip()
                if first and not first.endswith("/") and "." in posixpath.basename(first):
                    return posixpath.dirname(first) or "~"
                return first
            return self.state.remote_workspace.get().strip() or "~"

        local_path = tk.StringVar(value=initial_local_dir())
        server_path = tk.StringVar(value=initial_server_dir())
        status_text = tk.StringVar(value="Connecting to server...")
        progress_text = tk.StringVar(value="Ready")
        progress_percent_text = tk.StringVar(value="0%")

        top = ttk.Frame(dialog, padding=(12, 12, 12, 6))
        top.pack(fill=tk.X)
        start_button = ttk.Button(top, text="Start upload", style="Accent.TButton", state=tk.DISABLED)
        start_button.pack(side=tk.LEFT)
        ttk.Label(top, textvariable=progress_text, anchor=tk.W).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 8))
        ttk.Label(top, textvariable=progress_percent_text, width=6, anchor=tk.E).pack(side=tk.RIGHT)
        progress = ttk.Progressbar(dialog, mode="determinate", maximum=1, value=0)
        progress.pack(fill=tk.X, padx=12, pady=(0, 6))
        ttk.Label(dialog, textvariable=status_text, foreground="#64748b").pack(anchor=tk.W, padx=12, pady=(0, 8))

        panes = ttk.PanedWindow(dialog, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        local_frame = ttk.Frame(panes, padding=8)
        server_frame = ttk.Frame(panes, padding=8)
        panes.add(local_frame, weight=1)
        panes.add(server_frame, weight=1)

        def build_browser(parent: ttk.Frame, title: str, variable: tk.StringVar, go_cmd, up_cmd, new_folder_cmd=None, selectmode=tk.BROWSE):
            ttk.Label(parent, text=title, font=("Inter", 10, "bold")).pack(anchor=tk.W, pady=(0, 6))
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, pady=(0, 8))
            ttk.Entry(row, textvariable=variable).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
            ttk.Button(row, text="↵", width=3, command=go_cmd).pack(side=tk.LEFT, padx=(0, 6))
            ttk.Button(row, text="↑", width=3, command=up_cmd).pack(side=tk.LEFT, padx=(0, 6))
            if new_folder_cmd is not None:
                ttk.Button(row, text="+ Folder", command=new_folder_cmd).pack(side=tk.LEFT)
            list_frame = ttk.Frame(parent)
            list_frame.pack(fill=tk.BOTH, expand=True)
            listing = tk.Listbox(list_frame, selectmode=selectmode, activestyle="dotbox")
            scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listing.yview)
            listing.configure(yscrollcommand=scroll.set)
            listing.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scroll.pack(side=tk.RIGHT, fill=tk.Y)
            return listing

        def is_mri_name(name: str) -> bool:
            return name.lower().endswith((".nii", ".nii.gz", ".mgz", ".mgh", ".dcm", ".dicom", ".ima"))

        def refresh_local(path_text: str | None = None) -> None:
            nonlocal local_entries
            path = Path(path_text or local_path.get().strip() or ".").expanduser()
            try:
                path = path.resolve()
                dirs = []
                files = []
                for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                    if child.name.startswith("."):
                        continue
                    entry = {"name": child.name, "path": str(child), "is_dir": child.is_dir()}
                    if child.is_dir():
                        dirs.append(entry)
                    elif child.is_file():
                        files.append(entry)
                local_entries = [{"name": "..", "path": str(path.parent), "is_dir": True}, *dirs, *files]
                local_list.delete(0, tk.END)
                for entry in local_entries:
                    prefix = "[D] " if entry["is_dir"] else "    "
                    local_list.insert(tk.END, prefix + entry["name"])
                local_path.set(str(path))
                status_text.set("Select local files or DICOM folders to upload.")
            except Exception as exc:
                status_text.set(f"Local browse failed: {type(exc).__name__}: {exc}")

        def normalize_server_path(path_text: str) -> str:
            ssh = ssh_holder.get("ssh")
            path = path_text.strip() or "~"
            if ssh is not None:
                try:
                    path = ssh.expand_path(path)
                except Exception:
                    pass
            return posixpath.normpath(path) if path.startswith("/") else path

        def refresh_server(path_text: str | None = None) -> None:
            nonlocal server_entries
            ssh = ssh_holder.get("ssh")
            if ssh is None:
                return
            try:
                path = normalize_server_path(path_text or server_path.get())
                attrs = ssh.sftp.listdir_attr(path)
                dirs = []
                files = []
                for item in attrs:
                    if item.filename.startswith("."):
                        continue
                    entry = {"name": item.filename, "path": posixpath.join(path, item.filename), "is_dir": stat.S_ISDIR(item.st_mode)}
                    if entry["is_dir"]:
                        dirs.append(entry)
                    else:
                        files.append(entry)
                server_entries = [{"name": "..", "path": posixpath.dirname(path.rstrip("/")) or "/", "is_dir": True}, *sorted(dirs, key=lambda x: x["name"].lower()), *sorted(files, key=lambda x: x["name"].lower())]
                server_list.delete(0, tk.END)
                for entry in server_entries:
                    prefix = "[D] " if entry["is_dir"] else "    "
                    server_list.insert(tk.END, prefix + entry["name"])
                server_path.set(path)
                status_text.set("Choose the server destination folder.")
            except Exception as exc:
                status_text.set(f"Server browse failed: {type(exc).__name__}: {exc}")

        def create_server_folder() -> None:
            ssh = ssh_holder.get("ssh")
            if ssh is None:
                messagebox.showerror("Server not connected", "SSH server is not connected yet.", parent=dialog)
                return
            current = normalize_server_path(server_path.get())
            name = simpledialog.askstring("New server folder", "Folder name:", parent=dialog)
            if not name:
                return
            name = name.strip().strip("/")
            if not name or "/" in name or name in {".", ".."}:
                messagebox.showerror("Invalid folder name", "Folder name cannot be empty, '.', '..', or contain '/'.", parent=dialog)
                return
            new_path = posixpath.join(current, name)
            try:
                ssh.mkdir_p(new_path)
                refresh_server(new_path)
                status_text.set(f"Created folder: {new_path}")
            except Exception as exc:
                messagebox.showerror("Create folder failed", f"Could not create folder:\n\n{type(exc).__name__}: {exc}", parent=dialog)

        local_list = build_browser(
            local_frame,
            "Local folder",
            local_path,
            lambda: refresh_local(local_path.get()),
            lambda: refresh_local(str(Path(local_path.get()).expanduser().parent)),
            selectmode=tk.EXTENDED,
        )
        server_list = build_browser(
            server_frame,
            "Server folder",
            server_path,
            lambda: refresh_server(server_path.get()),
            lambda: refresh_server(posixpath.dirname(normalize_server_path(server_path.get()).rstrip("/")) or "/"),
            new_folder_cmd=create_server_folder,
        )

        def open_local(_event=None) -> None:
            selection = local_list.curselection()
            if selection and local_entries[selection[0]]["is_dir"]:
                refresh_local(local_entries[selection[0]]["path"])

        def open_server(_event=None) -> None:
            selection = server_list.curselection()
            if selection and server_entries[selection[0]]["is_dir"]:
                refresh_server(server_entries[selection[0]]["path"])

        def selected_local_inputs() -> list[Path]:
            inputs: list[Path] = []
            for idx in local_list.curselection():
                entry = local_entries[idx]
                if entry["name"] == "..":
                    continue
                inputs.append(Path(entry["path"]))
            return inputs

        def upload_file_pairs(inputs: list[Path], dest_dir: str) -> tuple[list[tuple[Path, str]], list[str]]:
            pairs: list[tuple[Path, str]] = []
            remote_roots: list[str] = []
            for src in inputs:
                if src.is_dir():
                    remote_root = posixpath.join(dest_dir, src.name)
                    remote_roots.append(remote_root)
                    for root, dirs, files in os.walk(src):
                        dirs[:] = [name for name in dirs if not name.startswith(".")]
                        for name in sorted(files):
                            if name.startswith("."):
                                continue
                            local_file = Path(root) / name
                            rel = local_file.relative_to(src).as_posix()
                            pairs.append((local_file, posixpath.join(remote_root, rel)))
                else:
                    remote_file = posixpath.join(dest_dir, src.name)
                    remote_roots.append(remote_file)
                    pairs.append((src, remote_file))
            return pairs, remote_roots

        def preflight_upload(pairs: list[tuple[Path, str]], dest_dir: str) -> tuple[list[tuple[Path, str]], int] | None:
            ssh = ssh_holder.get("ssh")
            if ssh is None:
                return None
            ssh.mkdir_p(dest_dir)
            upload_items: list[tuple[Path, str]] = []
            skipped = 0
            overwrite_all: bool | None = None
            for src, remote_file in pairs:
                ssh.mkdir_p(posixpath.dirname(remote_file))
                exists = False
                try:
                    ssh.sftp.stat(remote_file)
                    exists = True
                except OSError:
                    exists = False
                if exists:
                    if overwrite_all is True:
                        upload_items.append((src, remote_file))
                        continue
                    if overwrite_all is False:
                        skipped += 1
                        continue
                    choice = self._ask_upload_overwrite(remote_file)
                    if choice == "cancel":
                        return None
                    if choice == "yes_all":
                        overwrite_all = True
                        upload_items.append((src, remote_file))
                    elif choice == "no_all":
                        overwrite_all = False
                        skipped += 1
                    elif choice == "yes":
                        upload_items.append((src, remote_file))
                    else:
                        skipped += 1
                        continue
                else:
                    upload_items.append((src, remote_file))
            return upload_items, skipped

        def apply_uploaded_inputs(remote_paths: list[str], uploaded_dirs: bool) -> None:
            if not remote_paths:
                return
            self.state.input_source.set("Server")
            if uploaded_dirs:
                self.state.input_mode.set("dir")
                self.state.selected_files = []
                self.state.input_path.set(remote_paths[0] if len(remote_paths) == 1 else normalize_server_path(server_path.get()))
            elif len(remote_paths) == 1:
                self.state.input_mode.set("file")
                self.state.selected_files = remote_paths
                self.state.input_path.set(remote_paths[0])
            else:
                self.state.input_mode.set("files")
                self.state.selected_files = remote_paths
                self.state.input_path.set("; ".join(remote_paths))
            self._input_source_paths["Server"] = self.state.input_path.get().strip()
            self._input_source_selected_files["Server"] = list(self.state.selected_files)
            self._last_input_source = "Server"
            self._sync_input_source_controls()
            self._refresh_input_label()
            self._validate_configuration()

        def start_upload() -> None:
            if upload_running["value"]:
                return
            ssh = ssh_holder.get("ssh")
            if ssh is None:
                messagebox.showerror("Server not connected", "SSH server is not connected yet.", parent=dialog)
                return
            inputs = selected_local_inputs()
            if not inputs:
                messagebox.showwarning("No files selected", "Select one or more local files or DICOM folders to upload.", parent=dialog)
                return
            dest_dir = normalize_server_path(server_path.get())
            pairs, remote_paths = upload_file_pairs(inputs, dest_dir)
            uploaded_dirs = any(path.is_dir() for path in inputs)
            if not pairs:
                status_text.set("No files found to upload.")
                return
            preflight = preflight_upload(pairs, dest_dir)
            if preflight is None:
                status_text.set("Upload cancelled.")
                return
            upload_items, skipped = preflight
            if not upload_items:
                status_text.set("No files uploaded.")
                return
            upload_running["value"] = True
            self._set_button_busy(start_button, True, "Uploading")
            progress.configure(maximum=len(pairs), value=skipped)
            percent = int((skipped / len(pairs)) * 100) if pairs else 0
            progress_text.set(f"Uploading {len(upload_items)} file(s), skipped {skipped}")
            progress_percent_text.set(f"{percent}%")

            def worker() -> None:
                uploaded: list[str] = []
                processed = skipped
                try:
                    for src, remote_file in upload_items:
                        processed += 1
                        self.root.after(0, lambda p=processed, name=src.name: (status_text.set(f"Uploading: {name}"), progress.configure(value=p), progress_text.set(f"{p} of {len(pairs)} files"), progress_percent_text.set(f"{int((p / len(pairs)) * 100)}%")))
                        ssh.sftp.put(str(src), remote_file)
                        uploaded.append(remote_file)
                    self.root.after(0, lambda: (progress.configure(value=len(pairs)), progress_text.set("Upload complete"), progress_percent_text.set("100%"), status_text.set(f"Uploaded {len(uploaded)} file(s)."), apply_uploaded_inputs(remote_paths, uploaded_dirs), refresh_server(dest_dir)))
                except Exception as exc:
                    self.root.after(0, lambda e=exc: (progress_text.set("Upload failed"), status_text.set(f"Upload failed: {type(e).__name__}: {e}")))
                finally:
                    def finish() -> None:
                        upload_running["value"] = False
                        self._set_button_busy(start_button, False)
                        if ssh_holder.get("ssh") is not None:
                            start_button.configure(state=tk.NORMAL)
                    self.root.after(0, finish)

            threading.Thread(target=worker, daemon=True).start()

        def connect_server() -> None:
            try:
                ssh = RemoteSSHClient(ssh_config, lambda _line: None)
                ssh.connect()
                ssh_holder["ssh"] = ssh
                refresh_server(server_path.get())
                start_button.configure(state=tk.NORMAL)
            except Exception as exc:
                status_text.set(f"SSH failed: {type(exc).__name__}: {exc}")

        def close() -> None:
            if upload_running["value"]:
                if not messagebox.askyesno("Upload running", "Close while upload is running?", parent=dialog):
                    return
            ssh = ssh_holder.get("ssh")
            if ssh is not None:
                ssh.close()
                ssh_holder["ssh"] = None
            dialog.destroy()

        local_list.bind("<Double-Button-1>", open_local)
        server_list.bind("<Double-Button-1>", open_server)
        start_button.configure(command=start_upload)
        dialog.protocol("WM_DELETE_WINDOW", close)
        refresh_local(local_path.get())
        self.root.after(50, connect_server)

    def _browse_input(self) -> None:
        if self.state.run_target.get() == "Server":
            if self.state.input_source.get() != "Server":
                self._switch_input_source("Server")
            self._browse_remote_input()
            return
        if self.state.input_source.get() != "Local":
            self._switch_input_source("Local")
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
        else:
            path = filedialog.askdirectory(title="Select MRI input folder")
            if path:
                self.state.selected_files = []
                self.state.input_path.set(path)
        self._input_source_paths[self.state.input_source.get()] = self.state.input_path.get().strip()
        self._input_source_selected_files[self.state.input_source.get()] = list(self.state.selected_files)
        self._refresh_input_label()

    def _browse_remote_input(self) -> None:
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return
        mode = self.state.input_mode.get()
        dialog = tk.Toplevel(self.root)
        dialog.title("Browse server input")
        dialog.geometry("760x520")
        dialog.transient(self.root)
        dialog.grab_set()

        current_path = tk.StringVar(value=self.state.input_path.get().strip() or "~")
        status_text = tk.StringVar(value="Connecting...")
        selected: dict[str, list[str] | str] = {"paths": []}
        entries: list[dict] = []
        ssh_holder: dict[str, RemoteSSHClient | None] = {"ssh": None}

        top = ttk.Frame(dialog, padding=(12, 12, 12, 6))
        top.pack(fill=tk.X)
        ttk.Label(top, text="Server path").pack(anchor=tk.W)
        path_row = ttk.Frame(top)
        path_row.pack(fill=tk.X, pady=(2, 6))
        ttk.Entry(path_row, textvariable=current_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        body = ttk.Frame(dialog, padding=(12, 0, 12, 6))
        body.pack(fill=tk.BOTH, expand=True)
        selectmode = tk.EXTENDED if mode == "files" else tk.BROWSE
        listing = tk.Listbox(body, selectmode=selectmode, height=18, activestyle="dotbox")
        scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=listing.yview)
        listing.configure(yscrollcommand=scroll.set)
        listing.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        bottom = ttk.Frame(dialog, padding=(12, 0, 12, 12))
        bottom.pack(fill=tk.X)
        ttk.Label(bottom, textvariable=status_text, foreground="#64748b").pack(side=tk.LEFT, fill=tk.X, expand=True)

        def normalize_remote_path(path: str) -> str:
            path = path.strip() or "~"
            ssh = ssh_holder.get("ssh")
            if ssh is not None:
                try:
                    path = ssh.expand_path(path)
                except Exception:
                    pass
            return posixpath.normpath(path) if path.startswith("/") else path

        def is_mri_name(name: str) -> bool:
            lower = name.lower()
            return lower.endswith((".nii", ".nii.gz", ".mgz", ".mgh", ".dcm", ".dicom", ".ima"))

        def is_dicom_name(name: str) -> bool:
            return name.lower().endswith((".dcm", ".dicom", ".ima"))

        def dir_contains_dicom(path: str) -> bool:
            ssh = ssh_holder.get("ssh")
            if ssh is None:
                return False
            try:
                for item in ssh.sftp.listdir_attr(path):
                    if item.filename.startswith("."):
                        continue
                    if not stat.S_ISDIR(item.st_mode) and is_dicom_name(item.filename):
                        return True
            except OSError:
                return False
            return False

        def load_dir(path: str) -> None:
            nonlocal entries
            ssh = ssh_holder.get("ssh")
            if ssh is None:
                return
            try:
                path = normalize_remote_path(path)
                attrs = ssh.sftp.listdir_attr(path)
                dirs = []
                files = []
                for item in attrs:
                    if item.filename.startswith("."):
                        continue
                    row = {"name": item.filename, "path": posixpath.join(path, item.filename), "is_dir": stat.S_ISDIR(item.st_mode)}
                    if row["is_dir"]:
                        dirs.append(row)
                    elif mode != "dir" and is_mri_name(item.filename):
                        files.append(row)
                entries = [{"name": "..", "path": posixpath.dirname(path.rstrip("/")) or "/", "is_dir": True}, *sorted(dirs, key=lambda x: x["name"].lower()), *sorted(files, key=lambda x: x["name"].lower())]
                listing.delete(0, tk.END)
                for row in entries:
                    prefix = "[D] " if row["is_dir"] else "    "
                    listing.insert(tk.END, prefix + row["name"])
                current_path.set(path)
                status_text.set("Select a folder." if mode == "dir" else "Double-click folders to browse; select MRI file(s) or DICOM folder(s).")
            except Exception as exc:
                status_text.set(f"Browse failed: {type(exc).__name__}: {exc}")

        def connect_and_load() -> None:
            try:
                ssh = RemoteSSHClient(ssh_config, lambda _line: None)
                ssh.connect()
                ssh_holder["ssh"] = ssh
                load_dir(current_path.get())
            except Exception as exc:
                status_text.set(f"SSH failed: {type(exc).__name__}: {exc}")

        def open_selected(_event=None) -> None:
            selection = listing.curselection()
            if not selection:
                return
            row = entries[selection[0]]
            if row["is_dir"]:
                load_dir(str(row["path"]))

        def choose() -> None:
            path = normalize_remote_path(current_path.get())
            selection = listing.curselection()
            chosen: list[str] = []
            if mode == "dir":
                if selection and entries[selection[0]]["is_dir"]:
                    path = str(entries[selection[0]]["path"])
                selected["paths"] = [path]
            else:
                for idx in selection:
                    row = entries[idx]
                    if not row["is_dir"]:
                        chosen.append(str(row["path"]))
                    elif dir_contains_dicom(str(row["path"])):
                        chosen.append(str(row["path"]))
                if not chosen and mode == "file":
                    chosen = [path]
                selected["paths"] = chosen
            dialog.destroy()

        def close() -> None:
            dialog.destroy()

        def on_destroy(_event=None) -> None:
            ssh = ssh_holder.get("ssh")
            if ssh is not None:
                ssh.close()
                ssh_holder["ssh"] = None

        ttk.Button(path_row, text="Go", command=lambda: load_dir(current_path.get())).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(path_row, text="Up", command=lambda: load_dir(posixpath.dirname(normalize_remote_path(current_path.get()).rstrip("/")) or "/")).pack(side=tk.LEFT)
        listing.bind("<Double-Button-1>", open_selected)
        ttk.Button(bottom, text="Cancel", command=close).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(bottom, text="Select", style="Accent.TButton", command=choose).pack(side=tk.RIGHT)
        dialog.protocol("WM_DELETE_WINDOW", close)
        dialog.bind("<Destroy>", on_destroy, add="+")
        self.root.after(50, connect_and_load)
        self.root.wait_window(dialog)

        paths = list(selected.get("paths") or [])
        if not paths:
            return
        if mode == "file":
            self.state.selected_files = [paths[0]]
            self.state.input_path.set(paths[0])
        elif mode == "files":
            self.state.selected_files = paths
            self.state.input_path.set("; ".join(paths))
        else:
            self.state.selected_files = []
            self.state.input_path.set(paths[0])
        self._input_source_paths[self.state.input_source.get()] = self.state.input_path.get().strip()
        self._input_source_selected_files[self.state.input_source.get()] = list(self.state.selected_files)
        self._refresh_input_label()

    def _mri_filetypes(self) -> tuple[tuple[str, str], tuple[str, str]]:
        return (("MRI files", "*.nii *.nii.gz *.mgz *.mgh *.dcm *.dicom *.ima"), ("All files", "*.*"))

    def _browse_directory(self, variable: tk.StringVar) -> None:
        path = filedialog.askdirectory(title="Select directory")
        if path:
            variable.set(path)

    def _browse_remote_key(self) -> None:
        path = filedialog.askopenfilename(
            title="Select SSH private key",
            filetypes=(("SSH key", "*"), ("All files", "*.*")),
        )
        if path:
            self.state.remote_key_path.set(path)

    def _apply_stats_preset_for_mode(self, mode: str) -> None:
        preset = self.PRESET_CONFIGS.get(mode)
        if preset is None:
            return
        enabled = set(preset["stats"])

        for stat, var in self.state.stat_vector_enabled_vars.items():
            var.set(stat in enabled)
        for stat in enabled:
            if not self.state.selected_atlases_for_stat(stat):
                first_atlas = next(iter(self.state.stat_atlas_vars.get(stat, {})), "")
                if first_atlas:
                    self.state.set_stat_atlas_choice(stat, first_atlas)

    def _update_stats_vector_controls(self, mode: str) -> None:
        locked = set()
        if mode in self.PRESET_CONFIGS:
            locked = set(STAT_VECTOR_DEFS)

        for stat, check in getattr(self, "stat_vector_checkbuttons", {}).items():
            check.configure(state=tk.DISABLED if stat in locked else tk.NORMAL)
        for stat, combo in getattr(self, "stat_atlas_combos", {}).items():
            var = self.state.stat_vector_enabled_vars.get(stat)
            combo.configure(state="readonly" if var is not None and var.get() else tk.DISABLED)

    def _apply_pipeline_mode(self, apply_stats_preset: bool = True, show_custom_tools: bool = True, update_tools_visibility: bool = True) -> None:
        if getattr(self, "_preserve_pipeline_tools_visibility", False):
            update_tools_visibility = False
        mode = self._normalize_pipeline_mode(self.state.pipeline_mode.get())
        if mode != self.state.pipeline_mode.get():
            self.state.pipeline_mode.set(mode)
            return
        if apply_stats_preset:
            self._apply_stats_preset_for_mode(mode)
        preset = self.PRESET_CONFIGS.get(mode)
        if preset is not None:
            fixed_tools = preset["tools"]
            for stage, tool in fixed_tools.items():
                if stage in self.state.tool_vars:
                    self.state.tool_vars[stage].set(tool_display_name(tool) if tool else "")
            for combo in self.tool_combos.values():
                combo.configure(state="disabled")
            stats = set(preset["stats"])
            if stats == self.VOLUME_STATS:
                self.state.pipeline_note.set(f"{mode}: cortical and subcortical volume vectors are selected. Surface steps 7-8 are skipped.")
            elif stats == self.THICKNESS_STATS:
                suffix = " FastSurfer presets use FastSurferVINN for segmentation and FreeSurfer surface steps for thickness."
                self.state.pipeline_note.set(f"{mode}: cortical thickness vector is selected with FreeSurfer aparc by default. Surface steps 7-8 are enabled." + (suffix if mode.startswith("FastSurfer") else ""))
            else:
                suffix = " FastSurfer presets use FastSurferVINN for segmentation and FreeSurfer surface steps for thickness."
                self.state.pipeline_note.set(f"{mode}: volume vectors and cortical thickness are selected. Surface steps 7-8 are enabled." + (suffix if mode.startswith("FastSurfer") else ""))
        else:
            self._apply_custom_tool_defaults()
            for combo in self.tool_combos.values():
                combo.configure(state="readonly")
            self.state.pipeline_note.set("Custom mode: choose tools freely for each stage.")
            if update_tools_visibility:
                self._set_pipeline_tools_visible(show_custom_tools)
        if preset is not None and update_tools_visibility:
            self._set_pipeline_tools_visible(False)
        self._update_stats_vector_controls(mode)
        self._update_config_tool_status_labels()

    def _selected_tools(self) -> dict[str, str]:
        if self._normalize_pipeline_mode(self.state.pipeline_mode.get()) != "Custom":
            self._apply_pipeline_mode(apply_stats_preset=False)
        return self.state.get_selected_tools()

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

        workspace = self.state.collect_workspace()
        workspace_name = Path(path).stem
        workspace["name"] = workspace_name
        self.state.workspace_name = workspace_name
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(workspace, f, indent=2, ensure_ascii=False)
            self._log(f"Saved workspace: {path}")
        except Exception as exc:
            messagebox.showerror("Save workspace failed", str(exc))

    def _load_workspace(self) -> None:
        if self.remote_connecting:
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

        tools_visible = self.pipeline_tools_visible.get()
        self._preserve_pipeline_tools_visibility = True
        try:
            with open(path, "r", encoding="utf-8") as f:
                workspace = json.load(f)
            self.state.workspace_name = Path(path).stem
            self.state.apply_workspace(workspace)
            self._apply_pipeline_mode(apply_stats_preset="stats_vectors" not in workspace, update_tools_visibility=False)
            self._on_run_target_changed()
            self._last_input_source = self.state.input_source.get()
            self._input_source_paths[self._last_input_source] = self.state.input_path.get().strip()
            self._input_source_selected_files[self._last_input_source] = list(self.state.selected_files)
            self._refresh_input_label()
            self._validate_configuration()
            self._log(f"Loaded workspace: {path}")
        except Exception as exc:
            messagebox.showerror("Load workspace failed", str(exc))
        finally:
            self._preserve_pipeline_tools_visibility = False
            self._set_pipeline_tools_visible(tools_visible)

    def _save_config(self) -> None:
        self._save_workspace()

    def _load_config(self) -> None:
        self._load_workspace()

    def _collect_run_config(self) -> dict:
        return {
            "version": 1,
            "type": "mri-pipeline-preset",
            "pipeline_mode": self.state.pipeline_mode.get(),
            "tools": self.state.get_selected_tools(),
            "stats_vectors": self.state.get_stats_vector_config(),
        }

    def _apply_run_config(self, config: dict) -> None:
        self.state.pipeline_mode.set(self._normalize_pipeline_mode(config.get("pipeline_mode", "Custom")))

        tools = config.get("tools", {})
        for stage, value in tools.items():
            if stage in self.state.tool_vars:
                tool_key = tool_key_from_display(value)
                if not tool_key and value in TOOL_DEFS:
                    tool_key = value
                self.state.tool_vars[stage].set(tool_display_name(tool_key) if is_tool_enabled(tool_key) else "")

        self.state.apply_stats_vector_config(config.get("stats_vectors", {}))
        self._apply_pipeline_mode(apply_stats_preset=False)
        self._update_config_tool_status_labels()
        self._validate_configuration()

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
            self._log(f"Saved preset: {path}")
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
            self._log(f"Loaded preset: {path}")
        except Exception as exc:
            messagebox.showerror("Load preset failed", str(exc))


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
                
        self._validate_configuration()

    def _configure_batch(self) -> None:
        from ui.batch_window import BatchConfigWindow
        BatchConfigWindow(self.root, self)

    def _setup_validation_traces(self) -> None:
        variables = [
            self.state.input_source,
            self.state.input_mode,
            self.state.input_path,
            self.state.output_dir,
            self.state.license_dir,
            self.state.device,
            self.state.threads,
            self.state.non_recursive,
            self.state.run_target,
            self.state.remote_host,
            self.state.remote_port,
            self.state.remote_username,
            self.state.remote_key_path,
            self.state.remote_workspace,
            self.state.remote_python,
            self.state.pipeline_mode,
            self.state.export_outputs_enabled,
            self.state.export_default_format,
        ]
        for var in variables:
            var.trace_add("write", lambda *_args: self._validate_configuration())

        self.state.run_target.trace_add("write", lambda *_args: self._update_python_env_hint())
        self.state.remote_workspace.trace_add("write", lambda *_args: self._update_python_env_hint())
        self.state.threads.trace_add("write", lambda *_args: self._clamp_threads())
        for var in (
            self.state.remote_host,
            self.state.remote_port,
            self.state.remote_username,
            self.state.remote_password,
            self.state.remote_key_path,
            self.state.remote_workspace,
        ):
            var.trace_add("write", lambda *_args: self._invalidate_remote_thread_max())

        self.state.input_path.trace_add("write", self._refresh_input_label)

        for tool_var in self.state.tool_vars.values():
            tool_var.trace_add("write", lambda *_args: (self._validate_configuration(), self._update_config_tool_status_labels()))

        for var in [*self.state.export_name_vars.values(), *self.state.export_format_vars.values()]:
            var.trace_add("write", lambda *_args: self._validate_configuration())

        for var in [*self.state.stat_vector_enabled_vars.values(), *self.state.stat_atlas_choice_vars.values()]:
            var.trace_add("write", lambda *_args: self._validate_configuration())

    def _validate_configuration(self) -> bool:
        errors: list[str] = []
        input_source = "Server" if self.state.run_target.get() == "Server" else "Local"
        mode = self.state.input_mode.get()
        raw_input = self.state.input_path.get().strip()
        if not raw_input:
            errors.append("Choose an input MRI file or folder.")
        elif self.state.run_target.get() != "Server" and input_source != "Local":
            errors.append("Local runs can only use local input data.")
        elif input_source == "Server" and self.state.run_target.get() != "Server":
            errors.append("Server input requires Run on = Server.")
        elif input_source == "Local" and mode == "file":
            path = self.state.selected_files[0] if self.state.selected_files else raw_input
            if not _is_supported_mri_input(path):
                errors.append("Input file or DICOM folder does not exist.")
        elif input_source == "Local" and mode == "files":
            files = self.state.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
            if not files:
                errors.append("Choose at least one input file.")
            elif any(not _is_supported_mri_input(p) for p in files):
                errors.append("One or more selected input files or DICOM folders do not exist.")
        elif input_source == "Local":
            if not Path(raw_input).is_dir():
                errors.append("Input folder does not exist.")
        elif input_source == "Server":
            files = self.state.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
            if mode == "file" and raw_input == "~" and not self.state.selected_files:
                errors.append("Choose a server MRI file or upload input to server first.")
            elif mode == "files" and (not files or files == ["~"]):
                errors.append("Choose server MRI files or upload input to server first.")
            elif mode == "dir" and raw_input == "~" and not self.state.selected_files:
                errors.append("Choose a server MRI folder or upload input to server first.")

        if self.state.run_target.get() != "Server" and not self.state.output_dir.get().strip():
            errors.append("Choose an output directory.")
        if self.state.export_outputs_enabled.get():
            invalid_names = [name.get().strip() for name in self.state.export_name_vars.values() if not name.get().strip() or any(sep in name.get() for sep in ("/", "\\"))]
            if invalid_names:
                errors.append("Export file names cannot be empty or contain path separators.")
        for stat, stat_def in STAT_VECTOR_DEFS.items():
            if self.state.stat_vector_enabled_vars.get(stat) and self.state.stat_vector_enabled_vars[stat].get():
                if stat_def.get("atlases") and not self.state.selected_atlases_for_stat(stat):
                    errors.append(f"Choose at least one atlas for {stat_def['label']}.")
        try:
            threads = int(self.state.threads.get())
            if threads < 1:
                errors.append("Threads must be at least 1.")
            elif self.state.run_target.get() == "Server" and self._server_connected() and not self._server_thread_max_known():
                errors.append("Connect Server could not read the server CPU thread limit.")
            elif self.max_threads is not None and threads > self.max_threads:
                errors.append(f"Threads cannot exceed max CPU threads ({self.max_threads}).")
        except (tk.TclError, ValueError):
            errors.append("Threads must be a valid integer.")

        selected_tools = self.state.get_selected_tools()
        missing_stages = [
            stage for stage in STAGE_ORDER
            if stage not in self.OPTIONAL_STAGES and enabled_tools_for_stage(stage) and not selected_tools.get(stage)
        ]
        if missing_stages:
            errors.append("Select one tool for every pipeline stage.")
        disabled_tools = [tool for tool in selected_tools.values() if tool and not is_tool_enabled(tool)]
        if disabled_tools:
            errors.append(f"Disabled tools selected: {', '.join(tool_display_name(tool) for tool in disabled_tools)}")

        target = self.state.run_target.get()
        image_statuses = self.tool_image_statuses.setdefault(target, {})
        required_images: list[str] = []
        for tool in selected_tools.values():
            image = str(TOOL_DEFS.get(tool, {}).get("image", ""))
            if tool and is_tool_enabled(tool) and image and image not in required_images:
                required_images.append(image)
        if required_images and (target != "Server" or self._server_connected()):
            unknown = [image for image in required_images if image_statuses.get(image, "Unknown") == "Unknown"]
            not_installed = [image for image in required_images if image_statuses.get(image, "Unknown") not in {"Installed", "Unknown"}]
            if unknown:
                errors.append("Check Docker images before running.")
            elif not_installed:
                errors.append("Install selected Docker images before running.")

        needs_license = any(TOOL_DEFS.get(tool, {}).get("needs_license") for tool in selected_tools.values())
        if needs_license and not Path(self.state.license_dir.get().strip()).exists():
            errors.append("FreeSurfer license directory is required for selected tools.")

        if self.state.run_target.get() == "Server":
            if not self.state.remote_host.get().strip():
                errors.append("Remote Host/IP is required.")
            if not self.state.remote_username.get().strip():
                errors.append("Remote Username is required.")
            try:
                port = int(self.state.remote_port.get())
                if port < 1 or port > 65535:
                    errors.append("Remote port must be between 1 and 65535.")
            except (tk.TclError, ValueError):
                errors.append("Remote port must be a valid integer.")
            if not self.state.remote_workspace.get().strip():
                errors.append("Remote workspace is required.")
            elif self._current_remote_connection_signature() is not None and not self._server_connected():
                errors.append("Connect to the server before running.")

        ok = not errors
        can_start = self._can_start_new_pipeline()
        if hasattr(self, "run_button"):
            self.run_button.configure(state=tk.NORMAL if ok and can_start else tk.DISABLED)
        if hasattr(self, "restart_button"):
            self.restart_button.configure(state=tk.NORMAL if ok and can_start else tk.DISABLED)
        self.state.config_status.set("Configuration complete. Ready to run." if ok else errors[0])
        return ok


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
    root.geometry("1400x900+80+60")
    root.minsize(1180, 700)
    PipelineGUI(root)
    root.update_idletasks()
    root.deiconify()
    root.lift()
    print(f"MRI Pipeline GUI is running on DISPLAY={os.environ.get('DISPLAY', '')}.", flush=True)
    root.mainloop()

if __name__ == "__main__":
    main()
