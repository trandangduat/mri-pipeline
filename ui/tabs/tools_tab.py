import tkinter as tk
from tkinter import ttk

from ui.components.cards import create_card


def build_tools_tab(parent: ttk.Frame, gui) -> None:
    root = ttk.Frame(parent, padding=8)
    root.pack(fill=tk.BOTH, expand=True)

    py_card = create_card(root, "PY", "Python Environment", "Check Python/pip and install packages for the selected target", {"fill": tk.X, "pady": (0, 8)})
    py_row = ttk.Frame(py_card)
    py_row.pack(fill=tk.X)
    ttk.Label(py_row, text="Using target:").pack(side=tk.LEFT)
    ttk.Label(py_row, textvariable=gui.state.run_target, width=8, anchor=tk.W).pack(side=tk.LEFT, padx=(8, 16))
    ttk.Label(py_row, text="Status:").pack(side=tk.LEFT)
    ttk.Label(py_row, textvariable=gui.python_env_status, width=40, anchor=tk.W).pack(side=tk.LEFT, padx=(8, 16))
    ttk.Button(py_row, text="Check Python", command=gui._check_python_environment).pack(side=tk.LEFT, padx=3)
    ttk.Button(py_row, text="Install Python Packages", command=gui._install_python_requirements).pack(side=tk.LEFT, padx=3)
    ttk.Label(
        py_card,
        text="Note: this installs packages from requirements.txt. Python itself must already be installed on the selected machine.",
        foreground="#64748b",
    ).pack(anchor=tk.W, pady=(6, 0))

    top = create_card(root, "IMG", "Docker Images", "Check and download local/server tool images", {"fill": tk.BOTH, "expand": True, "pady": (0, 8)})

    controls = ttk.Frame(top)
    controls.pack(fill=tk.X, pady=(0, 8))
    ttk.Label(controls, text="Using target:").pack(side=tk.LEFT)
    ttk.Label(controls, textvariable=gui.state.run_target, width=8, anchor=tk.W).pack(side=tk.LEFT, padx=(8, 12))
    ttk.Button(controls, text="Refresh", command=gui._refresh_tool_image_statuses).pack(side=tk.LEFT, padx=3)
    ttk.Button(controls, text="Download Selected", command=gui._ensure_selected_tool_images).pack(side=tk.LEFT, padx=3)
    ttk.Button(controls, text="Download Missing", command=gui._ensure_missing_tool_images).pack(side=tk.LEFT, padx=3)

    columns = ("stage", "tool", "image", "status")
    gui.tools_tree = ttk.Treeview(top, columns=columns, show="headings", height=13)
    gui.tools_tree.heading("stage", text="Stage")
    gui.tools_tree.heading("tool", text="Tool")
    gui.tools_tree.heading("image", text="Image")
    gui.tools_tree.heading("status", text="Status")
    gui.tools_tree.column("stage", width=190, anchor=tk.W)
    gui.tools_tree.column("tool", width=210, anchor=tk.W)
    gui.tools_tree.column("image", width=360, anchor=tk.W)
    gui.tools_tree.column("status", width=110, anchor=tk.W)
    scroll = ttk.Scrollbar(top, orient=tk.VERTICAL, command=gui.tools_tree.yview)
    gui.tools_tree.configure(yscrollcommand=scroll.set)
    gui.tools_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)

    log_card = create_card(root, "LOG", "Image log", "Short install/check events", {"fill": tk.BOTH, "expand": False})
    gui.tools_log_text = tk.Text(log_card, wrap=tk.WORD, height=8, state=tk.DISABLED, font=("JetBrains Mono", 10))
    log_scroll = ttk.Scrollbar(log_card, orient=tk.VERTICAL, command=gui.tools_log_text.yview)
    gui.tools_log_text.configure(yscrollcommand=log_scroll.set)
    gui.tools_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    gui._refresh_tools_tree()
