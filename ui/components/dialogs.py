import tkinter as tk
from tkinter import ttk

def build_image_dialog(parent: tk.Tk, title: str) -> tuple[tk.Toplevel, tk.Text, ttk.Progressbar, dict[str, bool]]:
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.geometry("760x460")
    dialog.transient(parent)
    dialog.grab_set()
    ttk.Label(dialog, text=title, font=("Inter", 12, "bold")).pack(anchor=tk.W, padx=12, pady=(12, 6))
    
    log = tk.Text(dialog, wrap=tk.WORD, height=20, font=("JetBrains Mono", 10), state=tk.DISABLED)
    scroll = ttk.Scrollbar(dialog, orient=tk.VERTICAL, command=log.yview)
    log.configure(yscrollcommand=scroll.set)
    log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0), pady=(0, 12))
    scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 12), pady=(0, 12))
    
    progress = ttk.Progressbar(dialog, mode="indeterminate")
    progress.pack(fill=tk.X, padx=12, pady=(0, 12))
    progress.start(10)
    
    state = {"ok": False, "done": False}
    return dialog, log, progress, state

def append_dialog_log(log: tk.Text, line: str) -> None:
    log.configure(state=tk.NORMAL)
    log.insert(tk.END, line + "\n")
    log.see(tk.END)
    log.configure(state=tk.DISABLED)
