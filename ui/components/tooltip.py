import tkinter as tk

class Tooltip:
    def __init__(self, widget: tk.Widget, text: str = "widget info", delay: int = 500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.id: str | None = None
        self.tw: tk.Toplevel | None = None
        
        self.widget.bind("<Enter>", self.schedule)
        self.widget.bind("<Leave>", self.unschedule)
        self.widget.bind("<ButtonPress>", self.unschedule)

    def schedule(self, event=None) -> None:
        self.unschedule()
        if self.text and self.widget.cget("state") != "hidden":
            self.id = self.widget.after(self.delay, self.show)

    def unschedule(self, event=None) -> None:
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)
        self.hide()

    def show(self, event=None) -> None:
        self.unschedule()
        if not self.text:
            return
        
        x_off, y_off = 20, 20
        x, y, cx, cy = self.widget.bbox("insert") or (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + x_off
        y += self.widget.winfo_rooty() + y_off

        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(
            self.tw, 
            text=self.text, 
            justify=tk.LEFT,
            background="#1e293b", 
            foreground="#f8fafc",
            relief=tk.SOLID, borderwidth=1,
            font=("Inter", 9, "normal"),
            padx=5, pady=3
        )
        label.pack(ipadx=1)

    def hide(self) -> None:
        tw = self.tw
        self.tw = None
        if tw:
            tw.destroy()

    def update_text(self, text: str) -> None:
        self.text = text
        if self.tw and self.tw.winfo_exists():
            for child in self.tw.winfo_children():
                if isinstance(child, tk.Label):
                    child.configure(text=text)
