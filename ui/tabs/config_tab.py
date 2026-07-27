from __future__ import annotations

import tkinter as tk
from difflib import SequenceMatcher
from tkinter import ttk
from ui.components.cards import create_card
from ui.components.tooltip import Tooltip
from pipeline.config import ATLAS_DEFS, EXPORT_OUTPUT_ITEMS, STAT_VECTOR_DEFS
from pipeline.registry import STAGE_ORDER, STAGE_LABELS, enabled_tools_for_stage, tool_display_name
from pipeline.presets import PIPELINE_MODES

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


def _enable_combobox_type_search(combo: ttk.Combobox, gui) -> None:
    all_values = [str(value) for value in combo.cget("values")]
    popdown_listbox = ""
    popdown_query = ""
    popdown_reset_after: str | None = None

    def tokens(value: str) -> list[str]:
        normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
        return [part for part in normalized.split() if part]

    def compact(value: str) -> str:
        return "".join(tokens(value))

    def fuzzy_score(query: str, value: str) -> float:
        query_tokens = tokens(query)
        if not query_tokens:
            return 1.0
        value_tokens = tokens(value)
        value_compact = compact(value)
        score = 0.0
        for query_token in query_tokens:
            token_scores = []
            for value_token in value_tokens:
                if value_token == query_token:
                    token_scores.append(4.0)
                elif value_token.startswith(query_token):
                    token_scores.append(3.0)
                elif query_token in value_token:
                    token_scores.append(2.0)
                else:
                    token_scores.append(SequenceMatcher(None, query_token, value_token).ratio())
            if query_token in value_compact:
                token_scores.append(2.5)
            best = max(token_scores, default=0.0)
            if best < 0.55:
                return 0.0
            score += best
        return score + SequenceMatcher(None, compact(query), value_compact).ratio()

    def ranked_values(query: str) -> list[str]:
        query = query.strip()
        if not query:
            return all_values
        scored = [(fuzzy_score(query, value), idx, value) for idx, value in enumerate(all_values)]
        matches = [(score, idx, value) for score, idx, value in scored if score > 0]
        matches.sort(key=lambda item: (-item[0], item[1]))
        return [value for _score, _idx, value in matches]

    def update_popdown_values(values: list[str]) -> None:
        if not popdown_listbox:
            return
        try:
            combo.tk.call(popdown_listbox, "delete", 0, "end")
            for value in values:
                combo.tk.call(popdown_listbox, "insert", "end", value)
        except tk.TclError:
            pass

    def refresh_values(query: str) -> list[str]:
        matches = ranked_values(query)
        values = matches or all_values
        combo.configure(values=values)
        update_popdown_values(values)
        return matches

    def select_first_match() -> None:
        current = combo.get().strip()
        if current in all_values:
            combo.configure(values=all_values)
            return
        matches = ranked_values(current)
        if matches:
            combo.set(matches[0])
        combo.configure(values=all_values)

    def select_entry_text() -> None:
        try:
            combo.selection_range(0, tk.END)
            combo.icursor(tk.END)
        except tk.TclError:
            pass

    def on_focus_in(_event: tk.Event) -> None:
        combo.configure(values=all_values)
        combo.after_idle(select_entry_text)

    def on_keyrelease(event: tk.Event) -> None:
        if event.keysym in {"Return", "Tab", "Escape", "Up", "Down", "Left", "Right"}:
            return
        refresh_values(combo.get())

    def on_return(_event: tk.Event) -> str:
        select_first_match()
        return "break"

    def reset_popdown_query() -> None:
        nonlocal popdown_query, popdown_reset_after
        popdown_query = ""
        popdown_reset_after = None

    def highlight_popdown(index: int) -> None:
        if index < 0 or not popdown_listbox:
            return
        try:
            combo.tk.call(popdown_listbox, "selection", "clear", 0, "end")
            combo.tk.call(popdown_listbox, "selection", "set", index)
            combo.tk.call(popdown_listbox, "activate", index)
            combo.tk.call(popdown_listbox, "see", index)
        except tk.TclError:
            pass

    def on_popdown_keypress(keysym: str, char: str) -> str:
        nonlocal popdown_query, popdown_reset_after
        if keysym in {"Escape", "Return", "Tab", "Up", "Down"}:
            return ""
        if keysym in {"BackSpace", "Delete"}:
            popdown_query = popdown_query[:-1]
        elif char and char.isprintable():
            popdown_query += char
        else:
            return ""
        matches = refresh_values(popdown_query)
        combo.set(popdown_query)
        if matches:
            highlight_popdown(0)
        if popdown_reset_after is not None:
            combo.after_cancel(popdown_reset_after)
        popdown_reset_after = combo.after(1500, reset_popdown_query)
        return "break"

    popdown_keypress_cmd = combo.register(on_popdown_keypress)

    def bind_popdown_listbox() -> None:
        nonlocal popdown_listbox
        reset_popdown_query()
        combo.configure(values=all_values)
        try:
            popdown = combo.tk.call("ttk::combobox::PopdownWindow", str(combo))
            popdown_listbox = f"{popdown}.f.l"
            script = f'if {{[{popdown_keypress_cmd} %K {{%A}}] eq "break"}} break'
            combo.tk.call("bind", popdown_listbox, "<KeyPress>", script)
        except tk.TclError:
            popdown_listbox = ""

    combo.bind("<FocusIn>", on_focus_in, add="+")
    combo.bind("<KeyRelease>", on_keyrelease, add="+")
    combo.bind("<Return>", on_return, add="+")
    combo.bind("<FocusOut>", lambda _event: select_first_match(), add="+")
    combo.bind("<<ComboboxSelected>>", lambda _event: combo.configure(values=all_values), add="+")
    combo.configure(postcommand=bind_popdown_listbox)

