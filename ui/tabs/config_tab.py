import tkinter as tk
from tkinter import ttk
from ui.components.cards import create_card
from pipeline_runner import ATLAS_DEFS, EXPORT_OUTPUT_ITEMS, STAT_VECTOR_DEFS, STAGE_ORDER, STAGE_LABELS, enabled_tools_for_stage, tool_display_name

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

    mode_row = ttk.Frame(frame)
    mode_row.grid(row=0, column=0, columnspan=3, sticky=tk.EW, pady=(0, 12))
    ttk.Button(mode_row, text="Save preset", command=gui._save_run_config).pack(side=tk.RIGHT, padx=(8, 0))
    ttk.Button(mode_row, text="Load preset", style="Accent.TButton", command=gui._load_run_config).pack(side=tk.RIGHT)
    ttk.Label(mode_row, text="Preset").pack(side=tk.LEFT)
    ttk.Combobox(
        mode_row, textvariable=gui.state.pipeline_mode,
        values=getattr(gui, "PIPELINE_MODES", ("Custom",)),
        state="readonly",
        width=56,
    ).pack(side=tk.LEFT, padx=(8, 12))

    tools_toggle_row = ttk.Frame(frame)
    tools_toggle_row.grid(row=1, column=0, columnspan=3, sticky=tk.EW, pady=(0, 8))
    ttk.Button(
        tools_toggle_row,
        textvariable=gui.pipeline_tools_toggle_text,
        command=gui._toggle_pipeline_tools,
    ).pack(side=tk.LEFT)

    gui.tool_combos = getattr(gui, "tool_combos", {})
    gui.tool_status_labels = getattr(gui, "tool_status_labels", {})
    gui.pipeline_tools_body = ttk.Frame(frame)
    gui.pipeline_tools_body.grid(row=2, column=0, columnspan=3, sticky=tk.EW)
    gui.pipeline_tools_body.columnconfigure(0, weight=1)
    gui.pipeline_tools_body.columnconfigure(1, weight=1)
    gui.pipeline_tools_body.columnconfigure(2, weight=0)

    for idx, stage in enumerate(STAGE_ORDER):
        row = idx
        tools = enabled_tools_for_stage(stage)
        tool_labels = [tool_display_name(tool) for tool in tools]
        var = gui.state.tool_vars[stage]

        step = ttk.Frame(gui.pipeline_tools_body)
        step.grid(row=row, column=0, sticky=tk.EW, pady=5)


        ttk.Label(
            step,
            text=f"{idx + 1}. {STAGE_LABELS.get(stage, stage)}",
            width=32,
            anchor=tk.W,
        ).pack(side=tk.LEFT)

        combo = ttk.Combobox(gui.pipeline_tools_body, textvariable=var, values=tool_labels, state="readonly", width=28)
        combo.grid(row=row, column=1, sticky=tk.EW, padx=(6, 0), pady=5)
        gui.tool_combos[stage] = combo
        status = ttk.Label(gui.pipeline_tools_body, text="Not checked", width=10, anchor=tk.W, foreground="#64748b")
        status.grid(row=row, column=2, sticky=tk.W, padx=(2, 0), pady=5)
        gui.tool_status_labels[stage] = status

    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)
    frame.columnconfigure(2, weight=0)

    stats_row = 3

    stats_frame = ttk.Frame(frame)
    stats_frame.grid(row=stats_row, column=0, columnspan=3, sticky=tk.EW, pady=(8, 10))
    stats_frame.columnconfigure(1, weight=1)
    ttk.Label(stats_frame, text="Stats vectors").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))

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
        check.grid(row=row, column=0, sticky=tk.W, padx=(8, 10), pady=3)
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
            combo.grid(row=row, column=1, sticky=tk.EW, padx=(10, 0), pady=3)
            stat_option_widgets[stat] = combo
            gui.stat_atlas_combos[stat] = combo
            first_atlas = next((atlas for atlas in stat_def.get("atlases", ()) if atlas in ATLAS_DEFS), "")
            if first_atlas:
                gui.state.set_stat_atlas_choice(stat, first_atlas)
        gui.state.stat_vector_enabled_vars[stat].trace_add("write", sync_stats_options)
    sync_stats_options()

    lic_row = ttk.Frame(frame)
    lic_row.grid(row=stats_row + 1, column=0, columnspan=3, sticky=tk.EW, pady=(0, 5))
    ttk.Label(lic_row, text="FreeSurfer license").pack(anchor=tk.W, pady=(0, 2))
    input_frame = ttk.Frame(lic_row)
    input_frame.pack(fill=tk.X, expand=True)
    ttk.Entry(input_frame, textvariable=gui.state.license_dir).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
    ttk.Button(input_frame, text="Browse", style="Accent.TButton", command=lambda: gui._browse_directory(gui.state.license_dir)).pack(side=tk.RIGHT)

    gui.state.pipeline_mode.trace_add("write", lambda *_args: gui._apply_pipeline_mode())
    gui._apply_pipeline_mode(show_custom_tools=False)
    gui._update_config_tool_status_labels()

