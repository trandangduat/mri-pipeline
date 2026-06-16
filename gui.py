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
    run_batch_pipeline,
    run_pipeline,
)
from remote.remote_runner import RemoteRunConfig, RemoteRunner
from remote.ssh_client import SSHConfig


class LineChart(ttk.Frame):
    def __init__(self, parent: tk.Widget, title: str, color: str, unit: str, minimum_scale: float) -> None:
        super().__init__(parent)
        self.title = title
        self.color = color
        self.unit = unit
        self.minimum_scale = minimum_scale
        self.points: list[float] = []
        self.max_points = 180
        self.label = tk.StringVar(value=f"{title}: n/a")

        ttk.Label(self, textvariable=self.label).pack(anchor=tk.W, pady=(0, 4))
        self.canvas = tk.Canvas(self, height=90, bg="#111827", highlightthickness=1, highlightbackground="#374151")
        self.canvas.pack(fill=tk.X, expand=True)

    def reset(self) -> None:
        self.points.clear()
        self.label.set(f"{self.title}: n/a")
        self._draw()

    def add(self, value: float, text: str) -> None:
        self.points.append(max(value, 0.0))
        self.points = self.points[-self.max_points :]
        self.label.set(f"{self.title}: {text}")
        self._draw()

    def _draw(self) -> None:
        self.canvas.delete("all")
        width = max(self.canvas.winfo_width(), 10)
        height = max(self.canvas.winfo_height(), 10)
        pad_left = 42
        pad_bottom = 24
        pad_top = 10
        pad_right = 8
        max_value = max(self.minimum_scale, max(self.points or [0]))

        self.canvas.create_line(pad_left, height - pad_bottom, width - pad_right, height - pad_bottom, fill="#4b5563")
        self.canvas.create_line(pad_left, pad_top, pad_left, height - pad_bottom, fill="#4b5563")

        self.canvas.create_text(6, pad_top + 2, text=f"{max_value:.0f}{self.unit}", fill="#9ca3af", anchor=tk.W, font=("Segoe UI", 8))
        self.canvas.create_text(6, height - pad_bottom, text=f"0{self.unit}", fill="#9ca3af", anchor=tk.W, font=("Segoe UI", 8))

        for frac in (0.25, 0.5, 0.75):
            y = height - pad_bottom - frac * (height - pad_bottom - pad_top)
            self.canvas.create_line(pad_left, y, width - pad_right, y, fill="#1f2937")

        if len(self.points) < 2:
            return

        usable_w = width - pad_left - pad_right
        usable_h = height - pad_bottom - pad_top
        step = usable_w / max(len(self.points) - 1, 1)
        coords: list[float] = []
        for idx, point in enumerate(self.points):
            x = pad_left + idx * step
            y = height - pad_bottom - (min(point, max_value) / max_value) * usable_h
            coords.extend([x, y])
        self.canvas.create_line(*coords, fill=self.color, width=2, smooth=True)