def build_configuration_tab(parent: ttk.Frame, gui) -> None:
    parent.rowconfigure(0, weight=1)
    parent.columnconfigure(0, weight=1)

    panes = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
    panes.grid(row=0, column=0, sticky=tk.NSEW, padx=8, pady=8)

    left_outer, left = _scrollable_column(panes)
    right_outer, right = _scrollable_column(panes)
    panes.add(left_outer, weight=1)
    panes.add(right_outer, weight=1)

    _build_tools_section(left, gui)
    _build_input_section(right, gui)
    _build_settings_section(right, gui)
    _build_remote_section(right, gui)

    gui._on_run_target_changed()


def _scrollable_column(parent: ttk.PanedWindow) -> tuple[ttk.Frame, ttk.Frame]:
    outer = ttk.Frame(parent)
    outer.rowconfigure(0, weight=1)
    outer.columnconfigure(0, weight=1)

    canvas = tk.Canvas(outer, highlightthickness=0)
    scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
    scroll_frame = ttk.Frame(canvas, padding=8)
    window_id = canvas.create_window((0, 0), window=scroll_frame, anchor=tk.NW)
    is_scrollable = False

    def update_scrollbar_visibility() -> None:
        nonlocal is_scrollable
        bbox = canvas.bbox("all")
        content_height = bbox[3] - bbox[1] if bbox else 0
        is_scrollable = content_height > canvas.winfo_height() + 1
        if is_scrollable:
            scrollbar.grid(row=0, column=1, sticky=tk.NS)
        else:
            canvas.yview_moveto(0)
            scrollbar.grid_remove()

    def sync_scroll_region(_event=None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.after_idle(update_scrollbar_visibility)

    def sync_window_width(event: tk.Event) -> None:
        canvas.itemconfigure(window_id, width=event.width)
        canvas.after_idle(update_scrollbar_visibility)

    def on_mousewheel(event: tk.Event) -> str:
        if not is_scrollable:
            return ""
        if event.num == 4:
            canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            canvas.yview_scroll(3, "units")
        else:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    def bind_mousewheel(_event=None) -> None:
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        canvas.bind_all("<Button-4>", on_mousewheel)
        canvas.bind_all("<Button-5>", on_mousewheel)

    def unbind_mousewheel(_event=None) -> None:
        canvas.unbind_all("<MouseWheel>")
        canvas.unbind_all("<Button-4>")
        canvas.unbind_all("<Button-5>")

    scroll_frame.bind("<Configure>", sync_scroll_region)
    canvas.bind("<Configure>", sync_window_width)
    canvas.bind("<MouseWheel>", on_mousewheel)
    canvas.bind("<Button-4>", on_mousewheel)
    canvas.bind("<Button-5>", on_mousewheel)
    canvas.bind("<Enter>", bind_mousewheel)
    canvas.bind("<Leave>", unbind_mousewheel)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.grid(row=0, column=0, sticky=tk.NSEW)
    scrollbar.grid(row=0, column=1, sticky=tk.NS)
    scrollbar.grid_remove()
    return outer, scroll_frame

def _build_tools_section(parent: ttk.Frame, gui) -> None:
    frame = create_card(parent, "01", "Pipeline Tools", "Nine-step MRI processing pipeline", {"fill": tk.X})
    frame.columnconfigure(0, weight=1)

    mode_row = ttk.Frame(frame)
    mode_row.grid(row=0, column=0, sticky=tk.EW, pady=(0, 16))
    mode_row.columnconfigure(1, weight=1)
    ttk.Label(mode_row, text="Preset").grid(row=0, column=0, sticky=tk.W, padx=(0, 12))
    ttk.Combobox(
        mode_row, textvariable=gui.state.pipeline_mode,
        values=PIPELINE_MODES,
        state="readonly",
        width=34,
    ).grid(row=0, column=1, sticky=tk.EW, padx=(0, 12))
    ttk.Button(mode_row, text="Load preset", style="Accent.TButton", command=gui.config_ctrl._load_run_config).grid(row=0, column=2, sticky=tk.E, padx=(0, 8))
    ttk.Button(mode_row, text="Save preset", command=gui.config_ctrl._save_run_config).grid(row=0, column=3, sticky=tk.E, padx=(0, 8))
    ttk.Button(
        mode_row,
        textvariable=gui.pipeline_tools_toggle_text,
        command=gui._toggle_pipeline_tools,
    ).grid(row=0, column=4, sticky=tk.E)

    gui.tool_combos = getattr(gui, "tool_combos", {})
    gui.tools_ctrl.status_labels = getattr(gui, "status_labels", {})
    gui.pipeline_tools_body = ttk.Frame(frame)
    gui.pipeline_tools_body.grid(row=1, column=0, sticky=tk.EW, pady=(0, 14))
    gui.pipeline_tools_body.columnconfigure(0, weight=1)

    tools_table = ttk.Frame(gui.pipeline_tools_body, padding=(0, 4))
    tools_table.grid(row=0, column=0, sticky=tk.EW)
    tools_table.columnconfigure(0, weight=3, minsize=220)
    tools_table.columnconfigure(1, weight=2, minsize=250)
    tools_table.columnconfigure(2, weight=0, minsize=135)
    tools_table.rowconfigure(0, minsize=42)

    ttk.Label(tools_table, text="Step", foreground="#64748b", font=("Inter", 9, "bold"), anchor=tk.W).grid(row=0, column=0, sticky=tk.EW, padx=(4, 10))
    ttk.Label(tools_table, text="Tool", foreground="#64748b", font=("Inter", 9, "bold"), anchor=tk.W).grid(row=0, column=1, sticky=tk.EW, padx=(10, 10))
    ttk.Label(tools_table, text="Status", foreground="#64748b", font=("Inter", 9, "bold"), anchor=tk.W).grid(row=0, column=2, sticky=tk.EW, padx=(10, 4))
    ttk.Separator(tools_table, orient=tk.HORIZONTAL).grid(row=1, column=0, columnspan=3, sticky=tk.EW)

    for idx, stage in enumerate(STAGE_ORDER):
        row = 2 + idx * 2
        tools = enabled_tools_for_stage(stage)
        tool_labels = [tool_display_name(tool) for tool in tools]
        var = gui.state.tool_vars[stage]

        tools_table.rowconfigure(row, minsize=46)
        gui.tool_step_labels = getattr(gui, "tool_step_labels", {})
        step_label = ttk.Label(
            tools_table,
            text=f"{idx + 1}. {STAGE_LABELS.get(stage, stage)}",
            foreground="#111827",
            font=("Inter", 10),
            anchor=tk.W,
        )
        step_label.grid(row=row, column=0, sticky=tk.EW, padx=(4, 10))
        gui.tool_step_labels[stage] = step_label

        combo = ttk.Combobox(tools_table, textvariable=var, values=tool_labels, state="readonly", width=30)
        combo.grid(row=row, column=1, sticky=tk.EW, padx=(10, 10))
        gui.tool_combos[stage] = combo
        status = ttk.Label(tools_table, text="Not checked", foreground="#64748b", font=("Inter", 10), anchor=tk.W)
        status.grid(row=row, column=2, sticky=tk.EW, padx=(10, 4))
        gui.tools_ctrl.status_labels[stage] = status
        if idx < len(STAGE_ORDER) - 1:
            ttk.Separator(tools_table, orient=tk.HORIZONTAL).grid(row=row + 1, column=0, columnspan=3, sticky=tk.EW)

    stats_row = 2

    stats_frame = ttk.LabelFrame(frame, text=" Stats vectors ", padding=(12, 10))
    stats_frame.grid(row=stats_row, column=0, sticky=tk.EW, pady=(0, 14))
    stats_frame.columnconfigure(1, weight=1)

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
            atlas_combo.configure(state=tk.NORMAL if gui.state.stat_vector_enabled_vars[stat].get() else tk.DISABLED)

    for idx, (stat, stat_def) in enumerate(STAT_VECTOR_DEFS.items()):
        row = idx
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
                state=tk.NORMAL,
                width=28,
            )
            combo.grid(row=row, column=1, sticky=tk.EW, padx=(10, 6), pady=4)
            _enable_combobox_type_search(combo, gui)
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

    adv_frame = ttk.Frame(frame)
    adv_frame.grid(row=stats_row + 2, column=0, sticky=tk.EW, pady=(10, 0))
    gui.adv_toggle_text = tk.StringVar(value="▶ Advanced Settings")
    
    def sync_adv_options(*_args) -> None:
        if gui.state.show_advanced_settings.get():
            adv_options.grid(row=1, column=0, columnspan=2, sticky=tk.EW, padx=0, pady=(5, 0))
            gui.adv_toggle_text.set("▼ Advanced Settings")
        else:
            adv_options.grid_remove()
            gui.adv_toggle_text.set("▶ Advanced Settings")

    def toggle_adv() -> None:
        gui.state.show_advanced_settings.set(not gui.state.show_advanced_settings.get())
        sync_adv_options()

    ttk.Button(adv_frame, textvariable=gui.adv_toggle_text, command=toggle_adv).grid(row=0, column=0, sticky=tk.W, pady=(0, 2))

    adv_options = ttk.Frame(adv_frame)
    adv_options.columnconfigure(1, weight=1)
    
    ttk.Label(adv_options, text="Optimization Mode").grid(row=0, column=0, sticky=tk.W, padx=8, pady=(8, 3))
    ttk.Combobox(
        adv_options, 
        textvariable=gui.state.optimization_mode, 
        values=("Use default options", "Throughput", "FCFS (FIFO)", 'Complete oriented ("ASAP")'), 
        state="readonly", 
        width=25
    ).grid(row=0, column=1, sticky=tk.W, padx=8, pady=(8, 3))

    ttk.Checkbutton(
        adv_options,
        text="Use NeuroFLOW scheduler",
        variable=gui.state.neuroflow_enabled,
    ).grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=8, pady=(8, 3))

    ttk.Label(adv_options, text="NeuroFLOW max concurrent tasks").grid(row=2, column=0, sticky=tk.W, padx=8, pady=(8, 3))
    ttk.Spinbox(
        adv_options,
        from_=1,
        to=16,
        textvariable=gui.state.neuroflow_max_concurrent_tasks,
        width=6,
    ).grid(row=2, column=1, sticky=tk.W, padx=8, pady=(8, 3))

    gui.state.show_advanced_settings.trace_add("write", sync_adv_options)
    sync_adv_options()


    gui.state.pipeline_mode.trace_add("write", lambda *_args: gui._apply_pipeline_mode())
    gui._apply_pipeline_mode(show_custom_tools=False)
    gui.tools_ctrl._update_config_status_labels()

