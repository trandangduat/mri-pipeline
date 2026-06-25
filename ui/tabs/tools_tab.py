import tkinter as tk
from tkinter import ttk

from ui.components.cards import create_card


def build_tools_tab(parent: ttk.Frame, gui) -> None:
    canvas = tk.Canvas(parent, highlightthickness=0)
    scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
    root = ttk.Frame(canvas, padding=8)
    window_id = canvas.create_window((0, 0), window=root, anchor=tk.NW)

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

    root.bind("<Configure>", _sync_scroll_region)
    canvas.bind("<Configure>", _sync_window_width)
    canvas.bind("<MouseWheel>", _on_mousewheel)
    canvas.bind("<Button-4>", _on_mousewheel)
    canvas.bind("<Button-5>", _on_mousewheel)
    canvas.bind("<Enter>", _bind_mousewheel)
    canvas.bind("<Leave>", _unbind_mousewheel)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    py_card = create_card(root, "PY", "Python Environment", "Local Python and remote virtual environment", {"fill": tk.X, "pady": (0, 8)})
    py_card.columnconfigure(1, weight=1)
    ttk.Label(py_card, text="Target").grid(row=0, column=0, sticky=tk.W, pady=(0, 6))
    ttk.Label(py_card, textvariable=gui.state.run_target, anchor=tk.W).grid(row=0, column=1, sticky=tk.W, padx=(10, 16), pady=(0, 6))
    ttk.Label(py_card, text="Status").grid(row=1, column=0, sticky=tk.W, pady=(0, 6))
    status_frame = ttk.Frame(py_card)
    status_frame.grid(row=1, column=1, sticky=tk.EW, padx=(10, 16), pady=(0, 6))
    gui.python_env_status_icon_label = ttk.Label(status_frame)
    gui.python_env_status_icon_label.pack(side=tk.LEFT, padx=(0, 6))
    gui.python_env_status_label = ttk.Label(status_frame, textvariable=gui.python_env_status, anchor=tk.W)
    gui.python_env_status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Label(py_card, text="Environment").grid(row=2, column=0, sticky=tk.W, pady=(0, 8))
    ttk.Label(py_card, textvariable=gui.python_env_hint, anchor=tk.W, wraplength=720).grid(row=2, column=1, sticky=tk.EW, padx=(10, 16), pady=(0, 8))
    py_buttons = ttk.Frame(py_card)
    py_buttons.grid(row=0, column=2, rowspan=3, sticky=tk.E, padx=(8, 0))
    ttk.Button(py_buttons, text="Check Environment", command=gui._check_python_environment).pack(side=tk.TOP, fill=tk.X, pady=(0, 4))
    ttk.Button(py_buttons, text="Create / Update Packages", command=gui._install_python_requirements).pack(side=tk.TOP, fill=tk.X)

    top = create_card(root, "IMG", "Docker Images", "Check and download local/server tool images", {"fill": tk.BOTH, "expand": True, "pady": (0, 8)})

    controls = ttk.Frame(top)
    controls.pack(fill=tk.X, pady=(0, 8))
    ttk.Label(controls, text="Using target:").pack(side=tk.LEFT)
    ttk.Label(controls, textvariable=gui.state.run_target, width=8, anchor=tk.W).pack(side=tk.LEFT, padx=(8, 12))

    button_group = ttk.Frame(controls)
    button_group.pack(side=tk.RIGHT)
    ttk.Button(button_group, text="Refresh", command=gui._refresh_tool_image_statuses).pack(side=tk.LEFT, padx=3)
    ttk.Button(button_group, text="Select All", command=gui._select_all_tool_images).pack(side=tk.LEFT, padx=3)
    ttk.Button(button_group, text="Unselect All", command=gui._unselect_all_tool_images).pack(side=tk.LEFT, padx=3)
    ttk.Button(button_group, text="Select Missing", command=gui._select_missing_tool_images).pack(side=tk.LEFT, padx=3)
    gui.tools_download_button = ttk.Button(button_group, text="Download", style="Accent.TButton", command=gui._ensure_checked_tool_images, state=tk.DISABLED)
    gui.tools_download_button.pack(side=tk.LEFT, padx=(8, 3))

    table = ttk.Frame(top)
    table.pack(fill=tk.BOTH, expand=True)
    table.columnconfigure(1, weight=1)
    table.columnconfigure(2, weight=1)
    table.columnconfigure(3, weight=3)
    table.columnconfigure(4, minsize=140)
    ttk.Label(table, text="", width=4).grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=(0, 6))
    ttk.Label(table, text="Stage", font=("Inter", 9, "bold")).grid(row=0, column=1, sticky=tk.W, padx=8, pady=(0, 6))
    ttk.Label(table, text="Tool", font=("Inter", 9, "bold")).grid(row=0, column=2, sticky=tk.W, padx=8, pady=(0, 6))
    ttk.Label(table, text="Image", font=("Inter", 9, "bold")).grid(row=0, column=3, sticky=tk.W, padx=8, pady=(0, 6))
    ttk.Label(table, text="Status", font=("Inter", 9, "bold")).grid(row=0, column=4, sticky=tk.W, padx=8, pady=(0, 6))
    ttk.Separator(table, orient=tk.HORIZONTAL).grid(row=1, column=0, columnspan=5, sticky=tk.EW, pady=(0, 4))
    gui.tools_table_frame = table

    log_card = ttk.LabelFrame(root, text=" Image log ", padding=12)
    log_card.pack(fill=tk.X, pady=(0, 8))
    log_header = ttk.Frame(log_card)
    log_header.pack(fill=tk.X)
    gui.tools_log_toggle_text = tk.StringVar(value="Show Image Log")
    ttk.Button(log_header, textvariable=gui.tools_log_toggle_text, command=gui._toggle_tools_log).pack(side=tk.LEFT)
    gui.tools_log_body = ttk.Frame(log_card)
    gui.tools_log_text = tk.Text(gui.tools_log_body, wrap=tk.WORD, height=8, state=tk.DISABLED, font=("JetBrains Mono", 10))
    log_scroll = ttk.Scrollbar(gui.tools_log_body, orient=tk.VERTICAL, command=gui.tools_log_text.yview)
    gui.tools_log_text.configure(yscrollcommand=log_scroll.set)
    gui.tools_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    gui._refresh_tools_tree()
    gui._set_python_env_status(gui.python_env_status.get())
