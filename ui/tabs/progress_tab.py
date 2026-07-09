import tkinter as tk
from tkinter import ttk
from pipeline_runner import STAGE_LABELS, STAGE_ORDER
from ui.components.cards import create_card
from ui.components.charts import MetricsCharts, LineChart

def _target(context: dict | None, gui, name: str, value):
    if context is not None:
        context[name] = value
    else:
        setattr(gui, name, value)


def _var(context: dict | None, gui, name: str):
    if context is not None:
        return context[name]
    return getattr(gui.state, name)


def build_progress_tab(parent: ttk.Frame, gui, context: dict | None = None) -> None:
    if context is not None:
        header = ttk.Frame(parent, padding=(8, 8, 8, 0))
        header.pack(fill=tk.X)
        ttk.Label(header, textvariable=context["tab_title"], font=("Inter", 10, "bold")).pack(side=tk.LEFT)
        ttk.Button(
            header,
            text="Close tab",
            command=lambda: gui._close_progress_tab(context["id"]),
        ).pack(side=tk.RIGHT)

    panes = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
    panes.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    left = ttk.Frame(panes, padding=8)
    right_scroll_canvas = tk.Canvas(panes, highlightthickness=0)
    right_scrollbar = ttk.Scrollbar(panes, orient=tk.VERTICAL, command=right_scroll_canvas.yview)
    right = ttk.Frame(right_scroll_canvas, padding=8)
    right_window_id = right_scroll_canvas.create_window((0, 0), window=right, anchor=tk.NW)

    def _on_right_frame_configure(_event):
        right_scroll_canvas.configure(scrollregion=right_scroll_canvas.bbox("all"))

    right.bind("<Configure>", _on_right_frame_configure)

    def _on_right_canvas_configure(event):
        right_scroll_canvas.itemconfig(right_window_id, width=event.width)

    right_scroll_canvas.bind("<Configure>", _on_right_canvas_configure)
    right_scroll_canvas.configure(yscrollcommand=right_scrollbar.set)

    def _on_mousewheel(event):
        right_scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_scroll_recursive(widget):
        try:
            widget.bind("<MouseWheel>", _on_mousewheel, add="+")
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            _bind_scroll_recursive(child)

    right_scroll_canvas.bind("<MouseWheel>", _on_mousewheel)
    right.bind("<MouseWheel>", _on_mousewheel)
    for child in right.winfo_children():
        _bind_scroll_recursive(child)

    panes.add(left, weight=1)
    panes.add(right_scroll_canvas, weight=3)
    right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    summary = create_card(left, "RUN", "Batch summary", "Sequential execution: 1 image at a time", {"fill": tk.X, "pady": (0, 10)})
    ttk.Label(summary, textvariable=_var(context, gui, "batch_total_text")).pack(anchor=tk.W, pady=2)
    ttk.Label(summary, textvariable=_var(context, gui, "batch_running_text")).pack(anchor=tk.W, pady=2)
    ttk.Label(summary, textvariable=_var(context, gui, "batch_failed_text")).pack(anchor=tk.W, pady=2)

    list_card = create_card(left, "IMG", "Input images", "Click an image to inspect details", {"fill": tk.BOTH, "expand": True})
    # Cannot use ttk.Canvas, so keep tk.Canvas
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

    detail = create_card(right, "DETAIL", "Selected image", "Step status, runtime metrics, and log", {"fill": tk.BOTH, "expand": True})
    ttk.Label(detail, textvariable=_var(context, gui, "detail_title")).pack(anchor=tk.W, pady=(0, 8))

    job_info = ttk.Frame(detail)
    job_info.pack(fill=tk.X, pady=(0, 8))
    ttk.Label(job_info, text="Preset:", font=("Inter", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
    ttk.Label(job_info, textvariable=_var(context, gui, "job_preset_text"), foreground="#475569").pack(side=tk.LEFT, padx=(0, 16))
    ttk.Label(job_info, text="Threads:", font=("Inter", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
    ttk.Label(job_info, textvariable=_var(context, gui, "job_threads_text"), foreground="#475569").pack(side=tk.LEFT, padx=(0, 16))
    ttk.Label(job_info, text="Device:", font=("Inter", 9, "bold")).pack(side=tk.LEFT, padx=(0, 4))
    ttk.Label(job_info, textvariable=_var(context, gui, "job_device_text"), foreground="#475569").pack(side=tk.LEFT)

    steps = ttk.LabelFrame(detail, text=" Processing steps ", padding=10)
    steps.pack(fill=tk.X, pady=(0, 8))
    columns = ("", "Step", "Tool", "Status", "Duration", "RAM", "CPU", "GPU")
    widths = (28, 210, 150, 92, 80, 90, 72, 72)
    for col, (heading, width) in enumerate(zip(columns, widths)):
        steps.columnconfigure(col, weight=1 if heading == "Step" else 0, minsize=width)
        ttk.Label(steps, text=heading, font=("Inter", 9, "bold")).grid(row=0, column=col, sticky=tk.W, padx=(0, 8), pady=(0, 6))
    ttk.Separator(steps, orient=tk.HORIZONTAL).grid(row=1, column=0, columnspan=len(columns), sticky=tk.EW, pady=(0, 4))
    step_summary_rows = {}
    _target(context, gui, "step_summary_rows", step_summary_rows)
    for idx, stage in enumerate(STAGE_ORDER, start=0):
        row = 2 + idx
        icon = ttk.Label(steps, width=2)
        icon.grid(row=row, column=0, sticky=tk.W, padx=(0, 8), pady=2)
        step = ttk.Label(steps, text=STAGE_LABELS.get(stage, stage), anchor=tk.W)
        step.grid(row=row, column=1, sticky=tk.EW, padx=(0, 8), pady=2)
        tool = ttk.Label(steps, text="", anchor=tk.W, foreground="#475569")
        tool.grid(row=row, column=2, sticky=tk.W, padx=(0, 8), pady=2)
        status = ttk.Label(steps, text="Pending", anchor=tk.W, foreground="#64748b")
        status.grid(row=row, column=3, sticky=tk.W, padx=(0, 8), pady=2)
        duration = ttk.Label(steps, text="", anchor=tk.W)
        duration.grid(row=row, column=4, sticky=tk.W, padx=(0, 8), pady=2)
        ram = ttk.Label(steps, text="", anchor=tk.W)
        ram.grid(row=row, column=5, sticky=tk.W, padx=(0, 8), pady=2)
        cpu = ttk.Label(steps, text="", anchor=tk.W)
        cpu.grid(row=row, column=6, sticky=tk.W, padx=(0, 8), pady=2)
        gpu = ttk.Label(steps, text="", anchor=tk.W)
        gpu.grid(row=row, column=7, sticky=tk.W, padx=(0, 0), pady=2)
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
    
    detail_chart = MetricsCharts(detail)
    _target(context, gui, "detail_chart", detail_chart)
    detail_chart.pack(fill=tk.X, pady=(0, 8))
    
    gpu_chart = LineChart(detail, "GPU", "#f59e0b", "%", 100.0)
    _target(context, gui, "gpu_chart", gpu_chart)
    gpu_chart.pack(fill=tk.X, pady=(0, 8))
    
    log_card = ttk.LabelFrame(detail, text=" Image log ", padding=12)
    _target(context, gui, "progress_log_card", log_card)
    log_card.pack(fill=tk.X, pady=(0, 0))
    log_header = ttk.Frame(log_card)
    log_header.pack(fill=tk.X)
    progress_log_toggle_text = tk.StringVar(value="Show Image Log")
    _target(context, gui, "progress_log_toggle_text", progress_log_toggle_text)
    if context is not None:
        toggle_command = lambda: (gui._activate_progress_context(context["id"]), gui._toggle_progress_log())
    else:
        toggle_command = gui._toggle_progress_log
    ttk.Button(log_header, textvariable=progress_log_toggle_text, command=toggle_command).pack(side=tk.LEFT)
    if context is not None:
        copy_command = lambda: (gui._activate_progress_context(context["id"]), gui._copy_progress_log())
    else:
        copy_command = gui._copy_progress_log
    ttk.Button(log_header, text="Copy log", command=copy_command).pack(side=tk.RIGHT)
    progress_log_body = ttk.Frame(log_card)
    _target(context, gui, "progress_log_body", progress_log_body)
    log_text = tk.Text(
        progress_log_body,
        wrap=tk.WORD,
        height=22,
        state=tk.DISABLED,
        
        padx=12,
        pady=10,
        font=("JetBrains Mono", 10),
    )
    _target(context, gui, "log_text", log_text)
    log_scroll = ttk.Scrollbar(progress_log_body, orient=tk.VERTICAL, command=log_text.yview)
    log_text.configure(yscrollcommand=log_scroll.set)
    log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
