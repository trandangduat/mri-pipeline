import tkinter as tk
from tkinter import ttk
import sv_ttk


def configure_windows_dpi_awareness() -> None:
    """Prevent Windows from bitmap-scaling Tk, which makes text look blurry."""
    try:
        import ctypes
        import sys

        if not sys.platform.startswith("win"):
            return
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

def setup_styles(root) -> None:
    # Thiết lập giao diện Light Mode làm mặc định
    sv_ttk.set_theme("light")
    
    # Set màu nền chuẩn của sv-ttk light theme cho cửa sổ gốc 
    # để tránh bị lộ nền của Tkinter mặc định
    root.configure(bg="#fafafa")
    try:
        pixels_per_inch = root.winfo_fpixels("1i")
        if pixels_per_inch > 0:
            root.tk.call("tk", "scaling", pixels_per_inch / 72.0)
    except Exception:
        pass
    
    # Đổi toàn bộ font thành Inter, giữ nguyên kích cỡ mặc định (không scale down nữa)
    import tkinter.font as tkfont
    for font_name in tkfont.names():
        f = tkfont.nametofont(font_name)
        f.configure(family="Inter")
                
    # Keep fixed font for code
    try:
        fixed = tkfont.nametofont("TkFixedFont")
        fixed.configure(family="JetBrains Mono")
    except:
        pass
        
    style = ttk.Style(root)
    # Lấy kích cỡ của body font để tính toán kích cỡ cho tiêu đề pane
    try:
        body_font = tkfont.nametofont("TkDefaultFont")
        base_size = body_font.cget("size")
        if isinstance(base_size, int):
            title_size = (base_size - 3) if base_size < 0 else (base_size + 2)
        else:
            title_size = 12
    except:
        title_size = 12

    # In đậm tiêu đề pane (LabelFrame) và tăng kích cỡ lên 2 cỡ
    style.configure("TLabelframe.Label", font=("Inter", title_size, "bold"))

    _setup_skipped_combobox_style(root, style)
    
    # Selected list item background
    style.configure("Selected.TFrame", background="#e2e8f0")
    style.configure("Selected.TLabel", background="#e2e8f0")
    style.configure("ToolSelected.TFrame", background="#cbd5e1")
    style.configure("ToolSelected.TLabel", background="#cbd5e1")
    style.configure("ToolSelected.TCheckbutton", background="#cbd5e1")


def _setup_skipped_combobox_style(root: tk.Misc, style: ttk.Style) -> None:
    """Dimmed combobox look for skipped pipeline steps (sv-ttk disabled sprites are nearly white)."""
    try:
        from PIL import Image, ImageDraw, ImageTk
    except ImportError:
        style.configure("Skipped.TCombobox", foreground="#94a3b8")
        style.map("Skipped.TCombobox", foreground=[("disabled", "#94a3b8"), ("!disabled", "#94a3b8")])
        return

    size = 20
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=4, fill=(236, 239, 244, 255), outline=(203, 213, 225, 255))
    photo = ImageTk.PhotoImage(img, master=root)
    root._skipped_combobox_photo = photo  # type: ignore[attr-defined]

    try:
        style.element_create("SkippedCombobox.field", "image", photo, border=5, sticky="nsew")
    except tk.TclError:
        # Element already exists (theme reload / repeated setup)
        pass

    style.layout(
        "Skipped.TCombobox",
        [
            (
                "SkippedCombobox.field",
                {
                    "sticky": "nswe",
                    "children": [
                        (
                            "Combobox.padding",
                            {
                                "sticky": "nswe",
                                "children": [("Combobox.textarea", {"sticky": "nswe"})],
                            },
                        )
                    ],
                },
            )
        ],
    )
    style.configure("Skipped.TCombobox", foreground="#94a3b8", padding=(6, 1, 6, 2))
    style.map("Skipped.TCombobox", foreground=[("disabled", "#94a3b8"), ("!disabled", "#94a3b8")])
