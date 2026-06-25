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
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pipeline_runner import (
    PROJECT_ROOT,
    STAGE_ORDER,
    TOOL_DEFS,
    STAT_VECTOR_DEFS,
    enabled_tools_for_stage,
    is_tool_enabled,
    tool_display_name,
    tool_key_from_display,
)
from remote.remote_runner import RemoteRunner
from ui.gui_jobs import JobsMixin
from ui.gui_pipeline import PipelineMixin
from ui.gui_progress import ProgressMixin
from ui.gui_tools import ToolsMixin
from ui.state import AppState
from ui.styles import configure_windows_dpi_awareness, setup_styles
from ui.tabs.config_tab import build_configuration_tab
from ui.tabs.progress_tab import build_progress_tab
from ui.tabs.tools_tab import build_tools_tab


class PipelineGUI(ToolsMixin, JobsMixin, PipelineMixin, ProgressMixin):
    FREESURFER_FIXED_TOOLS = {
        "reorientation": "mri_convert_fs7",
        "brain_extraction": "synthstrip_fs7",
        "segmentation": "synthseg_freesurfer_fs7",
        "template_registration": "",
        "bias_correction": "ants_n4",
        "white_matter_segmentation": "",
        "surface_reconstruction": "",
        "surface_registration": "",
        "stats_extraction": "",
    }

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MRI Pipeline GUI")
        self.root.geometry("1250x950")
        self.root.minsize(1050, 760)

        # Initialize State
        self.state = AppState()
        
        # Apply Styles

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.metrics_queue: queue.Queue[tuple[float | None, int | None, float | None, str]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.running = False
        self.stop_requested = threading.Event()
        
        self.remote_runner: RemoteRunner | None = None
        self.active_job: dict | None = None
        self.job_poll_after_id: str | None = None
        self.job_log_offset = 0
        self.remote_frame: ttk.Frame | None = None
        self.remote_body: ttk.Frame | None = None
        self.remote_pack_options: dict | None = None
        self.remote_toggle_button: ttk.Button | None = None
        self.remote_status_icon_label: ttk.Label | None = None
        self.actions_frame: ttk.Frame | None = None

        self.tool_combos: dict[str, ttk.Combobox] = {}
        self.step_tree: ttk.Treeview | None = None
        self.stage_items: dict[str, str] = {}
        self.notebook: ttk.Notebook | None = None
        self.config_tab: ttk.Frame | None = None
        self.progress_tab: ttk.Frame | None = None
        self.toolbar_icons: dict[str, tk.PhotoImage] = {}
        self.image_runs: dict[str, dict] = {}
        self.image_rows: dict[str, dict] = {}
        self.current_image_key = ""
        self.active_image_key = ""
        self.tools_tab: ttk.Frame | None = None
        self.tools_tree: ttk.Treeview | None = None
        self.tools_table_frame: ttk.Frame | None = None
        self.tools_log_text: tk.Text | None = None
        self.tools_log_body: ttk.Frame | None = None
        self.tools_log_toggle_text: tk.StringVar | None = None
        self.tools_log_visible = False
        self.tools_checked_tools: set[str] = set()
        self.tools_check_vars: dict[str, tk.BooleanVar] = {}
        self.tools_status_icon_labels: dict[str, ttk.Label] = {}
        self.tools_download_button: ttk.Button | None = None
        self.tools_row_widgets: dict[str, dict] = {}
        self.python_env_status = tk.StringVar(value="Not checked")
        self.python_env_hint = tk.StringVar(value=sys.executable or "")
        self.python_env_status_icon_label: ttk.Label | None = None
        self.python_env_status_label: ttk.Label | None = None
        self.tool_image_statuses: dict[str, dict[str, str]] = {"Local": {}, "Server": {}}
        self.tool_status_labels: dict[str, ttk.Label] = {}
        self.progress_log_body: ttk.Frame | None = None
        self.progress_log_toggle_text: tk.StringVar | None = None
        self.progress_log_visible = False
        self.step_summary_rows: dict[str, dict[str, ttk.Label]] = {}
        self.progress_selected_tools: dict[str, str] = {}
        self.remote_poll_in_flight = False

        self._build_ui()
        self._update_python_env_hint()
        self._setup_validation_traces()
        self._validate_configuration()
        self._poll_queues()

        self._spinner_frames = []
        self._spinner_idx = 0
        self._init_spinner_frames()
        if self._spinner_frames:
            self.root.after(100, self._animate_spinner)

    def _init_spinner_frames(self):
        try:
            from PIL import Image, ImageTk
            import os
            icon_path = os.path.join(os.path.dirname(__file__), "icons", "running.png")
            if os.path.exists(icon_path):
                img = Image.open(icon_path).convert("RGBA")
                img_small = img.resize((20, 20), resample=Image.BICUBIC)
                self._spinner_frames_small = []
                for i in range(12):
                    angle = -i * 30
                    rot = img.rotate(angle, resample=Image.BICUBIC)
                    self._spinner_frames.append(ImageTk.PhotoImage(rot))
                    rot_small = img_small.rotate(angle, resample=Image.BICUBIC)
                    self._spinner_frames_small.append(ImageTk.PhotoImage(rot_small))
        except Exception:
            pass

    def _animate_spinner(self):
        if not self._spinner_frames:
            return
        self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_frames)
        frame = self._spinner_frames[self._spinner_idx]
        frame_small = self._spinner_frames_small[self._spinner_idx] if hasattr(self, "_spinner_frames_small") else frame
        
        if hasattr(self, "tools_status_icon_labels") and hasattr(self, "tool_image_statuses"):
            for tool_key, label in self.tools_status_icon_labels.items():
                status = self._tool_status(tool_key)
                if status in {"Downloading", "Checking"}:
                    try:
                        label.configure(image=frame)
                    except Exception:
                        pass
                        
        if hasattr(self, "image_rows"):
            for key, row in self.image_rows.items():
                if row.get("status"):
                    try:
                        status_text = row["status"].cget("text")
                        if status_text == "Running" and row.get("icon"):
                            row["icon"].configure(image=frame_small)
                    except Exception:
                        pass

        run = getattr(self, "image_runs", {}).get(getattr(self, "current_image_key", ""))
        if run and hasattr(self, "step_summary_rows"):
            for stage, step in run.get("steps", {}).items():
                if step.get("status") == "Running" and stage in self.step_summary_rows:
                    try:
                        self.step_summary_rows[stage]["icon"].configure(image=frame)
                    except Exception:
                        pass

        self.root.after(100, self._animate_spinner)

    def _build_ui(self) -> None:
        root_frame = ttk.Frame(self.root)
        root_frame.pack(fill=tk.BOTH, expand=True)

        self._build_app_toolbar(root_frame)
        self._build_status_bar(root_frame)
        self._build_tabs(root_frame)

    def _make_icon(self, name: str) -> tk.PhotoImage | None:
        if name in self.toolbar_icons:
            return self.toolbar_icons[name]
        try:
            import os
            icon_path = os.path.join(os.path.dirname(__file__), "icons", f"{name}.png")
            if os.path.exists(icon_path):
                img = tk.PhotoImage(file=icon_path)
                self.toolbar_icons[name] = img
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
        icon = self._make_icon(icon_name) if icon_name else None
        label.configure(image=icon if icon is not None else "")

    def _toolbar_button(self, parent: ttk.Frame, key: str, label: str, command) -> ttk.Button:
        icon = self._make_icon(key)
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
        
        self.run_button = self._toolbar_button(toolbar, "run", "Run", lambda: self._start_pipeline(resume=False, restart=False))
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
        self.progress_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.config_tab, text="Pipeline configuration")
        self.notebook.add(self.tools_tab, text="Tools / Docker Images")
        self.notebook.add(self.progress_tab, text="Run progress", state="disabled")

        build_configuration_tab(self.config_tab, self)
        build_tools_tab(self.tools_tab, self)
        build_progress_tab(self.progress_tab, self)

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
        self.state.server_text.set("Server: remote" if enabled else "Server: local")
        self.state.remote_visible.set(enabled)
        if self.remote_frame is not None:
            if enabled:
                try:
                    self.remote_frame.pack(**(self.remote_pack_options or {"fill": tk.X, "pady": (0, 10)}))
                except tk.TclError:
                    pass
            else:
                self.remote_frame.pack_forget()
        self._set_widget_tree_state(self.remote_body, tk.NORMAL if enabled else tk.DISABLED)
        self.state.remote_status.set("Remote: configure SSH server" if enabled else "")
        self._update_python_env_hint()
        self._set_python_env_status("Not checked")
        self._refresh_tools_tree()
        self._update_config_tool_status_labels()
        self._validate_configuration()

    def _browse_input(self) -> None:
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
        self._refresh_input_label()

    def _mri_filetypes(self) -> tuple[tuple[str, str], tuple[str, str]]:
        return (("MRI files", "*.nii *.nii.gz *.mgz *.mgh *.dcm"), ("All files", "*.*"))

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

    def _apply_pipeline_mode(self) -> None:
        fixed = self.state.pipeline_mode.get() == "FreeSurfer Fixed"
        if fixed:
            for stage, tool in self.FREESURFER_FIXED_TOOLS.items():
                if stage in self.state.tool_vars:
                    self.state.tool_vars[stage].set(tool_display_name(tool) if tool else "")
            for combo in self.tool_combos.values():
                combo.configure(state="disabled")
            self.state.pipeline_note.set(
                "Fixed FreeSurfer stack with FS8 tools temporarily disabled to save disk. Template registration and stats extraction are skipped."
            )
        else:
            for combo in self.tool_combos.values():
                combo.configure(state="readonly")
            self.state.pipeline_note.set("Custom mode: choose tools freely for each stage.")
        self._update_config_tool_status_labels()

    def _selected_tools(self) -> dict[str, str]:
        if self.state.pipeline_mode.get() == "FreeSurfer Fixed":
            self._apply_pipeline_mode()
        return self.state.get_selected_tools()

    def _collect_config(self) -> dict:
        return {
            "version": 1,
            "run_target": self.state.run_target.get(),
            "pipeline_mode": self.state.pipeline_mode.get(),
            "input_mode": self.state.input_mode.get(),
            "input_path": self.state.input_path.get(),
            "selected_files": self.state.selected_files,
            "output_dir": self.state.output_dir.get(),
            "license_dir": self.state.license_dir.get(),
            "device": self.state.device.get(),
            "threads": int(self.state.threads.get()),
            "non_recursive": self.state.non_recursive.get(),
            "tools": self.state.get_selected_tools(),
            "remote": {
                "host": self.state.remote_host.get(),
                "port": int(self.state.remote_port.get()),
                "username": self.state.remote_username.get(),
                "key_path": self.state.remote_key_path.get(),
                "workspace": self.state.remote_workspace.get(),
                "python": self.state.remote_python.get(),
            },
        }

    def _apply_config(self, config: dict) -> None:
        self.state.input_mode.set(config.get("input_mode", "file"))
        self.state.run_target.set(config.get("run_target", "Local"))
        loaded_pipeline_mode = config.get("pipeline_mode", "Custom Tools")
        if loaded_pipeline_mode == "FreeSurfer Fixed (7 steps)":
            loaded_pipeline_mode = "FreeSurfer Fixed"
        if loaded_pipeline_mode not in ("FreeSurfer Fixed", "Custom Tools"):
            loaded_pipeline_mode = "Custom Tools"
        self.state.pipeline_mode.set(loaded_pipeline_mode)
        self.state.input_path.set(config.get("input_path", ""))
        self.state.selected_files = list(config.get("selected_files", []))
        self.state.output_dir.set(config.get("output_dir", str(PROJECT_ROOT / "outputs")))
        self.state.license_dir.set(config.get("license_dir", str(PROJECT_ROOT / "license")))
        self.state.device.set(config.get("device", "cpu"))
        self.state.threads.set(int(config.get("threads", 4)))
        self.state.non_recursive.set(bool(config.get("non_recursive", False)))

        tools = config.get("tools", {})
        for stage, value in tools.items():
            if stage in self.state.tool_vars:
                tool_key = tool_key_from_display(value)
                self.state.tool_vars[stage].set(tool_display_name(tool_key) if is_tool_enabled(tool_key) else "")

        self._apply_pipeline_mode()

        remote = config.get("remote", {})
        self.state.remote_host.set(remote.get("host", ""))
        self.state.remote_port.set(int(remote.get("port", 22)))
        self.state.remote_username.set(remote.get("username", ""))
        self.state.remote_password.set("")
        self.state.remote_key_path.set(remote.get("key_path", ""))
        self.state.remote_workspace.set(remote.get("workspace", "~/mri-remote-jobs"))
        self.state.remote_python.set(remote.get("python", "python3"))

        self._on_run_target_changed()
        self._refresh_input_label()
        self._log(f"Loaded config: {config.get('name', 'unnamed')}")

    def _save_workspace(self) -> None:
        config_dir = PROJECT_ROOT / "configs"
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
        workspace["name"] = Path(path).stem
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(workspace, f, indent=2, ensure_ascii=False)
            self._log(f"Saved workspace: {path}")
        except Exception as exc:
            messagebox.showerror("Save workspace failed", str(exc))

    def _load_workspace(self) -> None:
        config_dir = PROJECT_ROOT / "configs"
        path = filedialog.askopenfilename(
            title="Load workspace",
            initialdir=str(config_dir),
            filetypes=(("Workspace JSON", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                workspace = json.load(f)
            self.state.apply_workspace(workspace)
            self._refresh_input_label()
            self._validate_configuration()
            self._log(f"Loaded workspace: {path}")
        except Exception as exc:
            messagebox.showerror("Load workspace failed", str(exc))

    def _save_config(self) -> None:
        self._save_workspace()

    def _load_config(self) -> None:
        self._load_workspace()

    def _collect_run_config(self) -> dict:
        return {
            "version": 1,
            "type": "mri-pipeline-run-config",
            "pipeline_mode": self.state.pipeline_mode.get(),
            "tools": self.state.get_selected_tools(),
            "stats_vectors": self.state.get_stats_vector_config(),
            "license_dir": self.state.license_dir.get(),
            "device": self.state.device.get(),
            "threads": int(self.state.threads.get()),
            "non_recursive": self.state.non_recursive.get(),
        }

    def _apply_run_config(self, config: dict) -> None:
        loaded_pipeline_mode = config.get("pipeline_mode", "Custom Tools")
        if loaded_pipeline_mode == "FreeSurfer Fixed (7 steps)":
            loaded_pipeline_mode = "FreeSurfer Fixed"
        if loaded_pipeline_mode not in ("FreeSurfer Fixed", "Custom Tools"):
            loaded_pipeline_mode = "Custom Tools"
        self.state.pipeline_mode.set(loaded_pipeline_mode)

        tools = config.get("tools", {})
        for stage, value in tools.items():
            if stage in self.state.tool_vars:
                tool_key = tool_key_from_display(value)
                if not tool_key and value in TOOL_DEFS:
                    tool_key = value
                self.state.tool_vars[stage].set(tool_display_name(tool_key) if is_tool_enabled(tool_key) else "")

        self.state.apply_stats_vector_config(config.get("stats_vectors", {}))
        if "license_dir" in config:
            self.state.license_dir.set(config.get("license_dir", ""))
        if "device" in config:
            self.state.device.set(config.get("device", "cpu"))
        if "threads" in config:
            self.state.threads.set(int(config.get("threads", 4)))
        if "non_recursive" in config:
            self.state.non_recursive.set(bool(config.get("non_recursive", False)))
        self._apply_pipeline_mode()
        self._update_config_tool_status_labels()
        self._validate_configuration()

    def _save_run_config(self) -> None:
        config_dir = PROJECT_ROOT / "configs" / "run_configs"
        config_dir.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(
            title="Save run config",
            initialdir=str(config_dir),
            defaultextension=".json",
            filetypes=(("Run Config JSON", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return
        data = self._collect_run_config()
        data["name"] = Path(path).stem
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._log(f"Saved run config: {path}")
        except Exception as exc:
            messagebox.showerror("Save run config failed", str(exc))

    def _load_run_config(self) -> None:
        config_dir = PROJECT_ROOT / "configs" / "run_configs"
        path = filedialog.askopenfilename(
            title="Load run config",
            initialdir=str(config_dir),
            filetypes=(("Run Config JSON", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
            if config.get("type") not in (None, "mri-pipeline-run-config"):
                messagebox.showerror("Invalid run config", "Selected file is not an MRI pipeline run config.")
                return
            self._apply_run_config(config)
            self._log(f"Loaded run config: {path}")
        except Exception as exc:
            messagebox.showerror("Load run config failed", str(exc))


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

        self.state.input_path.trace_add("write", self._refresh_input_label)

        for tool_var in self.state.tool_vars.values():
            tool_var.trace_add("write", lambda *_args: (self._validate_configuration(), self._update_config_tool_status_labels()))

        for var in [*self.state.export_name_vars.values(), *self.state.export_format_vars.values()]:
            var.trace_add("write", lambda *_args: self._validate_configuration())

        for var in [*self.state.stat_vector_enabled_vars.values(), *(atlas for atlas_vars in self.state.stat_atlas_vars.values() for atlas in atlas_vars.values())]:
            var.trace_add("write", lambda *_args: self._validate_configuration())

    def _validate_configuration(self) -> bool:
        errors: list[str] = []
        mode = self.state.input_mode.get()
        raw_input = self.state.input_path.get().strip()
        if not raw_input:
            errors.append("Choose an input MRI file or folder.")
        elif mode == "file":
            path = self.state.selected_files[0] if self.state.selected_files else raw_input
            if not Path(path).is_file():
                errors.append("Input file does not exist.")
        elif mode == "files":
            files = self.state.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
            if not files:
                errors.append("Choose at least one input file.")
            elif any(not Path(p).is_file() for p in files):
                errors.append("One or more selected input files do not exist.")
        else:
            if not Path(raw_input).is_dir():
                errors.append("Input folder does not exist.")

        if not self.state.output_dir.get().strip():
            errors.append("Choose an output directory.")
        if self.state.export_outputs_enabled.get():
            invalid_names = [name.get().strip() for name in self.state.export_name_vars.values() if not name.get().strip() or any(sep in name.get() for sep in ("/", "\\"))]
            if invalid_names:
                errors.append("Export file names cannot be empty or contain path separators.")
        for stat, stat_def in STAT_VECTOR_DEFS.items():
            if self.state.stat_vector_enabled_vars.get(stat) and self.state.stat_vector_enabled_vars[stat].get():
                if stat_def.get("atlases") and not any(var.get() for var in self.state.stat_atlas_vars.get(stat, {}).values()):
                    errors.append(f"Choose at least one atlas for {stat_def['label']}.")
        try:
            if int(self.state.threads.get()) < 1:
                errors.append("Threads must be at least 1.")
        except (tk.TclError, ValueError):
            errors.append("Threads must be a valid integer.")

        selected_tools = self.state.get_selected_tools()
        missing_stages = [stage for stage in STAGE_ORDER if enabled_tools_for_stage(stage) and not selected_tools.get(stage)]
        if missing_stages:
            errors.append("Select one tool for every pipeline stage.")
        disabled_tools = [tool for tool in selected_tools.values() if tool and not is_tool_enabled(tool)]
        if disabled_tools:
            errors.append(f"Disabled tools selected: {', '.join(tool_display_name(tool) for tool in disabled_tools)}")

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

        ok = not errors
        if hasattr(self, "run_button"):
            self.run_button.configure(state=tk.NORMAL if ok and not self.running else tk.DISABLED)
        if hasattr(self, "restart_button"):
            self.restart_button.configure(state=tk.NORMAL if ok and not self.running else tk.DISABLED)
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
    root.geometry("1000x700+80+60")
    root.minsize(850, 600)
    PipelineGUI(root)
    root.update_idletasks()
    root.deiconify()
    root.lift()
    print(f"MRI Pipeline GUI is running on DISPLAY={os.environ.get('DISPLAY', '')}.", flush=True)
    root.mainloop()

if __name__ == "__main__":
    main()
