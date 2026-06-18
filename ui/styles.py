import tkinter as tk
from tkinter import ttk
import sv_ttk
import darkdetect

def setup_styles(root) -> None:
    # Thiết lập giao diện Light Mode làm mặc định
    sv_ttk.set_theme("light")
    
    # Set màu nền chuẩn của sv-ttk light theme cho cửa sổ gốc 
    # để tránh bị lộ nền của Tkinter mặc định
    root.configure(bg="#fafafa")
    
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
    
    # Define custom ttk styles here for Card and Accent buttons
    style.configure("Card.TFrame", relief="solid", borderwidth=1)
