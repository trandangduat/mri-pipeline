import tkinter as tk
from tkinter import ttk
from ui.components.cards import create_card
from ui.components.tooltip import Tooltip
from pipeline_runner import ATLAS_DEFS, EXPORT_OUTPUT_ITEMS, STAT_VECTOR_DEFS, STAGE_ORDER, STAGE_LABELS, enabled_tools_for_stage, tool_display_name

PANEL_BG = "#ffffff"
PANEL_BORDER = "#e5e7eb"


def _rounded_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs) -> None:
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    canvas.create_polygon(points, smooth=True, splinesteps=12, **kwargs)


def _rounded_panel(parent: tk.Widget, row: int, pady=0, radius: int = 12, padding: tuple[int, int] = (0, 0)) -> tk.Frame:
    canvas = tk.Canvas(parent, bg="#fafafa", highlightthickness=0, bd=0)
    canvas.grid(row=row, column=0, sticky=tk.EW, pady=pady)
    body = tk.Frame(canvas, bg=PANEL_BG, padx=padding[0], pady=padding[1])
    window_id = canvas.create_window((1, 1), window=body, anchor=tk.NW)

    def redraw(_event=None) -> None:
        width = max(canvas.winfo_width(), body.winfo_reqwidth() + 2)
        height = max(body.winfo_reqheight() + 2, 2)
        canvas.configure(height=height)
        canvas.delete("panel")
        _rounded_rect(canvas, 0, 0, width - 1, height - 1, radius, fill=PANEL_BG, outline=PANEL_BORDER, width=1, tags="panel")
        canvas.tag_lower("panel")
        canvas.itemconfigure(window_id, width=max(width - 2, 1), height=max(height - 2, 1))

    canvas.bind("<Configure>", redraw)
    body.bind("<Configure>", lambda _event: canvas.after_idle(redraw))
    return body

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
    
    gui._on_run_target_changed()

