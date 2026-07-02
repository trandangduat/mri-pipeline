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
from remote.ssh_client import RemoteSSHClient
from ui.gui_jobs import JobsMixin
from ui.gui_pipeline import PipelineMixin
from ui.gui_progress import ProgressMixin
from ui.gui_tools import ToolsMixin
from ui.state import AppState
from ui.styles import configure_windows_dpi_awareness, setup_styles
from ui.tabs.config_tab import build_configuration_tab
from ui.tabs.tools_tab import build_tools_tab


class PipelineGUI(ToolsMixin, JobsMixin, PipelineMixin, ProgressMixin):
    PIPELINE_MODES = ("Custom", "FS7", "FS8", "Volume", "Volume & Cortical Thickness")
    PIPELINE_MODE_ALIASES = {
        "Custom Tools": "Custom",
        "FreeSurfer 7": "FS7",
        "FreeSurfer 8": "FS8",
        "FreeSurfer Fixed": "FS7",
        "FreeSurfer Fixed (7 steps)": "FS7",
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
    MODE_TOOLSETS = {
        "FS7": FREESURFER_7_TOOLS,
        "FS8": FREESURFER_8_TOOLS,
        "Volume": FREESURFER_7_TOOLS,
        "Volume & Cortical Thickness": FREESURFER_7_SURFACE_TOOLS,
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
        self.stat_vector_checkbuttons: dict[str, ttk.Checkbutton] = {}
        self.stat_atlas_combos: dict[str, ttk.Combobox] = {}
        self.step_tree: ttk.Treeview | None = None
        self.stage_items: dict[str, str] = {}
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
                if status in {"Downloading", "Checking", "Deleting"}:
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

    def _on_input_source_changed(self) -> None:
        old_source = getattr(self, "_last_input_source", "Local")
        new_source = self.state.input_source.get()
        if old_source != new_source:
            self._input_source_paths[old_source] = self.state.input_path.get().strip()
            self._input_source_selected_files[old_source] = list(self.state.selected_files)
            next_path = self._input_source_paths.get(new_source, "")
            if new_source == "Server" and not next_path:
                next_path = "~"
            self.state.input_path.set(next_path)
            self.state.selected_files = list(self._input_source_selected_files.get(new_source, [])) if next_path else []
            self._last_input_source = new_source
        self._refresh_input_label()

    def _browse_input(self) -> None:
        if self.state.input_source.get() == "Server":
            self._browse_remote_input()
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
            return lower.endswith((".nii", ".nii.gz", ".mgz", ".mgh", ".dcm"))

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
                status_text.set("Select a folder." if mode == "dir" else "Double-click folders to browse; select MRI file(s).")
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

    def _apply_stats_preset_for_mode(self, mode: str) -> None:
        if mode == "Volume":
            enabled = {"cortical_volume", "subcortical_volume"}
        elif mode == "Volume & Cortical Thickness":
            enabled = set(STAT_VECTOR_DEFS)
        else:
            return

        for stat, var in self.state.stat_vector_enabled_vars.items():
            var.set(stat in enabled)
        if mode == "Volume & Cortical Thickness" and not self.state.selected_atlases_for_stat("cortical_thickness"):
            first_atlas = next(iter(self.state.stat_atlas_vars.get("cortical_thickness", {})), "")
            if first_atlas:
                self.state.set_stat_atlas_choice("cortical_thickness", first_atlas)

    def _update_stats_vector_controls(self, mode: str) -> None:
        locked = set()
        if mode == "Volume":
            locked = set(STAT_VECTOR_DEFS)
        elif mode == "Volume & Cortical Thickness":
            locked = set(STAT_VECTOR_DEFS)

        for stat, check in getattr(self, "stat_vector_checkbuttons", {}).items():
            check.configure(state=tk.DISABLED if stat in locked else tk.NORMAL)
        for stat, combo in getattr(self, "stat_atlas_combos", {}).items():
            var = self.state.stat_vector_enabled_vars.get(stat)
            combo.configure(state="readonly" if var is not None and var.get() else tk.DISABLED)

    def _apply_pipeline_mode(self, apply_stats_preset: bool = True) -> None:
        mode = self._normalize_pipeline_mode(self.state.pipeline_mode.get())
        if mode != self.state.pipeline_mode.get():
            self.state.pipeline_mode.set(mode)
            return
        if apply_stats_preset:
            self._apply_stats_preset_for_mode(mode)
        fixed_tools = self.MODE_TOOLSETS.get(mode)
        if fixed_tools is not None:
            for stage, tool in fixed_tools.items():
                if stage in self.state.tool_vars:
                    self.state.tool_vars[stage].set(tool_display_name(tool) if tool else "")
            for combo in self.tool_combos.values():
                combo.configure(state="disabled")
            if mode == "FS8":
                self.state.pipeline_note.set("Fixed FreeSurfer 8 stack: FS8 convert, SynthStrip, SynthSeg, SynthMorph, WM mask, and stats. Surface steps 7-8 are skipped.")
            elif mode == "FS7":
                self.state.pipeline_note.set("Fixed FreeSurfer 7 stack: FS7 convert, SynthStrip, SynthSeg, WM mask, and stats; registration uses SynthMorph FS8. Surface steps 7-8 are skipped.")
            elif mode == "Volume":
                self.state.pipeline_note.set("Volume preset: cortical and subcortical volume vectors are selected. Surface steps 7-8 are skipped.")
            else:
                self.state.pipeline_note.set("Volume & Cortical Thickness preset: all stats vectors are selected and all 9 pipeline steps are enabled.")
        else:
            self._apply_custom_tool_defaults()
            for combo in self.tool_combos.values():
                combo.configure(state="readonly")
            self.state.pipeline_note.set("Custom mode: choose tools freely for each stage.")
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
        workspace["name"] = Path(path).stem
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(workspace, f, indent=2, ensure_ascii=False)
            self._log(f"Saved workspace: {path}")
        except Exception as exc:
            messagebox.showerror("Save workspace failed", str(exc))

    def _load_workspace(self) -> None:
        config_dir = PROJECT_ROOT / "configs" / "workspaces"
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
            self._last_input_source = self.state.input_source.get()
            self._input_source_paths[self._last_input_source] = self.state.input_path.get().strip()
            self._input_source_selected_files[self._last_input_source] = list(self.state.selected_files)
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

        self.state.input_path.trace_add("write", self._refresh_input_label)

        for tool_var in self.state.tool_vars.values():
            tool_var.trace_add("write", lambda *_args: (self._validate_configuration(), self._update_config_tool_status_labels()))

        for var in [*self.state.export_name_vars.values(), *self.state.export_format_vars.values()]:
            var.trace_add("write", lambda *_args: self._validate_configuration())

        for var in [*self.state.stat_vector_enabled_vars.values(), *self.state.stat_atlas_choice_vars.values()]:
            var.trace_add("write", lambda *_args: self._validate_configuration())

    def _validate_configuration(self) -> bool:
        errors: list[str] = []
        input_source = self.state.input_source.get()
        mode = self.state.input_mode.get()
        raw_input = self.state.input_path.get().strip()
        if not raw_input:
            errors.append("Choose an input MRI file or folder.")
        elif input_source == "Server" and self.state.run_target.get() != "Server":
            errors.append("Server input requires Run on = Server.")
        elif input_source == "Local" and mode == "file":
            path = self.state.selected_files[0] if self.state.selected_files else raw_input
            if not Path(path).is_file():
                errors.append("Input file does not exist.")
        elif input_source == "Local" and mode == "files":
            files = self.state.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
            if not files:
                errors.append("Choose at least one input file.")
            elif any(not Path(p).is_file() for p in files):
                errors.append("One or more selected input files do not exist.")
        elif input_source == "Local":
            if not Path(raw_input).is_dir():
                errors.append("Input folder does not exist.")
        elif input_source == "Server":
            files = self.state.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
            if mode == "file" and raw_input == "~" and not self.state.selected_files:
                errors.append("Choose a server MRI file.")
            elif mode == "files" and (not files or files == ["~"]):
                errors.append("Choose at least one server input file.")

        if not self.state.output_dir.get().strip():
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
            if int(self.state.threads.get()) < 1:
                errors.append("Threads must be at least 1.")
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
        if required_images:
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
