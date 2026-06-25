import tkinter as tk
from tkinter import ttk
from pipeline_runner import STAGE_LABELS, STAGE_ORDER
from ui.components.cards import create_card
from ui.components.charts import MetricsCharts, LineChart

def build_progress_tab(parent: ttk.Frame, gui) -> None:
    panes = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
    panes.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    left = ttk.Frame(panes, padding=8)
    right = ttk.Frame(panes, padding=8)
    panes.add(left, weight=1)
    panes.add(right, weight=3)

    summary = create_card(left, "RUN", "Batch summary", "Sequential execution: 1 image at a time", {"fill": tk.X, "pady": (0, 10)})
    ttk.Label(summary, textvariable=gui.state.batch_total_text).pack(anchor=tk.W, pady=2)
    ttk.Label(summary, textvariable=gui.state.batch_running_text).pack(anchor=tk.W, pady=2)
    ttk.Label(summary, textvariable=gui.state.batch_failed_text).pack(anchor=tk.W, pady=2)

    list_card = create_card(left, "IMG", "Input images", "Click an image to inspect details", {"fill": tk.BOTH, "expand": True})
    # Cannot use ttk.Canvas, so keep tk.Canvas
    gui.image_list_canvas = tk.Canvas(list_card, highlightthickness=0)
    image_scroll = ttk.Scrollbar(list_card, orient=tk.VERTICAL, command=gui.image_list_canvas.yview)
    gui.image_list_frame = ttk.Frame(gui.image_list_canvas)
    def _on_frame_configure(_event):
        gui.image_list_canvas.configure(scrollregion=gui.image_list_canvas.bbox("all"))
    gui.image_list_frame.bind("<Configure>", _on_frame_configure)
    
    frame_id = gui.image_list_canvas.create_window((0, 0), window=gui.image_list_frame, anchor=tk.NW)
    def _on_canvas_configure(event):
        gui.image_list_canvas.itemconfig(frame_id, width=event.width)
    gui.image_list_canvas.bind("<Configure>", _on_canvas_configure)
    gui.image_list_canvas.configure(yscrollcommand=image_scroll.set)
    gui.image_list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    image_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    detail = create_card(right, "DETAIL", "Selected image", "Step status, runtime metrics, and log", {"fill": tk.BOTH, "expand": True})
    ttk.Label(detail, textvariable=gui.state.detail_title).pack(anchor=tk.W, pady=(0, 8))

    steps = ttk.LabelFrame(detail, text=" Processing steps ", padding=10)
    steps.pack(fill=tk.X, pady=(0, 8))
    columns = ("", "Step", "Tool", "Status", "Duration", "RAM", "CPU", "GPU")
    widths = (28, 210, 150, 92, 80, 90, 72, 72)
    for col, (heading, width) in enumerate(zip(columns, widths)):
        steps.columnconfigure(col, weight=1 if heading == "Step" else 0, minsize=width)
        ttk.Label(steps, text=heading, font=("Inter", 9, "bold")).grid(row=0, column=col, sticky=tk.W, padx=(0, 8), pady=(0, 6))
    ttk.Separator(steps, orient=tk.HORIZONTAL).grid(row=1, column=0, columnspan=len(columns), sticky=tk.EW, pady=(0, 4))
    gui.step_summary_rows = {}
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
        gui.step_summary_rows[stage] = {
            "icon": icon,
            "step": step,
            "tool": tool,
            "status": status,
            "duration": duration,
            "ram": ram,
            "cpu": cpu,
            "gpu": gpu,
        }
    
    gui.detail_chart = MetricsCharts(detail)
    gui.detail_chart.pack(fill=tk.X, pady=(0, 8))
    
    gui.gpu_chart = LineChart(detail, "GPU", "#f59e0b", "%", 100.0)
    gui.gpu_chart.pack(fill=tk.X, pady=(0, 8))
    
    log_card = ttk.LabelFrame(detail, text=" Image log ", padding=12)
    log_card.pack(fill=tk.X, pady=(0, 0))
    log_header = ttk.Frame(log_card)
    log_header.pack(fill=tk.X)
    gui.progress_log_toggle_text = tk.StringVar(value="Show Image Log")
    ttk.Button(log_header, textvariable=gui.progress_log_toggle_text, command=gui._toggle_progress_log).pack(side=tk.LEFT)
    gui.progress_log_body = ttk.Frame(log_card)
    gui.log_text = tk.Text(
        gui.progress_log_body,
        wrap=tk.WORD,
        height=14,
        state=tk.DISABLED,
        
        padx=12,
        pady=10,
        font=("JetBrains Mono", 10),
    )
    log_scroll = ttk.Scrollbar(gui.progress_log_body, orient=tk.VERTICAL, command=gui.log_text.yview)
    gui.log_text.configure(yscrollcommand=log_scroll.set)
    gui.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