def _build_input_section(parent: ttk.Frame, gui) -> None:
    frame = create_card(parent, "", "Input & output", "", {"fill": tk.X, "pady": (0, 18)})

    mode_row = ttk.Frame(frame)
    mode_row.grid(row=0, column=0, columnspan=5, sticky=tk.EW, pady=(0, 10))
    ttk.Radiobutton(mode_row, text="Single file", variable=gui.state.input_mode, value="file", command=gui._refresh_input_label).pack(side=tk.LEFT)
    ttk.Radiobutton(mode_row, text="Multiple files", variable=gui.state.input_mode, value="files", command=gui._refresh_input_label).pack(side=tk.LEFT, padx=(14, 0))
    ttk.Radiobutton(mode_row, text="Batch folder", variable=gui.state.input_mode, value="dir", command=gui._refresh_input_label).pack(side=tk.LEFT, padx=(14, 0))

    gui.input_source_row = ttk.Frame(frame)
    gui.input_source_row.grid(row=1, column=0, columnspan=5, sticky=tk.EW, pady=3)
    ttk.Label(gui.input_source_row, text="Input Source").pack(anchor=tk.W, pady=(0, 2))
    input_source_inner = ttk.Frame(gui.input_source_row)
    input_source_inner.pack(fill=tk.X, expand=True)
    gui.input_source_combo = ttk.Combobox(
        input_source_inner,
        textvariable=gui.state.input_source,
        values=("Local", "Server"),
        state="readonly",
        width=10
    )
    gui.input_source_combo.pack(side=tk.LEFT, padx=(0, 14))

    upload_options = {"text": "Upload input to server", "command": gui.remote_ctrl._upload_input_to_server_placeholder}
    upload_icon = gui._make_icon("load") if hasattr(gui, "_make_icon") else None
    if upload_icon is not None:
        upload_options.update({"image": upload_icon, "compound": tk.LEFT})
    gui.upload_input_button = ttk.Button(input_source_inner, **upload_options)
    gui.upload_input_button.pack(side=tk.LEFT)
    gui.upload_input_tooltip = Tooltip(gui.upload_input_button, "Standard Upload: Sync all local files to the server before running.\nFor Lazy Upload (upload & process simultaneously), just click 'Run'.")
    
    # We trace input_source to trigger _switch_input_source properly
    def _on_input_source_change(*_args):
        gui._switch_input_source(gui.state.input_source.get())
    gui.state.input_source.trace_add("write", _on_input_source_change)

    container = ttk.Frame(frame)
    container.grid(row=3, column=0, columnspan=5, sticky=tk.EW, pady=3)
    ttk.Label(container, textvariable=gui.input_location_label_var).pack(anchor=tk.W, pady=(0, 2))

    input_frame = ttk.Frame(container)
    input_frame.pack(fill=tk.X, expand=True)
    ttk.Entry(input_frame, textvariable=gui.state.input_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

    gui.file_count_label = ttk.Label(input_frame, text="")
    gui.file_count_label.pack(side=tk.LEFT, padx=(0, 8))

    gui.btn_config_batch = ttk.Button(input_frame, text="Configure Batch", command=gui.config_ctrl._configure_batch, state=tk.DISABLED)
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
    gui.server_output_browse_button = ttk.Button(server_input_frame, text="Browse Server", style="Accent.TButton", command=gui.remote_ctrl._browse_server_output)
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

    ttk.Label(frame, text="RAM %", width=10).grid(row=1, column=0, sticky=tk.W, pady=(10, 4))
    ram_row = ttk.Frame(frame)
    ram_row.grid(row=1, column=1, sticky=tk.W, padx=(8, 0), pady=(10, 4))
    ram_vcmd = (gui.root.register(gui.validation_ctrl._validate_ram_percent_input), "%P")
    gui.ram_percent_spinbox = ttk.Spinbox(
        ram_row,
        from_=1,
        to=100,
        textvariable=gui.state.ram_percent,
        width=8,
        validate="key",
        validatecommand=ram_vcmd,
    )
    gui.ram_percent_spinbox.pack(side=tk.LEFT)

    ttk.Label(frame, text="Device", width=10).grid(row=2, column=0, sticky=tk.W, pady=(10, 0))
    ttk.Combobox(frame, textvariable=gui.state.device, values=("cpu", "gpu"), state="readonly", width=10).grid(row=2, column=1, sticky=tk.EW, padx=(8, 0), pady=(10, 0))

    ttk.Label(frame, text="Threads", width=10).grid(row=3, column=0, sticky=tk.W, pady=(10, 4))
    thread_row = ttk.Frame(frame)
    thread_row.grid(row=3, column=1, sticky=tk.W, padx=(8, 0), pady=(10, 4))
    thread_vcmd = (gui.root.register(gui.validation_ctrl._validate_thread_input), "%P")
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

    gui.runtime_warning_label = ttk.Label(frame, text="", foreground="#ef4444", font=("Inter", 9))
    gui.runtime_warning_label.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))
    gui.runtime_warning_label.grid_remove()

    def _update_runtime_warning(*_args):
        try:
            threads = int(gui.state.threads.get())
            ram = int(gui.state.ram_percent.get())
            max_t = gui.max_threads or gui.local_max_threads
            if threads >= max_t or ram > 90:
                gui.runtime_warning_label.configure(text="Warning: Using more than 90% RAM or all Threads may freeze your system. Consider leaving at least 10%.")
                gui.runtime_warning_label.grid()
            else:
                gui.runtime_warning_label.grid_remove()
        except Exception:
            pass

    gui.state.threads.trace_add("write", lambda *_args: _update_runtime_warning())
    gui.state.ram_percent.trace_add("write", lambda *_args: _update_runtime_warning())
    gui.state.run_target.trace_add("write", lambda *_args: _update_runtime_warning())
    gui.thread_max_text.trace_add("write", lambda *_args: _update_runtime_warning())
    gui.thread_max_text.trace_add("write", lambda *_args: _update_runtime_warning())


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
    gui.pipeline_ctrl.remote_pack_options = {"fill": tk.X, "pady": (0, 18)}
    frame = create_card(parent, "", "Remote Server", "", gui.pipeline_ctrl.remote_pack_options)
    gui.pipeline_ctrl.remote_frame = frame
    gui.pipeline_ctrl.remote_body = frame

    ttk.Label(frame, text="Host/IP", width=10).grid(row=0, column=0, sticky=tk.W, pady=4)
    host_entry = ttk.Entry(frame, textvariable=gui.state.remote_host)
    gui.pipeline_ctrl.register_remote_host_entry(host_entry)
    host_entry
    gui.pipeline_ctrl.remote_host_entry.grid(row=0, column=1, sticky=tk.EW, padx=(8, 16), pady=3)
    ttk.Label(frame, text="Port", width=8).grid(row=0, column=2, sticky=tk.W, pady=4)
    gui.pipeline_ctrl.remote_port_entry = ttk.Entry(frame, textvariable=gui.state.remote_port, width=8)
    gui.pipeline_ctrl.remote_port_entry.grid(row=0, column=3, sticky=tk.EW, padx=(8, 0), pady=3)

    ttk.Label(frame, text="Username", width=10).grid(row=1, column=0, sticky=tk.W, pady=4)
    user_entry = ttk.Entry(frame, textvariable=gui.state.remote_username)
    gui.pipeline_ctrl.register_remote_username_entry(user_entry)
    user_entry
    gui.pipeline_ctrl.remote_username_entry.grid(row=1, column=1, sticky=tk.EW, padx=(8, 16), pady=3)
    ttk.Label(frame, text="Password", width=8).grid(row=1, column=2, sticky=tk.W, pady=4)
    password_entry = ttk.Entry(frame, textvariable=gui.state.remote_password, show="*")
    gui.pipeline_ctrl.register_remote_password_entry(password_entry)
    password_entry
    gui.pipeline_ctrl.remote_password_entry.grid(row=1, column=3, sticky=tk.EW, padx=(8, 0), pady=3)

    ttk.Label(frame, text="SSH Key", width=10).grid(row=2, column=0, sticky=tk.W, pady=4)
    gui.pipeline_ctrl.remote_key_entry = ttk.Entry(frame, textvariable=gui.state.remote_key_path)
    gui.pipeline_ctrl.remote_key_entry.grid(row=2, column=1, columnspan=2, sticky=tk.EW, padx=(8, 8), pady=3)
    gui.remote_key_browse_button = ttk.Button(frame, text="Browse", style="Accent.TButton", command=gui.remote_ctrl._browse_remote_key)
    gui.remote_key_browse_button.grid(row=2, column=3, sticky=tk.EW, padx=(0, 0), pady=3)

    ttk.Label(frame, text="Workspace", width=10).grid(row=3, column=0, sticky=tk.W, pady=4)
    gui.remote_workspace_entry = ttk.Entry(frame, textvariable=gui.state.remote_workspace)
    gui.remote_workspace_entry.grid(row=3, column=1, columnspan=3, sticky=tk.EW, padx=(8, 0), pady=3)

    buttons = ttk.Frame(frame)
    buttons.grid(row=4, column=0, columnspan=4, sticky=tk.EW, pady=(8, 0))
    gui.pipeline_ctrl.remote_connect_button = ttk.Button(buttons, text="Connect Server", style="Accent.TButton", command=gui.pipeline_ctrl._remote_test_ssh)
    gui.pipeline_ctrl.remote_connect_button.pack(side=tk.LEFT)
    gui.pipeline_ctrl.remote_status_icon_label = ttk.Label(buttons)
    gui.pipeline_ctrl.remote_status_icon_label.pack(side=tk.LEFT, padx=(12, 6))
    if hasattr(gui, "_set_remote_status_icon"):
        gui.remote_ctrl._set_remote_status_icon("pending")
    gui.remote_status_label = ttk.Label(buttons, textvariable=gui.state.remote_status)
    gui.remote_status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    frame.columnconfigure(1, weight=1)
    frame.columnconfigure(3, weight=1)
