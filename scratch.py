import tkinter as tk
from tkinter import ttk
import sv_ttk

def test():
    root = tk.Tk()
    sv_ttk.set_theme("light")
    
    style = ttk.Style()
    style.configure("Selected.TCheckbutton", background="#cbd5e1")
    style.configure("Unselected.TCheckbutton", background="#fafafa")
    
    f = tk.Frame(root, bg="#cbd5e1", padx=20, pady=20)
    f.pack()
    
    var = tk.BooleanVar()
    cb = ttk.Checkbutton(f, text="Selected Checkbox", style="Selected.TCheckbutton", variable=var)
    cb.pack()

    f2 = tk.Frame(root, bg="#fafafa", padx=20, pady=20)
    f2.pack()
    
    cb2 = ttk.Checkbutton(f2, text="Unselected Checkbox", style="Unselected.TCheckbutton", variable=var)
    cb2.pack()
    
    root.after(2000, root.destroy)
    root.mainloop()

if __name__ == "__main__":
    test()
