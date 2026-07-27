from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui.components.cards import create_card
from ui.components.tooltip import Tooltip


def build_tools_tab(parent: ttk.Frame, ctrl) -> None:
    root = ttk.Frame(parent, padding=16)
    root.pack(fill=tk.BOTH, expand=True)

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
    ctrl.python_env_install_button = ttk.Button(py_buttons, text="Create / Update Environment", command=ctrl._install_python_requirements)
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

    table_outer = ttk.Frame(top)
    table_outer.pack(fill=tk.BOTH, expand=True)
    columns = ("selected", "stage", "tool", "image", "download_size", "installed_size", "status")
    tree = ttk.Treeview(table_outer, columns=columns, show="headings", selectmode="none", height=18)
    tree.heading("selected", text="")
    tree.heading("stage", text="Stage")
    tree.heading("tool", text="Tool")
    tree.heading("image", text="Image")
    tree.heading("download_size", text="Download size")
    tree.heading("installed_size", text="Installed size")
    tree.heading("status", text="Status")
    tree.column("selected", width=42, minwidth=42, stretch=False, anchor=tk.CENTER)
    tree.column("stage", width=170, minwidth=130, stretch=True)
    tree.column("tool", width=220, minwidth=160, stretch=True)
    tree.column("image", width=360, minwidth=220, stretch=True)
    tree.column("download_size", width=110, minwidth=90, stretch=False)
    tree.column("installed_size", width=110, minwidth=90, stretch=False)
    tree.column("status", width=130, minwidth=110, stretch=False)
    tree_scroll = ttk.Scrollbar(table_outer, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=tree_scroll.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_tree_mousewheel(event):
        if event.num == 4:
            tree.yview_scroll(-4, "units")
        elif event.num == 5:
            tree.yview_scroll(4, "units")
        else:
            tree.yview_scroll(int(-1 * (event.delta / 120)) * 4, "units")
        return "break"

    tree.bind("<MouseWheel>", _on_tree_mousewheel)
    tree.bind("<Button-4>", _on_tree_mousewheel)
    tree.bind("<Button-5>", _on_tree_mousewheel)
    tree.bind("<Button-1>", ctrl._on_tree_click)
    ctrl.tree = tree
    ctrl.table_frame = None

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
    ctrl.gui.remote_ctrl._sync_remote_connection_controls()
