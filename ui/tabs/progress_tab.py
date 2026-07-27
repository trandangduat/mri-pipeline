from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from pipeline.registry import STAGE_LABELS, STAGE_ORDER
from ui.components.cards import create_card
from ui.components.charts import LineChart
from ui.formatters import truncate_middle


def _target(context: dict | None, gui, name: str, value):
    if context is not None:
        context[name] = value
    else:
        setattr(gui, name, value)


def _var(context: dict | None, gui, name: str):
    if context is not None:
        return context[name]
    return getattr(gui.state, name)


class ProgressMetricsPanel(ttk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self.panel_width = 280
        self.container_label = tk.StringVar(value="Container: n/a")
        ttk.Label(self, textvariable=self.container_label, foreground="#475569", wraplength=self.panel_width, justify=tk.LEFT).pack(anchor=tk.W, fill=tk.X, pady=(0, 8))
        self.cpu_chart = LineChart(self, "CPU", "#22c55e", "%", 100.0)
        self.gpu_chart = LineChart(self, "GPU", "#3b82f6", "%", 100.0)
        self.ram_chart = LineChart(self, "RAM", "#f87171", " MiB", 1024.0)
        for chart in (self.cpu_chart, self.gpu_chart, self.ram_chart):
            chart.canvas.configure(width=self.panel_width, height=68)
        self.cpu_chart.pack(fill=tk.X, pady=(0, 10))
        self.gpu_chart.pack(fill=tk.X, pady=(0, 10))
        self.ram_chart.pack(fill=tk.X)

    def reset(self) -> None:
        self.container_label.set("Container: n/a")
        self.cpu_chart.reset()
        self.gpu_chart.reset()
        self.ram_chart.reset()

    def add(self, cpu_pct: float | None, ram_bytes: int | None, container_name: str) -> None:
        cpu = max(cpu_pct or 0.0, 0.0)
        ram_mib = (ram_bytes or 0) / (1024 * 1024)
        ram_text = f"{ram_mib:.1f} MiB" if ram_mib < 1024 else f"{ram_mib / 1024:.2f} GiB"
        self.container_label.set(f"Container: {truncate_middle(container_name, 44) if container_name else 'n/a'}")
        self.cpu_chart.add(cpu, f"{cpu:.1f}%")
        self.ram_chart.add(ram_mib, ram_text)


def _progress_action(gui, context: dict | None, action) -> None:
    if context is not None:
        gui._activate_progress_context(context["id"])
    action()


def build_progress_tab(parent: ttk.Frame, gui, context: dict | None = None) -> None:
    parent.rowconfigure(2, weight=1)
    parent.columnconfigure(0, weight=1)

    header = ttk.Frame(parent, padding=(16, 14, 16, 10))
    header.grid(row=0, column=0, sticky=tk.EW)
    header.columnconfigure(0, weight=1)

    title_area = ttk.Frame(header)
    title_area.grid(row=0, column=0, sticky=tk.EW)
    title_var = context["tab_title"] if context is not None else gui.state.detail_title
    ttk.Label(title_area, textvariable=title_var, font=("Inter", 12, "bold")).pack(anchor=tk.W)
    time_row = ttk.Frame(title_area)
    time_row.pack(anchor=tk.W, pady=(2, 0))
    ttk.Label(time_row, text="Started: ", foreground="#475569").pack(side=tk.LEFT)
    ttk.Label(time_row, textvariable=context["job_started_text"] if context is not None else gui.state.status_text, foreground="#475569").pack(side=tk.LEFT)
    ttk.Label(time_row, text="  -  Elapsed: ", foreground="#475569").pack(side=tk.LEFT)
    ttk.Label(time_row, textvariable=context["job_elapsed_text"] if context is not None else gui.state.overall_progress_text, foreground="#475569").pack(side=tk.LEFT)

    actions = ttk.Frame(header)
    actions.grid(row=0, column=1, sticky=tk.E)
    ttk.Button(
        actions,
        text="Job Info",
        command=lambda: _progress_action(gui, context, gui._show_active_job_info),
    ).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(
        actions,
        text="Download outputs",
        command=lambda: _progress_action(gui, context, gui._download_active_job_outputs),
    ).pack(side=tk.LEFT, padx=(0, 8))
    if context is not None:
        ttk.Button(
            actions,
            text="Close tab",
            command=lambda: _progress_action(gui, context, lambda: gui._close_progress_tab(context["id"])),
        ).pack(side=tk.LEFT)

    ttk.Separator(parent, orient=tk.HORIZONTAL).grid(row=1, column=0, sticky=tk.EW)

    body = ttk.Frame(parent, padding=16)
    body.grid(row=2, column=0, sticky=tk.NSEW)
    body.rowconfigure(0, weight=1)
    body.columnconfigure(0, weight=1)

    panes = ttk.PanedWindow(body, orient=tk.HORIZONTAL)
    panes.grid(row=0, column=0, sticky=tk.NSEW)

    left = ttk.Frame(panes, width=280, padding=(0, 0, 12, 0))
    left.rowconfigure(1, weight=1)
    panes.add(left, weight=0)

    center = ttk.Frame(panes, padding=(12, 0, 12, 0))
    center.rowconfigure(0, weight=1)
    panes.add(center, weight=0)

    right = ttk.Frame(panes, width=320, padding=(12, 0, 0, 0))
    panes.add(right, weight=1)

    summary = create_card(left, "RUN", "Batch overview", "", {"fill": tk.X, "pady": (0, 12)})
    summary_items = (
        ("✓", _var(context, gui, "batch_total_text"), "#16a34a"),
        ("●", _var(context, gui, "batch_running_text"), "#2563eb"),
        ("!", _var(context, gui, "batch_failed_text"), "#dc2626"),
    )
    for icon, text_var, color in summary_items:
        row = ttk.Frame(summary)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=icon, foreground=color, width=2, font=("Inter", 10, "bold")).pack(side=tk.LEFT)
        ttk.Label(row, textvariable=text_var, foreground=color, font=("Inter", 10, "bold")).pack(side=tk.LEFT)

    list_card = create_card(left, "IMG", "Input images", "", {"fill": tk.BOTH, "expand": True})
    image_list_canvas = tk.Canvas(list_card, highlightthickness=0)
    _target(context, gui, "image_list_canvas", image_list_canvas)
    image_scroll = ttk.Scrollbar(list_card, orient=tk.VERTICAL, command=image_list_canvas.yview)
    image_list_frame = ttk.Frame(image_list_canvas)
    _target(context, gui, "image_list_frame", image_list_frame)

    def _on_frame_configure(_event):
        image_list_canvas.configure(scrollregion=image_list_canvas.bbox("all"))

    image_list_frame.bind("<Configure>", _on_frame_configure)
    frame_id = image_list_canvas.create_window((0, 0), window=image_list_frame, anchor=tk.NW)

    def _on_canvas_configure(event):
        image_list_canvas.itemconfig(frame_id, width=event.width)

    image_list_canvas.bind("<Configure>", _on_canvas_configure)
    image_list_canvas.configure(yscrollcommand=image_scroll.set)
    image_list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    image_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    detail = create_card(center, "DETAIL", "Selected image", "", {"fill": tk.BOTH, "expand": True})
    detail.columnconfigure(0, weight=1)
    detail_title = ttk.Label(detail, textvariable=_var(context, gui, "detail_title"), font=("Inter", 11, "bold"), wraplength=680, justify=tk.LEFT)
    detail_title.pack(anchor=tk.W, fill=tk.X, pady=(0, 4))

    detail._tool_labels = []

    def _sync_detail_wrap(event) -> None:
        if str(event.widget) == str(detail):
            detail_title.configure(wraplength=max(320, event.width - 24))
            tool_wrap = max(180, event.width - 500)
            for tl in detail._tool_labels:
                tl.configure(wraplength=tool_wrap)

    detail.bind("<Configure>", _sync_detail_wrap)

    steps = ttk.LabelFrame(detail, text=" Progress ", padding=10)
    steps.pack(fill=tk.X, expand=False, pady=(0, 8))
    columns = ("", "Stage", "Tools", "Status", "Time", "CPU", "RAM", "GPU")
    widths = (24, 165, 260, 72, 60, 60, 82, 50)
    for col, (heading, width) in enumerate(zip(columns, widths)):
        weight = 1 if heading == "Tools" else 0
        steps.columnconfigure(col, weight=weight, minsize=width)
        ttk.Label(steps, text=heading, font=("Inter", 9, "bold")).grid(row=0, column=col, sticky=tk.W, padx=(0, 8), pady=(0, 6))
    ttk.Separator(steps, orient=tk.HORIZONTAL).grid(row=1, column=0, columnspan=len(columns), sticky=tk.EW, pady=(0, 4))
    step_summary_rows = {}
    _target(context, gui, "step_summary_rows", step_summary_rows)
    for idx, stage in enumerate(STAGE_ORDER, start=0):
        row = 2 + idx
        icon = ttk.Label(steps, width=2)
        icon.grid(row=row, column=0, sticky=tk.W, padx=(0, 8), pady=6)
        step = ttk.Label(steps, text=STAGE_LABELS.get(stage, stage), anchor=tk.W)
        step.grid(row=row, column=1, sticky=tk.EW, padx=(0, 8), pady=6)
        tool = ttk.Label(steps, text="", anchor=tk.W, foreground="#475569")
        tool.grid(row=row, column=2, sticky=tk.W, padx=(0, 8), pady=6)
        detail._tool_labels.append(tool)
        status = ttk.Label(steps, text="Pending", anchor=tk.W, foreground="#64748b")
        status.grid(row=row, column=3, sticky=tk.W, padx=(0, 8), pady=6)
        duration = ttk.Label(steps, text="", anchor=tk.W)
        duration.grid(row=row, column=4, sticky=tk.W, padx=(0, 8), pady=6)
        cpu = ttk.Label(steps, text="", anchor=tk.W)
        cpu.grid(row=row, column=5, sticky=tk.W, padx=(0, 8), pady=6)
        ram = ttk.Label(steps, text="", anchor=tk.W)
        ram.grid(row=row, column=6, sticky=tk.W, padx=(0, 8), pady=6)
        gpu = ttk.Label(steps, text="", anchor=tk.W)
        gpu.grid(row=row, column=7, sticky=tk.W, padx=(0, 0), pady=6)
        step_summary_rows[stage] = {
            "icon": icon,
            "step": step,
            "tool": tool,
            "status": status,
            "duration": duration,
            "ram": ram,
            "cpu": cpu,
            "gpu": gpu,
        }

    log_card = ttk.LabelFrame(detail, text=" Image log ", padding=12)
    _target(context, gui, "progress_log_card", log_card)
    log_card.pack(fill=tk.X)
    log_header = ttk.Frame(log_card)
    log_header.pack(fill=tk.X)
    progress_log_toggle_text = tk.StringVar(value="Show Image Log")
    _target(context, gui, "progress_log_toggle_text", progress_log_toggle_text)
    toggle_command = (lambda: _progress_action(gui, context, gui._toggle_progress_log)) if context is not None else gui._toggle_progress_log
    ttk.Button(log_header, textvariable=progress_log_toggle_text, command=toggle_command).pack(side=tk.LEFT)
    copy_command = (lambda: _progress_action(gui, context, gui._copy_progress_log)) if context is not None else gui._copy_progress_log
    ttk.Button(log_header, text="Copy log", command=copy_command).pack(side=tk.RIGHT)
    progress_log_body = ttk.Frame(log_card)
    _target(context, gui, "progress_log_body", progress_log_body)
    log_text = tk.Text(progress_log_body, wrap=tk.WORD, height=12, state=tk.DISABLED, padx=12, pady=10, font=("JetBrains Mono", 10))
    _target(context, gui, "log_text", log_text)
    log_scroll = ttk.Scrollbar(progress_log_body, orient=tk.VERTICAL, command=log_text.yview)
    log_text.configure(yscrollcommand=log_scroll.set)
    log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    runtime_card = create_card(right, "CFG", "Runtime settings", "", {"fill": tk.X, "pady": (0, 12)})
    preset_label = ttk.Label(runtime_card, text=f"Preset: {_var(context, gui, 'job_preset_text').get() or 'n/a'}", foreground="#475569", justify=tk.LEFT)
    preset_label.pack(anchor=tk.W, fill=tk.X, pady=(0, 4))
    _target(context, gui, "progress_preset_label", preset_label)
    threads_label = ttk.Label(runtime_card, text=f"Threads: {_var(context, gui, 'job_threads_text').get() or 'n/a'}", foreground="#475569", justify=tk.LEFT)
    threads_label.pack(anchor=tk.W, fill=tk.X, pady=(0, 4))
    _target(context, gui, "progress_threads_label", threads_label)
    device_label = ttk.Label(runtime_card, text=f"Device: {_var(context, gui, 'job_device_text').get() or 'n/a'}", foreground="#475569", justify=tk.LEFT)
    device_label.pack(anchor=tk.W, fill=tk.X)
    _target(context, gui, "progress_device_label", device_label)

    def _sync_runtime_wrap(event) -> None:
        if str(event.widget) == str(runtime_card):
            wrap = max(200, event.width - 24)
            preset_label.configure(wraplength=wrap)
            threads_label.configure(wraplength=wrap)
            device_label.configure(wraplength=wrap)

    runtime_card.bind("<Configure>", _sync_runtime_wrap)

    metrics_card = create_card(right, "MET", "Metrics", "", {"fill": tk.X})
    detail_chart = ProgressMetricsPanel(metrics_card)
    _target(context, gui, "detail_chart", detail_chart)
    detail_chart.pack(fill=tk.X)
    gpu_chart = detail_chart.gpu_chart
    _target(context, gui, "gpu_chart", gpu_chart)