def _build_input_section(parent: ttk.Frame, gui) -> None:
    frame = create_card(parent, "", "Input & output", "", {"fill": tk.X, "pady": (0, 10)})

    mode_row = ttk.Frame(frame)
    mode_row.grid(row=0, column=0, columnspan=5, sticky=tk.EW, pady=(0, 10))
    ttk.Radiobutton(mode_row, text="Single file", variable=gui.state.input_mode, value="file", command=gui._refresh_input_label).pack(side=tk.LEFT)
    ttk.Radiobutton(mode_row, text="Multiple files", variable=gui.state.input_mode, value="files", command=gui._refresh_input_label).pack(side=tk.LEFT, padx=(14, 0))
    ttk.Radiobutton(mode_row, text="Batch folder", variable=gui.state.input_mode, value="dir", command=gui._refresh_input_label).pack(side=tk.LEFT, padx=(14, 0))

    gui.upload_input_row = ttk.Frame(frame)
    gui.upload_input_row.grid(row=1, column=0, columnspan=5, sticky=tk.EW, pady=(0, 8))
    upload_options = {"text": "Upload input to server", "command": gui._upload_input_to_server_placeholder}
    upload_icon = gui._make_icon("load") if hasattr(gui, "_make_icon") else None
    if upload_icon is not None:
        upload_options.update({"image": upload_icon, "compound": tk.LEFT})
    gui.upload_input_button = ttk.Button(gui.upload_input_row, **upload_options)
    gui.upload_input_button.pack(side=tk.LEFT)

    container = ttk.Frame(frame)
    container.grid(row=2, column=0, columnspan=5, sticky=tk.EW, pady=3)
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

    ttk.Separator(frame, orient=tk.HORIZONTAL).grid(row=3, column=0, columnspan=5, sticky=tk.EW, pady=10)

    gui.output_dir_row = _path_row(frame, "Output directory", gui.state.output_dir, 4, lambda: gui._browse_directory(gui.state.output_dir))

    export_frame = ttk.Frame(frame)
    export_frame.grid(row=5, column=0, columnspan=5, sticky=tk.EW, pady=(10, 0))
    export_frame.columnconfigure(1, weight=1)

    def sync_export_options(*_args) -> None:
        if gui.state.export_outputs_enabled.get():
            options.grid(row=1, column=0, columnspan=3, sticky=tk.EW, padx=0, pady=(2, 0))
        else:
            options.grid_remove()

    ttk.Checkbutton(export_frame, text="Custom output files", variable=gui.state.export_outputs_enabled, command=sync_export_options).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 2))

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
    frame = create_card(parent, "", "Runtime Settings", "", {"fill": tk.X, "pady": (0, 10)})

    ttk.Label(frame, text="Run on", width=10).grid(row=0, column=0, sticky=tk.W, pady=(4, 0))
    target_combo = ttk.Combobox(frame, textvariable=gui.state.run_target, values=("Local", "Server"), state="readonly", width=10)
    target_combo.grid(row=0, column=1, sticky=tk.EW, padx=(8, 0), pady=(4, 0))

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
    gui.remote_pack_options = {"fill": tk.X, "pady": (0, 10)}
    frame = create_card(parent, "", "Remote Server", "", gui.remote_pack_options)
    gui.remote_frame = frame
    gui.remote_body = frame

    ttk.Label(frame, text="Host/IP", width=10).grid(row=0, column=0, sticky=tk.W, pady=4)
    ttk.Entry(frame, textvariable=gui.state.remote_host).grid(row=0, column=1, sticky=tk.EW, padx=(8, 16), pady=3)
    ttk.Label(frame, text="Port", width=8).grid(row=0, column=2, sticky=tk.W, pady=4)
    ttk.Entry(frame, textvariable=gui.state.remote_port, width=8).grid(row=0, column=3, sticky=tk.EW, padx=(8, 0), pady=3)

    ttk.Label(frame, text="Username", width=10).grid(row=1, column=0, sticky=tk.W, pady=4)
    ttk.Entry(frame, textvariable=gui.state.remote_username).grid(row=1, column=1, sticky=tk.EW, padx=(8, 16), pady=3)
    ttk.Label(frame, text="Password", width=8).grid(row=1, column=2, sticky=tk.W, pady=4)
    ttk.Entry(frame, textvariable=gui.state.remote_password, show="*").grid(row=1, column=3, sticky=tk.EW, padx=(8, 0), pady=3)

    ttk.Label(frame, text="SSH Key", width=10).grid(row=2, column=0, sticky=tk.W, pady=4)
    ttk.Entry(frame, textvariable=gui.state.remote_key_path).grid(row=2, column=1, columnspan=2, sticky=tk.EW, padx=(8, 8), pady=3)
    ttk.Button(frame, text="Browse", style="Accent.TButton", command=gui._browse_remote_key).grid(row=2, column=3, sticky=tk.EW, padx=(0, 0), pady=3)

    ttk.Label(frame, text="Workspace", width=10).grid(row=3, column=0, sticky=tk.W, pady=4)
    ttk.Entry(frame, textvariable=gui.state.remote_workspace).grid(row=3, column=1, columnspan=3, sticky=tk.EW, padx=(8, 0), pady=3)

    buttons = ttk.Frame(frame)
    buttons.grid(row=4, column=0, columnspan=4, sticky=tk.EW, pady=(8, 0))
    ttk.Button(buttons, text="Test SSH", style="Accent.TButton", command=gui._remote_test_ssh).pack(side=tk.LEFT)
    gui.remote_status_icon_label = ttk.Label(buttons)
    gui.remote_status_icon_label.pack(side=tk.LEFT, padx=(12, 6))
    if hasattr(gui, "_set_remote_status_icon"):
        gui._set_remote_status_icon("pending")
    gui.remote_status_label = ttk.Label(buttons, textvariable=gui.state.remote_status)
    gui.remote_status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    frame.columnconfigure(1, weight=1)
    frame.columnconfigure(3, weight=1)
