import tkinter as tk
from tkinter import ttk
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
        if getattr(gui.image_list_canvas, "_scroll_timer", None):
            gui.image_list_canvas.after_cancel(gui.image_list_canvas._scroll_timer)
        gui.image_list_canvas._scroll_timer = gui.image_list_canvas.after(50, lambda: gui.image_list_canvas.configure(scrollregion=gui.image_list_canvas.bbox("all")))
    gui.image_list_frame.bind("<Configure>", _on_frame_configure)
    
    frame_id = gui.image_list_canvas.create_window((0, 0), window=gui.image_list_frame, anchor=tk.NW)
    def _on_canvas_configure(event):
        if getattr(gui.image_list_canvas, "_width_timer", None):
            gui.image_list_canvas.after_cancel(gui.image_list_canvas._width_timer)
        w = event.width
        gui.image_list_canvas._width_timer = gui.image_list_canvas.after(20, lambda: gui.image_list_canvas.itemconfig(frame_id, width=w))
    gui.image_list_canvas.bind("<Configure>", _on_canvas_configure)
    gui.image_list_canvas.configure(yscrollcommand=image_scroll.set)
    gui.image_list_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    image_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    detail = create_card(right, "DETAIL", "Selected image", "CPU, GPU, RAM and log", {"fill": tk.BOTH, "expand": True})
    ttk.Label(detail, textvariable=gui.state.detail_title).pack(anchor=tk.W, pady=(0, 8))
    
    gui.detail_chart = MetricsCharts(detail)
    gui.detail_chart.pack(fill=tk.X, pady=(0, 8))
    
    gui.gpu_chart = LineChart(detail, "GPU", "#f59e0b", "%", 100.0)
    gui.gpu_chart.pack(fill=tk.X, pady=(0, 8))
    
    gui.log_text = tk.Text(
        detail,
        wrap=tk.WORD,
        height=14,
        state=tk.DISABLED,
        
        padx=12,
        pady=10,
        font=("JetBrains Mono", 10),
    )
    log_scroll = ttk.Scrollbar(detail, orient=tk.VERTICAL, command=gui.log_text.yview)
    gui.log_text.configure(yscrollcommand=log_scroll.set)
    gui.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
