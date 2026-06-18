import tkinter as tk
from tkinter import ttk

def create_card(
    parent: tk.Widget,
    badge: str,
    title: str,
    subtitle: str = "",
    pack_options: dict | None = None,
) -> ttk.Frame:
    """Creates a card-like UI container with a header and a body."""
    # Use LabelFrame for a modern group box look, discarding the badge and subtitle to reduce clutter.
    outer = ttk.LabelFrame(parent, text=f" {title} ", padding=16)
    outer.pack(**(pack_options or {"fill": tk.X, "pady": (0, 16)}))
    return outer