class MetricsCharts(ttk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self.container_label = tk.StringVar(value="Container: n/a")
        ttk.Label(self, textvariable=self.container_label).pack(anchor=tk.W, pady=(0, 6))

        charts = ttk.Frame(self)
        charts.pack(fill=tk.X, expand=True)
        self.cpu_chart = LineChart(charts, "CPU", "#60a5fa", "%", 100.0)
        self.ram_chart = LineChart(charts, "RAM", "#34d399", " MiB", 1024.0)
        self.cpu_chart.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.ram_chart.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

    def reset(self) -> None:
        self.container_label.set("Container: n/a")
        self.cpu_chart.reset()
        self.ram_chart.reset()

    def add(self, cpu_pct: float | None, ram_bytes: int | None, container_name: str) -> None:
        cpu = max(cpu_pct or 0.0, 0.0)
        ram_mib = (ram_bytes or 0) / (1024 * 1024)
        ram_text = f"{ram_mib:.1f} MiB" if ram_mib < 1024 else f"{ram_mib / 1024:.2f} GiB"
        self.container_label.set(f"Container: {container_name or 'n/a'}")
        self.cpu_chart.add(cpu, f"{cpu:.1f}%")
        self.ram_chart.add(ram_mib, ram_text)


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

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.metrics_queue: queue.Queue[tuple[float | None, int | None, str]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.running = False
        self.stop_requested = threading.Event()

        self.input_mode = tk.StringVar(value="file")
        self.input_path = tk.StringVar()
        self.selected_files: list[str] = []
        self.output_dir = tk.StringVar(value=str(PROJECT_ROOT / "outputs"))
        self.license_dir = tk.StringVar(value=str(PROJECT_ROOT / "license"))
        self.device = tk.StringVar(value="cpu")
        self.threads = tk.IntVar(value=4)
        self.non_recursive = tk.BooleanVar(value=False)
        self.run_target = tk.StringVar(value="Local")
        self.pipeline_mode = tk.StringVar(value="Custom Tools")
        self.allow_custom_tools = tk.BooleanVar(value=True)
        self.remote_host = tk.StringVar()
        self.remote_port = tk.IntVar(value=22)
        self.remote_username = tk.StringVar()
        self.remote_password = tk.StringVar()
        self.remote_key_path = tk.StringVar()
        self.remote_workspace = tk.StringVar(value="~/mri-remote-jobs")
        self.remote_python = tk.StringVar(value="python3")
        self.remote_status = tk.StringVar(value="Remote: idle")
        self.remote_runner: RemoteRunner | None = None
        self.remote_visible = tk.BooleanVar(value=True)
        self.remote_frame: ttk.LabelFrame | None = None
        self.remote_toggle_button: ttk.Button | None = None
        self.actions_frame: ttk.Frame | None = None

        self.tool_vars: dict[str, tk.StringVar] = {}
        self.tool_combos: dict[str, ttk.Combobox] = {}
        self.pipeline_note = tk.StringVar(value="Standard pipeline with editable tools.")
        self.step_tree: ttk.Treeview | None = None
        self.stage_items: dict[str, str] = {}
        self.status_text = tk.StringVar(value="Ready")
        self.server_text = tk.StringVar(value="Server: local")
        self.cpu_text = tk.StringVar(value="CPU 0%")
        self.ram_text = tk.StringVar(value="RAM n/a")
        self.overall_progress_var = tk.DoubleVar(value=0)
        self.overall_progress_text = tk.StringVar(value="0%")

        self._build_ui()
        self._poll_queues()

    def _build_ui(self) -> None:
        root_frame = ttk.Frame(self.root, padding=12)
        root_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(root_frame, text="MRI Pipeline Runner", font=("Segoe UI", 16, "bold")).pack(anchor=tk.W, pady=(0, 8))

        self._build_tools_section(root_frame)

        top = ttk.Frame(root_frame)
        top.pack(fill=tk.X)
        self._build_input_section(top)
        self._build_settings_section(top)
        self._build_remote_section(root_frame)
        self.remote_frame.pack_forget()
        self.remote_visible.set(False)
        self._build_actions_section(root_frame)
        self._build_metrics_section(root_frame)
        self._build_log_section(root_frame)

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Config", command=self._load_config)
        file_menu.add_command(label="Save Config", command=self._save_config)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        pipeline_menu = tk.Menu(menubar, tearoff=0)
        pipeline_menu.add_command(label="Run", command=lambda: self._start_pipeline(resume=False, restart=False))
        pipeline_menu.add_command(label="Resume", command=lambda: self._start_pipeline(resume=True, restart=False))
        pipeline_menu.add_command(label="Restart All", command=lambda: self._start_pipeline(resume=False, restart=True))
        pipeline_menu.add_command(label="Pause After Current Step", command=self._request_stop)
        menubar.add_cascade(label="Pipeline", menu=pipeline_menu)

        remote_menu = tk.Menu(menubar, tearoff=0)
        remote_menu.add_command(label="Test SSH", command=self._remote_test_ssh)
        remote_menu.add_command(label="Check Docker", command=self._remote_check_docker)
        remote_menu.add_command(label="Check Images", command=self._remote_check_images)
        menubar.add_cascade(label="Remote", menu=remote_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Check Environment", command=self._check_environment)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        menubar.add_cascade(label="Help", menu=tk.Menu(menubar, tearoff=0))
        self.root.configure(menu=menubar)

    def _build_toolbar(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent)
        bar.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(bar, text="Open Config", command=self._load_config).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bar, text="Save Config", command=self._save_config).pack(side=tk.LEFT, padx=(0, 12))
        self.run_button = ttk.Button(bar, text="Run", command=lambda: self._start_pipeline(resume=False, restart=False))
        self.run_button.pack(side=tk.LEFT, padx=(0, 6))
        self.resume_button = ttk.Button(bar, text="Resume", command=lambda: self._start_pipeline(resume=True, restart=False))
        self.resume_button.pack(side=tk.LEFT, padx=(0, 6))
        self.restart_button = ttk.Button(bar, text="Restart All", command=lambda: self._start_pipeline(resume=False, restart=True))
        self.restart_button.pack(side=tk.LEFT, padx=(0, 6))
        self.stop_button = ttk.Button(bar, text="Pause", command=self._request_stop, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(0, 12))
        ttk.Button(bar, text="Download Outputs", command=self._download_outputs_action).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bar, text="Check Environment", command=self._check_environment).pack(side=tk.LEFT)

    def _build_pipeline_config_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Pipeline Configuration", padding=10)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        ttk.Label(frame, text="Pipeline mode:").grid(row=0, column=0, sticky=tk.W, pady=4)
        ttk.Combobox(
            frame,
            textvariable=self.pipeline_mode,
            values=("Standard MRI preprocessing", "FreeSurfer Fixed (7 steps)", "Custom Tools"),
            state="readonly",
            width=34,
        ).grid(row=0, column=1, sticky=tk.W, padx=(8, 16), pady=4)
        ttk.Checkbutton(
            frame,
            text="Allow custom tools per step",
            variable=self.allow_custom_tools,
            command=self._apply_pipeline_mode,
        ).grid(row=0, column=2, sticky=tk.W, pady=4)

        ttk.Label(frame, text="Run target:").grid(row=1, column=0, sticky=tk.W, pady=8)
        ttk.Radiobutton(frame, text="Local", variable=self.run_target, value="Local", command=self._on_run_target_changed).grid(row=1, column=1, sticky=tk.W, pady=8)
        ttk.Radiobutton(frame, text="Server", variable=self.run_target, value="Server", command=self._on_run_target_changed).grid(row=1, column=1, sticky=tk.W, padx=(90, 0), pady=8)
        ttk.Label(frame, text="Device:").grid(row=1, column=2, sticky=tk.W, pady=8)
        ttk.Combobox(frame, textvariable=self.device, values=("cpu", "gpu"), state="readonly", width=10).grid(row=1, column=2, sticky=tk.W, padx=(55, 0), pady=8)
        ttk.Label(frame, text="Threads:").grid(row=1, column=3, sticky=tk.W, padx=(20, 6), pady=8)
        ttk.Spinbox(frame, from_=1, to=64, textvariable=self.threads, width=6).grid(row=1, column=4, sticky=tk.W, pady=8)
        ttk.Label(frame, textvariable=self.pipeline_note).grid(row=2, column=0, columnspan=5, sticky=tk.W, pady=(4, 0))

    def _build_input_output_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Input and Output", padding=10)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        mode_row = ttk.Frame(frame)
        mode_row.grid(row=0, column=0, columnspan=3, sticky=tk.EW, pady=(0, 6))
        ttk.Label(mode_row, text="Input type:").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_row, text="Single file", variable=self.input_mode, value="file", command=self._refresh_input_label).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Radiobutton(mode_row, text="Multiple files", variable=self.input_mode, value="files", command=self._refresh_input_label).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Radiobutton(mode_row, text="Batch folder", variable=self.input_mode, value="dir", command=self._refresh_input_label).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Checkbutton(mode_row, text="Non-recursive batch", variable=self.non_recursive).pack(side=tk.LEFT, padx=(16, 0))
        self.file_count_label = ttk.Label(mode_row, text="")
        self.file_count_label.pack(side=tk.LEFT, padx=(12, 0))

        ttk.Label(frame, text="Input path:").grid(row=1, column=0, sticky=tk.W, pady=3)
        ttk.Entry(frame, textvariable=self.input_path).grid(row=1, column=1, sticky=tk.EW, padx=(8, 8), pady=3)
        ttk.Button(frame, text="Browse...", command=self._browse_input).grid(row=1, column=2, pady=3)
        ttk.Label(frame, text="Output directory:").grid(row=2, column=0, sticky=tk.W, pady=3)
        ttk.Entry(frame, textvariable=self.output_dir).grid(row=2, column=1, sticky=tk.EW, padx=(8, 8), pady=3)
        ttk.Button(frame, text="Browse...", command=lambda: self._browse_directory(self.output_dir)).grid(row=2, column=2, pady=3)
        ttk.Label(frame, text="FreeSurfer license:").grid(row=3, column=0, sticky=tk.W, pady=3)
        ttk.Entry(frame, textvariable=self.license_dir).grid(row=3, column=1, sticky=tk.EW, padx=(8, 8), pady=3)
        ttk.Button(frame, text="Browse...", command=lambda: self._browse_directory(self.license_dir)).grid(row=3, column=2, pady=3)
        frame.columnconfigure(1, weight=1)

    def _build_steps_panel(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Processing Steps", padding=8)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        columns = ("enabled", "step", "tool", "status", "progress")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=7, selectmode="browse")
        tree.heading("enabled", text="Enabled")
        tree.heading("step", text="Step")
        tree.heading("tool", text="Tool")
        tree.heading("status", text="Status")
        tree.heading("progress", text="Progress")
        tree.column("enabled", width=70, anchor=tk.CENTER, stretch=False)
        tree.column("step", width=260, anchor=tk.W)
        tree.column("tool", width=170, anchor=tk.W)
        tree.column("status", width=120, anchor=tk.CENTER)
        tree.column("progress", width=110, anchor=tk.CENTER, stretch=False)
        tree.pack(fill=tk.BOTH, expand=True)
        self.step_tree = tree

        for stage in STAGE_ORDER:
            iid = tree.insert("", tk.END, values=("✓", STAGE_LABELS.get(stage, stage), self.tool_vars[stage].get(), "Ready", "0%"))
            self.stage_items[stage] = iid

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(buttons, text="Configure Step...", command=self._configure_selected_step).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Move Up", command=lambda: self._log("Pipeline order is fixed; Move Up is UI placeholder.")).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Move Down", command=lambda: self._log("Pipeline order is fixed; Move Down is UI placeholder.")).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Reset", command=self._reset_pipeline_tools).pack(side=tk.LEFT, padx=(8, 0))

    def _build_status_bar(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent)
        bar.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(bar, textvariable=self.status_text, width=22).pack(side=tk.LEFT)
        ttk.Progressbar(bar, variable=self.overall_progress_var, maximum=100).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 8))
        ttk.Label(bar, textvariable=self.overall_progress_text, width=5).pack(side=tk.LEFT)
        ttk.Label(bar, textvariable=self.cpu_text, width=12).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(bar, textvariable=self.ram_text, width=16).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(bar, textvariable=self.server_text, width=22).pack(side=tk.LEFT, padx=(8, 0))

    def _update_step_table(self) -> None:
        if not self.step_tree:
            return
        for stage in STAGE_ORDER:
            iid = self.stage_items.get(stage)
            if iid:
                current = list(self.step_tree.item(iid, "values"))
                status = current[3] if len(current) > 3 else "Ready"
                progress = current[4] if len(current) > 4 else "0%"
                self.step_tree.item(iid, values=("✓", STAGE_LABELS.get(stage, stage), self.tool_vars[stage].get(), status, progress))

    def _set_step_status(self, stage: str, status: str, progress: float | None = None) -> None:
        if not self.step_tree or stage not in self.stage_items:
            return
        iid = self.stage_items[stage]
        values = list(self.step_tree.item(iid, "values"))
        if len(values) < 5:
            values = ["✓", STAGE_LABELS.get(stage, stage), self.tool_vars.get(stage, tk.StringVar()).get(), "Ready", "0%"]
        values[3] = status
        if progress is not None:
            values[4] = f"{int(progress * 100)}%"
        self.step_tree.item(iid, values=values)

    def _configure_selected_step(self) -> None:
        if self.pipeline_mode.get() == "FreeSurfer Fixed (7 steps)" or not self.allow_custom_tools.get():
            messagebox.showinfo("Tools locked", "Current pipeline mode does not allow changing tools per step.")
            return
        if not self.step_tree:
            return
        selected = self.step_tree.selection()
        if not selected:
            messagebox.showinfo("Select step", "Please select a processing step first.")
            return
        stage = next((s for s, iid in self.stage_items.items() if iid == selected[0]), "")
        if not stage:
            return
        tools = [name for name, meta in TOOL_DEFS.items() if meta["stage"] == stage]

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Configure {STAGE_LABELS.get(stage, stage)}")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text=STAGE_LABELS.get(stage, stage), font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=12, pady=(12, 6))
        choice = tk.StringVar(value=self.tool_vars[stage].get())
        ttk.Combobox(dialog, textvariable=choice, values=tools, state="readonly", width=36).pack(fill=tk.X, padx=12, pady=6)

        def apply_choice() -> None:
            self.tool_vars[stage].set(choice.get())
            self._update_step_table()
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.pack(fill=tk.X, padx=12, pady=(6, 12))
        ttk.Button(buttons, text="Apply", command=apply_choice).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    def _reset_pipeline_tools(self) -> None:
        self.pipeline_mode.set("Standard MRI preprocessing")
        self.allow_custom_tools.set(True)
        defaults = {
            "reorientation": "mri_convert",
            "brain_extraction": "synthstrip",
            "segmentation": "fastsurfervinn",
            "bias_correction": "ants_n4",
            "template_registration": "synthmorph",
            "white_matter_segmentation": "wm_seg",
            "stats_extraction": "freesurfer_stats",
        }
        for stage, tool in defaults.items():
            self.tool_vars[stage].set(tool)
        self._apply_pipeline_mode()

    def _build_input_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="2. Input", padding=10)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        mode_row = ttk.Frame(frame)
        mode_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Radiobutton(mode_row, text="Single file", variable=self.input_mode, value="file", command=self._refresh_input_label).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_row, text="Multiple files", variable=self.input_mode, value="files", command=self._refresh_input_label).pack(side=tk.LEFT, padx=(12, 0))
        ttk.Radiobutton(mode_row, text="Batch folder", variable=self.input_mode, value="dir", command=self._refresh_input_label).pack(side=tk.LEFT, padx=(12, 0))

        path_row = ttk.Frame(frame)
        path_row.pack(fill=tk.X)
        ttk.Entry(path_row, textvariable=self.input_path).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(path_row, text="Browse...", command=self._browse_input).pack(side=tk.LEFT, padx=(8, 0))

        opt_row = ttk.Frame(frame)
        opt_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Checkbutton(opt_row, text="Non-recursive batch", variable=self.non_recursive).pack(side=tk.LEFT)
        self.file_count_label = ttk.Label(opt_row, text="")
        self.file_count_label.pack(side=tk.LEFT, padx=(14, 0))

    def _build_settings_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="3. Settings", padding=10)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._path_row(frame, "Output directory", self.output_dir, 0)
        self._path_row(frame, "FreeSurfer license directory", self.license_dir, 1)

        ttk.Label(frame, text="Device").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Combobox(frame, textvariable=self.device, values=("cpu", "gpu"), state="readonly", width=10).grid(row=2, column=1, sticky=tk.W, pady=(8, 0))
        ttk.Label(frame, text="Threads").grid(row=2, column=2, sticky=tk.W, padx=(20, 8), pady=(8, 0))
        ttk.Spinbox(frame, from_=1, to=64, textvariable=self.threads, width=8).grid(row=2, column=3, sticky=tk.W, pady=(8, 0))
        frame.columnconfigure(1, weight=1)

    def _path_row(self, parent: ttk.LabelFrame, label: str, variable: tk.StringVar, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=3)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, columnspan=3, sticky=tk.EW, padx=(8, 8), pady=3)
        ttk.Button(parent, text="Browse...", command=lambda: self._browse_directory(variable)).grid(row=row, column=4, pady=3)

    def _build_tools_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="1. Pipeline Tools", padding=10)
        frame.pack(fill=tk.X, pady=(8, 8))

        mode_row = ttk.Frame(frame)
        mode_row.grid(row=0, column=0, columnspan=4, sticky=tk.EW, pady=(0, 8))
        ttk.Label(mode_row, text="Pipeline mode:").pack(side=tk.LEFT)
        ttk.Combobox(
            mode_row,
            textvariable=self.pipeline_mode,
            values=("FreeSurfer Fixed (7 steps)", "Custom Tools"),
            state="readonly",
            width=28,
        ).pack(side=tk.LEFT, padx=(8, 12))
        ttk.Label(mode_row, textvariable=self.pipeline_note).pack(side=tk.LEFT, fill=tk.X, expand=True)

        defaults = {
            "reorientation": "mri_convert",
            "brain_extraction": "synthstrip",
            "segmentation": "fastsurfervinn",
            "bias_correction": "ants_n4",
            "template_registration": "synthmorph",
            "white_matter_segmentation": "wm_seg",
            "stats_extraction": "freesurfer_stats",
        }

        for idx, stage in enumerate(STAGE_ORDER):
            row = idx // 2 + 1
            col = (idx % 2) * 2
            tools = [name for name, meta in TOOL_DEFS.items() if meta["stage"] == stage]
            var = tk.StringVar(value=defaults.get(stage, tools[0] if tools else ""))
            self.tool_vars[stage] = var
            ttk.Label(frame, text=STAGE_LABELS.get(stage, stage), width=32).grid(row=row, column=col, sticky=tk.W, pady=2)
            combo = ttk.Combobox(frame, textvariable=var, values=tools, state="readonly", width=24)
            combo.grid(row=row, column=col + 1, sticky=tk.W, padx=(4, 18), pady=2)
            self.tool_combos[stage] = combo

        self.pipeline_mode.trace_add("write", lambda *_args: self._apply_pipeline_mode())
        self._apply_pipeline_mode()

    def _build_remote_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Remote Server (SSH)", padding=10)
        frame.pack(fill=tk.X, pady=(8, 8))
        self.remote_frame = frame

        ttk.Label(frame, text="Host/IP").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame, textvariable=self.remote_host, width=18).grid(row=0, column=1, sticky=tk.EW, padx=(6, 12), pady=2)
        ttk.Label(frame, text="Port").grid(row=0, column=2, sticky=tk.W, pady=2)
        ttk.Spinbox(frame, from_=1, to=65535, textvariable=self.remote_port, width=7).grid(row=0, column=3, sticky=tk.W, padx=(6, 12), pady=2)
        ttk.Label(frame, text="Username").grid(row=0, column=4, sticky=tk.W, pady=2)
        ttk.Entry(frame, textvariable=self.remote_username, width=16).grid(row=0, column=5, sticky=tk.EW, padx=(6, 12), pady=2)
        ttk.Label(frame, text="Password").grid(row=0, column=6, sticky=tk.W, pady=2)
        ttk.Entry(frame, textvariable=self.remote_password, show="*", width=16).grid(row=0, column=7, sticky=tk.EW, padx=(6, 0), pady=2)

        ttk.Label(frame, text="SSH Key").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame, textvariable=self.remote_key_path).grid(row=1, column=1, columnspan=3, sticky=tk.EW, padx=(6, 6), pady=2)
        ttk.Button(frame, text="Browse", command=self._browse_remote_key).grid(row=1, column=4, sticky=tk.W, padx=(0, 12), pady=2)
        ttk.Label(frame, text="Workspace").grid(row=1, column=5, sticky=tk.W, pady=2)
        ttk.Entry(frame, textvariable=self.remote_workspace).grid(row=1, column=6, sticky=tk.EW, padx=(6, 12), pady=2)
        ttk.Label(frame, text="Python").grid(row=1, column=7, sticky=tk.W, pady=2)
        ttk.Entry(frame, textvariable=self.remote_python, width=10).grid(row=1, column=8, sticky=tk.EW, padx=(6, 0), pady=2)

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=9, sticky=tk.EW, pady=(8, 0))
        ttk.Button(buttons, text="Test SSH", command=self._remote_test_ssh).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Check Docker", command=self._remote_check_docker).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Check Images", command=self._remote_check_images).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Download Outputs", command=self._remote_download_outputs).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Clean Remote Job", command=self._remote_clean_job).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(frame, textvariable=self.remote_status).grid(row=3, column=0, columnspan=9, sticky=tk.W, pady=(8, 0))

        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(6, weight=1)

    def _toggle_remote_section(self) -> None:
        if self.remote_frame is None:
            return
        if self.remote_visible.get():
            self.remote_frame.pack_forget()
            self.remote_visible.set(False)
            if self.remote_toggle_button:
                self.remote_toggle_button.configure(text="Show Remote Settings")
        else:
            pack_options = {"fill": tk.X, "pady": (8, 8)}
            if self.actions_frame is not None:
                pack_options["before"] = self.actions_frame
            self.remote_frame.pack(**pack_options)
            self.remote_visible.set(True)
            if self.remote_toggle_button:
                self.remote_toggle_button.configure(text="Hide Remote Settings")

    def _on_run_target_changed(self) -> None:
        if self.remote_frame is None:
            return
        if self.run_target.get() == "Server":
            if not self.remote_visible.get():
                pack_options = {"fill": tk.X, "pady": (8, 8)}
                if self.actions_frame is not None:
                    pack_options["before"] = self.actions_frame
                self.remote_frame.pack(**pack_options)
                self.remote_visible.set(True)
        else:
            if self.remote_visible.get():
                self.remote_frame.pack_forget()
                self.remote_visible.set(False)

    def _build_actions_section(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=(0, 8))
        self.actions_frame = frame

        ttk.Button(frame, text="Save Config", command=self._save_config).pack(side=tk.LEFT)
        ttk.Button(frame, text="Load Config", command=self._load_config).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(frame, text="Run target:").pack(side=tk.LEFT, padx=(16, 4))
        target_combo = ttk.Combobox(
            frame,
            textvariable=self.run_target,
            values=("Local", "Server"),
            state="readonly",
            width=9,
        )
        target_combo.pack(side=tk.LEFT)
        self.run_target.trace_add("write", lambda *_args: self._on_run_target_changed())

        self.run_button = ttk.Button(frame, text="Run Pipeline", command=lambda: self._start_pipeline(resume=False, restart=False))
        self.run_button.pack(side=tk.LEFT, padx=(16, 0))
        self.resume_button = ttk.Button(frame, text="Resume", command=lambda: self._start_pipeline(resume=True, restart=False))
        self.resume_button.pack(side=tk.LEFT, padx=(8, 0))
        self.restart_button = ttk.Button(frame, text="Restart All", command=lambda: self._start_pipeline(resume=False, restart=True))
        self.restart_button.pack(side=tk.LEFT, padx=(8, 0))
        self.stop_button = ttk.Button(frame, text="Pause After Current Step", command=self._request_stop, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(8, 0))
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 0))

    def _build_metrics_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="4. Live Docker CPU/RAM", padding=10)
        frame.pack(fill=tk.X, pady=(0, 8))
        self.chart = MetricsCharts(frame)
        self.chart.pack(fill=tk.X, expand=True)

    def _build_log_section(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="5. Log", padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(frame, wrap=tk.WORD, height=16, state=tk.DISABLED)
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _browse_input(self) -> None:
        mode = self.input_mode.get()
        if mode == "file":
            path = filedialog.askopenfilename(title="Select MRI file", filetypes=self._mri_filetypes())
            if path:
                self.selected_files = [path]
                self.input_path.set(path)
        elif mode == "files":
            paths = filedialog.askopenfilenames(title="Select MRI files", filetypes=self._mri_filetypes())
            if paths:
                self.selected_files = list(paths)
                self.input_path.set("; ".join(self.selected_files))
        else:
            path = filedialog.askdirectory(title="Select MRI input folder")
            if path:
                self.selected_files = []
                self.input_path.set(path)
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
            self.remote_key_path.set(path)

    def _apply_pipeline_mode(self) -> None:
        fixed = self.pipeline_mode.get() == "FreeSurfer Fixed (7 steps)"
        if fixed:
            for stage, tool in self.FREESURFER_FIXED_TOOLS.items():
                if stage in self.tool_vars:
                    self.tool_vars[stage].set(tool)
            for combo in self.tool_combos.values():
                combo.configure(state="disabled")
            self.pipeline_note.set(
                "Fixed FreeSurfer stack. Note: bias correction still uses ants_n4 until a FreeSurfer replacement image exists."
            )
        else:
            for combo in self.tool_combos.values():
                combo.configure(state="readonly")
            self.pipeline_note.set("Custom mode: choose tools freely for each stage.")

    def _selected_tools(self) -> dict[str, str]:
        if self.pipeline_mode.get() == "FreeSurfer Fixed (7 steps)":
            self._apply_pipeline_mode()
        return {stage: var.get() for stage, var in self.tool_vars.items()}

    def _collect_config(self) -> dict:
        return {
            "version": 1,
            "run_target": self.run_target.get(),
            "pipeline_mode": self.pipeline_mode.get(),
            "input_mode": self.input_mode.get(),
            "input_path": self.input_path.get(),
            "selected_files": self.selected_files,
            "output_dir": self.output_dir.get(),
            "license_dir": self.license_dir.get(),
            "device": self.device.get(),
            "threads": self.threads.get(),
            "non_recursive": self.non_recursive.get(),
            "tools": {stage: var.get() for stage, var in self.tool_vars.items()},
            "remote": {
                "host": self.remote_host.get(),
                "port": self.remote_port.get(),
                "username": self.remote_username.get(),
                "key_path": self.remote_key_path.get(),
                "workspace": self.remote_workspace.get(),
                "python": self.remote_python.get(),
            },
        }

    def _apply_config(self, config: dict) -> None:
        self.input_mode.set(config.get("input_mode", "file"))
        self.run_target.set(config.get("run_target", "Local"))
        loaded_pipeline_mode = config.get("pipeline_mode", "Custom Tools")
        if loaded_pipeline_mode not in ("FreeSurfer Fixed (7 steps)", "Custom Tools"):
            loaded_pipeline_mode = "Custom Tools"
        self.pipeline_mode.set(loaded_pipeline_mode)
        self.input_path.set(config.get("input_path", ""))
        self.selected_files = list(config.get("selected_files", []))
        self.output_dir.set(config.get("output_dir", str(PROJECT_ROOT / "outputs")))
        self.license_dir.set(config.get("license_dir", str(PROJECT_ROOT / "license")))
        self.device.set(config.get("device", "cpu"))
        self.threads.set(int(config.get("threads", 4)))
        self.non_recursive.set(bool(config.get("non_recursive", False)))

        tools = config.get("tools", {})
        for stage, value in tools.items():
            if stage in self.tool_vars:
                self.tool_vars[stage].set(value)

        self._apply_pipeline_mode()

        remote = config.get("remote", {})
        self.remote_host.set(remote.get("host", ""))
        self.remote_port.set(int(remote.get("port", 22)))
        self.remote_username.set(remote.get("username", ""))
        self.remote_key_path.set(remote.get("key_path", ""))
        self.remote_workspace.set(remote.get("workspace", "~/mri-remote-jobs"))
        self.remote_python.set(remote.get("python", "python3"))

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

        config = self._collect_config()
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
            self._apply_config(config)
            self._log(f"Config path: {path}")
        except Exception as exc:
            messagebox.showerror("Load config failed", str(exc))

    def _refresh_input_label(self) -> None:
        if self.input_mode.get() == "files":
            self.file_count_label.configure(text=f"Selected: {len(self.selected_files)} files")
        else:
            self.file_count_label.configure(text="")

    def _start_pipeline(self, resume: bool = False, restart: bool = False) -> None:
        if self.running:
            return

        if self.run_target.get() == "Server":
            self._start_remote_pipeline(resume=resume, restart=restart)
            return

        run_request = self._build_run_request()
        if run_request is None:
            return
        run_request["resume"] = resume
        run_request["restart"] = restart

        self.running = True
        self.stop_requested.clear()
        self.run_button.configure(state=tk.DISABLED)
        self.resume_button.configure(state=tk.DISABLED)
        self.restart_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.progress.start(10)
        self.chart.reset()
        self.overall_progress_var.set(0)
        self.overall_progress_text.set("0%")
        self.status_text.set("Running")
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

    def _start_remote_pipeline(self, resume: bool = False, restart: bool = False) -> None:
        runner = self.remote_runner if resume and self.remote_runner else self._build_remote_runner(resume=resume)
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
                local_path = runner.download_outputs(self.output_dir.get())
                self._log(f"Downloaded outputs to: {local_path}")

        title = "Remote Resume" if resume else ("Remote Restart" if restart else "Remote Run")
        self._run_remote_task(title, task, clear_log=True, enable_pause=True)

    def _build_run_request(self) -> dict | None:
        mode = self.input_mode.get()
        raw_input = self.input_path.get().strip()
        if not raw_input:
            messagebox.showerror("Missing input", "Chưa chọn file hoặc folder MRI.")
            return None

        selected_tools = self._selected_tools()
        base = {
            "mode": mode,
            "output_dir": self.output_dir.get().strip(),
            "license_dir": self.license_dir.get().strip(),
            "device": self.device.get(),
            "threads": int(self.threads.get()),
            "selected_tools": selected_tools,
        }

        if mode == "file":
            path = self.selected_files[0] if self.selected_files else raw_input
            if not Path(path).is_file():
                messagebox.showerror("Invalid input", f"Không tồn tại file: {path}")
                return None
            base["input_file"] = path
        elif mode == "files":
            files = self.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
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
            base["recursive"] = not self.non_recursive.get()

        return base

    def _build_ssh_config(self) -> SSHConfig | None:
        host = self.remote_host.get().strip()
        username = self.remote_username.get().strip()
        if not host or not username:
            messagebox.showerror("Missing remote server", "Cần nhập Host/IP và Username của remote server.")
            return None

        return SSHConfig(
            host=host,
            port=int(self.remote_port.get()),
            username=username,
            password=self.remote_password.get(),
            key_path=self.remote_key_path.get().strip(),
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
            remote_workspace=self.remote_workspace.get().strip() or "~/mri-remote-jobs",
            remote_python=self.remote_python.get().strip() or "python3",
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
        return RemoteRunner(remote_config, on_log=self._log)

    def _run_remote_task(self, title: str, task, clear_log: bool = False, enable_pause: bool = False) -> None:
        if self.running:
            self._append_log("Remote task ignored: another task is already running.")
            return
        self.running = True
        self.remote_status.set(f"Remote: {title} running...")
        self.stop_requested.clear()
        self.run_button.configure(state=tk.DISABLED)
        self.resume_button.configure(state=tk.DISABLED)
        self.restart_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL if enable_pause else tk.DISABLED)
        self.progress.start(10)
        if clear_log:
            self._clear_log()
            self.chart.reset()
            self.overall_progress_var.set(0)
            self.overall_progress_text.set("0%")
            self.status_text.set("Running")
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
                self.root.after(0, lambda: self.remote_status.set("Remote: idle"))
                self.root.after(0, self._set_idle_state)

        threading.Thread(target=worker, daemon=True).start()

    def _remote_test_ssh(self) -> None:
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return

        def task():
            runner = RemoteRunner(RemoteRunConfig(ssh=ssh_config), on_log=self._log)
            runner.test_ssh()
        self._run_remote_task("Test SSH", task)

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
        selected_tools = self._selected_tools()

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
        if self.run_target.get() == "Server":
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
        if self.run_target.get() == "Server":
            self._remote_download_outputs()
        else:
            self._log(f"Local outputs are already in: {self.output_dir.get()}")

    def _required_images_for_current_tools(self) -> list[str]:
        images: list[str] = []
        for tool_key in self._selected_tools().values():
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
        self.status_text.set(title)
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
            local_path = self.remote_runner.download_outputs(self.output_dir.get())
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
        self._log(f"[{ts}] {status.upper()} {stage}: {msg}")
        pct_value = max(0, min(100, pct * 100))
        self.overall_progress_var.set(pct_value)
        self.overall_progress_text.set(f"{int(pct_value)}%")
        self.status_text.set(status.capitalize())
        if stage in self.stage_items:
            label = {
                "running": "Running",
                "success": "Done",
                "failed": "Failed",
                "paused": "Paused",
            }.get(status, status.capitalize())
            self._set_step_status(stage, label, pct)
        if self.run_target.get() == "Server":
            self.server_text.set("Server: connected")
        else:
            self.server_text.set("Server: local")

    def _on_image_start(self, input_file: str, idx: int, total: int) -> None:
        self._log(f"Starting image {idx}/{total}: {input_file}")
        self.metrics_queue.put((0.0, 0, "new image"))

    def _on_image_done(self, result: BatchImageResult, idx: int, total: int) -> None:
        status = "OK" if result.success else "FAILED"
        self._log(f"Done image {idx}/{total}: {result.subject_id} | {status}")

    def _on_metrics(self, stage: str, tool: str, cpu_pct: float | None, ram_bytes: int | None, elapsed: float, container_name: str) -> None:
        self.metrics_queue.put((cpu_pct, ram_bytes, container_name))

    def _request_stop(self) -> None:
        self.stop_requested.set()
        if self.run_target.get() == "Server" and self.remote_runner and self.remote_runner.remote_job_dir:
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
        self.run_button.configure(state=tk.NORMAL)
        self.resume_button.configure(state=tk.NORMAL)
        self.restart_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.running = False
        self.status_text.set("Ready")
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
            self.chart.add(cpu_pct, ram_bytes, container_name)
            cpu = max(cpu_pct or 0.0, 0.0)
            ram_mib = (ram_bytes or 0) / (1024 * 1024)
            self.cpu_text.set(f"CPU {cpu:.0f}%")
            self.ram_text.set(f"RAM {ram_mib / 1024:.2f} GB" if ram_mib >= 1024 else f"RAM {ram_mib:.0f} MB")

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
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("ERROR: No Linux GUI display detected.", file=sys.stderr)
        sys.exit(1)

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"ERROR: Could not start Tkinter GUI: {exc}", file=sys.stderr)
        sys.exit(1)

    PipelineGUI(root)
    root.update_idletasks()
    try:
        root.state("zoomed")
    except tk.TclError:
        try:
            root.attributes("-zoomed", True)
        except tk.TclError:
            pass
    root.deiconify()
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()
    root.after(1500, lambda: root.attributes("-topmost", False))
    print("MRI Pipeline GUI is running.", flush=True)
    root.mainloop()


if __name__ == "__main__":
    main()
