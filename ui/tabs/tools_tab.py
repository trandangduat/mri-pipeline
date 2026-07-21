import tkinter as tk
from tkinter import ttk

from ui.components.cards import create_card
from ui.components.tooltip import Tooltip


def build_tools_tab(parent: ttk.Frame, ctrl) -> None:
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
    ttk.Label(py_card, textvariable=ctrl.gui.state.run_target, anchor=tk.W).grid(row=0, column=1, sticky=tk.W, padx=(10, 16), pady=(0, 6))
    ttk.Label(py_card, text="Status").grid(row=1, column=0, sticky=tk.W, pady=(0, 6))
    status_frame = ttk.Frame(py_card)
    status_frame.grid(row=1, column=1, sticky=tk.EW, padx=(10, 16), pady=(0, 6))
    ctrl.python_env_status_icon_label = ttk.Label(status_frame)
    ctrl.python_env_status_icon_label.pack(side=tk.LEFT, padx=(0, 6))
    ctrl.python_env_status_label = ttk.Label(status_frame, textvariable=ctrl.python_env_status, anchor=tk.W)
    ctrl.python_env_status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Label(py_card, text="Environment").grid(row=2, column=0, sticky=tk.W, pady=(0, 8))
    ttk.Label(py_card, textvariable=ctrl.python_env_hint, anchor=tk.W, wraplength=720).grid(row=2, column=1, sticky=tk.EW, padx=(10, 16), pady=(0, 8))
    py_buttons = ttk.Frame(py_card)
    py_buttons.grid(row=0, column=2, rowspan=3, sticky=tk.E, padx=(8, 0))
    ctrl.python_env_check_button = ttk.Button(py_buttons, text="Check Environment", command=ctrl._check_python_environment)
    ctrl.python_env_check_button.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))
    ctrl.python_env_install_button = ttk.Button(py_buttons, text="Create / Update Packages", command=ctrl._install_python_requirements)
    ctrl.python_env_install_button.pack(side=tk.TOP, fill=tk.X)

    top = create_card(root, "IMG", "Docker Images", "Check and download local/server tool images", {"fill": tk.BOTH, "expand": True, "pady": (0, 8)})

    controls = ttk.Frame(top)
    controls.pack(fill=tk.X, pady=(0, 8))
    ttk.Label(controls, text="Using target:").pack(side=tk.LEFT)
    ttk.Label(controls, textvariable=ctrl.gui.state.run_target, width=8, anchor=tk.W).pack(side=tk.LEFT, padx=(8, 12))

    button_group = ttk.Frame(controls)
    button_group.pack(side=tk.RIGHT)
    ctrl.refresh_button = ttk.Button(button_group, text="Refresh", command=ctrl._refresh_image_statuses)
    ctrl.refresh_button.pack(side=tk.LEFT)
    ctrl.tools_refresh_tooltip = Tooltip(ctrl.refresh_button, "")

    ctrl.select_all_button = ttk.Button(button_group, text="Select All", command=ctrl._select_all_images)
    ctrl.select_all_button.pack(side=tk.LEFT, padx=3)
    ctrl.unselect_all_button = ttk.Button(button_group, text="Unselect All", command=ctrl._unselect_all_images)
    ctrl.unselect_all_button.pack(side=tk.LEFT, padx=3)
    ctrl.select_missing_button = ttk.Button(button_group, text="Select Missing", command=ctrl._select_missing_images)
    ctrl.select_missing_button.pack(side=tk.LEFT, padx=3)
    ctrl.download_button = ttk.Button(button_group, text="Download", style="Accent.TButton", command=ctrl._ensure_checked_images, state=tk.DISABLED)
    ctrl.download_button.pack(side=tk.LEFT, padx=(8, 3))
    ctrl.delete_button = ttk.Button(button_group, text="Delete", command=ctrl._delete_checked_images, state=tk.DISABLED)
    ctrl.delete_button.pack(side=tk.LEFT, padx=3)

    table = ttk.Frame(top)
    table.pack(fill=tk.BOTH, expand=True)
    table.columnconfigure(1, weight=1)
    table.columnconfigure(2, weight=1)
    table.columnconfigure(3, weight=3)
    table.columnconfigure(4, minsize=90)
    table.columnconfigure(5, minsize=90)
    table.columnconfigure(6, minsize=140)
    ttk.Label(table, text="", width=4).grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=(0, 6))
    ttk.Label(table, text="Stage", font=("Inter", 9, "bold")).grid(row=0, column=1, sticky=tk.W, padx=8, pady=(0, 6))
    ttk.Label(table, text="Tool", font=("Inter", 9, "bold")).grid(row=0, column=2, sticky=tk.W, padx=8, pady=(0, 6))
    ttk.Label(table, text="Image", font=("Inter", 9, "bold")).grid(row=0, column=3, sticky=tk.W, padx=8, pady=(0, 6))
    ttk.Label(table, text="Download size", font=("Inter", 9, "bold")).grid(row=0, column=4, sticky=tk.W, padx=8, pady=(0, 6))
    ttk.Label(table, text="Installed size", font=("Inter", 9, "bold")).grid(row=0, column=5, sticky=tk.W, padx=8, pady=(0, 6))
    ttk.Label(table, text="Status", font=("Inter", 9, "bold")).grid(row=0, column=6, sticky=tk.W, padx=8, pady=(0, 6))
    ttk.Separator(table, orient=tk.HORIZONTAL).grid(row=1, column=0, columnspan=7, sticky=tk.EW, pady=(0, 4))
    ctrl.table_frame = table

    log_card = ttk.LabelFrame(root, text=" Image log ", padding=12)
    log_card.pack(fill=tk.X, pady=(0, 8))
    log_header = ttk.Frame(log_card)
    log_header.pack(fill=tk.X)
    ctrl.log_toggle_text = tk.StringVar(value="Show Image Log")
    ttk.Button(log_header, textvariable=ctrl.log_toggle_text, command=ctrl._toggle_log).pack(side=tk.LEFT)
    ctrl.log_body = ttk.Frame(log_card)
    ctrl.log_text = tk.Text(ctrl.log_body, wrap=tk.WORD, height=8, state=tk.DISABLED, font=("JetBrains Mono", 10))
    log_scroll = ttk.Scrollbar(ctrl.log_body, orient=tk.VERTICAL, command=ctrl.log_text.yview)
    ctrl.log_text.configure(yscrollcommand=log_scroll.set)
    ctrl.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    ctrl._refresh_tree()
    ctrl._preload_docker_hub_image_sizes()
    ctrl._set_python_env_status(ctrl.python_env_status.get())
    ctrl.gui._sync_remote_connection_controls()
