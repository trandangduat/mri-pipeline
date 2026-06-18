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
from tkinter import filedialog, messagebox, ttk

from pipeline_runner import (
    PROJECT_ROOT,
    STAGE_LABELS,
    STAGE_ORDER,
    TOOL_DEFS,
    BatchImageResult,
    PipelineConfig,
    _derive_subject_id,
    _discover_mri_files,
    build_subject_id_map,
    ensure_image,
    image_exists,
    run_batch_pipeline,
    run_pipeline,
)
from remote.remote_runner import RemoteRunConfig, RemoteRunner
from ui.state import AppState
from ui.styles import setup_styles
from ui.components.dialogs import build_image_dialog, append_dialog_log
from ui.tabs.config_tab import build_configuration_tab
from ui.tabs.progress_tab import build_progress_tab
from remote.ssh_client import SSHConfig


class PipelineGUI:
    FREESURFER_FIXED_TOOLS = {
        "reorientation": "mri_convert",
        "brain_extraction": "synthstrip",
        "segmentation": "synthseg_freesurfer",
        "bias_correction": "ants_n4",
        "template_registration": "synthmorph",
        "white_matter_segmentation": "wm_seg",
        "stats_extraction": "freesurfer_stats",
    }

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MRI Pipeline GUI - Tkinter")
        self.root.geometry("1250x950")
        self.root.minsize(1050, 760)

        # Initialize State
        self.state = AppState()
        
        # Apply Styles

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.metrics_queue: queue.Queue[tuple[float | None, int | None, str]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.running = False
        self.stop_requested = threading.Event()
        
        self.remote_runner: RemoteRunner | None = None
        self.remote_frame: ttk.Frame | None = None
        self.remote_body: ttk.Frame | None = None
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

        self._build_ui()
        self._setup_validation_traces()
        self._validate_configuration()
        self._poll_queues()

    def _build_ui(self) -> None:
        root_frame = ttk.Frame(self.root)
        root_frame.pack(fill=tk.BOTH, expand=True)

        self._build_app_toolbar(root_frame)
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

        self.save_button = self._toolbar_button(toolbar, "save", "Save Config", self._save_config)
        self.load_button = self._toolbar_button(toolbar, "load", "Load Config", self._load_config)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12, pady=4)
        
        self.run_button = self._toolbar_button(toolbar, "run", "Run Pipeline", lambda: self._start_pipeline(resume=True, restart=False))
        self.stop_button = self._toolbar_button(toolbar, "pause", "Stop", self._request_stop)
        self.stop_button.configure(state=tk.DISABLED)
        
        status = ttk.Frame(toolbar)
        status.pack(side=tk.RIGHT, fill=tk.Y)
        
        # We add some styling and spacing to the status texts to make them look like a cohesive modern status badge
        ttk.Label(status, textvariable=self.state.overall_progress_text, width=4, anchor=tk.E).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Separator(status, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, pady=6)
        ttk.Label(status, textvariable=self.state.server_text, foreground="#475569").pack(side=tk.RIGHT, padx=8)
        ttk.Separator(status, orient=tk.VERTICAL).pack(side=tk.RIGHT, fill=tk.Y, pady=6)
        ttk.Label(status, textvariable=self.state.status_text).pack(side=tk.RIGHT, padx=8)

    def _build_tabs(self, parent: ttk.Frame) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.config_tab = ttk.Frame(self.notebook)
        self.progress_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.config_tab, text="Pipeline configuration")
        self.notebook.add(self.progress_tab, text="Run progress", state="disabled")

        build_configuration_tab(self.config_tab, self)
        build_progress_tab(self.progress_tab, self)

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
        self._set_widget_tree_state(self.remote_body, tk.NORMAL if enabled else tk.DISABLED)
        self.state.remote_status.set("Remote: configure SSH server" if enabled else "")
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
        fixed = self.state.pipeline_mode.get() == "FreeSurfer Fixed (7 steps)"
        if fixed:
            for stage, tool in self.FREESURFER_FIXED_TOOLS.items():
                if stage in self.state.tool_vars:
                    self.state.tool_vars[stage].set(tool)
            for combo in self.tool_combos.values():
                combo.configure(state="disabled")
            self.state.pipeline_note.set(
                "Fixed FreeSurfer stack. Note: bias correction still uses ants_n4 until a FreeSurfer replacement image exists."
            )
        else:
            for combo in self.tool_combos.values():
                combo.configure(state="readonly")
            self.state.pipeline_note.set("Custom mode: choose tools freely for each stage.")

    def _selected_tools(self) -> dict[str, str]:
        if self.state.pipeline_mode.get() == "FreeSurfer Fixed (7 steps)":
            self._apply_pipeline_mode()
        return {stage: var.get() for stage, var in self.state.tool_vars.items()}

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
        if loaded_pipeline_mode not in ("FreeSurfer Fixed (7 steps)", "Custom Tools"):
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
                self.state.tool_vars[stage].set(value)

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

    def _save_config(self) -> None:
        config_dir = PROJECT_ROOT / "configs"
        config_dir.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(
            title="Save pipeline config",
            initialdir=str(config_dir),
            defaultextension=".json",
            filetypes=(("JSON config", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return

        config = self.state.collect_config()
        config["name"] = Path(path).stem
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self._log(f"Saved config: {path}")
        except Exception as exc:
            messagebox.showerror("Save config failed", str(exc))

    def _load_config(self) -> None:
        config_dir = PROJECT_ROOT / "configs"
        path = filedialog.askopenfilename(
            title="Load pipeline config",
            initialdir=str(config_dir),
            filetypes=(("JSON config", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
            self.state.apply_config(config)
            self._log(f"Config path: {path}")
        except Exception as exc:
            messagebox.showerror("Load config failed", str(exc))

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
        ]
        for var in variables:
            var.trace_add("write", lambda *_args: self._validate_configuration())

        self.state.input_path.trace_add("write", self._refresh_input_label)

        for tool_var in self.state.tool_vars.values():
            tool_var.trace_add("write", lambda *_args: self._validate_configuration())

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
        try:
            if int(self.state.threads.get()) < 1:
                errors.append("Threads must be at least 1.")
        except (tk.TclError, ValueError):
            errors.append("Threads must be a valid integer.")

        selected_tools = self.state.get_selected_tools()
        missing_stages = [stage for stage in STAGE_ORDER if not selected_tools.get(stage)]
        if missing_stages:
            errors.append("Select one tool for every pipeline stage.")

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
        required_tools = list(dict.fromkeys(self.state.get_selected_tools().values()))

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
                self.root.after(0, lambda: append_dialog_log(log, f"REMOTE IMAGE ERROR: {type(exc).__name__}: {exc}"))
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
        self.resume_button.configure(state=tk.DISABLED)
        self.restart_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.progress.start(10)
        self.detail_chart.reset()
        self.gpu_chart.reset()
        self.state.overall_progress_var.set(0)
        self.state.overall_progress_text.set("0%")
        self.state.status_text.set("Running")
        for stage in STAGE_ORDER:
            self._set_step_status(stage, "Ready", 0)
        self._clear_log()
        self._log("=" * 80)
        if restart:
            self._log("Restart mode: existing subject outputs will be removed before running.")
        elif resume:
            self._log("Resume mode: completed stages in pipeline_state.json will be skipped.")
        self._log("Starting pipeline...")

        self.worker = threading.Thread(target=self._run_worker, args=(run_request,), daemon=True)
        self.worker.start()

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

        def task():
            if not runner.remote_job_dir:
                runner.upload_job()
            code = runner.run_remote()
            self._log(f"Remote pipeline exited with code {code}")
            if code == 0:
                local_path = runner.download_outputs(self.state.output_dir.get())
                self._log(f"Downloaded outputs to: {local_path}")

        title = "Remote Resume" if resume else ("Remote Restart" if restart else "Remote Run")
        self._run_remote_task(title, task, clear_log=True, enable_pause=True)

    def _build_run_request(self) -> dict | None:
        mode = self.state.input_mode.get()
        raw_input = self.state.input_path.get().strip()
        if not raw_input:
            messagebox.showerror("Missing input", "Chưa chọn file hoặc folder MRI.")
            return None

        selected_tools = self.state.get_selected_tools()
        base = {
            "mode": mode,
            "output_dir": self.state.output_dir.get().strip(),
            "license_dir": self.state.license_dir.get().strip(),
            "device": self.state.device.get(),
            "threads": int(self.state.threads.get()),
            "selected_tools": selected_tools,
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
        name = Path(input_file).name or input_file
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
        }
        row = ttk.Frame(self.image_list_frame)
        row.pack(fill=tk.X, pady=(0, 6))
        top = ttk.Frame(row)
        top.pack(fill=tk.X, padx=8, pady=(6, 2))
        title = ttk.Label(top, text=f"{idx}/{total} {name}", anchor=tk.W, font=("Inter", 9, "bold"))
        title.pack(side=tk.LEFT, fill=tk.X, expand=True)
        status = ttk.Label(top, text="Pending", anchor=tk.E, font=("Inter", 8))
        status.pack(side=tk.RIGHT)
        var = tk.DoubleVar(value=0)
        bar = ttk.Progressbar(row, variable=var, maximum=100, mode="determinate")
        bar.pack(fill=tk.X, padx=8, pady=(0, 8))
        for widget in (row, top, title, status, bar):
            widget.bind("<Button-1>", lambda _e, key=input_file: self._select_image(key))
        self.image_rows[input_file] = {"frame": row, "title": title, "status": status, "var": var}

    def _select_image(self, input_file: str) -> None:
        if input_file not in self.image_runs:
            return
        self.current_image_key = input_file
        for key, row in self.image_rows.items():
            row["frame"].configure(relief="solid" if key == input_file else "flat")
        run = self.image_runs[input_file]
        self.state.detail_title.set(f"{run['idx']}/{run['total']} {run['name']} - {run['status']}")
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

    def _update_image_run(self, input_file: str, status: str | None = None, percent: float | None = None, log_line: str | None = None) -> None:
        if input_file not in self.image_runs:
            self._create_image_run(input_file, len(self.image_runs) + 1, max(self.state.current_total_images, len(self.image_runs) + 1))
        run = self.image_runs[input_file]
        if status is not None:
            run["status"] = status
            self.image_rows[input_file]["status"].configure(text=status)
        if percent is not None:
            pct = max(0.0, min(100.0, percent))
            run["percent"] = pct
            self.image_rows[input_file]["var"].set(pct)
        if log_line:
            run["logs"].append(log_line)
            run["logs"] = run["logs"][-2500:]
        if self.current_image_key == input_file:
            self.state.detail_title.set(f"{run['idx']}/{run['total']} {run['name']} - {run['status']}")

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
            resume=resume,
        )
        return RemoteRunner(remote_config, on_log=self._remote_log_event)

    def _match_progress_input_key(self, input_file: str) -> str:
        if input_file in self.image_runs:
            return input_file
        remote_name = Path(input_file).name
        if len(remote_name) > 5 and remote_name[:4].isdigit() and remote_name[4] == "_":
            remote_name = remote_name[5:]
        for key, run in self.image_runs.items():
            if Path(key).name == remote_name or run.get("name") == remote_name:
                return key
        return input_file

    def _remote_log_event(self, line: str) -> None:
        self.root.after(0, lambda l=line: self._handle_remote_log_event(l))

    def _handle_remote_log_event(self, line: str) -> None:
        if not line.startswith("MRI_EVENT "):
            self._log(line)
            if self.current_image_key:
                self._update_image_run(self.current_image_key, log_line=line)
            return
        try:
            event = json.loads(line[len("MRI_EVENT "):])
        except json.JSONDecodeError:
            self._log(line)
            return

        kind = event.get("kind")
        if kind == "image_start":
            key = self._match_progress_input_key(str(event.get("input_file", "")))
            idx = int(event.get("idx", len(self.image_runs) + 1))
            total = int(event.get("total", max(self.state.current_total_images, idx)))
            self.state.current_total_images = max(self.state.current_total_images, total)
            self.current_image_key = key
            self.state.current_running_images = 1
            self._update_batch_summary()
            self._update_image_run(key, status="Running", percent=0, log_line=f"Remote image {idx}/{total} started: {key}")
            self.root.after(0, lambda k=key: self._select_image(k))
        elif kind == "progress":
            pct = float(event.get("pct", 0)) * 100
            status = str(event.get("status", "running"))
            stage = str(event.get("stage", "pipeline"))
            msg = str(event.get("msg", ""))
            label = {"running": "Running", "success": "Running", "failed": "Failed", "paused": "Paused"}.get(status, status.capitalize())
            self.state.overall_progress_var.set(max(0, min(100, pct)))
            self.state.overall_progress_text.set(f"{int(max(0, min(100, pct)))}%")
            self.state.status_text.set(status.capitalize())
            if self.current_image_key:
                self._update_image_run(self.current_image_key, status=label, percent=pct, log_line=f"REMOTE {status.upper()} {stage}: {msg}")
        elif kind == "image_done":
            key = self._match_progress_input_key(str(event.get("input_file", "")))
            success = bool(event.get("success"))
            self.state.current_running_images = 0
            if success:
                self.state.current_success_images += 1
                self._update_image_run(key, status="Done", percent=100, log_line=f"Remote image done: {event.get('subject_id', key)} | OK")
            else:
                self.state.current_failed_images += 1
                self._update_image_run(key, status="Failed", log_line=f"Remote image failed: {event.get('error', '')}")
            self._update_batch_summary()
        elif kind == "image_preflight":
            self._log(f"Remote image preflight {event.get('status')}: {event.get('tool')}")

    def _run_remote_task(self, title: str, task, clear_log: bool = False, enable_pause: bool = False) -> None:
        if self.running:
            self._append_log("Remote task ignored: another task is already running.")
            return
        self.running = True
        self.state.remote_status.set(f"Remote: {title} running...")
        self.stop_requested.clear()
        self.run_button.configure(state=tk.DISABLED)
        self.resume_button.configure(state=tk.DISABLED)
        self.restart_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL if enable_pause else tk.DISABLED)
        self.progress.start(10)
        if clear_log:
            self._clear_log()
            self.detail_chart.reset()
            self.gpu_chart.reset()
            self.state.overall_progress_var.set(0)
            self.state.overall_progress_text.set("0%")
            self.state.status_text.set("Running")
            for stage in STAGE_ORDER:
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
                self.root.after(0, lambda: self.state.remote_status.set("Testing SSH connection..."))
                runner = RemoteRunner(RemoteRunConfig(ssh=ssh_config), on_log=lambda x: None)
                runner.test_ssh()
                self.root.after(0, lambda: self.state.remote_status.set("✅ SSH Connection Successful"))
            except Exception as exc:
                self.root.after(0, lambda: self.state.remote_status.set(f"❌ SSH Connection Failed: {exc}"))

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

        def task():
            runner.config.resume = resume
            code = runner.run_remote()
            self.remote_runner = runner
            self._log(f"Remote pipeline exited with code {code}")
        self._run_remote_task("Run On Server" if not resume else "Resume Remote", task)

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
        output_dir = Path(req["output_dir"]).resolve()
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
            output_dir=req["output_dir"],
            subject_id=subject_id,
            license_dir=req["license_dir"],
            device=req["device"],
            threads=req["threads"],
            resume=req.get("resume", False),
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
            self._update_image_run(input_file, status="Done", percent=100, log_line=f"Single file finished: {subject_id} | OK")
        else:
            self.state.current_failed_images += 1
            self._update_image_run(input_file, status="Failed", log_line=f"Single file finished: {subject_id} | FAILED")
        self._update_batch_summary()

    def _run_multiple(self, req: dict) -> None:
        files = req["input_files"]
        self._log(f"Selected {len(files)} files")
        run_batch_pipeline(
            input_dir=req["input_dir"],
            output_dir=req["output_dir"],
            license_dir=req["license_dir"],
            device=req["device"],
            threads=req["threads"],
            resume=req.get("resume", False),
            selected_tools=req["selected_tools"],
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
        run_batch_pipeline(
            input_dir=req["input_dir"],
            output_dir=req["output_dir"],
            license_dir=req["license_dir"],
            device=req["device"],
            threads=req["threads"],
            resume=req.get("resume", False),
            selected_tools=req["selected_tools"],
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
        self.state.overall_progress_var.set(pct_value)
        self.state.overall_progress_text.set(f"{int(pct_value)}%")
        self.state.status_text.set(status.capitalize())
        if self.current_image_key:
            label = {
                "running": "Running",
                "success": "Running" if stage != "pipeline" else "Done",
                "failed": "Failed",
                "paused": "Paused",
            }.get(status, status.capitalize())
            self._update_image_run(self.current_image_key, status=label, percent=pct_value, log_line=line)
        if stage in self.stage_items:
            label = {
                "running": "Running",
                "success": "Done",
                "failed": "Failed",
                "paused": "Paused",
            }.get(status, status.capitalize())
            self._set_step_status(stage, label, pct)
        if self.state.run_target.get() == "Server":
            self.state.server_text.set("Server: connected")
        else:
            self.state.server_text.set("Server: local")

    def _on_image_start(self, input_file: str, idx: int, total: int) -> None:
        self._log(f"Starting image {idx}/{total}: {input_file}")
        self.current_image_key = input_file
        self.state.current_running_images = 1
        self._update_batch_summary()
        self._update_image_run(input_file, status="Running", percent=0, log_line=f"Starting image {idx}/{total}: {input_file}")
        self._select_image(input_file)
        self.metrics_queue.put((0.0, 0, "new image"))

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
        self._update_image_run(result.input_file, status=row_status, percent=pct, log_line=f"Done image {idx}/{total}: {result.subject_id} | {status}")

    def _on_metrics(self, stage: str, tool: str, cpu_pct: float | None, ram_bytes: int | None, elapsed: float, container_name: str) -> None:
        if self.current_image_key and self.current_image_key in self.image_runs:
            run = self.image_runs[self.current_image_key]
            run["cpu"].append(max(cpu_pct or 0.0, 0.0))
            run["ram"].append(ram_bytes or 0)
            run["gpu"].append(0.0)
            run["container"] = container_name or "n/a"
            run["cpu"] = run["cpu"][-180:]
            run["ram"] = run["ram"][-180:]
            run["gpu"] = run["gpu"][-180:]
        self.metrics_queue.put((cpu_pct, ram_bytes, container_name))

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
        self._log("Pause requested. The current Docker step will finish, then state will be saved as PAUSED.")

    def _set_idle_state(self) -> None:
        self.progress.stop()
        self.run_button.configure(state=tk.NORMAL if self._validate_configuration() else tk.DISABLED)
        self.resume_button.configure(state=tk.NORMAL)
        self.restart_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.running = False
        self.state.status_text.set("Ready")
        self._log("Pipeline finished.")
        self._log("=" * 80)

    def _poll_queues(self) -> None:
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(line)

        while True:
            try:
                cpu_pct, ram_bytes, container_name = self.metrics_queue.get_nowait()
            except queue.Empty:
                break
            if hasattr(self, "detail_chart"):
                self.detail_chart.add(cpu_pct, ram_bytes, container_name)
            cpu = max(cpu_pct or 0.0, 0.0)
            ram_mib = (ram_bytes or 0) / (1024 * 1024)
            self.state.cpu_text.set(f"CPU {cpu:.0f}%")
            self.state.ram_text.set(f"RAM {ram_mib / 1024:.2f} GB" if ram_mib >= 1024 else f"RAM {ram_mib:.0f} MB")

        self.root.after(100, self._poll_queues)

    def _log(self, line: str) -> None:
        self.log_queue.put(line)

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
