"""Tkinter GUI for the MRI Docker pipeline.

Features:
- Single file, multiple files, or batch folder input.
- Tool selection for every pipeline stage.
- Live log output.
- Live Docker container CPU/RAM chart via pipeline_runner.on_metrics.
"""

from __future__ import annotations

import os
import json
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from pipeline_runner import (
    PROJECT_ROOT,
    STAGE_LABELS,
    STAGE_ORDER,
    TOOL_DEFS,
    BatchImageResult,
    ExportConfig,
    PipelineConfig,
    STAT_VECTOR_DEFS,
    StatsVectorConfig,
    _derive_subject_id,
    _discover_mri_files,
    build_subject_id_map,
    enabled_tools_for_stage,
    ensure_image,
    image_exists,
    is_tool_enabled,
    run_batch_pipeline,
    run_pipeline,
    tool_display_name,
    tool_key_from_display,
)

def truncate_middle(text: str, max_len: int = 30) -> str:
    if len(text) <= max_len:
        return text
    half = (max_len - 3) // 2
    return text[:half] + "..." + text[-half:]

from remote.remote_runner import RemoteRunConfig, RemoteRunner
from ui.state import AppState
from ui.styles import setup_styles
from ui.components.dialogs import build_image_dialog, append_dialog_log
from ui.tabs.config_tab import build_configuration_tab
from ui.tabs.progress_tab import build_progress_tab
from ui.tabs.tools_tab import build_tools_tab
from remote.ssh_client import SSHConfig
from pipeline.jobs import create_local_job_dir, load_job_registry, read_json, upsert_job_registry, write_json


