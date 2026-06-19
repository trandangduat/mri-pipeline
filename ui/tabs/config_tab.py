import tkinter as tk
from tkinter import ttk
from ui.components.cards import create_card
from pipeline_runner import STAGE_ORDER, STAGE_LABELS, enabled_tools_for_stage

def build_configuration_tab(parent: ttk.Frame, gui) -> None:
    canvas = tk.Canvas(parent, highlightthickness=0)
    scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
    scroll_frame = ttk.Frame(canvas)
    window_id = canvas.create_window((0, 0), window=scroll_frame, anchor=tk.NW)

    def _sync_scroll_region(_event=None):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _sync_window_width(event):
        canvas.itemconfigure(window_id, width=event.width)

    def _on_mousewheel(event):
        if event.num == 4:
            canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            canvas.yview_scroll(3, "units")
        else:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_mousewheel(_event=None):
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_mousewheel)
        canvas.bind_all("<Button-5>", _on_mousewheel)

    def _unbind_mousewheel(_event=None):
        canvas.unbind_all("<MouseWheel>")
        canvas.unbind_all("<Button-4>")
        canvas.unbind_all("<Button-5>")

    scroll_frame.bind("<Configure>", _sync_scroll_region)
    canvas.bind("<Configure>", _sync_window_width)
    canvas.bind("<MouseWheel>", _on_mousewheel)
    canvas.bind("<Button-4>", _on_mousewheel)
    canvas.bind("<Button-5>", _on_mousewheel)
    canvas.bind("<Enter>", _bind_mousewheel)
    canvas.bind("<Leave>", _unbind_mousewheel)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    panes = ttk.PanedWindow(scroll_frame, orient=tk.HORIZONTAL)
    panes.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    left = ttk.Frame(panes, padding=8)
    right = ttk.Frame(panes, padding=8)
    panes.add(left, weight=1)
    panes.add(right, weight=1)

    _build_tools_section(left, gui)
    _build_input_section(right, gui)
    _build_settings_section(right, gui)
    _build_remote_section(right, gui)
    
    gui.state.remote_visible.set(True)
    gui._on_run_target_changed()

