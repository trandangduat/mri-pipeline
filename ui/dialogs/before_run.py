from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from ui.gui_validation import RunReadinessCondition


STATUS_STYLE = {
    "ok": ("Installed", "OK"),
    "not_done": ("Missing", "Not done"),
}


def show_before_run_dialog(gui: Any) -> bool:
    conditions = gui.validation_ctrl.run_readiness_conditions()
    if all(condition.ok for condition in conditions):
        return True

    dialog = tk.Toplevel(gui.root)
    dialog.title("Before run")
    dialog.geometry("880x520")
    dialog.minsize(760, 420)
    dialog.transient(gui.root)
    dialog.grab_set()

    expanded: dict[str, tk.Widget] = {}

    root = ttk.Frame(dialog, padding=14)
    root.pack(fill=tk.BOTH, expand=True)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    table = ttk.Frame(root)
    table.grid(row=0, column=0, sticky=tk.NSEW)
    table.columnconfigure(0, weight=2, minsize=210)
    table.columnconfigure(2, weight=3, minsize=280)
    table.columnconfigure(3, weight=1, minsize=150)

    ttk.Label(table, text="Condition", font=("Inter", 9, "bold")).grid(row=0, column=0, sticky=tk.W, padx=(4, 8), pady=(0, 6))
    ttk.Label(table, text="", width=3).grid(row=0, column=1, sticky=tk.W, padx=4, pady=(0, 6))
    ttk.Label(table, text="Location", font=("Inter", 9, "bold")).grid(row=0, column=2, sticky=tk.W, padx=8, pady=(0, 6))
    ttk.Label(table, text="Status", font=("Inter", 9, "bold")).grid(row=0, column=3, sticky=tk.W, padx=8, pady=(0, 6))
    ttk.Separator(table, orient=tk.HORIZONTAL).grid(row=1, column=0, columnspan=4, sticky=tk.EW, pady=(0, 4))

    def status_label(parent: tk.Widget, condition: RunReadinessCondition) -> tk.Label:
        tool_status, text = STATUS_STYLE.get(condition.status_kind, ("Missing", "Not done"))
        icon = gui.tools_ctrl._tool_status_icon_image(tool_status, small=True)
        fg = gui.tools_ctrl._status_color(tool_status)
        label = tk.Label(parent, text=f" {text}" if icon else text, image=icon or "", compound=tk.LEFT, anchor=tk.W, fg=fg, bg="#fafafa")
        label.image = icon
        return label

    def toggle_details(condition: RunReadinessCondition, row: int) -> None:
        existing = expanded.pop(condition.key, None)
        if existing is not None:
            existing.destroy()
            return
        detail = tk.Label(
            table,
            text=condition.details,
            justify=tk.LEFT,
            anchor=tk.W,
            bg="#f8fafc",
            fg="#475569",
            padx=10,
            pady=7,
            wraplength=760,
        )
        detail.grid(row=row + 1, column=0, columnspan=4, sticky=tk.EW, padx=(0, 0), pady=(0, 4))
        expanded[condition.key] = detail

    row = 2
    for condition in conditions:
        bg = "#fafafa"
        for col in range(4):
            table.columnconfigure(col, pad=0)
        condition_frame = tk.Frame(table, bg=bg, padx=4, pady=6)
        condition_frame.grid(row=row, column=0, sticky=tk.NSEW, padx=0, pady=1)
        tk.Label(condition_frame, text=condition.name, anchor=tk.W, bg=bg, fg="#111827").pack(fill=tk.X)

        help_frame = tk.Frame(table, bg=bg, padx=4, pady=4)
        help_frame.grid(row=row, column=1, sticky=tk.NSEW, padx=0, pady=1)
        ttk.Button(help_frame, text="?", width=2, command=lambda c=condition, r=row: toggle_details(c, r)).pack(anchor=tk.W)

        location_frame = tk.Frame(table, bg=bg, padx=8, pady=6)
        location_frame.grid(row=row, column=2, sticky=tk.NSEW, padx=0, pady=1)
        tk.Label(location_frame, text=condition.location, anchor=tk.W, bg=bg, fg="#475569").pack(fill=tk.X)

        status_frame = tk.Frame(table, bg=bg, padx=8, pady=6)
        status_frame.grid(row=row, column=3, sticky=tk.NSEW, padx=0, pady=1)
        status_label(status_frame, condition).pack(anchor=tk.W)

        ttk.Separator(table, orient=tk.HORIZONTAL).grid(row=row + 2, column=0, columnspan=4, sticky=tk.EW, pady=(1, 1))
        row += 3

    buttons = ttk.Frame(root)
    buttons.grid(row=1, column=0, sticky=tk.EW, pady=(14, 0))
    buttons.columnconfigure(0, weight=1)

    def close() -> None:
        dialog.destroy()

    ttk.Button(buttons, text="Close", command=close).grid(row=0, column=1, sticky=tk.E)
    dialog.protocol("WM_DELETE_WINDOW", close)
    gui.root.wait_window(dialog)
    return False