class PipelineGUI:
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
        self.tool_image_statuses: dict[str, dict[str, str]] = {"Local": {}, "Server": {}}
        self.tool_status_labels: dict[str, ttk.Label] = {}

        self._build_ui()
        self._setup_validation_traces()
        self._validate_configuration()
        self._poll_queues()
        self.root.after(700, self._maybe_prompt_existing_jobs)

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
                for i in range(12):
                    angle = -i * 30
                    rot = img.rotate(angle, resample=Image.BICUBIC)
                    self._spinner_frames.append(ImageTk.PhotoImage(rot))
        except Exception:
            pass

    def _animate_spinner(self):
        if not self._spinner_frames:
            return
        self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_frames)
        frame = self._spinner_frames[self._spinner_idx]
        
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
                            row["icon"].configure(image=frame)
                    except Exception:
                        pass
                        
        self.root.after(100, self._animate_spinner)

    def _build_ui(self) -> None:
        root_frame = ttk.Frame(self.root)
        root_frame.pack(fill=tk.BOTH, expand=True)

        self._build_app_toolbar(root_frame)
        self._build_tabs(root_frame)
        self._build_status_bar(root_frame)

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
                img = tk.PhotoImage(file=icon_path).subsample(2, 2)
                self.toolbar_icons[icon_key] = img
                return img
        except Exception:
            pass
        return None

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
        
        self.resume_button = self._toolbar_button(toolbar, "run", "Run / Resume", lambda: self._start_pipeline(resume=True, restart=False))
        self.resume_button.configure(style="Accent.TButton")
        self.run_button = self.resume_button
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

    def _attach_job_dialog(self) -> None:
        if self.running:
            messagebox.showinfo("Job running", "A job is already being monitored.")
            return
        jobs = self._known_jobs()
        if not jobs:
            self._attach_manual_job_dialog()
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Background Jobs")
        dialog.geometry("900x420")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Select a background job to view progress/logs or download completed remote outputs.").pack(anchor=tk.W, padx=12, pady=(12, 6))
        columns = ("target", "state", "job", "output")
        tree = ttk.Treeview(dialog, columns=columns, show="headings", height=12)
        tree.heading("target", text="Target")
        tree.heading("state", text="State")
        tree.heading("job", text="Job")
        tree.heading("output", text="Output")
        tree.column("target", width=80, anchor=tk.W)
        tree.column("state", width=90, anchor=tk.W)
        tree.column("job", width=360, anchor=tk.W)
        tree.column("output", width=300, anchor=tk.W)
        tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        item_to_job: dict[str, dict] = {}
        for idx, job in enumerate(jobs):
            job_label = job.get("remote_job_dir") or job.get("job_dir") or job.get("job_id", "")
            item = tree.insert("", tk.END, values=(job.get("target", ""), job.get("state", ""), job_label, job.get("effective_output_dir") or job.get("output_dir", "")))
            item_to_job[item] = job
            if idx == 0:
                tree.selection_set(item)

        buttons = ttk.Frame(dialog)
        buttons.pack(fill=tk.X, padx=12, pady=(4, 12))

        def selected_job() -> dict | None:
            selection = tree.selection()
            if not selection:
                return None
            return item_to_job.get(selection[0])

        def attach_selected() -> None:
            job = selected_job()
            if not job:
                return
            dialog.destroy()
            self._attach_registry_job(job)

        def download_selected() -> None:
            job = selected_job()
            if not job:
                return
            dialog.destroy()
            self._download_registry_job(job)

        ttk.Button(buttons, text="View / Attach", style="Accent.TButton", command=attach_selected).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Download Outputs", command=download_selected).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Manual Attach", command=lambda: (dialog.destroy(), self._attach_manual_job_dialog())).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)
        tree.bind("<Double-1>", lambda _event: attach_selected())

    def _attach_manual_job_dialog(self) -> None:
        if self.state.run_target.get() == "Server":
            remote_dir = simpledialog.askstring("Attach remote job", "Remote job directory:", parent=self.root)
            if remote_dir:
                self._attach_registry_job({"target": "Server", "remote_job_dir": remote_dir.strip(), "state": "unknown"})
            return
        job_dir = filedialog.askdirectory(title="Attach local job", initialdir=str(Path(self.state.output_dir.get()) / "jobs"))
        if job_dir:
            self._attach_registry_job({"target": "Local", "job_dir": job_dir, "state": "unknown"})

    def _attach_registry_job(self, job: dict) -> None:
        target = job.get("target")
        if target == "Server":
            runner = self._remote_runner_from_job_entry(job)
            if runner is None:
                return
            self.remote_runner = runner
            self.state.run_target.set("Server")
            self._on_run_target_changed()
            input_files = list(job.get("input_files") or [])
            self.active_job = {"target": "Server", "remote_job_dir": runner.remote_job_dir, "done": False, "registry_entry": job}
        else:
            job_dir = Path(str(job.get("job_dir", "")))
            config = read_json(job_dir / "job_config.json", {})
            input_files = list(job.get("input_files") or []) or (self._input_files_for_progress(config) if config else [])
            self.active_job = {"target": "Local", "job_dir": str(job_dir), "done": False, "registry_entry": job}
            self.state.run_target.set("Local")
            self._on_run_target_changed()
        self.job_log_offset = 0
        self._prepare_progress_tab(input_files)
        self._show_progress_tab()
        self._enter_background_monitor_state("Attached background job")
        self._schedule_job_poll()

    def _remote_runner_from_job_entry(self, job: dict) -> RemoteRunner | None:
        remote = dict(job.get("remote") or {})
        if remote:
            self.state.remote_host.set(remote.get("host", self.state.remote_host.get()))
            self.state.remote_port.set(int(remote.get("port", self.state.remote_port.get() or 22)))
            self.state.remote_username.set(remote.get("username", self.state.remote_username.get()))
            self.state.remote_key_path.set(remote.get("key_path", self.state.remote_key_path.get()))
            self.state.remote_workspace.set(remote.get("workspace", self.state.remote_workspace.get()))
            self.state.remote_python.set(remote.get("python", self.state.remote_python.get()))
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return None
        runner = RemoteRunner(
            RemoteRunConfig(
                ssh=ssh_config,
                remote_workspace=self.state.remote_workspace.get().strip() or "~/mri-remote-jobs",
                remote_python=self.state.remote_python.get().strip() or "python3",
                output_dir=str(job.get("output_dir") or self.state.output_dir.get().strip()),
                download_subdir=str(job.get("download_subdir") or ""),
            ),
            on_log=self._remote_log_event,
        )
        remote_dir = str(job.get("remote_job_dir") or "").strip()
        if not remote_dir:
            messagebox.showerror("Missing remote job", "Selected registry entry has no remote job directory.")
            return None
        runner.attach_job(remote_dir)
        metadata = runner.read_remote_metadata()
        if metadata.get("download_subdir"):
            runner.config.download_subdir = str(metadata.get("download_subdir"))
        return runner

    def _download_registry_job(self, job: dict) -> None:
        if job.get("target") == "Server":
            runner = self._remote_runner_from_job_entry(job)
            if runner is None:
                return
            self.remote_runner = runner
            self._remote_download_outputs()
            return
        output_dir = job.get("effective_output_dir") or job.get("output_dir")
        self._log(f"Local outputs are already available in: {output_dir}")

    def _enter_background_monitor_state(self, title: str) -> None:
        self.running = True
        self.stop_requested.clear()
        if hasattr(self, "run_button"):
            self.run_button.configure(state=tk.DISABLED)
        if hasattr(self, "resume_button"):
            self.resume_button.configure(state=tk.DISABLED)
        if hasattr(self, "restart_button"):
            self.restart_button.configure(state=tk.DISABLED)
        if hasattr(self, "stop_button"):
            self.stop_button.configure(state=tk.NORMAL)
        if hasattr(self, "progress"):
            self.progress.start(10)
        self.state.status_text.set("Running in background")
        self._log(title)

    def _registry_entry_for_local_job(self, job_dir: Path, req: dict, pid: int | None = None, state: str = "running") -> dict:
        files = self._input_files_for_progress(req)
        now = time.time()
        return {
            "job_id": job_dir.name,
            "target": "Local",
            "state": state,
            "job_dir": str(job_dir),
            "pid": pid,
            "started_at": now,
            "updated_at": now,
            "output_dir": req.get("output_dir", ""),
            "effective_output_dir": req.get("effective_output_dir", req.get("output_dir", "")),
            "download_subdir": req.get("batch_output_name", "") if req.get("is_batch") else "",
            "input_files": files,
            "run_request": req,
        }

    def _registry_entry_for_remote_job(self, runner: RemoteRunner, remote_dir: str, state: str = "running") -> dict:
        cfg = runner.config
        files = []
        if cfg.input_mode == "file" and cfg.input_file:
            files = [cfg.input_file]
        elif cfg.input_mode == "files":
            files = list(cfg.input_files)
        elif cfg.input_dir:
            try:
                files = _discover_mri_files(cfg.input_dir, recursive=cfg.recursive)
            except Exception:
                files = []
        now = time.time()
        return {
            "job_id": Path(remote_dir).name,
            "target": "Server",
            "state": state,
            "remote_job_dir": remote_dir,
            "started_at": now,
            "updated_at": now,
            "output_dir": cfg.output_dir,
            "download_subdir": cfg.download_subdir,
            "input_files": files,
            "remote": {
                "host": cfg.ssh.host,
                "port": int(cfg.ssh.port),
                "username": cfg.ssh.username,
                "key_path": cfg.ssh.key_path,
                "workspace": cfg.remote_workspace,
                "python": cfg.remote_python,
            },
        }

    def _update_registry_for_active_job(self, state: str, exit_code=None) -> None:
        if not self.active_job:
            return
        entry = dict(self.active_job.get("registry_entry") or {})
        if not entry:
            entry = dict(self.active_job)
        entry.update({"state": state, "exit_code": exit_code, "updated_at": time.time()})
        upsert_job_registry(entry)
        self.active_job["registry_entry"] = entry

    def _pid_is_running(self, pid: int | str | None) -> bool:
        if not pid:
            return False
        try:
            pid_int = int(pid)
            if pid_int <= 0:
                return False
            os.kill(pid_int, 0)
            return True
        except Exception:
            return False

    def _refresh_registry_entry_status(self, entry: dict) -> dict:
        entry = dict(entry)
        if entry.get("target") != "Local":
            return entry
        job_dir = Path(str(entry.get("job_dir", "")))
        if not job_dir.exists():
            entry["state"] = "missing"
            return entry
        status = read_json(job_dir / "job_status.json", {})
        exit_path = job_dir / "exit_code.txt"
        if exit_path.exists() or status.get("state") in {"completed", "failed"}:
            code = status.get("exit_code")
            if code is None and exit_path.exists():
                code = exit_path.read_text(encoding="utf-8", errors="replace").strip()
            entry["state"] = "completed" if str(code) == "0" else "failed"
            entry["exit_code"] = code
        elif self._pid_is_running(status.get("pid") or entry.get("pid")):
            entry["state"] = "running"
        elif entry.get("state") == "running":
            entry["state"] = "unknown"
        entry["updated_at"] = time.time()
        return entry

    def _known_jobs(self) -> list[dict]:
        jobs = [self._refresh_registry_entry_status(entry) for entry in load_job_registry()]
        for entry in jobs:
            upsert_job_registry(entry)
        return jobs

    def _running_or_unknown_jobs(self) -> list[dict]:
        return [entry for entry in self._known_jobs() if entry.get("state") in {"running", "unknown", "uploaded"}]

    def _maybe_prompt_existing_jobs(self) -> None:
        if self.running or self.active_job:
            return
        candidates = self._running_or_unknown_jobs()
        if not candidates:
            return
        job = candidates[0]
        label = job.get("remote_job_dir") or job.get("job_dir") or job.get("job_id", "background job")
        answer = messagebox.askyesnocancel(
            "Background job found",
            f"Found an unfinished background job:\n\n{label}\n\nAttach now to view progress?\n\nYes = Attach\nNo = Start/continue without attaching\nCancel = Do nothing",
        )
        if answer is True:
            self._attach_registry_job(job)

    def _confirm_start_with_existing_jobs(self) -> bool:
        candidates = self._running_or_unknown_jobs()
        if not candidates:
            return True
        job = candidates[0]
        label = job.get("remote_job_dir") or job.get("job_dir") or job.get("job_id", "background job")
        answer = messagebox.askyesnocancel(
            "Background job already exists",
            f"There is an unfinished background job:\n\n{label}\n\nAttach to it instead of starting another job?\n\nYes = Attach existing job\nNo = Start a new job anyway\nCancel = Do nothing",
        )
        if answer is True:
            self._attach_registry_job(job)
            return False
        return answer is False

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
            if not self.state.remote_python.get().strip():
                errors.append("Remote Python command is required.")

        ok = not errors
        if hasattr(self, "run_button"):
            self.run_button.configure(state=tk.NORMAL if ok and not self.running else tk.DISABLED)
        if hasattr(self, "restart_button"):
            self.restart_button.configure(state=tk.NORMAL if ok and not self.running else tk.DISABLED)
        self.state.config_status.set("Configuration complete. Ready to run." if ok else errors[0])
        return ok

    def _check_images_action(self) -> None:
        if not self._validate_configuration():
            messagebox.showerror("Configuration incomplete", self.state.config_status.get())
            return
        if self.state.run_target.get() == "Server":
            runner = self._build_remote_runner()
            if runner and self._ensure_remote_images_with_dialog(runner):
                self.remote_runner = runner
                self._log("Remote image preflight completed successfully.")
        else:
            if self._ensure_local_images_with_dialog():
                self._log("Local image preflight completed successfully.")

    def _tool_image(self, tool_key: str) -> str:
        return str(TOOL_DEFS.get(tool_key, {}).get("image", ""))

    def _all_enabled_images(self) -> list[str]:
        images: list[str] = []
        for tool_key, tool in TOOL_DEFS.items():
            if not is_tool_enabled(tool_key):
                continue
            image = str(tool.get("image", ""))
            if image and image not in images:
                images.append(image)
        return images

    def _tool_status(self, tool_key: str, target: str | None = None) -> str:
        if not tool_key:
            return "Skipped"
        if not is_tool_enabled(tool_key):
            return "Disabled"
        image = self._tool_image(tool_key)
        if not image:
            return "Unknown"
        target = target or self.state.run_target.get()
        return self.tool_image_statuses.setdefault(target, {}).get(image, "Unknown")

    def _status_label_text(self, status: str) -> str:
        return "Not checked" if status == "Unknown" else status

    def _tool_status_icon(self, status: str) -> str:
        return {
            "Installed": "✓",
            "Missing": "✕",
            "Downloading": "↓",
            "Checking": "…",
            "Disabled": "",
            "Skipped": "",
            "Error": "!",
            "Unknown": "?",
        }.get(status, "?")

    def _tool_check_text(self, tool_key: str) -> str:
        return "[x]" if tool_key in self.tools_checked_tools else "[ ]"

    def _tool_status_icon_image(self, status: str) -> tk.PhotoImage | None:
        icon_name = {
            "Installed": "success",
            "Missing": "failed",
            "Downloading": "running",
            "Checking": "running",
            "Error": "failed",
            "Disabled": None,
            "Skipped": None,
            "Unknown": "pending",
        }.get(status, "pending")
        if not icon_name:
            return None
        key = f"tool_status_{icon_name}"
        if key in self.toolbar_icons:
            return self.toolbar_icons[key]
        icon_path = Path(__file__).parent / "icons" / f"{icon_name}.png"
        if not icon_path.exists():
            return None
        try:
            img = tk.PhotoImage(file=str(icon_path))
            self.toolbar_icons[key] = img
            return img
        except Exception:
            return None

    def _tools_checkbox_enabled(self, tool_key: str, status: str | None = None) -> bool:
        if not is_tool_enabled(tool_key):
            return False
        status = status or self._tool_status(tool_key)
        return status != "Installed"

    def _update_tools_download_button(self) -> None:
        button = getattr(self, "tools_download_button", None)
        if button is None:
            return
        enabled = any(self._tools_checkbox_enabled(tool) for tool in self.tools_checked_tools)
        button.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def _status_color(self, status: str) -> str:
        return {
            "Installed": "#16a34a",
            "Missing": "#dc2626",
            "Downloading": "#2563eb",
            "Checking": "#2563eb",
            "Disabled": "#64748b",
            "Skipped": "#64748b",
            "Error": "#dc2626",
        }.get(status, "#64748b")

    def _set_image_status(self, target: str, image: str, status: str) -> None:
        if not image:
            return
        self.tool_image_statuses.setdefault(target, {})[image] = status
        self._refresh_tools_tree()
        self._update_config_tool_status_labels()

    def _refresh_tools_tree(self) -> None:
        table = getattr(self, "tools_table_frame", None)
        if table is None:
            return
        target = self.state.run_target.get()
        for row, (tool_key, tool) in enumerate(TOOL_DEFS.items(), start=2):
            stage = str(tool.get("stage", ""))
            image = str(tool.get("image", ""))
            status = self._tool_status(tool_key, target)
            enabled = self._tools_checkbox_enabled(tool_key, status)
            if not enabled:
                self.tools_checked_tools.discard(tool_key)
            var = self.tools_check_vars.get(tool_key)
            if var is None:
                var = tk.BooleanVar(value=tool_key in self.tools_checked_tools)
                self.tools_check_vars[tool_key] = var
            var.set(tool_key in self.tools_checked_tools)

            def on_check(key=tool_key, check_var=var) -> None:
                if check_var.get():
                    self.tools_checked_tools.add(key)
                else:
                    self.tools_checked_tools.discard(key)
                self._refresh_tools_tree()
                self._update_tools_download_button()

            widgets = self.tools_row_widgets.get(tool_key)
            if widgets is None:
                cells = []
                for col in range(5):
                    cell = tk.Frame(table, padx=4, pady=2, bg="#fafafa")
                    cell.grid(row=row, column=col, sticky=tk.NSEW, padx=0, pady=1)
                    cells.append(cell)
                check = ttk.Checkbutton(
                    cells[0],
                    variable=var,
                    command=on_check,
                )
                check.pack(anchor=tk.W)
                stage_label = tk.Label(cells[1], anchor=tk.W, bg="#fafafa", fg="#111827")
                stage_label.pack(fill=tk.BOTH, expand=True)
                tool_label = tk.Label(cells[2], anchor=tk.W, bg="#fafafa", fg="#111827")
                tool_label.pack(fill=tk.BOTH, expand=True)
                image_label = tk.Label(cells[3], anchor=tk.W, bg="#fafafa", fg="#475569")
                image_label.pack(fill=tk.BOTH, expand=True)
                status_label = tk.Label(cells[4], text="", anchor=tk.CENTER, bg="#fafafa", fg="#111827")
                status_label.pack(anchor=tk.W)
                widgets = {
                    "cells": cells,
                    "check": check,
                    "stage": stage_label,
                    "tool": tool_label,
                    "image": image_label,
                    "status": status_label,
                }
                self.tools_row_widgets[tool_key] = widgets

            row_selected = tool_key in self.tools_checked_tools
            bg = "#cbd5e1" if row_selected else "#fafafa"
            for cell in widgets["cells"]:
                cell.configure(bg=bg)
                
            style = ttk.Style()
            style.configure("Selected.TCheckbutton", background="#cbd5e1")
            style.configure("Unselected.TCheckbutton", background="#fafafa")
            check_style = "Selected.TCheckbutton" if row_selected else "Unselected.TCheckbutton"
            
            widgets["check"].configure(state=tk.NORMAL if enabled else tk.DISABLED, style=check_style)
            widgets["stage"].configure(text=STAGE_LABELS.get(stage, stage), bg=bg)
            widgets["tool"].configure(text=tool_display_name(tool_key), bg=bg)
            widgets["image"].configure(text=image, bg=bg)
            icon = self._tool_status_icon_image(status)
            if icon is not None:
                widgets["status"].configure(image=icon, text="", compound=tk.CENTER, bg=bg)
            else:
                widgets["status"].configure(image="", text=self._tool_status_icon(status), compound=tk.CENTER, bg=bg, fg=self._status_color(status), font=("Inter", 10, "bold"))
            self.tools_status_icon_labels[tool_key] = widgets["status"]
        self._update_tools_download_button()

    def _on_tools_tree_click(self, event) -> None:
        tree = getattr(self, "tools_tree", None)
        if tree is None:
            return
        region = tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        column = tree.identify_column(event.x)
        if column != "#1":
            return
        item = tree.identify_row(event.y)
        if not item or item not in TOOL_DEFS or not is_tool_enabled(item):
            return
        if item in self.tools_checked_tools:
            self.tools_checked_tools.remove(item)
        else:
            self.tools_checked_tools.add(item)
        self._refresh_tools_tree()
        return "break"

    def _toggle_tools_log(self) -> None:
        body = getattr(self, "tools_log_body", None)
        label = getattr(self, "tools_log_toggle_text", None)
        if body is None:
            return
        self.tools_log_visible = not self.tools_log_visible
        if self.tools_log_visible:
            body.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
            if label is not None:
                label.set("Hide Image Log")
        else:
            body.pack_forget()
            if label is not None:
                label.set("Show Image Log")

    def _append_tools_log(self, line: str) -> None:
        log = getattr(self, "tools_log_text", None)
        if log is None:
            return
        log.configure(state=tk.NORMAL)
        log.insert(tk.END, line + "\n")
        log.see(tk.END)
        log.configure(state=tk.DISABLED)

    def _selected_tool_rows(self) -> list[str]:
        return [tool for tool in self.tools_checked_tools if tool in TOOL_DEFS]

    def _build_image_remote_runner(self) -> RemoteRunner | None:
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return None
        return RemoteRunner(
            RemoteRunConfig(
                ssh=ssh_config,
                remote_workspace=self.state.remote_workspace.get().strip() or "~/mri-remote-jobs",
                remote_python=self.state.remote_python.get().strip() or "python3",
                output_dir=self.state.output_dir.get().strip(),
                license_dir=self.state.license_dir.get().strip(),
                export_config=self.state.get_export_config(),
                stats_vector_config=self.state.get_stats_vector_config(),
                selected_tools={},
            ),
            on_log=self._tools_remote_log_event,
        )

    def _tools_remote_log_event(self, line: str) -> None:
        keep = ("Connecting SSH", "SSH connected", "Python OK:", "Python missing:", "pip OK:", "pip missing:", "Installing", "Installed:", "Missing:", "Downloading:", "Failed:")
        if line.startswith(keep):
            self.root.after(0, lambda l=line: self._append_tools_log(l))

    def _set_python_env_status(self, status: str) -> None:
        self.python_env_status.set(status)

    def _check_python_environment(self) -> None:
        target = self.state.run_target.get()
        self._set_python_env_status("Checking...")
        self._append_tools_log(f"Checking Python: {target}")

        def worker() -> None:
            if target == "Local":
                try:
                    version = subprocess.run([sys.executable, "--version"], capture_output=True, text=True, timeout=30)
                    pip = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, text=True, timeout=30)
                    py_text = (version.stdout or version.stderr).strip() or "Python not found"
                    pip_text = (pip.stdout or pip.stderr).strip() or "pip not found"
                    python_ok = version.returncode == 0
                    pip_ok = pip.returncode == 0
                    self.root.after(0, lambda t=py_text, ok=python_ok: self._append_tools_log(("Python OK: " if ok else "Python missing: ") + t))
                    self.root.after(0, lambda t=pip_text, ok=pip_ok: self._append_tools_log(("pip OK: " if ok else "pip missing: ") + t))
                    if python_ok and pip_ok:
                        status = "Local: Python OK, pip OK"
                    elif python_ok:
                        status = "Local: Python OK, pip missing"
                    else:
                        status = "Local: Python missing"
                    self.root.after(0, lambda s=status: self._set_python_env_status(s))
                except Exception as exc:
                    self.root.after(0, lambda e=exc: self._append_tools_log(f"Python check failed: {type(e).__name__}: {e}"))
                    self.root.after(0, lambda: self._set_python_env_status("Local: Error"))
                return

            runner = self._build_image_remote_runner()
            if runner is None:
                self.root.after(0, lambda: self._set_python_env_status("Not configured"))
                return
            try:
                details = runner.check_python_details()
                python_ok = bool(details["python_ok"])
                pip_ok = bool(details["pip_ok"])
                if python_ok and pip_ok:
                    status = "Server: Python OK, pip OK"
                elif python_ok:
                    status = "Server: Python OK, pip missing"
                else:
                    status = "Server: Python missing"
                self.root.after(0, lambda s=status: self._set_python_env_status(s))
            except Exception as exc:
                self.root.after(0, lambda e=exc: self._append_tools_log(f"Python check failed: {type(e).__name__}: {e}"))
                self.root.after(0, lambda: self._set_python_env_status("Server: Error"))

        threading.Thread(target=worker, daemon=True).start()

    def _install_python_requirements(self) -> None:
        target = self.state.run_target.get()
        requirements = PROJECT_ROOT / "requirements.txt"
        if not requirements.exists():
            messagebox.showerror("Missing requirements", f"requirements.txt not found: {requirements}")
            return
        self._set_python_env_status("Installing...")
        self._append_tools_log(f"Installing Python packages from requirements.txt: {target}")

        def worker() -> None:
            if target == "Local":
                try:
                    pip_check = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, text=True, timeout=30)
                    if pip_check.returncode != 0:
                        self.root.after(0, lambda: self._append_tools_log("pip missing: trying ensurepip..."))
                        subprocess.run([sys.executable, "-m", "ensurepip", "--user", "--upgrade"], capture_output=True, text=True, timeout=120)
                    proc = subprocess.run(
                        [sys.executable, "-m", "pip", "install", "--user", "-r", str(requirements)],
                        capture_output=True,
                        text=True,
                        timeout=900,
                    )
                    ok = proc.returncode == 0
                    msg = "Python packages installed: Local" if ok else "Python packages failed: Local"
                    self.root.after(0, lambda m=msg: self._append_tools_log(m))
                    if not ok:
                        tail = " | ".join((proc.stderr or proc.stdout).strip().splitlines()[-3:])
                        self.root.after(0, lambda t=tail: self._append_tools_log(f"pip error: {t}"))
                    self.root.after(0, lambda: self._set_python_env_status("Local: Python packages installed" if ok else "Local: Package install failed"))
                except Exception as exc:
                    self.root.after(0, lambda e=exc: self._append_tools_log(f"Install failed: {type(e).__name__}: {e}"))
                    self.root.after(0, lambda: self._set_python_env_status("Local: Package install failed"))
                return

            runner = self._build_image_remote_runner()
            if runner is None:
                self.root.after(0, lambda: self._set_python_env_status("Not configured"))
                return
            try:
                ok = runner.install_python_requirements()
                msg = "Python packages installed: Server" if ok else "Python packages failed: Server"
                self.root.after(0, lambda m=msg: self._append_tools_log(m))
                self.root.after(0, lambda: self._set_python_env_status("Server: Python packages installed" if ok else "Server: Package install failed"))
            except Exception as exc:
                self.root.after(0, lambda e=exc: self._append_tools_log(f"Install failed: {type(e).__name__}: {e}"))
                self.root.after(0, lambda: self._set_python_env_status("Server: Package install failed"))

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_tool_image_statuses(self) -> None:
        target = self.state.run_target.get()
        images = self._all_enabled_images()
        if not images:
            self._append_tools_log("No enabled tool images to check.")
            return
        for image in images:
            self.tool_image_statuses.setdefault(target, {})[image] = "Checking"
        self._refresh_tools_tree()
        self._update_config_tool_status_labels()

        def worker() -> None:
            if target == "Local":
                for image in images:
                    self.root.after(0, lambda i=image: self._append_tools_log(f"Checking: {i}"))
                    status = "Installed" if image_exists(image) else "Missing"
                    self.root.after(0, lambda i=image, s=status: self._set_image_status("Local", i, s))
                    self.root.after(0, lambda i=image, s=status: self._append_tools_log(f"{s}: {i}"))
                return

            runner = self._build_image_remote_runner()
            if runner is None:
                for image in images:
                    self.root.after(0, lambda i=image: self._set_image_status("Server", i, "Unknown"))
                return
            try:
                statuses = runner.check_image_statuses(images)
                for image, installed in statuses.items():
                    status = "Installed" if installed else "Missing"
                    self.root.after(0, lambda i=image, s=status: self._set_image_status("Server", i, s))
            except Exception as exc:
                self.root.after(0, lambda e=exc: self._append_tools_log(f"Error: {type(e).__name__}: {e}"))
                for image in images:
                    self.root.after(0, lambda i=image: self._set_image_status("Server", i, "Error"))

        threading.Thread(target=worker, daemon=True).start()

    def _ensure_tool_images(self, tool_keys: list[str]) -> None:
        target = self.state.run_target.get()
        tool_keys = [tool for tool in dict.fromkeys(tool_keys) if tool in TOOL_DEFS and is_tool_enabled(tool)]
        if not tool_keys:
            self._append_tools_log("No enabled tools selected.")
            return
        for tool_key in tool_keys:
            self._set_image_status(target, self._tool_image(tool_key), "Downloading")

        def worker() -> None:
            if target == "Local":
                for tool_key in tool_keys:
                    image = self._tool_image(tool_key)
                    self.root.after(0, lambda i=image: self._append_tools_log(f"Downloading: {i}"))
                    ok, err, _ = ensure_image(tool_key, on_build_log=None)
                    status = "Installed" if ok and image_exists(image) else "Error"
                    self.root.after(0, lambda i=image, s=status: self._set_image_status("Local", i, s))
                    msg = f"Installed: {image}" if status == "Installed" else f"Failed: {image} {err}"
                    self.root.after(0, lambda m=msg: self._append_tools_log(m))
                return

            runner = self._build_image_remote_runner()
            if runner is None:
                return
            try:
                ok = runner.ensure_tool_images(tool_keys)
                images = [self._tool_image(tool) for tool in tool_keys]
                statuses = runner.check_image_statuses(images)
                for image, installed in statuses.items():
                    status = "Installed" if installed else ("Missing" if ok else "Error")
                    self.root.after(0, lambda i=image, s=status: self._set_image_status("Server", i, s))
            except Exception as exc:
                self.root.after(0, lambda e=exc: self._append_tools_log(f"Error: {type(e).__name__}: {e}"))
                for tool_key in tool_keys:
                    self.root.after(0, lambda i=self._tool_image(tool_key): self._set_image_status("Server", i, "Error"))

        threading.Thread(target=worker, daemon=True).start()

    def _ensure_checked_tool_images(self) -> None:
        self._ensure_tool_images(self._selected_tool_rows())

    def _select_all_tool_images(self) -> None:
        target = self.state.run_target.get()
        self.tools_checked_tools = {
            tool for tool in TOOL_DEFS
            if self._tools_checkbox_enabled(tool, self._tool_status(tool, target))
        }
        self._refresh_tools_tree()
        self._update_tools_download_button()

    def _unselect_all_tool_images(self) -> None:
        self.tools_checked_tools.clear()
        self._refresh_tools_tree()
        self._update_tools_download_button()

    def _select_missing_tool_images(self) -> None:
        target = self.state.run_target.get()
        self.tools_checked_tools = {
            tool for tool in TOOL_DEFS
            if self._tools_checkbox_enabled(tool, self._tool_status(tool, target))
            and self._tool_status(tool, target) in ("Missing", "Unknown", "Error")
        }
        self._refresh_tools_tree()
        self._update_tools_download_button()

    def _ensure_missing_tool_images(self) -> None:
        target = self.state.run_target.get()
        missing = [tool for tool in TOOL_DEFS if self._tool_status(tool, target) in ("Missing", "Unknown") and is_tool_enabled(tool)]
        self._ensure_tool_images(missing)

    def _update_config_tool_status_labels(self) -> None:
        if not getattr(self, "tool_status_labels", None):
            return
        target = self.state.run_target.get()
        for stage, label in self.tool_status_labels.items():
            tool_key = tool_key_from_display(self.state.tool_vars.get(stage).get()) if stage in self.state.tool_vars else ""
            status = self._tool_status(tool_key, target)
            label.configure(text=self._status_label_text(status), foreground=self._status_color(status))

    def _build_image_dialog(self, title: str) -> tuple[tk.Toplevel, tk.Text, ttk.Progressbar, dict[str, bool]]:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("760x460")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text=title, font=("Inter", 12, "bold")).pack(anchor=tk.W, padx=12, pady=(12, 6))
        log = tk.Text(dialog, wrap=tk.WORD, height=20, font=("JetBrains Mono", 10), state=tk.DISABLED)
        scroll = ttk.Scrollbar(dialog, orient=tk.VERTICAL, command=log.yview)
        log.configure(yscrollcommand=scroll.set)
        log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0), pady=(0, 12))
        scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 12), pady=(0, 12))
        progress = ttk.Progressbar(dialog, mode="indeterminate")
        progress.pack(fill=tk.X, padx=12, pady=(0, 12))
        progress.start(10)
        state = {"ok": False, "done": False}
        return dialog, log, progress, state

    def _append_dialog_log(self, log: tk.Text, line: str) -> None:
        log.configure(state=tk.NORMAL)
        log.insert(tk.END, line + "\n")
        log.see(tk.END)
        log.configure(state=tk.DISABLED)

    def _ensure_local_images_with_dialog(self) -> bool:
        dialog, log, progress, state = build_image_dialog(self.root, "Docker image preflight")
        required_tools = [tool for tool in dict.fromkeys(self.state.get_selected_tools().values()) if tool and is_tool_enabled(tool)]

        def worker() -> None:
            ok = True
            try:
                for tool_key in required_tools:
                    tool = TOOL_DEFS.get(tool_key, {})
                    image = tool.get("image", tool_key)
                    self.root.after(0, lambda i=image: append_dialog_log(log, f"Checking {i}"))
                    result, err, _build_time = ensure_image(
                        tool_key,
                        on_progress=None,
                        on_build_log=lambda line: self.root.after(0, lambda l=line: append_dialog_log(log, l)),
                    )
                    if not result:
                        ok = False
                        self.root.after(0, lambda e=err: append_dialog_log(log, f"ERROR: {e}"))
                        break
                    if not image_exists(image):
                        ok = False
                        self.root.after(0, lambda i=image: append_dialog_log(log, f"ERROR: image still missing after ensure: {i}"))
                        break
                    self.root.after(0, lambda i=image: append_dialog_log(log, f"OK image: {i}"))
            finally:
                state["ok"] = ok
                state["done"] = True
                self.root.after(0, progress.stop)
                self.root.after(0, dialog.destroy if ok else lambda: None)

        threading.Thread(target=worker, daemon=True).start()
        self.root.wait_window(dialog)
        return state["ok"]

    def _ensure_remote_images_with_dialog(self, runner: RemoteRunner) -> bool:
        dialog, log, progress, state = build_image_dialog(self.root, "Remote Docker image preflight")

        def worker() -> None:
            ok = True
            try:
                def on_line(line: str) -> None:
                    self.root.after(0, lambda l=line: append_dialog_log(log, l))

                runner.on_log = on_line
                if not runner.remote_job_dir:
                    runner.upload_job()
                ok = runner.ensure_images()
            except Exception as exc:
                ok = False
                err_msg = f"REMOTE IMAGE ERROR: {type(exc).__name__}: {exc}"
                self.root.after(0, lambda m=err_msg: append_dialog_log(log, m))
            finally:
                runner.on_log = self._remote_log_event
                state["ok"] = ok
                state["done"] = True
                self.root.after(0, progress.stop)
                self.root.after(0, dialog.destroy if ok else lambda: None)

        threading.Thread(target=worker, daemon=True).start()
        self.root.wait_window(dialog)
        return state["ok"]

    def _start_pipeline(self, resume: bool = False, restart: bool = False) -> None:
        if self.running:
            return

        if not self._validate_configuration():
            messagebox.showerror("Configuration incomplete", self.state.config_status.get())
            return

        if not self._confirm_start_with_existing_jobs():
            return

        if self.state.run_target.get() == "Server":
            runner = self.remote_runner if resume and self.remote_runner else self._build_remote_runner(resume=resume)
            if not runner:
                return
            if restart:
                self.remote_runner = None
            runner.config.resume = resume
            if not self._ensure_remote_images_with_dialog(runner):
                messagebox.showerror("Docker images missing", "Remote Docker image preflight failed. Pipeline was not started.")
                return
            self.remote_runner = runner
            self._prepare_progress_tab(self._input_files_for_progress())
            self._show_progress_tab()
            self._start_remote_pipeline(resume=resume, restart=restart, runner=runner)
            return

        run_request = self._build_run_request()
        if run_request is None:
            return
        run_request["resume"] = resume
        run_request["restart"] = restart

        if not self._ensure_local_images_with_dialog():
            messagebox.showerror("Docker images missing", "Local Docker image preflight failed. Pipeline was not started.")
            return

        self._prepare_progress_tab(self._input_files_for_progress(run_request))
        self._show_progress_tab()

        self.running = True
        self.stop_requested.clear()
        self.run_button.configure(state=tk.DISABLED)
        if hasattr(self, "resume_button"):
            self.resume_button.configure(state=tk.DISABLED)
        if hasattr(self, "restart_button"):
            self.restart_button.configure(state=tk.DISABLED)
        if hasattr(self, "stop_button"):
            self.stop_button.configure(state=tk.NORMAL)
        if hasattr(self, "progress"):
            self.progress.start(10)
        self.detail_chart.reset()
        self.gpu_chart.reset()
        self.state.overall_progress_var.set(0)
        self.state.overall_progress_text.set("0%")
        self.state.status_text.set("Running")
        for stage in STAGE_ORDER:
            if hasattr(self, "_set_step_status"):
                self._set_step_status(stage, "Ready", 0)
        self._clear_log()
        self._log("=" * 80)
        if restart:
            self._log("Restart mode: existing subject outputs will be removed before running.")
        elif resume:
            self._log("Resume mode: completed stages in pipeline_state.json will be skipped.")
        self._log("Starting pipeline...")
        self._start_local_background_pipeline(run_request)

    def _start_local_background_pipeline(self, run_request: dict) -> None:
        job_dir = create_local_job_dir(run_request.get("output_dir") or PROJECT_ROOT / "outputs")
        run_request = dict(run_request)
        run_request["job_dir"] = str(job_dir)
        run_request["run_target"] = "Local"
        config_path = job_dir / "job_config.json"
        write_json(config_path, run_request)

        cmd = [sys.executable, "-m", "pipeline.job_worker", "--job-config", str(config_path)]
        kwargs = {
            "cwd": str(PROJECT_ROOT),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **kwargs)
        write_json(job_dir / "launcher_status.json", {"pid": proc.pid, "started_at": time.time(), "command": cmd})
        entry = self._registry_entry_for_local_job(job_dir, run_request, proc.pid)
        upsert_job_registry(entry)
        self._log(f"Local background job started: {job_dir}")
        self._log("You can close the GUI. The local worker process will keep running.")
        self.active_job = {"target": "Local", "job_dir": str(job_dir), "pid": proc.pid, "done": False, "registry_entry": entry}
        self.job_log_offset = 0
        self._schedule_job_poll()

    def _start_remote_pipeline(self, resume: bool = False, restart: bool = False, runner: RemoteRunner | None = None) -> None:
        runner = runner or (self.remote_runner if resume and self.remote_runner else self._build_remote_runner(resume=resume))
        if not runner:
            return
        if resume and self.remote_runner is None:
            self._log("No previous remote job is loaded in this GUI session; creating a new remote job instead.")
        if restart:
            self.remote_runner = None
        runner.config.resume = resume
        self.remote_runner = runner
        self._enter_background_monitor_state("Starting remote background job...")
        remote_dir = runner.start_remote_detached()
        entry = self._registry_entry_for_remote_job(runner, remote_dir)
        upsert_job_registry(entry)
        self._log(f"Remote background job started: {remote_dir}")
        self._log("You can close the GUI. Reopen and attach this remote job to monitor or download outputs.")
        self.active_job = {"target": "Server", "remote_job_dir": remote_dir, "done": False, "registry_entry": entry}
        self.job_log_offset = 0
        self._schedule_job_poll()

    def _build_run_request(self) -> dict | None:
        mode = self.state.input_mode.get()
        raw_input = self.state.input_path.get().strip()
        if not raw_input:
            messagebox.showerror("Missing input", "Chưa chọn file hoặc folder MRI.")
            return None

        selected_tools = self.state.get_selected_tools()
        is_batch = mode == "dir"
        output_dir = self.state.output_dir.get().strip()
        batch_output_name = f"batch_{time.strftime('%Y%m%d_%H%M%S')}" if is_batch else ""
        base = {
            "mode": mode,
            "output_dir": output_dir,
            "effective_output_dir": str(Path(output_dir) / batch_output_name) if batch_output_name else output_dir,
            "is_batch": is_batch,
            "batch_output_name": batch_output_name,
            "license_dir": self.state.license_dir.get().strip(),
            "device": self.state.device.get(),
            "threads": int(self.state.threads.get()),
            "selected_tools": selected_tools,
            "export_config": self.state.get_export_config(),
            "stats_vector_config": self.state.get_stats_vector_config(),
        }

        if mode == "file":
            path = self.state.selected_files[0] if self.state.selected_files else raw_input
            if not Path(path).is_file():
                messagebox.showerror("Invalid input", f"Không tồn tại file: {path}")
                return None
            base["input_file"] = path
        elif mode == "files":
            files = self.state.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
            missing = [p for p in files if not Path(p).is_file()]
            if not files or missing:
                messagebox.showerror("Invalid input", "Danh sách file không hợp lệ.")
                return None
            base["input_files"] = files
            base["input_dir"] = self._common_input_root(files)
        else:
            if not Path(raw_input).is_dir():
                messagebox.showerror("Invalid input", f"Không tồn tại folder: {raw_input}")
                return None
            if self.state.selected_files:
                base["mode"] = "files"
                base["input_files"] = self.state.selected_files
                base["input_dir"] = self._common_input_root(self.state.selected_files)
            else:
                base["input_dir"] = raw_input
                base["recursive"] = not self.state.non_recursive.get()

        return base

    def _input_files_for_progress(self, req: dict | None = None) -> list[str]:
        if req is None:
            req = self._build_run_request()
        if not req:
            return []
        if req["mode"] == "file":
            return [req["input_file"]]
        if req["mode"] == "files":
            return list(req["input_files"])
        return _discover_mri_files(req["input_dir"], recursive=req.get("recursive", True))

    def _show_progress_tab(self) -> None:
        if self.notebook is None or self.progress_tab is None:
            return
        self.notebook.tab(self.progress_tab, state="normal")
        self.notebook.select(self.progress_tab)

    def _prepare_progress_tab(self, files: list[str]) -> None:
        self.image_runs.clear()
        self.image_rows.clear()
        self.current_image_key = ""
        self.active_image_key = ""
        self.state.current_total_images = len(files)
        self.state.current_success_images = 0
        self.state.current_failed_images = 0
        self.state.current_running_images = 0
        self._update_batch_summary()
        for child in self.image_list_frame.winfo_children():
            child.destroy()
        self._clear_log()
        self.detail_chart.reset()
        self.gpu_chart.reset()
        self.state.detail_title.set("Select an input image")
        for idx, path in enumerate(files, start=1):
            self._create_image_run(path, idx, len(files))
        if files:
            self._select_image(files[0])

    def _create_image_run(self, input_file: str, idx: int, total: int) -> None:
        if input_file in self.image_runs:
            return
        name = _derive_subject_id(input_file)
        self.image_runs[input_file] = {
            "input_file": input_file,
            "name": name,
            "idx": idx,
            "total": total,
            "status": "Pending",
            "percent": 0.0,
            "logs": [],
            "cpu": [],
            "ram": [],
            "gpu": [],
            "container": "n/a",
            "stage": "Queued",
            "stage_detail": "Waiting to start",
        }
        
        container = ttk.Frame(self.image_list_frame)
        container.pack(fill=tk.X)
        
        row = ttk.Frame(container)
        row.pack(fill=tk.X, padx=4, pady=4)
        
        top = ttk.Frame(row)
        top.pack(fill=tk.X, padx=4, pady=(4, 2))
        
        icon_img = self._get_status_icon("Pending")
        icon_label = ttk.Label(top, image=icon_img) if icon_img else ttk.Label(top, text="..")
        icon_label.pack(side=tk.LEFT, padx=(0, 4))
        
        center = ttk.Frame(top)
        center.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        
        display_name = truncate_middle(name, 25)
        title = ttk.Label(center, text=display_name, anchor=tk.W, font=("Inter", 9, "bold"))
        title.pack(fill=tk.X)

        status_label = ttk.Label(center, text="Pending", anchor=tk.W, foreground="#64748b")
        status_label.pack(fill=tk.X)

        # Add an arrow label for selection
        arrow_label = ttk.Label(top, text="", anchor=tk.E, font=("Inter", 12, "bold"))
        arrow_label.pack(side=tk.RIGHT, padx=(4, 0))
        
        var = tk.DoubleVar(value=0)
        bar = ttk.Progressbar(row, variable=var, maximum=100, mode="determinate")
        bar.pack(fill=tk.X, padx=4, pady=(0, 4))
        
        sep = ttk.Separator(container, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X)
        
        for widget in (container, row, top, center, icon_label, title, status_label, arrow_label, bar, sep):
            widget.bind("<Button-1>", lambda _e, key=input_file: self._select_image(key))
            
        self.image_rows[input_file] = {
            "container": container,
            "frame": row,
            "top": top,
            "center": center,
            "icon": icon_label,
            "title": title,
            "status": status_label,
            "arrow": arrow_label,
            "var": var,
        }

    def _select_image(self, input_file: str) -> None:
        if input_file not in self.image_runs:
            return
        self.current_image_key = input_file
        for key, row in self.image_rows.items():
            is_selected = key == input_file
            
            # Change background to darker when selected
            try:
                frame_style = "Selected.TFrame" if is_selected else "TFrame"
                label_style = "Selected.TLabel" if is_selected else "TLabel"
                
                row["container"].configure(style=frame_style)
                row["frame"].configure(style=frame_style)
                row["top"].configure(style=frame_style)
                row["center"].configure(style=frame_style)
                
                row["icon"].configure(style=label_style)
                row["title"].configure(style=label_style)
                row["status"].configure(style=label_style)
                row["arrow"].configure(style=label_style)
            except Exception as e:
                pass
            
            row["frame"].configure(relief="solid" if is_selected else "flat")
            row["arrow"].configure(text="›" if is_selected else "")
            
        run = self.image_runs[input_file]
        self.state.detail_title.set(f"{run['idx']}/{run['total']} {run['name']} - {run.get('stage', run['status'])}")
        self._render_selected_detail()

    def _render_selected_detail(self) -> None:
        run = self.image_runs.get(self.current_image_key)
        if not run:
            return
        self.detail_chart.reset()
        self.gpu_chart.reset()
        self.detail_chart.container_label.set(f"Container: {run.get('container', 'n/a')}")
        for cpu, ram, container in zip(run["cpu"], run["ram"], [run.get("container", "n/a")] * len(run["cpu"])):
            self.detail_chart.add(cpu, ram, container)
        for gpu in run["gpu"]:
            self.gpu_chart.add(gpu, f"{gpu:.1f}%")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, "\n".join(run["logs"][-2000:]))
        if run["logs"]:
            self.log_text.insert(tk.END, "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _update_image_run(
        self,
        input_file: str,
        status: str | None = None,
        percent: float | None = None,
        log_line: str | None = None,
        stage_text: str | None = None,
    ) -> None:
        if input_file not in self.image_runs:
            self._create_image_run(input_file, len(self.image_runs) + 1, max(self.state.current_total_images, len(self.image_runs) + 1))
        run = self.image_runs[input_file]
        
        if stage_text is not None:
            run["stage"] = stage_text
            run["stage_detail"] = stage_text
            
        if status is not None:
            run["status"] = status
            display_text = run.get("stage", status) if status == "Running" else status
            self.image_rows[input_file]["status"].configure(text=display_text)
            icon_img = self._get_status_icon(status)
            if icon_img:
                self.image_rows[input_file]["icon"].configure(image=icon_img, text="")
            else:
                self.image_rows[input_file]["icon"].configure(image="", text="•")
        elif stage_text is not None and run.get("status") == "Running":
            self.image_rows[input_file]["status"].configure(text=stage_text)

        if percent is not None:
            pct = max(0.0, min(100.0, percent))
            run["percent"] = pct
            self.image_rows[input_file]["var"].set(pct)
            
        if self.current_image_key == input_file:
            self.state.detail_title.set(f"{run['idx']}/{run['total']} {run['name']} - {run.get('stage', run.get('status', 'Queued'))}")

    def _update_batch_summary(self) -> None:
        self.state.batch_total_text.set(f"Success: {self.state.current_success_images} / {self.state.current_total_images}")
        self.state.batch_running_text.set(f"Running: {self.state.current_running_images}")
        self.state.batch_failed_text.set(f"Failed: {self.state.current_failed_images}")

    def _build_ssh_config(self) -> SSHConfig | None:
        host = self.state.remote_host.get().strip()
        username = self.state.remote_username.get().strip()
        if not host or not username:
            messagebox.showerror("Missing remote server", "Cần nhập Host/IP và Username của remote server.")
            return None

        return SSHConfig(
            host=host,
            port=int(self.state.remote_port.get()),
            username=username,
            password=self.state.remote_password.get(),
            key_path=self.state.remote_key_path.get().strip(),
        )

    def _build_remote_runner(self, resume: bool = False) -> RemoteRunner | None:
        req = self._build_run_request()
        if req is None:
            return None

        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return None

        remote_config = RemoteRunConfig(
            ssh=ssh_config,
            remote_workspace=self.state.remote_workspace.get().strip() or "~/mri-remote-jobs",
            remote_python=self.state.remote_python.get().strip() or "python3",
            input_mode=req["mode"],
            input_file=req.get("input_file", ""),
            input_files=req.get("input_files", []),
            input_dir=req.get("input_dir", ""),
            output_dir=req["output_dir"],
            license_dir=req["license_dir"],
            device=req["device"],
            threads=req["threads"],
            selected_tools=req["selected_tools"],
            export_config=req["export_config"],
            stats_vector_config=req["stats_vector_config"],
            recursive=req.get("recursive", True),
            download_subdir=req.get("batch_output_name", "") if req.get("is_batch") else "",
            resume=resume,
        )
        return RemoteRunner(remote_config, on_log=self._remote_log_event)

    def _match_progress_input_key(self, event: dict) -> str:
        input_file = str(event.get("input_file", ""))
        if input_file in self.image_runs:
            return input_file
            
        # Match by idx for accurate mapping when multiple files have the same basename
        idx = event.get("idx")
        if idx is not None:
            idx_int = int(idx)
            for key, run in self.image_runs.items():
                if run.get("idx") == idx_int:
                    return key
                    
        remote_name = Path(input_file).name
        if len(remote_name) > 5 and remote_name[:4].isdigit() and remote_name[4] == "_":
            remote_name = remote_name[5:]
        for key, run in self.image_runs.items():
            if Path(key).name == remote_name or run.get("name") == remote_name:
                return key
        return input_file

    def _remote_log_event(self, line: str) -> None:
        self.root.after(0, lambda l=line: self._handle_remote_log_event(l))

    def _schedule_job_poll(self) -> None:
        if self.job_poll_after_id:
            try:
                self.root.after_cancel(self.job_poll_after_id)
            except Exception:
                pass
        self.job_poll_after_id = self.root.after(1500, self._poll_active_job)

    def _poll_active_job(self) -> None:
        if not self.active_job:
            self.job_poll_after_id = None
            return
        try:
            target = self.active_job.get("target")
            if target == "Server":
                done = self._poll_remote_background_job()
            else:
                done = self._poll_local_background_job()
        except Exception as exc:
            self._log(f"BACKGROUND POLL ERROR: {type(exc).__name__}: {exc}")
            done = False

        if done:
            self.active_job["done"] = True
            self.job_poll_after_id = None
            self._set_idle_state()
            return
        self._schedule_job_poll()

    def _poll_local_background_job(self) -> bool:
        if not self.active_job:
            return True
        job_dir = Path(str(self.active_job.get("job_dir", "")))
        log_path = job_dir / "run.log"
        if log_path.exists():
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self.job_log_offset)
                data = f.read()
                self.job_log_offset = f.tell()
            self._handle_background_log_chunk(data)

        status = read_json(job_dir / "job_status.json", {})
        state = str(status.get("state", "running"))
        exit_path = job_dir / "exit_code.txt"
        if exit_path.exists() or state in {"completed", "failed"}:
            code = status.get("exit_code")
            if code is None and exit_path.exists():
                code = exit_path.read_text(encoding="utf-8", errors="replace").strip()
            self._log(f"Local background job finished with exit code {code}")
            self._update_registry_for_active_job("completed" if str(code) == "0" else "failed", code)
            return True
        self.state.status_text.set("Running in background")
        return False

    def _poll_remote_background_job(self) -> bool:
        if not self.remote_runner:
            return True
        data, self.job_log_offset = self.remote_runner.read_remote_log_since(self.job_log_offset)
        self._handle_background_log_chunk(data)
        status = self.remote_runner.remote_status()
        state = str(status.get("state", "running"))
        if state in {"completed", "failed"}:
            self._log(f"Remote background job finished with exit code {status.get('exit_code')}")
            self._log("Use Download Outputs to copy remote outputs to the local output folder.")
            self._update_registry_for_active_job(state, status.get("exit_code"))
            return True
        self.state.status_text.set("Running in background")
        self.state.remote_status.set(f"Remote: {state}")
        return False

    def _handle_background_log_chunk(self, data: str) -> None:
        for line in data.splitlines():
            if line.strip():
                self._handle_remote_log_event(line.rstrip())

    def _handle_remote_log_event(self, line: str) -> None:
        if not line.startswith("MRI_EVENT "):
            self._log(line)
            return
        try:
            event = json.loads(line[len("MRI_EVENT "):])
        except json.JSONDecodeError:
            self._log(line)
            return

        kind = event.get("kind")
        if kind == "image_start":
            key = self._match_progress_input_key(event)
            idx = int(event.get("idx", len(self.image_runs) + 1))
            total = int(event.get("total", max(self.state.current_total_images, idx)))
            self.state.current_total_images = max(self.state.current_total_images, total)
            self.active_image_key = key
            self.state.current_running_images = 1
            self._update_batch_summary()
            self._log(f"Remote image {idx}/{total} started: {key}")
            self._update_image_run(key, status="Running", percent=0, stage_text="Starting")
            self.root.after(0, lambda k=key: self._select_image(k))
        elif kind == "progress":
            pct = float(event.get("pct", 0)) * 100
            status = str(event.get("status", "running"))
            stage = str(event.get("stage", "pipeline"))
            msg = str(event.get("msg", ""))
            label = {"running": "Running", "success": "Running", "failed": "Failed", "paused": "Paused"}.get(status, status.capitalize())
            target_key = getattr(self, "active_image_key", "")
            current_run = self.image_runs.get(target_key, {}) if target_key else {}
            idx = int(current_run.get("idx", 1) or 1)
            total = max(int(current_run.get("total", self.state.current_total_images) or 1), 1)
            overall_pct = pct if stage == "batch" else (((idx - 1) + (pct / 100.0)) / total) * 100.0
            self.state.overall_progress_var.set(max(0, min(100, overall_pct)))
            self.state.overall_progress_text.set(f"{int(max(0, min(100, overall_pct)))}%")
            self.state.status_text.set(status.capitalize())
            prefix = "REMOTE " if self.state.run_target.get() == "Server" else ""
            self._log(f"{prefix}{status.upper()} {stage}: {msg}")
            if target_key:
                stage_name = STAGE_LABELS.get(stage, "Batch" if stage == "batch" else stage.replace("_", " ").title())
                stage_text = f"{stage_name} - {status.capitalize()}"
                image_pct = None if stage == "batch" else pct
                self._update_image_run(
                    target_key,
                    status=label,
                    percent=image_pct,
                    stage_text=stage_text,
                )
        elif kind == "image_done":
            key = self._match_progress_input_key(event)
            success = bool(event.get("success"))
            self.state.current_running_images = 0
            if success:
                self.state.current_success_images += 1
                self._log(f"Remote image done: {event.get('subject_id', key)} | OK")
                self._update_image_run(key, status="Done", percent=100, stage_text="Completed")
            else:
                self.state.current_failed_images += 1
                self._log(f"Remote image failed: {event.get('error', '')}")
                self._update_image_run(key, status="Failed", stage_text="Failed")
            self._update_batch_summary()
        elif kind == "image_preflight":
            self._log(f"Remote image preflight {event.get('status')}: {tool_display_name(str(event.get('tool', '')))}")
        elif kind == "metrics":
            cpu_pct = event.get("cpu_pct")
            ram_bytes = event.get("ram_bytes")
            gpu_pct = event.get("gpu_pct")
            self._on_metrics(
                str(event.get("stage", "")),
                str(event.get("tool", "")),
                float(cpu_pct) if cpu_pct is not None else None,
                int(ram_bytes) if ram_bytes is not None else None,
                float(event.get("elapsed", 0.0) or 0.0),
                str(event.get("container_name", "")),
                float(gpu_pct or 0.0),
            )

    def _run_remote_task(self, title: str, task, clear_log: bool = False, enable_pause: bool = False) -> None:
        if self.running:
            self._append_log("Remote task ignored: another task is already running.")
            return
        self.running = True
        self.state.remote_status.set(f"Remote: {title} running...")
        self.stop_requested.clear()
        if hasattr(self, "run_button"):
            self.run_button.configure(state=tk.DISABLED)
        if hasattr(self, "resume_button"):
            self.resume_button.configure(state=tk.DISABLED)
        if hasattr(self, "restart_button"):
            self.restart_button.configure(state=tk.DISABLED)
        if hasattr(self, "stop_button"):
            self.stop_button.configure(state=tk.NORMAL if enable_pause else tk.DISABLED)
        if hasattr(self, "progress"):
            self.progress.start(10)
        if clear_log:
            self._clear_log()
            self.detail_chart.reset()
            self.gpu_chart.reset()
            self.state.overall_progress_var.set(0)
            self.state.overall_progress_text.set("0%")
            self.state.status_text.set("Running")
            for stage in STAGE_ORDER:
                if hasattr(self, "_set_step_status"):
                    self._set_step_status(stage, "Ready", 0)
        self._append_log("=" * 80)
        self._append_log(f"Remote task started: {title}")

        def worker():
            try:
                task()
                self.log_queue.put(f"Remote task completed: {title}")
            except Exception as exc:
                self.log_queue.put(f"REMOTE ERROR [{title}]: {type(exc).__name__}: {exc}")
            finally:
                self.root.after(0, lambda: self.state.remote_status.set("Remote: idle"))
                self.root.after(0, self._set_idle_state)

        threading.Thread(target=worker, daemon=True).start()

    def _remote_test_ssh(self) -> None:
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return

        def task():
            try:
                def set_testing():
                    self.state.remote_status.set("Testing SSH connection...")
                    if hasattr(self, "remote_status_label"):
                        self.remote_status_label.configure(foreground="")
                self.root.after(0, set_testing)
                runner = RemoteRunner(RemoteRunConfig(ssh=ssh_config), on_log=lambda x: None)
                runner.test_ssh()
                def set_success():
                    self.state.remote_status.set("✅ SSH Connection Successful")
                    if hasattr(self, "remote_status_label"):
                        self.remote_status_label.configure(foreground="#16a34a") # green
                self.root.after(0, set_success)
            except Exception as exc:
                err_msg = f"❌ SSH Connection Failed: {exc}"
                def set_failed(m=err_msg):
                    self.state.remote_status.set(m)
                    if hasattr(self, "remote_status_label"):
                        self.remote_status_label.configure(foreground="#dc2626") # red
                self.root.after(0, set_failed)

        threading.Thread(target=task, daemon=True).start()

    def _remote_check_docker(self) -> None:
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return

        def task():
            runner = RemoteRunner(RemoteRunConfig(ssh=ssh_config), on_log=self._log)
            runner.check_docker()
        self._run_remote_task("Check Docker", task)

    def _remote_check_images(self) -> None:
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return
        selected_tools = self.state.get_selected_tools()

        def task():
            runner = RemoteRunner(RemoteRunConfig(ssh=ssh_config, selected_tools=selected_tools), on_log=self._log)
            missing = runner.check_images()
            if missing:
                self._log("Missing remote images:")
                for image in missing:
                    self._log(f"  - {image}")
            else:
                self._log("All required remote images are available.")
        self._run_remote_task("Check Images", task)

    def _check_environment(self) -> None:
        if self.state.run_target.get() == "Server":
            self._remote_check_docker()
            return

        def task():
            self._log(">>> docker ps")
            proc = subprocess.run(["docker", "ps"], capture_output=True, text=True, timeout=30)
            if proc.stdout.strip():
                self._log(proc.stdout.strip())
            if proc.stderr.strip():
                self._log(proc.stderr.strip())
            self._log(f"docker ps exit code: {proc.returncode}")

            self._log(">>> checking required local images")
            for image in self._required_images_for_current_tools():
                inspect = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, timeout=20)
                self._log(("OK" if inspect.returncode == 0 else "MISSING") + f" image: {image}")

        self._run_local_utility_task("Check Environment", task)

    def _download_outputs_action(self) -> None:
        if self.state.run_target.get() == "Server":
            self._remote_download_outputs()
        else:
            self._log(f"Local outputs are already in: {self.state.output_dir.get()}")

    def _required_images_for_current_tools(self) -> list[str]:
        images: list[str] = []
        for tool_key in self.state.get_selected_tools().values():
            if not tool_key or not is_tool_enabled(tool_key):
                continue
            tool = TOOL_DEFS.get(tool_key)
            if not tool:
                continue
            for key in ("base_image", "image"):
                image = tool.get(key)
                if image and image not in images:
                    images.append(image)
        return images

    def _run_local_utility_task(self, title: str, task) -> None:
        if self.running:
            self._append_log("Task ignored: another task is already running.")
            return
        self.running = True
        if hasattr(self, "progress"):
            self.progress.start(10)
        self.state.status_text.set(title)
        self._append_log("=" * 80)
        self._append_log(f"Task started: {title}")

        def worker():
            try:
                task()
                self.log_queue.put(f"Task completed: {title}")
            except Exception as exc:
                self.log_queue.put(f"TASK ERROR [{title}]: {type(exc).__name__}: {exc}")
            finally:
                self.root.after(0, self._set_idle_state)

        threading.Thread(target=worker, daemon=True).start()

    def _remote_upload_job(self) -> None:
        runner = self._build_remote_runner()
        if not runner:
            return

        def task():
            runner.upload_job()
            self.remote_runner = runner
            self._log(f"Uploaded remote job: {runner.remote_job_dir}")
        self._run_remote_task("Upload Job", task)

    def _remote_run(self, resume: bool = False) -> None:
        runner = self.remote_runner or self._build_remote_runner(resume=resume)
        if not runner:
            return
        runner.config.resume = resume
        self.remote_runner = runner
        self._prepare_progress_tab(self._input_files_for_progress())
        self._show_progress_tab()
        self._enter_background_monitor_state("Starting remote background job...")
        remote_dir = runner.start_remote_detached()
        entry = self._registry_entry_for_remote_job(runner, remote_dir)
        upsert_job_registry(entry)
        self._log(f"Remote background job started: {remote_dir}")
        self.active_job = {"target": "Server", "remote_job_dir": remote_dir, "done": False, "registry_entry": entry}
        self.job_log_offset = 0
        self._schedule_job_poll()

    def _remote_download_outputs(self) -> None:
        def task():
            if not self.remote_runner:
                self._log("No remote job is available. Run or upload a remote job first.")
                return
            local_path = self.remote_runner.download_outputs(self.state.output_dir.get())
            self._log(f"Downloaded outputs to: {local_path}")
        self._run_remote_task("Download Outputs", task)

    def _remote_clean_job(self) -> None:
        def task():
            if not self.remote_runner:
                self._log("No remote job is available to clean.")
                return
            self.remote_runner.clean_remote()
            self._log("Remote job cleaned.")
            self.remote_runner = None
        self._run_remote_task("Clean Remote Job", task)

    def _common_input_root(self, files: list[str]) -> str:
        parents = [str(Path(f).resolve().parent) for f in files]
        try:
            return os.path.commonpath(parents)
        except ValueError:
            return str(Path(files[0]).resolve().parent)

    def _run_worker(self, req: dict) -> None:
        try:
            if req.get("restart"):
                self._delete_restart_outputs(req)
            if req["mode"] == "file":
                self._run_single(req)
            elif req["mode"] == "files":
                self._run_multiple(req)
            else:
                self._run_batch(req)
        except Exception as exc:
            self._log(f"ERROR: {exc}")
        finally:
            self.root.after(0, self._set_idle_state)

    def _delete_restart_outputs(self, req: dict) -> None:
        output_dir = Path(req.get("effective_output_dir", req["output_dir"])).resolve()
        subject_ids: list[str] = []

        if req["mode"] == "file":
            subject_ids = [_derive_subject_id(req["input_file"])]
        elif req["mode"] == "files":
            subject_ids = list(build_subject_id_map(req["input_files"], req["input_dir"]).values())
        else:
            files = _discover_mri_files(req["input_dir"], recursive=req["recursive"])
            subject_ids = list(build_subject_id_map(files, req["input_dir"]).values())

        for subject_id in subject_ids:
            subject_dir = output_dir / subject_id
            if subject_dir.exists():
                self._log(f"Restart: removing {subject_dir}")
                shutil.rmtree(subject_dir)

    def _run_single(self, req: dict) -> None:
        input_file = req["input_file"]
        subject_id = _derive_subject_id(input_file)
        self.root.after(0, lambda: self._on_image_start(input_file, 1, 1))
        config = PipelineConfig(
            input_file=input_file,
            output_dir=req.get("effective_output_dir", req["output_dir"]),
            subject_id=subject_id,
            license_dir=req["license_dir"],
            device=req["device"],
            threads=req["threads"],
            resume=req.get("resume", False),
            export_config=ExportConfig.from_dict(req.get("export_config")),
            stats_vector_config=StatsVectorConfig.from_dict(req.get("stats_vector_config")),
            selected_tools=req["selected_tools"],
        )
        results = run_pipeline(
            config,
            on_progress=self._on_progress,
            on_build_log=self._log,
            on_metrics=self._on_metrics,
            should_stop=self.stop_requested.is_set,
        )
        ok = bool(results) and all(step.success for step in results)
        self._log(f"Single file finished: {subject_id} | status={'OK' if ok else 'FAILED'}")
        self.state.current_running_images = 0
        if ok:
            self.state.current_success_images += 1
            self._update_image_run(input_file, status="Done", percent=100, stage_text="Completed")
        else:
            self.state.current_failed_images += 1
            self._update_image_run(input_file, status="Failed", stage_text="Failed")
        self._update_batch_summary()

    def _run_multiple(self, req: dict) -> None:
        files = req["input_files"]
        self._log(f"Selected {len(files)} files")
        if req.get("is_batch"):
            self._log(f"Batch outputs will be saved to: {req.get('effective_output_dir')}")
        run_batch_pipeline(
            input_dir=req["input_dir"],
            output_dir=req.get("effective_output_dir", req["output_dir"]),
            license_dir=req["license_dir"],
            device=req["device"],
            threads=req["threads"],
            resume=req.get("resume", False),
            selected_tools=req["selected_tools"],
            export_config=ExportConfig.from_dict(req.get("export_config")),
            stats_vector_config=StatsVectorConfig.from_dict(req.get("stats_vector_config")),
            recursive=True,
            input_files=files,
            on_progress=self._on_progress,
            on_build_log=self._log,
            on_image_start=self._on_image_start,
            on_image_done=self._on_image_done,
            on_metrics=self._on_metrics,
            should_stop=self.stop_requested.is_set,
        )

    def _run_batch(self, req: dict) -> None:
        files = _discover_mri_files(req["input_dir"], recursive=req["recursive"])
        self._log(f"Found {len(files)} MRI files")
        if not files:
            return
        self._log(f"Batch outputs will be saved to: {req.get('effective_output_dir')}")
        run_batch_pipeline(
            input_dir=req["input_dir"],
            output_dir=req.get("effective_output_dir", req["output_dir"]),
            license_dir=req["license_dir"],
            device=req["device"],
            threads=req["threads"],
            resume=req.get("resume", False),
            selected_tools=req["selected_tools"],
            export_config=ExportConfig.from_dict(req.get("export_config")),
            stats_vector_config=StatsVectorConfig.from_dict(req.get("stats_vector_config")),
            recursive=req["recursive"],
            input_files=files,
            on_progress=self._on_progress,
            on_build_log=self._log,
            on_image_start=self._on_image_start,
            on_image_done=self._on_image_done,
            on_metrics=self._on_metrics,
            should_stop=self.stop_requested.is_set,
        )

    def _on_progress(self, stage: str, status: str, pct: float, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {status.upper()} {stage}: {msg}"
        self._log(line)
        pct_value = max(0, min(100, pct * 100))
        target_key = getattr(self, "active_image_key", "")
        current_run = self.image_runs.get(target_key, {}) if target_key else {}
        idx = int(current_run.get("idx", 1) or 1)
        total = max(int(current_run.get("total", self.state.current_total_images) or 1), 1)
        overall_pct = pct_value if stage == "batch" else (((idx - 1) + (pct_value / 100.0)) / total) * 100.0
        overall_pct = max(0, min(100, overall_pct))
        self.state.overall_progress_var.set(overall_pct)
        self.state.overall_progress_text.set(f"{int(overall_pct)}%")
        self.state.status_text.set(status.capitalize())
        if target_key:
            label = {
                "running": "Running",
                "success": "Running" if stage != "pipeline" else "Done",
                "failed": "Failed",
                "paused": "Paused",
            }.get(status, status.capitalize())
            stage_name = STAGE_LABELS.get(stage, "Batch" if stage == "batch" else stage.replace("_", " ").title())
            stage_text = f"{stage_name} - {status.capitalize()}"
            self._update_image_run(
                target_key,
                status=label,
                percent=None if stage == "batch" else pct_value,
                stage_text=stage_text,
            )
        if stage in self.stage_items:
            label = {
                "running": "Running",
                "success": "Done",
                "failed": "Failed",
                "paused": "Paused",
            }.get(status, status.capitalize())
            if hasattr(self, "_set_step_status"):
                self._set_step_status(stage, label, pct)
        if self.state.run_target.get() == "Server":
            self.state.server_text.set("Server: connected")
        else:
            self.state.server_text.set("Server: local")

    def _on_image_start(self, input_file: str, idx: int, total: int) -> None:
        self.active_image_key = input_file
        self._log(f"Starting image {idx}/{total}: {input_file}")
        self.state.current_running_images = 1
        self._update_batch_summary()
        self._update_image_run(input_file, status="Running", percent=0, stage_text="Starting")
        self._select_image(input_file)
        self.metrics_queue.put((getattr(self, "active_image_key", ""), 0.0, 0, 0.0, "new image"))

    def _on_image_done(self, result: BatchImageResult, idx: int, total: int) -> None:
        status = "OK" if result.success else "FAILED"
        self._log(f"Done image {idx}/{total}: {result.subject_id} | {status}")
        self.state.current_running_images = 0
        if result.success:
            self.state.current_success_images += 1
            row_status = "Done"
            pct = 100
        else:
            self.state.current_failed_images += 1
            row_status = "Failed"
            pct = self.image_runs.get(result.input_file, {}).get("percent", 0)
        self._update_batch_summary()
        self._update_image_run(result.input_file, status=row_status, percent=pct, stage_text="Completed" if result.success else "Failed")

    def _on_metrics(self, stage: str, tool: str, cpu_pct: float | None, ram_bytes: int | None, elapsed: float, container_name: str, gpu_pct: float | None = 0.0) -> None:
        target_key = getattr(self, "active_image_key", "")
        if target_key and target_key in self.image_runs:
            run = self.image_runs[target_key]
            run["cpu"].append(max(cpu_pct or 0.0, 0.0))
            run["ram"].append(ram_bytes or 0)
            run["gpu"].append(max(gpu_pct or 0.0, 0.0))
            run["container"] = container_name or "n/a"
            run["cpu"] = run["cpu"][-180:]
            run["ram"] = run["ram"][-180:]
            run["gpu"] = run["gpu"][-180:]
        self.metrics_queue.put((target_key, cpu_pct, ram_bytes, gpu_pct, container_name))

    def _request_stop(self) -> None:
        self.stop_requested.set()
        if self.state.run_target.get() == "Server" and self.remote_runner and self.remote_runner.remote_job_dir:
            def request_remote_pause():
                try:
                    self.remote_runner.request_pause()
                except Exception as exc:
                    self._log(f"REMOTE PAUSE ERROR: {type(exc).__name__}: {exc}")

            threading.Thread(target=request_remote_pause, daemon=True).start()
            self._log("Remote pause requested. Server will pause after the current pipeline stage.")
            return
        if self.active_job and self.active_job.get("target") == "Local" and self.active_job.get("job_dir"):
            try:
                stop_file = Path(str(self.active_job["job_dir"])) / "stop_requested"
                stop_file.touch()
                self._log(f"Local pause requested via stop file: {stop_file}")
            except Exception as exc:
                self._log(f"LOCAL PAUSE ERROR: {type(exc).__name__}: {exc}")
            return
        self._log("Pause requested. The current Docker step will finish, then state will be saved as PAUSED.")

    def _set_idle_state(self) -> None:
        if hasattr(self, "progress"):
            self.progress.stop()
        if hasattr(self, "run_button"):
            self.run_button.configure(state=tk.NORMAL if self._validate_configuration() else tk.DISABLED)
        if hasattr(self, "resume_button"):
            self.resume_button.configure(state=tk.NORMAL)
        if hasattr(self, "restart_button"):
            self.restart_button.configure(state=tk.NORMAL)
        if hasattr(self, "stop_button"):
            self.stop_button.configure(state=tk.DISABLED)
        self.running = False
        self.state.status_text.set("Ready")
        self._log("Pipeline finished.")
        self._log("=" * 80)

    def _poll_queues(self) -> None:
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, tuple):
                image_key, line_str = item
            else:
                image_key, line_str = None, item

            if image_key and image_key in self.image_runs:
                run = self.image_runs[image_key]
                run["logs"].append(line_str)
                run["logs"] = run["logs"][-2500:]

            if not image_key or image_key == self.current_image_key:
                self._append_log(line_str)

        while True:
            try:
                item = self.metrics_queue.get_nowait()
            except queue.Empty:
                break
            if len(item) == 5:
                image_key, cpu_pct, ram_bytes, gpu_pct, container_name = item
            else:
                image_key, cpu_pct, ram_bytes, gpu_pct, container_name = None, item[0], item[1], item[2], item[3]
                
            if not image_key or image_key == self.current_image_key:
                if hasattr(self, "detail_chart"):
                    self.detail_chart.add(cpu_pct, ram_bytes, container_name)
                if hasattr(self, "gpu_chart"):
                    gpu = max(gpu_pct or 0.0, 0.0)
                    self.gpu_chart.add(gpu, f"{gpu:.1f}%")
                cpu = max(cpu_pct or 0.0, 0.0)
                ram_mib = (ram_bytes or 0) / (1024 * 1024)
                self.state.cpu_text.set(f"CPU {cpu:.0f}%")
                self.state.ram_text.set(f"RAM {ram_mib / 1024:.2f} GB" if ram_mib >= 1024 else f"RAM {ram_mib:.0f} MB")

        self.root.after(100, self._poll_queues)
    def _log(self, line: str) -> None:
        self.log_queue.put((getattr(self, "active_image_key", ""), line))

    def _append_log(self, line: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)


def main() -> None:
    import sys
    import os
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("ERROR: No Linux GUI display detected.", file=sys.stderr)
        sys.exit(1)

    try:
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
