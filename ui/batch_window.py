import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import os
import glob
import posixpath
import stat
from pathlib import Path

from pipeline.discovery import _discover_mri_files

def find_mri_files(directory: str, recursive: bool = True) -> list[str]:
    return _discover_mri_files(directory, recursive=recursive)

def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

class BatchConfigWindow(tk.Toplevel):
    def __init__(self, parent, gui):
        super().__init__(parent)
        self.gui = gui
        self.title("Configure Batch MRI Files")
        self.geometry("800x600")
        self.transient(parent)
        self.grab_set()
        
        self.files_data = [] # List of dict: {"path": str, "size": str, "selected": bool}
        self.server_mode = self.gui.state.input_source.get() == "Server"
        self.ssh = None
        
        self.recursive_var = tk.BooleanVar(value=not self.gui.state.non_recursive.get())
        
        if self.server_mode:
            try:
                from remote.ssh_client import RemoteSSHClient
                ssh_config = self.gui._build_ssh_config()
                if ssh_config is None:
                    self.destroy()
                    return
                self.ssh = RemoteSSHClient(ssh_config, lambda _line: None)
                self.ssh.connect()
            except Exception as exc:
                messagebox.showerror("Server batch failed", f"Could not connect to server:\n\n{type(exc).__name__}: {exc}", parent=self)
                self.destroy()
                return

        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build_ui()
        self._scan_folder()
        
    def _build_ui(self):
        main_frame = ttk.Frame(self, padding=16)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Checkbox
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Checkbutton(top_frame, text="Scan recursively for MRI/DICOM inputs",
                        variable=self.recursive_var, command=self._scan_folder).pack(side=tk.LEFT)
                        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(btn_frame, text="Select X first files", command=self._select_x_first).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Select all", command=self._select_all).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(btn_frame, text="Unselect all", command=self._unselect_all).pack(side=tk.LEFT, padx=(10, 0))
        
        # Treeview
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.tree = ttk.Treeview(tree_frame, columns=("select", "path", "size"), show="headings", selectmode="none")
        self.tree.heading("select", text="Selected")
        self.tree.heading("path", text="File Path")
        self.tree.heading("size", text="File Size")
        self.tree.column("select", width=80, anchor=tk.CENTER)
        self.tree.column("path", width=550, anchor=tk.W)
        self.tree.column("size", width=100, anchor=tk.E)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        
        # Bottom Buttons
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X)
        ttk.Button(bottom_frame, text="Save", style="Accent.TButton", command=self._save).pack(side=tk.RIGHT, padx=(10, 0))
        ttk.Button(bottom_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
        
    def _scan_folder(self):
        directory = self.gui.state.input_path.get().strip()
        if self.server_mode:
            self._scan_server_folder(directory)
            return
        if not os.path.isdir(directory):
            self.files_data = []
            self._refresh_tree()
            return
            
        files = find_mri_files(directory, self.recursive_var.get())
        # Preserve selection if path already exists
        old_selected = {f["path"] for f in self.files_data if f["selected"]}
        # Also check gui.state.selected_files if this is first load
        if not self.files_data and self.gui.state.selected_files:
            old_selected.update(self.gui.state.selected_files)
            
        self.files_data = []
        for f in files:
            size_str = "Unknown"
            try:
                path = Path(f)
                if path.is_dir():
                    size_str = format_size(sum(child.stat().st_size for child in path.iterdir() if child.is_file()))
                else:
                    size_str = format_size(os.path.getsize(f))
            except Exception:
                pass
                
            selected = (f in old_selected) or (not old_selected and not self.gui.state.selected_files) # Default all true if no old selection
            self.files_data.append({
                "path": f,
                "size": size_str,
                "selected": selected
            })
            
        self._refresh_tree()

    def _is_mri_name(self, name: str) -> bool:
        return name.lower().endswith(('.mgz', '.nii', '.nii.gz', '.mgh', '.dcm', '.dicom', '.ima'))

    def _server_dir_contains_dicom(self, directory: str) -> tuple[bool, int]:
        assert self.ssh is not None
        total_size = 0
        try:
            for item in self.ssh.sftp.listdir_attr(directory):
                if item.filename.startswith("."):
                    continue
                if not stat.S_ISDIR(item.st_mode) and self._is_dicom_name(item.filename):
                    total_size += int(item.st_size or 0)
            return total_size > 0, total_size
        except OSError:
            return False, 0

    def _is_dicom_name(self, name: str) -> bool:
        return name.lower().endswith(('.dcm', '.dicom', '.ima'))

    def _scan_server_folder(self, directory: str):
        if self.ssh is None or not directory:
            self.files_data = []
            self._refresh_tree()
            return
        try:
            root = self.ssh.expand_path(directory)
            files = self._find_server_mri_files(root, self.recursive_var.get())
        except Exception as exc:
            messagebox.showerror("Server scan failed", f"Could not scan server folder:\n\n{type(exc).__name__}: {exc}", parent=self)
            self.files_data = []
            self._refresh_tree()
            return

        old_selected = {f["path"] for f in self.files_data if f["selected"]}
        if not self.files_data and self.gui.state.selected_files:
            old_selected.update(self.gui.state.selected_files)
        self.files_data = []
        for path, size in files:
            selected = (path in old_selected) or (not old_selected and not self.gui.state.selected_files)
            self.files_data.append({"path": path, "size": format_size(size), "selected": selected})
        self._refresh_tree()

    def _find_server_mri_files(self, directory: str, recursive: bool) -> list[tuple[str, int]]:
        assert self.ssh is not None
        results: list[tuple[str, int]] = []
        has_dicom, dicom_size = self._server_dir_contains_dicom(directory)
        if has_dicom:
            return [(directory, dicom_size)]
        attrs = self.ssh.sftp.listdir_attr(directory)
        for item in attrs:
            if item.filename.startswith("."):
                continue
            path = posixpath.join(directory, item.filename)
            is_dir = stat.S_ISDIR(item.st_mode)
            if is_dir and recursive:
                results.extend(self._find_server_mri_files(path, recursive))
            elif is_dir:
                has_child_dicom, child_size = self._server_dir_contains_dicom(path)
                if has_child_dicom:
                    results.append((path, child_size))
            elif not is_dir and self._is_mri_name(item.filename):
                results.append((path, int(item.st_size or 0)))
        return sorted(results, key=lambda item: item[0].lower())
        
    def _refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        for idx, f in enumerate(self.files_data):
            sel_text = "☑" if f["selected"] else "☐"
            self.tree.insert("", tk.END, iid=str(idx), values=(sel_text, f["path"], f["size"]))
            
    def _on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region == "cell":
            col = self.tree.identify_column(event.x)
            if col == "#1": # select column
                item_id = self.tree.identify_row(event.y)
                if item_id:
                    idx = int(item_id)
                    self.files_data[idx]["selected"] = not self.files_data[idx]["selected"]
                    self._refresh_tree()
                    
    def _select_x_first(self):
        x = simpledialog.askinteger("Select X first files", "Enter number of files to select:", parent=self, minvalue=1, maxvalue=len(self.files_data))
        if x is not None:
            self._unselect_all(refresh=False)
            for i in range(min(x, len(self.files_data))):
                self.files_data[i]["selected"] = True
            self._refresh_tree()
            
    def _select_all(self):
        for f in self.files_data:
            f["selected"] = True
        self._refresh_tree()
        
    def _unselect_all(self, refresh=True):
        for f in self.files_data:
            f["selected"] = False
        if refresh:
            self._refresh_tree()
            
    def _save(self):
        selected_paths = [f["path"] for f in self.files_data if f["selected"]]
        self.gui.state.selected_files = selected_paths
        self.gui.state.non_recursive.set(not self.recursive_var.get())
        self.gui._refresh_input_label()
        self._close()

    def _close(self):
        if self.ssh is not None:
            self.ssh.close()
            self.ssh = None
        self.destroy()