def _build_tools_section(parent: ttk.Frame, gui) -> None:
    frame = create_card(parent, "01", "Pipeline Tools", "Seven-stage MRI processing pipeline", {"fill": tk.BOTH, "expand": True})

    mode_row = ttk.Frame(frame)
    mode_row.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 12))
    ttk.Label(mode_row, text="Mode").pack(side=tk.LEFT)
    ttk.Combobox(
        mode_row, textvariable=gui.state.pipeline_mode,
        values=("FreeSurfer Fixed (7 steps)", "Custom Tools"),
        state="readonly",
        width=28,
    ).pack(side=tk.LEFT, padx=(8, 12))

    gui.tool_combos = getattr(gui, "tool_combos", {})
    gui.tool_status_labels = getattr(gui, "tool_status_labels", {})

    for idx, stage in enumerate(STAGE_ORDER):
        row = idx + 1
        tools = enabled_tools_for_stage(stage)
        var = gui.state.tool_vars[stage]
        
        step = ttk.Frame(frame)
        step.grid(row=row, column=0, sticky=tk.EW, pady=5)
        

        ttk.Label(
            step,
            text=f"{row}. {STAGE_LABELS.get(stage, stage)}",
            width=32,
            anchor=tk.W,
        ).pack(side=tk.LEFT)
        
        combo = ttk.Combobox(frame, textvariable=var, values=tools, state="readonly", width=24)
        combo.grid(row=row, column=1, sticky=tk.EW, padx=(10, 0), pady=5)
        gui.tool_combos[stage] = combo
        status = ttk.Label(frame, text="Not checked", width=14, anchor=tk.W, foreground="#64748b")
        status.grid(row=row, column=2, sticky=tk.W, padx=(10, 0), pady=5)
        gui.tool_status_labels[stage] = status

    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)
    frame.columnconfigure(2, weight=0)

    ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=8, column=0, columnspan=2, sticky=tk.EW, pady=10)
    
    lic_row = ttk.Frame(frame)
    lic_row.grid(row=9, column=0, columnspan=2, sticky=tk.EW, pady=(0, 5))
    ttk.Label(lic_row, text="FreeSurfer license").pack(anchor=tk.W, pady=(0, 2))
    input_frame = ttk.Frame(lic_row)
    input_frame.pack(fill=tk.X, expand=True)
    ttk.Entry(input_frame, textvariable=gui.state.license_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    ttk.Button(input_frame, text="Browse", style="Accent.TButton", command=lambda: gui._browse_directory(gui.state.license_dir)).pack(side=tk.RIGHT)

    gui.state.pipeline_mode.trace_add("write", lambda *_args: gui._apply_pipeline_mode())
    gui._apply_pipeline_mode()
    gui._update_config_tool_status_labels()

def _build_input_section(parent: ttk.Frame, gui) -> None:
    frame = create_card(parent, "", "Input & output", "", {"fill": tk.X, "pady": (0, 10)})

    mode_row = ttk.Frame(frame)
    mode_row.grid(row=0, column=0, columnspan=5, sticky=tk.EW, pady=(0, 10))
    ttk.Radiobutton(mode_row, text="Single file", variable=gui.state.input_mode, value="file", command=gui._refresh_input_label).pack(side=tk.LEFT)
    ttk.Radiobutton(mode_row, text="Multiple files", variable=gui.state.input_mode, value="files", command=gui._refresh_input_label).pack(side=tk.LEFT, padx=(14, 0))
    ttk.Radiobutton(mode_row, text="Batch folder", variable=gui.state.input_mode, value="dir", command=gui._refresh_input_label).pack(side=tk.LEFT, padx=(14, 0))

    container = ttk.Frame(frame)
    container.grid(row=1, column=0, columnspan=5, sticky=tk.EW, pady=3)
    ttk.Label(container, text="Input MRI").pack(anchor=tk.W, pady=(0, 2))
    
    input_frame = ttk.Frame(container)
    input_frame.pack(fill=tk.X, expand=True)
    ttk.Entry(input_frame, textvariable=gui.state.input_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    
    gui.file_count_label = ttk.Label(input_frame, text="")
    gui.file_count_label.pack(side=tk.LEFT, padx=(0, 8))
    
    gui.btn_config_batch = ttk.Button(input_frame, text="Configure Batch", command=gui._configure_batch, state=tk.DISABLED)
    gui.btn_config_batch.pack(side=tk.LEFT, padx=(0, 8))
    
    ttk.Button(input_frame, text="Browse", style="Accent.TButton", command=gui._browse_input).pack(side=tk.RIGHT)

    ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=2, column=0, columnspan=5, sticky=tk.EW, pady=10)

    _path_row(frame, "Output directory", gui.state.output_dir, 3, lambda: gui._browse_directory(gui.state.output_dir))

    frame.columnconfigure(1, weight=1)

def _build_settings_section(parent: ttk.Frame, gui) -> None:
    frame = create_card(parent, "", "Runtime Settings", "", {"fill": tk.X, "pady": (0, 10)})

    ttk.Label(frame, text="Device").grid(row=0, column=0, sticky=tk.W, pady=(4, 0))
    ttk.Combobox(frame, textvariable=gui.state.device, values=("cpu", "gpu"), state="readonly", width=10).grid(row=0, column=1, sticky=tk.EW, padx=(8, 16), pady=(4, 0))
    ttk.Label(frame, text="Threads").grid(row=0, column=2, sticky=tk.W, pady=(4, 0))
    ttk.Entry(frame, textvariable=gui.state.threads, width=8).grid(row=0, column=3, sticky=tk.W, padx=(8, 0), pady=(4, 0))
    
    ttk.Label(frame, text="Run on").grid(row=1, column=0, sticky=tk.W, pady=(10, 4))
    target_combo = ttk.Combobox(frame, textvariable=gui.state.run_target, values=("Local", "Server"), state="readonly", width=10)
    target_combo.grid(row=1, column=1, sticky=tk.EW, padx=(8, 16), pady=(10, 4))
    
    gui.state.run_target.trace_add("write", lambda *_args: gui._on_run_target_changed())
    frame.columnconfigure(1, weight=1)
    frame.columnconfigure(3, weight=1)

def _path_row(parent: ttk.Frame, label: str, variable: tk.StringVar, row: int, browse_cmd) -> None:
    container = ttk.Frame(parent)
    container.grid(row=row, column=0, columnspan=5, sticky=tk.EW, pady=3)
    ttk.Label(container, text=label).pack(anchor=tk.W, pady=(0, 2))
    input_frame = ttk.Frame(container)
    input_frame.pack(fill=tk.X, expand=True)
    ttk.Entry(input_frame, textvariable=variable).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    ttk.Button(input_frame, text="Browse", style="Accent.TButton", command=browse_cmd).pack(side=tk.RIGHT)

def _build_remote_section(parent: ttk.Frame, gui) -> None:
    frame = create_card(parent, "", "Remote Server", "", {"fill": tk.X, "pady": (0, 10)})
    gui.remote_frame = frame
    gui.remote_body = frame

    ttk.Label(frame, text="Host/IP").grid(row=0, column=0, sticky=tk.W, pady=3)
    ttk.Entry(frame, textvariable=gui.state.remote_host).grid(row=0, column=1, sticky=tk.EW, padx=(8, 16), pady=3)
    ttk.Label(frame, text="Port").grid(row=0, column=2, sticky=tk.W, pady=3)
    ttk.Entry(frame, textvariable=gui.state.remote_port, width=8).grid(row=0, column=3, sticky=tk.W, padx=(8, 0), pady=3)

    ttk.Label(frame, text="Username").grid(row=1, column=0, sticky=tk.W, pady=3)
    ttk.Entry(frame, textvariable=gui.state.remote_username).grid(row=1, column=1, sticky=tk.EW, padx=(8, 16), pady=3)
    ttk.Label(frame, text="Password").grid(row=1, column=2, sticky=tk.W, pady=3)
    ttk.Entry(frame, textvariable=gui.state.remote_password, show="*").grid(row=1, column=3, sticky=tk.EW, padx=(8, 0), pady=3)

    ssh_row = ttk.Frame(frame)
    ssh_row.grid(row=2, column=0, columnspan=4, sticky=tk.EW, pady=3)
    ttk.Label(ssh_row, text="SSH Key").pack(anchor=tk.W, pady=(0, 2))
    input_frame = ttk.Frame(ssh_row)
    input_frame.pack(fill=tk.X, expand=True)
    ttk.Entry(input_frame, textvariable=gui.state.remote_key_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    ttk.Button(input_frame, text="Browse", style="Accent.TButton", command=gui._browse_remote_key).pack(side=tk.RIGHT)

    ttk.Label(frame, text="Workspace").grid(row=3, column=0, sticky=tk.W, pady=3)
    ttk.Entry(frame, textvariable=gui.state.remote_workspace).grid(row=3, column=1, sticky=tk.EW, padx=(8, 16), pady=3)
    ttk.Label(frame, text="Python").grid(row=3, column=2, sticky=tk.W, pady=3)
    ttk.Entry(frame, textvariable=gui.state.remote_python).grid(row=3, column=3, sticky=tk.EW, padx=(8, 0), pady=3)

    buttons = ttk.Frame(frame)
    buttons.grid(row=4, column=0, columnspan=4, sticky=tk.EW, pady=(8, 0))
    ttk.Button(buttons, text="Test SSH", style="Accent.TButton", command=gui._remote_test_ssh).pack(side=tk.LEFT)

    gui.remote_status_label = ttk.Label(frame, textvariable=gui.state.remote_status)
    gui.remote_status_label.grid(row=5, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))

    frame.columnconfigure(1, weight=1)
    frame.columnconfigure(3, weight=1)