def _build_tools_section(parent: ttk.Frame, gui) -> None:
    frame = create_card(parent, "01", "Pipeline Tools", "Nine-step MRI processing pipeline", {"fill": tk.BOTH, "expand": True})
    frame.columnconfigure(0, weight=1)

    mode_row = ttk.Frame(frame)
    mode_row.grid(row=0, column=0, sticky=tk.EW, pady=(0, 16))
    mode_row.columnconfigure(1, weight=1)
    ttk.Label(mode_row, text="Preset").grid(row=0, column=0, sticky=tk.W, padx=(0, 12))
    ttk.Combobox(
        mode_row, textvariable=gui.state.pipeline_mode,
        values=getattr(gui, "PIPELINE_MODES", ("Custom",)),
        state="readonly",
        width=34,
    ).grid(row=0, column=1, sticky=tk.EW, padx=(0, 12))
    ttk.Button(mode_row, text="Load preset", style="Accent.TButton", command=gui._load_run_config).grid(row=0, column=2, sticky=tk.E, padx=(0, 8))
    ttk.Button(mode_row, text="Save preset", command=gui._save_run_config).grid(row=0, column=3, sticky=tk.E, padx=(0, 8))
    ttk.Button(
        mode_row,
        textvariable=gui.pipeline_tools_toggle_text,
        command=gui._toggle_pipeline_tools,
    ).grid(row=0, column=4, sticky=tk.E)

    gui.tool_combos = getattr(gui, "tool_combos", {})
    gui.tool_status_labels = getattr(gui, "tool_status_labels", {})
    gui.pipeline_tools_body = ttk.Frame(frame)
    gui.pipeline_tools_body.grid(row=1, column=0, sticky=tk.EW, pady=(0, 14))
    gui.pipeline_tools_body.columnconfigure(0, weight=1)

    tools_table = _rounded_panel(gui.pipeline_tools_body, row=0, radius=12)
    tools_table.columnconfigure(0, weight=3, minsize=220)
    tools_table.columnconfigure(1, weight=2, minsize=250)
    tools_table.columnconfigure(2, weight=0, minsize=135)
    tools_table.rowconfigure(0, minsize=42)

    tk.Label(tools_table, text="Step", bg=PANEL_BG, fg="#64748b", font=("Inter", 9, "bold"), anchor=tk.W).grid(row=0, column=0, sticky=tk.EW, padx=(14, 10))
    tk.Label(tools_table, text="Tool", bg=PANEL_BG, fg="#64748b", font=("Inter", 9, "bold"), anchor=tk.W).grid(row=0, column=1, sticky=tk.EW, padx=(10, 10))
    tk.Label(tools_table, text="Status", bg=PANEL_BG, fg="#64748b", font=("Inter", 9, "bold"), anchor=tk.W).grid(row=0, column=2, sticky=tk.EW, padx=(10, 14))
    tk.Frame(tools_table, bg=PANEL_BORDER, height=1).grid(row=1, column=0, columnspan=3, sticky=tk.EW)

    for idx, stage in enumerate(STAGE_ORDER):
        row = 2 + idx * 2
        tools = enabled_tools_for_stage(stage)
        tool_labels = [tool_display_name(tool) for tool in tools]
        var = gui.state.tool_vars[stage]

        tools_table.rowconfigure(row, minsize=46)
        tk.Label(
            tools_table,
            text=f"{idx + 1}. {STAGE_LABELS.get(stage, stage)}",
            bg=PANEL_BG,
            fg="#111827",
            font=("Inter", 10),
            anchor=tk.W,
        ).grid(row=row, column=0, sticky=tk.EW, padx=(14, 10))

        combo = ttk.Combobox(tools_table, textvariable=var, values=tool_labels, state="readonly", width=30)
        combo.grid(row=row, column=1, sticky=tk.EW, padx=(10, 10))
        gui.tool_combos[stage] = combo
        status = tk.Label(tools_table, text="Not checked", bg=PANEL_BG, fg="#64748b", font=("Inter", 10), anchor=tk.W)
        status.grid(row=row, column=2, sticky=tk.EW, padx=(10, 14))
        gui.tool_status_labels[stage] = status
        if idx < len(STAGE_ORDER) - 1:
            tk.Frame(tools_table, bg=PANEL_BORDER, height=1).grid(row=row + 1, column=0, columnspan=3, sticky=tk.EW)

    stats_row = 2

    stats_frame = _rounded_panel(frame, row=stats_row, pady=(0, 14), radius=12, padding=(12, 10))
    stats_frame.columnconfigure(1, weight=1)
    tk.Label(stats_frame, text="Stats vectors", bg=PANEL_BG, fg="#111827", font=("Inter", 10, "bold"), anchor=tk.W).grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 8))

    gui.stat_vector_checkbuttons = getattr(gui, "stat_vector_checkbuttons", {})
    gui.stat_atlas_combos = getattr(gui, "stat_atlas_combos", {})
    stat_option_widgets: dict[str, ttk.Combobox] = {}

    def sync_stats_options(*_args) -> None:
        for stat, atlas_combo in stat_option_widgets.items():
            choice_var = gui.state.stat_atlas_choice_vars.get(stat)
            if choice_var is not None and not choice_var.get():
                first_atlas = next(iter(gui.state.stat_atlas_vars[stat]), "")
                if first_atlas:
                    gui.state.set_stat_atlas_choice(stat, first_atlas)
            atlas_combo.configure(state="readonly" if gui.state.stat_vector_enabled_vars[stat].get() else tk.DISABLED)

    for idx, (stat, stat_def) in enumerate(STAT_VECTOR_DEFS.items()):
        row = idx + 1
        check = ttk.Checkbutton(
            stats_frame,
            text=stat_def["label"],
            variable=gui.state.stat_vector_enabled_vars[stat],
            command=sync_stats_options,
        )
        check.grid(row=row, column=0, sticky=tk.W, padx=(6, 18), pady=4)
        gui.stat_vector_checkbuttons[stat] = check

        atlas_values = [ATLAS_DEFS[atlas] for atlas in stat_def.get("atlases", ()) if atlas in ATLAS_DEFS]
        if atlas_values:
            combo = ttk.Combobox(
                stats_frame,
                textvariable=gui.state.stat_atlas_choice_vars[stat],
                values=atlas_values,
                state="readonly",
                width=28,
            )
            combo.grid(row=row, column=1, sticky=tk.EW, padx=(10, 6), pady=4)
            stat_option_widgets[stat] = combo
            gui.stat_atlas_combos[stat] = combo
            first_atlas = next((atlas for atlas in stat_def.get("atlases", ()) if atlas in ATLAS_DEFS), "")
            if first_atlas:
                gui.state.set_stat_atlas_choice(stat, first_atlas)
        gui.state.stat_vector_enabled_vars[stat].trace_add("write", sync_stats_options)
    sync_stats_options()

    lic_row = ttk.Frame(frame)
    lic_row.grid(row=stats_row + 1, column=0, sticky=tk.EW, pady=(0, 5))
    ttk.Label(lic_row, text="FreeSurfer license").pack(anchor=tk.W, pady=(0, 2))
    input_frame = ttk.Frame(lic_row)
    input_frame.pack(fill=tk.X, expand=True)
    ttk.Entry(input_frame, textvariable=gui.state.license_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    ttk.Button(input_frame, text="Browse", style="Accent.TButton", command=lambda: gui._browse_directory(gui.state.license_dir)).pack(side=tk.RIGHT)

    gui.state.pipeline_mode.trace_add("write", lambda *_args: gui._apply_pipeline_mode())
    gui._apply_pipeline_mode(show_custom_tools=False)
    gui._update_config_tool_status_labels()

def _build_input_section(parent: ttk.Frame, gui) -> None:
    frame = create_card(parent, "", "Input & output", "", {"fill": tk.X, "pady": (0, 18)})

    mode_row = ttk.Frame(frame)
    mode_row.grid(row=0, column=0, columnspan=5, sticky=tk.EW, pady=(0, 10))
    ttk.Radiobutton(mode_row, text="Single file", variable=gui.state.input_mode, value="file", command=gui._refresh_input_label).pack(side=tk.LEFT)
    ttk.Radiobutton(mode_row, text="Multiple files", variable=gui.state.input_mode, value="files", command=gui._refresh_input_label).pack(side=tk.LEFT, padx=(14, 0))
    ttk.Radiobutton(mode_row, text="Batch folder", variable=gui.state.input_mode, value="dir", command=gui._refresh_input_label).pack(side=tk.LEFT, padx=(14, 0))

    gui.input_source_row = ttk.Frame(frame)
    gui.input_source_row.grid(row=1, column=0, columnspan=5, sticky=tk.EW, pady=(0, 8))
    ttk.Label(gui.input_source_row, text="Input Source:").pack(side=tk.LEFT, padx=(0, 14))
    gui.input_source_local_rb = ttk.Radiobutton(gui.input_source_row, text="Local Data", variable=gui.state.input_source, value="Local", command=lambda: gui._switch_input_source("Local"))
    gui.input_source_local_rb.pack(side=tk.LEFT)
    gui.input_source_server_rb = ttk.Radiobutton(gui.input_source_row, text="Server Data", variable=gui.state.input_source, value="Server", command=lambda: gui._switch_input_source("Server"))
    gui.input_source_server_rb.pack(side=tk.LEFT, padx=(14, 0))

    gui.upload_input_row = ttk.Frame(frame)
    gui.upload_input_row.grid(row=2, column=0, columnspan=5, sticky=tk.EW, pady=(0, 8))
    upload_options = {"text": "Upload input to server", "command": gui._upload_input_to_server_placeholder}
    upload_icon = gui._make_icon("load") if hasattr(gui, "_make_icon") else None
    if upload_icon is not None:
        upload_options.update({"image": upload_icon, "compound": tk.LEFT})
    gui.upload_input_button = ttk.Button(gui.upload_input_row, **upload_options)
    gui.upload_input_button.pack(side=tk.LEFT)
    gui.upload_input_tooltip = Tooltip(gui.upload_input_button, "Standard Upload: Sync all local files to the server before running.\nFor Lazy Upload (upload & process simultaneously), just click 'Run'.")

    container = ttk.Frame(frame)
    container.grid(row=3, column=0, columnspan=5, sticky=tk.EW, pady=3)
    ttk.Label(container, textvariable=gui.input_location_label_var).pack(anchor=tk.W, pady=(0, 2))

    input_frame = ttk.Frame(container)
    input_frame.pack(fill=tk.X, expand=True)
    ttk.Entry(input_frame, textvariable=gui.state.input_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

    gui.file_count_label = ttk.Label(input_frame, text="")
    gui.file_count_label.pack(side=tk.LEFT, padx=(0, 8))

    gui.btn_config_batch = ttk.Button(input_frame, text="Configure Batch", command=gui._configure_batch, state=tk.DISABLED)
    gui.btn_config_batch.pack(side=tk.LEFT, padx=(0, 8))

    gui.input_browse_button = ttk.Button(input_frame, text="Browse", style="Accent.TButton", command=gui._browse_input)
    gui.input_browse_button.pack(side=tk.RIGHT)
    gui.input_browse_tooltip = Tooltip(gui.input_browse_button, "")

    ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=4, column=0, columnspan=5, sticky=tk.EW, pady=10)

    gui.output_dir_row = _path_row(frame, "Output Location", gui.state.output_dir, 5, lambda: gui._browse_directory(gui.state.output_dir))

    gui.server_output_dir_row = ttk.Frame(frame)
    gui.server_output_dir_row.grid(row=6, column=0, columnspan=5, sticky=tk.EW, pady=3)
    ttk.Label(gui.server_output_dir_row, text="Server Output Location").pack(anchor=tk.W, pady=(0, 2))
    server_input_frame = ttk.Frame(gui.server_output_dir_row)
    server_input_frame.pack(fill=tk.X, expand=True)
    ttk.Entry(server_input_frame, textvariable=gui.state.server_output_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    gui.server_output_browse_button = ttk.Button(server_input_frame, text="Browse Server", style="Accent.TButton", command=gui._browse_server_output)
    gui.server_output_browse_button.pack(side=tk.RIGHT)
    gui.server_output_tooltip = Tooltip(gui.server_output_browse_button, "")

    export_frame = ttk.Frame(frame)
    export_frame.grid(row=7, column=0, columnspan=5, sticky=tk.EW, pady=(10, 0))
    export_frame.columnconfigure(1, weight=1)

    gui.export_toggle_text = tk.StringVar(value="▼ Hide custom outputs" if gui.state.export_outputs_enabled.get() else "▶ Custom output files")

    def sync_export_options(*_args) -> None:
        if gui.state.export_outputs_enabled.get():
            options.grid(row=1, column=0, columnspan=3, sticky=tk.EW, padx=0, pady=(2, 0))
            gui.export_toggle_text.set("▼ Hide custom outputs")
        else:
            options.grid_remove()
            gui.export_toggle_text.set("▶ Custom output files")

    def toggle_export() -> None:
        current = gui.state.export_outputs_enabled.get()
        gui.state.export_outputs_enabled.set(not current)
        sync_export_options()

    ttk.Button(export_frame, textvariable=gui.export_toggle_text, command=toggle_export).grid(row=0, column=0, sticky=tk.W, pady=(0, 2))

    options = ttk.Frame(export_frame)
    options.columnconfigure(1, weight=1)
    ttk.Label(options, text="Output extension").grid(row=0, column=0, sticky=tk.W, padx=8, pady=(8, 3))
    ttk.Combobox(options, textvariable=gui.state.export_default_format, values=(".mgz", ".nii.gz"), state="readonly", width=10).grid(row=0, column=1, sticky=tk.W, padx=8, pady=(8, 3))
    ttk.Label(options, text="Output", font=("Inter", 9, "bold")).grid(row=1, column=0, sticky=tk.W, padx=8, pady=(8, 3))
    ttk.Label(options, text="File name", font=("Inter", 9, "bold")).grid(row=1, column=1, sticky=tk.W, padx=8, pady=(8, 3))
    for idx, (item_id, item) in enumerate(EXPORT_OUTPUT_ITEMS.items(), start=2):
        ttk.Label(options, text=item["label"]).grid(row=idx, column=0, sticky=tk.W, padx=8, pady=2)
        ttk.Entry(options, textvariable=gui.state.export_name_vars[item_id]).grid(row=idx, column=1, sticky=tk.EW, padx=8, pady=2)
    gui.state.export_outputs_enabled.trace_add("write", sync_export_options)
    sync_export_options()
    gui._sync_input_source_controls()

    frame.columnconfigure(1, weight=1)

def _build_settings_section(parent: ttk.Frame, gui) -> None:
    frame = create_card(parent, "", "Runtime Settings", "", {"fill": tk.X, "pady": (0, 18)})

    ttk.Label(frame, text="Run on", width=10).grid(row=0, column=0, sticky=tk.W, pady=(4, 0))
    gui.run_target_combo = ttk.Combobox(frame, textvariable=gui.state.run_target, values=("Local", "Server"), state="readonly", width=10)
    gui.run_target_combo.grid(row=0, column=1, sticky=tk.EW, padx=(8, 0), pady=(4, 0))

    ttk.Label(frame, text="Device", width=10).grid(row=1, column=0, sticky=tk.W, pady=(10, 0))
    ttk.Combobox(frame, textvariable=gui.state.device, values=("cpu", "gpu"), state="readonly", width=10).grid(row=1, column=1, sticky=tk.EW, padx=(8, 0), pady=(10, 0))

    ttk.Label(frame, text="Threads", width=10).grid(row=2, column=0, sticky=tk.W, pady=(10, 4))
    thread_row = ttk.Frame(frame)
    thread_row.grid(row=2, column=1, sticky=tk.W, padx=(8, 0), pady=(10, 4))
    thread_vcmd = (gui.root.register(gui._validate_thread_input), "%P")
    gui.thread_spinbox = ttk.Spinbox(
        thread_row,
        from_=1,
        to=gui.max_threads or 9999,
        textvariable=gui.state.threads,
        width=8,
        validate="key",
        validatecommand=thread_vcmd,
    )
    gui.thread_spinbox.pack(side=tk.LEFT)
    ttk.Label(thread_row, textvariable=gui.thread_max_text, foreground="#64748b").pack(side=tk.LEFT, padx=(8, 0))

    gui.state.run_target.trace_add("write", lambda *_args: gui._on_run_target_changed())
    frame.columnconfigure(1, weight=1)

def _path_row(parent: ttk.Frame, label: str, variable: tk.StringVar, row: int, browse_cmd) -> ttk.Frame:
    container = ttk.Frame(parent)
    container.grid(row=row, column=0, columnspan=5, sticky=tk.EW, pady=3)
    ttk.Label(container, text=label).pack(anchor=tk.W, pady=(0, 2))
    input_frame = ttk.Frame(container)
    input_frame.pack(fill=tk.X, expand=True)
    ttk.Entry(input_frame, textvariable=variable).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    ttk.Button(input_frame, text="Browse", style="Accent.TButton", command=browse_cmd).pack(side=tk.RIGHT)
    return container

def _build_remote_section(parent: ttk.Frame, gui) -> None:
    gui.remote_pack_options = {"fill": tk.X, "pady": (0, 18)}
    frame = create_card(parent, "", "Remote Server", "", gui.remote_pack_options)
    gui.remote_frame = frame
    gui.remote_body = frame

    ttk.Label(frame, text="Host/IP", width=10).grid(row=0, column=0, sticky=tk.W, pady=4)
    gui.remote_host_entry = ttk.Entry(frame, textvariable=gui.state.remote_host)
    gui.remote_host_entry.grid(row=0, column=1, sticky=tk.EW, padx=(8, 16), pady=3)
    ttk.Label(frame, text="Port", width=8).grid(row=0, column=2, sticky=tk.W, pady=4)
    gui.remote_port_entry = ttk.Entry(frame, textvariable=gui.state.remote_port, width=8)
    gui.remote_port_entry.grid(row=0, column=3, sticky=tk.EW, padx=(8, 0), pady=3)

    ttk.Label(frame, text="Username", width=10).grid(row=1, column=0, sticky=tk.W, pady=4)
    gui.remote_username_entry = ttk.Entry(frame, textvariable=gui.state.remote_username)
    gui.remote_username_entry.grid(row=1, column=1, sticky=tk.EW, padx=(8, 16), pady=3)
    ttk.Label(frame, text="Password", width=8).grid(row=1, column=2, sticky=tk.W, pady=4)
    gui.remote_password_entry = ttk.Entry(frame, textvariable=gui.state.remote_password, show="*")
    gui.remote_password_entry.grid(row=1, column=3, sticky=tk.EW, padx=(8, 0), pady=3)

    ttk.Label(frame, text="SSH Key", width=10).grid(row=2, column=0, sticky=tk.W, pady=4)
    gui.remote_key_entry = ttk.Entry(frame, textvariable=gui.state.remote_key_path)
    gui.remote_key_entry.grid(row=2, column=1, columnspan=2, sticky=tk.EW, padx=(8, 8), pady=3)
    gui.remote_key_browse_button = ttk.Button(frame, text="Browse", style="Accent.TButton", command=gui._browse_remote_key)
    gui.remote_key_browse_button.grid(row=2, column=3, sticky=tk.EW, padx=(0, 0), pady=3)

    ttk.Label(frame, text="Workspace", width=10).grid(row=3, column=0, sticky=tk.W, pady=4)
    gui.remote_workspace_entry = ttk.Entry(frame, textvariable=gui.state.remote_workspace)
    gui.remote_workspace_entry.grid(row=3, column=1, columnspan=3, sticky=tk.EW, padx=(8, 0), pady=3)

    buttons = ttk.Frame(frame)
    buttons.grid(row=4, column=0, columnspan=4, sticky=tk.EW, pady=(8, 0))
    gui.remote_connect_button = ttk.Button(buttons, text="Connect Server", style="Accent.TButton", command=gui._remote_test_ssh)
    gui.remote_connect_button.pack(side=tk.LEFT)
    gui.remote_status_icon_label = ttk.Label(buttons)
    gui.remote_status_icon_label.pack(side=tk.LEFT, padx=(12, 6))
    if hasattr(gui, "_set_remote_status_icon"):
        gui._set_remote_status_icon("pending")
    gui.remote_status_label = ttk.Label(buttons, textvariable=gui.state.remote_status)
    gui.remote_status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    frame.columnconfigure(1, weight=1)
    frame.columnconfigure(3, weight=1)
