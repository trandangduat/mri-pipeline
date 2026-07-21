import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from pathlib import Path
import threading
import subprocess

from remote.remote_api import RemoteSSHClient, list_remote_directory
from pipeline.config import PROJECT_ROOT

def show_upload_dialog(gui):
    if not gui._server_connected():
        messagebox.showwarning("Connect Server", "Please connect to the server first.")
        return
    ssh_config = gui.jobs_ctrl._build_ssh_config()
    if ssh_config is None:
        return

    dialog = tk.Toplevel(gui.root)
    dialog.title("Upload input to server")
    dialog.geometry("1080x650")
    dialog.transient(gui.root)
    dialog.grab_set()

    ssh_holder: dict[str, RemoteSSHClient | None] = {"ssh": None}
    local_entries: list[dict] = []
    server_entries: list[dict] = []
    upload_running = {"value": False}

    def initial_local_dir() -> str:
        raw = gui.state.input_path.get().strip()
        if raw and ";" not in raw:
            path = Path(raw).expanduser()
            if path.is_file():
                return str(path.parent)
            if path.is_dir():
                return str(path)
        return str(PROJECT_ROOT)

    def initial_server_dir() -> str:
        raw = gui.state.input_path.get().strip()
        if gui.state.input_source.get() == "Server" and raw:
            first = raw.split(";", 1)[0].strip()
            if first and not first.endswith("/") and "." in posixpath.basename(first):
                return posixpath.dirname(first) or "~"
            return first
        return gui.state.remote_workspace.get().strip() or "~"

    local_path = tk.StringVar(value=initial_local_dir())
    server_path = tk.StringVar(value=initial_server_dir())
    status_text = tk.StringVar(value="Connecting to server...")
    progress_text = tk.StringVar(value="Ready")
    progress_percent_text = tk.StringVar(value="0%")

    top = ttk.Frame(dialog, padding=(12, 12, 12, 6))
    top.pack(fill=tk.X)
    start_button = ttk.Button(top, text="Start upload", style="Accent.TButton", state=tk.DISABLED)
    start_button.pack(side=tk.LEFT)
    ttk.Label(top, textvariable=progress_text, anchor=tk.W).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 8))
    ttk.Label(top, textvariable=progress_percent_text, width=6, anchor=tk.E).pack(side=tk.RIGHT)
    progress = ttk.Progressbar(dialog, mode="determinate", maximum=1, value=0)
    progress.pack(fill=tk.X, padx=12, pady=(0, 6))
    ttk.Label(dialog, textvariable=status_text, foreground="#64748b").pack(anchor=tk.W, padx=12, pady=(0, 8))

    panes = ttk.PanedWindow(dialog, orient=tk.HORIZONTAL)
    panes.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
    local_frame = ttk.Frame(panes, padding=8)
    server_frame = ttk.Frame(panes, padding=8)
    panes.add(local_frame, weight=1)
    panes.add(server_frame, weight=1)

    def build_browser(parent: ttk.Frame, title: str, variable: tk.StringVar, go_cmd, up_cmd, new_folder_cmd=None, selectmode=tk.BROWSE):
        ttk.Label(parent, text=title, font=("Inter", 10, "bold")).pack(anchor=tk.W, pady=(0, 6))
        row = ttk.Frame(parent)
        row.pack(fill=tk.X, pady=(0, 8))
        ttk.Entry(row, textvariable=variable).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(row, text="↵", width=3, command=go_cmd).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(row, text="↑", width=3, command=up_cmd).pack(side=tk.LEFT, padx=(0, 6))
        if new_folder_cmd is not None:
            ttk.Button(row, text="+ Folder", command=new_folder_cmd).pack(side=tk.LEFT)
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True)
        listing = tk.Listbox(list_frame, selectmode=selectmode, activestyle="dotbox")
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listing.yview)
        listing.configure(yscrollcommand=scroll.set)
        listing.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        return listing

    def is_mri_name(name: str) -> bool:
        return name.lower().endswith((".nii", ".nii.gz", ".mgz", ".mgh", ".dcm", ".dicom", ".ima"))

    def refresh_local(path_text: str | None = None) -> None:
        nonlocal local_entries
        path = Path(path_text or local_path.get().strip() or ".").expanduser()
        try:
            path = path.resolve()
            dirs = []
            files = []
            for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if child.name.startswith("."):
                    continue
                entry = {"name": child.name, "path": str(child), "is_dir": child.is_dir()}
                if child.is_dir():
                    dirs.append(entry)
                elif child.is_file():
                    files.append(entry)
            local_entries = [{"name": "..", "path": str(path.parent), "is_dir": True}, *dirs, *files]
            local_list.delete(0, tk.END)
            for entry in local_entries:
                prefix = "[D] " if entry["is_dir"] else "    "
                local_list.insert(tk.END, prefix + entry["name"])
            local_path.set(str(path))
            status_text.set("Select local files or DICOM folders to upload.")
        except Exception as exc:
            status_text.set(f"Local browse failed: {type(exc).__name__}: {exc}")

    def normalize_server_path(path_text: str) -> str:
        ssh = ssh_holder.get("ssh")
        path = path_text.strip() or "~"
        if ssh is not None:
            try:
                path = ssh.expand_path(path)
            except Exception:
                pass
        return posixpath.normpath(path) if path.startswith("/") else path

    def refresh_server(path_text: str | None = None) -> None:
        nonlocal server_entries
        ssh = ssh_holder.get("ssh")
        if ssh is None:
            return
        try:
            path = normalize_server_path(path_text or server_path.get())
            attrs = ssh.sftp.listdir_attr(path)
            dirs = []
            files = []
            for item in attrs:
                if item.filename.startswith("."):
                    continue
                entry = {"name": item.filename, "path": posixpath.join(path, item.filename), "is_dir": stat.S_ISDIR(item.st_mode)}
                if entry["is_dir"]:
                    dirs.append(entry)
                else:
                    files.append(entry)
            server_entries = [{"name": "..", "path": posixpath.dirname(path.rstrip("/")) or "/", "is_dir": True}, *sorted(dirs, key=lambda x: x["name"].lower()), *sorted(files, key=lambda x: x["name"].lower())]
            server_list.delete(0, tk.END)
            for entry in server_entries:
                prefix = "[D] " if entry["is_dir"] else "    "
                server_list.insert(tk.END, prefix + entry["name"])
            server_path.set(path)
            status_text.set("Choose the server destination folder.")
        except Exception as exc:
            status_text.set(f"Server browse failed: {type(exc).__name__}: {exc}")

    def create_server_folder() -> None:
        ssh = ssh_holder.get("ssh")
        if ssh is None:
            messagebox.showerror("Server not connected", "SSH server is not connected yet.", parent=dialog)
            return
        current = normalize_server_path(server_path.get())
        name = simpledialog.askstring("New server folder", "Folder name:", parent=dialog)
        if not name:
            return
        name = name.strip().strip("/")
        if not name or "/" in name or name in {".", ".."}:
            messagebox.showerror("Invalid folder name", "Folder name cannot be empty, '.', '..', or contain '/'.", parent=dialog)
            return
        new_path = posixpath.join(current, name)
        try:
            ssh.mkdir_p(new_path)
            refresh_server(new_path)
            status_text.set(f"Created folder: {new_path}")
        except Exception as exc:
            messagebox.showerror("Create folder failed", f"Could not create folder:\n\n{type(exc).__name__}: {exc}", parent=dialog)

    local_list = build_browser(
        local_frame,
        "Local folder",
        local_path,
        lambda: refresh_local(local_path.get()),
        lambda: refresh_local(str(Path(local_path.get()).expanduser().parent)),
        selectmode=tk.EXTENDED,
    )
    server_list = build_browser(
        server_frame,
        "Server folder",
        server_path,
        lambda: refresh_server(server_path.get()),
        lambda: refresh_server(posixpath.dirname(normalize_server_path(server_path.get()).rstrip("/")) or "/"),
        new_folder_cmd=create_server_folder,
    )

    def open_local(_event=None) -> None:
        selection = local_list.curselection()
        if selection and local_entries[selection[0]]["is_dir"]:
            refresh_local(local_entries[selection[0]]["path"])

    def open_server(_event=None) -> None:
        selection = server_list.curselection()
        if selection and server_entries[selection[0]]["is_dir"]:
            refresh_server(server_entries[selection[0]]["path"])

    def selected_local_inputs() -> list[Path]:
        inputs: list[Path] = []
        for idx in local_list.curselection():
            entry = local_entries[idx]
            if entry["name"] == "..":
                continue
            inputs.append(Path(entry["path"]))
        return inputs

    def upload_file_pairs(inputs: list[Path], dest_dir: str) -> tuple[list[tuple[Path, str]], list[str]]:
        pairs: list[tuple[Path, str]] = []
        remote_roots: list[str] = []
        for src in inputs:
            if src.is_dir():
                remote_root = posixpath.join(dest_dir, src.name)
                remote_roots.append(remote_root)
                for root, dirs, files in os.walk(src):
                    dirs[:] = [name for name in dirs if not name.startswith(".")]
                    for name in sorted(files):
                        if name.startswith("."):
                            continue
                        local_file = Path(root) / name
                        rel = local_file.relative_to(src).as_posix()
                        pairs.append((local_file, posixpath.join(remote_root, rel)))
            else:
                remote_file = posixpath.join(dest_dir, src.name)
                remote_roots.append(remote_file)
                pairs.append((src, remote_file))
        return pairs, remote_roots

    def preflight_upload(pairs: list[tuple[Path, str]], dest_dir: str) -> tuple[list[tuple[Path, str]], int] | None:
        ssh = ssh_holder.get("ssh")
        if ssh is None:
            return None
        ssh.mkdir_p(dest_dir)
        upload_items: list[tuple[Path, str]] = []
        skipped = 0
        overwrite_all: bool | None = None
        for src, remote_file in pairs:
            ssh.mkdir_p(posixpath.dirname(remote_file))
            exists = False
            try:
                ssh.sftp.stat(remote_file)
                exists = True
            except OSError:
                exists = False
            if exists:
                if overwrite_all is True:
                    upload_items.append((src, remote_file))
                    continue
                if overwrite_all is False:
                    skipped += 1
                    continue
                choice = gui._ask_upload_overwrite(remote_file)
                if choice == "cancel":
                    return None
                if choice == "yes_all":
                    overwrite_all = True
                    upload_items.append((src, remote_file))
                elif choice == "no_all":
                    overwrite_all = False
                    skipped += 1
                elif choice == "yes":
                    upload_items.append((src, remote_file))
                else:
                    skipped += 1
                    continue
            else:
                upload_items.append((src, remote_file))
        return upload_items, skipped

    def apply_uploaded_inputs(remote_paths: list[str], uploaded_dirs: bool) -> None:
        if not remote_paths:
            return
        gui.state.input_source.set("Server")
        if uploaded_dirs:
            gui.state.input_mode.set("dir")
            gui.state.selected_files = []
            gui.state.input_path.set(remote_paths[0] if len(remote_paths) == 1 else normalize_server_path(server_path.get()))
        elif len(remote_paths) == 1:
            gui.state.input_mode.set("file")
            gui.state.selected_files = remote_paths
            gui.state.input_path.set(remote_paths[0])
        else:
            gui.state.input_mode.set("files")
            gui.state.selected_files = remote_paths
            gui.state.input_path.set("; ".join(remote_paths))
        gui._input_source_paths["Server"] = gui.state.input_path.get().strip()
        gui._input_source_selected_files["Server"] = list(gui.state.selected_files)
        gui._last_input_source = "Server"
        gui._sync_input_source_controls()
        gui._refresh_input_label()
        gui._validate_configuration()

    def start_upload() -> None:
        if upload_running["value"]:
            return
        ssh = ssh_holder.get("ssh")
        if ssh is None:
            messagebox.showerror("Server not connected", "SSH server is not connected yet.", parent=dialog)
            return
        inputs = selected_local_inputs()
        if not inputs:
            messagebox.showwarning("No files selected", "Select one or more local files or DICOM folders to upload.", parent=dialog)
            return
        dest_dir = normalize_server_path(server_path.get())
        pairs, remote_paths = upload_file_pairs(inputs, dest_dir)
        uploaded_dirs = any(path.is_dir() for path in inputs)
        if not pairs:
            status_text.set("No files found to upload.")
            return
        preflight = preflight_upload(pairs, dest_dir)
        if preflight is None:
            status_text.set("Upload cancelled.")
            return
        upload_items, skipped = preflight
        if not upload_items:
            status_text.set("No files uploaded.")
            return
        upload_running["value"] = True
        gui._set_button_busy(start_button, True, "Uploading")
        progress.configure(maximum=len(pairs), value=skipped)
        percent = int((skipped / len(pairs)) * 100) if pairs else 0
        progress_text.set(f"Uploading {len(upload_items)} file(s), skipped {skipped}")
        progress_percent_text.set(f"{percent}%")

        def worker() -> None:
            uploaded: list[str] = []
            processed = skipped
            try:
                for src, remote_file in upload_items:
                    processed += 1
                    gui.root.after(0, lambda p=processed, name=src.name: (status_text.set(f"Uploading: {name}"), progress.configure(value=p), progress_text.set(f"{p} of {len(pairs)} files"), progress_percent_text.set(f"{int((p / len(pairs)) * 100)}%")))
                    ssh.sftp.put(str(src), remote_file)
                    uploaded.append(remote_file)
                gui.root.after(0, lambda: (progress.configure(value=len(pairs)), progress_text.set("Upload complete"), progress_percent_text.set("100%"), status_text.set(f"Uploaded {len(uploaded)} file(s)."), apply_uploaded_inputs(remote_paths, uploaded_dirs), refresh_server(dest_dir)))
            except Exception as exc:
                gui.root.after(0, lambda e=exc: (progress_text.set("Upload failed"), status_text.set(f"Upload failed: {type(e).__name__}: {e}")))
            finally:
                def finish() -> None:
                    upload_running["value"] = False
                    gui._set_button_busy(start_button, False)
                    if ssh_holder.get("ssh") is not None:
                        start_button.configure(state=tk.NORMAL)
                gui.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def connect_server() -> None:
        try:
            ssh = RemoteSSHClient(ssh_config, lambda _line: None)
            ssh.connect()
            ssh_holder["ssh"] = ssh
            refresh_server(server_path.get())
            start_button.configure(state=tk.NORMAL)
        except Exception as exc:
            status_text.set(f"SSH failed: {type(exc).__name__}: {exc}")

    def close() -> None:
        if upload_running["value"]:
            if not messagebox.askyesno("Upload running", "Close while upload is running?", parent=dialog):
                return
        ssh = ssh_holder.get("ssh")
        if ssh is not None:
            ssh.close()
            ssh_holder["ssh"] = None
        dialog.destroy()

    local_list.bind("<Double-Button-1>", open_local)
    server_list.bind("<Double-Button-1>", open_server)
    start_button.configure(command=start_upload)
    dialog.protocol("WM_DELETE_WINDOW", close)
    refresh_local(local_path.get())
    gui.root.after(50, connect_server)

def show_remote_output_browser(gui):
    if not gui._server_connected():
        messagebox.showwarning("Connect Server", "Please connect to the server first.")
        return
    ssh_config = gui.jobs_ctrl._build_ssh_config()
    if ssh_config is None:
        return
        
    dialog = tk.Toplevel(gui.root)
    dialog.title("Browse Server Output Location")
    dialog.geometry("760x520")
    dialog.transient(gui.root)
    dialog.grab_set()

    current_path = tk.StringVar(value=gui.state.server_output_dir.get().strip() or "~")
    status_text = tk.StringVar(value="Connecting...")
    selected: dict[str, str | None] = {"path": None}
    entries: list[dict] = []
    ssh_holder: dict[str, RemoteSSHClient | None] = {"ssh": None}

    top = ttk.Frame(dialog, padding=(12, 12, 12, 6))
    top.pack(fill=tk.X)
    ttk.Label(top, text="Server output path").pack(anchor=tk.W)
    path_row = ttk.Frame(top)
    path_row.pack(fill=tk.X, pady=(2, 6))
    ttk.Entry(path_row, textvariable=current_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

    body = ttk.Frame(dialog, padding=(12, 0, 12, 6))
    body.pack(fill=tk.BOTH, expand=True)
    listing = tk.Listbox(body, selectmode=tk.BROWSE, height=18, activestyle="dotbox")
    scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=listing.yview)
    listing.configure(yscrollcommand=scroll.set)
    listing.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)

    bottom = ttk.Frame(dialog, padding=(12, 0, 12, 12))
    bottom.pack(fill=tk.X)
    ttk.Label(bottom, textvariable=status_text, foreground="#64748b").pack(side=tk.LEFT, fill=tk.X, expand=True)

    def normalize_remote_path(path: str) -> str:
        path = path.strip() or "~"
        ssh = ssh_holder.get("ssh")
        if ssh is not None:
            try:
                path = ssh.expand_path(path)
            except Exception:
                pass
        return posixpath.normpath(path) if path.startswith("/") else path

    def load_dir(path: str) -> None:
        nonlocal entries
        ssh = ssh_holder.get("ssh")
        if ssh is None:
            return
        try:
            path = normalize_remote_path(path)
            attrs = ssh.sftp.listdir_attr(path)
            dirs = []
            for item in attrs:
                if item.filename.startswith("."):
                    continue
                if stat.S_ISDIR(item.st_mode):
                    dirs.append({"name": item.filename, "path": posixpath.join(path, item.filename)})
            
            entries = [{"name": "..", "path": posixpath.dirname(path.rstrip("/")) or "/"}] + sorted(dirs, key=lambda x: x["name"].lower())
            listing.delete(0, tk.END)
            for row in entries:
                listing.insert(tk.END, "[D] " + row["name"])
            current_path.set(path)
            status_text.set("Select a folder for output.")
        except Exception as exc:
            status_text.set(f"Browse failed: {type(exc).__name__}: {exc}")

    def connect_and_load() -> None:
        try:
            ssh = RemoteSSHClient(ssh_config, lambda _line: None)
            ssh.connect()
            ssh_holder["ssh"] = ssh
            load_dir(current_path.get())
        except Exception as exc:
            status_text.set(f"SSH failed: {type(exc).__name__}: {exc}")
            
    def create_new_folder() -> None:
        ssh = ssh_holder.get("ssh")
        if ssh is None:
            return
        from tkinter import simpledialog
        current = normalize_remote_path(current_path.get())
        name = simpledialog.askstring("New folder", "Folder name:", parent=dialog)
        if not name:
            return
        name = name.strip().strip("/")
        if not name or "/" in name or name in {".", ".."}:
            messagebox.showerror("Invalid name", "Invalid folder name.", parent=dialog)
            return
        new_path = posixpath.join(current, name)
        try:
            ssh.mkdir_p(new_path)
            load_dir(new_path)
            status_text.set(f"Created folder: {new_path}")
        except Exception as exc:
            messagebox.showerror("Error", f"Could not create folder:\n{exc}", parent=dialog)

    def open_selected(_event=None) -> None:
        selection = listing.curselection()
        if not selection:
            return
        load_dir(str(entries[selection[0]]["path"]))

    def choose() -> None:
        path = normalize_remote_path(current_path.get())
        selection = listing.curselection()
        if selection:
            # User selected a specific folder in the list
            path = str(entries[selection[0]]["path"])
        selected["path"] = path
        dialog.destroy()

    def close() -> None:
        dialog.destroy()

    def on_destroy(_event=None) -> None:
        ssh = ssh_holder.get("ssh")
        if ssh is not None:
            ssh.close()
            ssh_holder["ssh"] = None

    ttk.Button(path_row, text="Go", command=lambda: load_dir(current_path.get())).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(path_row, text="Up", command=lambda: load_dir(posixpath.dirname(normalize_remote_path(current_path.get()).rstrip("/")) or "/")).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(path_row, text="+ Folder", command=create_new_folder).pack(side=tk.LEFT)
    
    listing.bind("<Double-Button-1>", open_selected)
    ttk.Button(bottom, text="Cancel", command=close).pack(side=tk.RIGHT, padx=(8, 0))
    ttk.Button(bottom, text="Select", style="Accent.TButton", command=choose).pack(side=tk.RIGHT)
    
    dialog.protocol("WM_DELETE_WINDOW", close)
    dialog.bind("<Destroy>", on_destroy, add="+")
    gui.root.after(50, connect_and_load)
    gui.root.wait_window(dialog)
    
    if selected.get("path"):
        gui.state.server_output_dir.set(selected["path"])

def show_remote_input_browser(gui):
    if not gui._server_connected():
        messagebox.showwarning("Connect Server", "Please connect to the server first.")
        return
    ssh_config = gui.jobs_ctrl._build_ssh_config()
    if ssh_config is None:
        return
    mode = gui.state.input_mode.get()
    dialog = tk.Toplevel(gui.root)
    dialog.title("Browse server input")
    dialog.geometry("760x520")
    dialog.transient(gui.root)
    dialog.grab_set()

    current_path = tk.StringVar(value=gui.state.input_path.get().strip() or "~")
    status_text = tk.StringVar(value="Connecting...")
    selected: dict[str, list[str] | str] = {"paths": []}
    entries: list[dict] = []
    ssh_holder: dict[str, RemoteSSHClient | None] = {"ssh": None}

    top = ttk.Frame(dialog, padding=(12, 12, 12, 6))
    top.pack(fill=tk.X)
    ttk.Label(top, text="Server path").pack(anchor=tk.W)
    path_row = ttk.Frame(top)
    path_row.pack(fill=tk.X, pady=(2, 6))
    ttk.Entry(path_row, textvariable=current_path).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

    body = ttk.Frame(dialog, padding=(12, 0, 12, 6))
    body.pack(fill=tk.BOTH, expand=True)
    selectmode = tk.EXTENDED if mode == "files" else tk.BROWSE
    listing = tk.Listbox(body, selectmode=selectmode, height=18, activestyle="dotbox")
    scroll = ttk.Scrollbar(body, orient=tk.VERTICAL, command=listing.yview)
    listing.configure(yscrollcommand=scroll.set)
    listing.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)

    bottom = ttk.Frame(dialog, padding=(12, 0, 12, 12))
    bottom.pack(fill=tk.X)
    ttk.Label(bottom, textvariable=status_text, foreground="#64748b").pack(side=tk.LEFT, fill=tk.X, expand=True)

    def normalize_remote_path(path: str) -> str:
        path = path.strip() or "~"
        ssh = ssh_holder.get("ssh")
        if ssh is not None:
            try:
                path = ssh.expand_path(path)
            except Exception:
                pass
        return posixpath.normpath(path) if path.startswith("/") else path

    def is_mri_name(name: str) -> bool:
        lower = name.lower()
        return lower.endswith((".nii", ".nii.gz", ".mgz", ".mgh", ".dcm", ".dicom", ".ima"))

    def is_dicom_name(name: str) -> bool:
        return name.lower().endswith((".dcm", ".dicom", ".ima"))

    def dir_contains_dicom(path: str) -> bool:
        ssh = ssh_holder.get("ssh")
        if ssh is None:
            return False
        try:
            for item in ssh.sftp.listdir_attr(path):
                if item.filename.startswith("."):
                    continue
                if not stat.S_ISDIR(item.st_mode) and is_dicom_name(item.filename):
                    return True
        except OSError:
            return False
        return False

    def load_dir(path: str) -> None:
        nonlocal entries
        ssh = ssh_holder.get("ssh")
        if ssh is None:
            return
        try:
            path = normalize_remote_path(path)
            attrs = ssh.sftp.listdir_attr(path)
            dirs = []
            files = []
            for item in attrs:
                if item.filename.startswith("."):
                    continue
                row = {"name": item.filename, "path": posixpath.join(path, item.filename), "is_dir": stat.S_ISDIR(item.st_mode)}
                if row["is_dir"]:
                    dirs.append(row)
                elif mode != "dir" and is_mri_name(item.filename):
                    files.append(row)
            entries = [{"name": "..", "path": posixpath.dirname(path.rstrip("/")) or "/", "is_dir": True}, *sorted(dirs, key=lambda x: x["name"].lower()), *sorted(files, key=lambda x: x["name"].lower())]
            listing.delete(0, tk.END)
            for row in entries:
                prefix = "[D] " if row["is_dir"] else "    "
                listing.insert(tk.END, prefix + row["name"])
            current_path.set(path)
            status_text.set("Select a folder." if mode == "dir" else "Double-click folders to browse; select MRI file(s) or DICOM folder(s).")
        except Exception as exc:
            status_text.set(f"Browse failed: {type(exc).__name__}: {exc}")

    def connect_and_load() -> None:
        try:
            ssh = RemoteSSHClient(ssh_config, lambda _line: None)
            ssh.connect()
            ssh_holder["ssh"] = ssh
            load_dir(current_path.get())
        except Exception as exc:
            status_text.set(f"SSH failed: {type(exc).__name__}: {exc}")

    def open_selected(_event=None) -> None:
        selection = listing.curselection()
        if not selection:
            return
        row = entries[selection[0]]
        if row["is_dir"]:
            load_dir(str(row["path"]))

    def choose() -> None:
        path = normalize_remote_path(current_path.get())
        selection = listing.curselection()
        chosen: list[str] = []
        if mode == "dir":
            if selection and entries[selection[0]]["is_dir"]:
                path = str(entries[selection[0]]["path"])
            selected["paths"] = [path]
        else:
            for idx in selection:
                row = entries[idx]
                if not row["is_dir"]:
                    chosen.append(str(row["path"]))
                elif dir_contains_dicom(str(row["path"])):
                    chosen.append(str(row["path"]))
            if not chosen and mode == "file":
                chosen = [path]
            selected["paths"] = chosen
        dialog.destroy()

    def close() -> None:
        dialog.destroy()

    def on_destroy(_event=None) -> None:
        ssh = ssh_holder.get("ssh")
        if ssh is not None:
            ssh.close()
            ssh_holder["ssh"] = None

    ttk.Button(path_row, text="Go", command=lambda: load_dir(current_path.get())).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(path_row, text="Up", command=lambda: load_dir(posixpath.dirname(normalize_remote_path(current_path.get()).rstrip("/")) or "/")).pack(side=tk.LEFT)
    listing.bind("<Double-Button-1>", open_selected)
    ttk.Button(bottom, text="Cancel", command=close).pack(side=tk.RIGHT, padx=(8, 0))
    ttk.Button(bottom, text="Select", style="Accent.TButton", command=choose).pack(side=tk.RIGHT)
    dialog.protocol("WM_DELETE_WINDOW", close)
    dialog.bind("<Destroy>", on_destroy, add="+")
    gui.root.after(50, connect_and_load)
    gui.root.wait_window(dialog)

    paths = list(selected.get("paths") or [])
    if not paths:
        return
    if mode == "file":
        gui.state.selected_files = [paths[0]]
        gui.state.input_path.set(paths[0])
    elif mode == "files":
        gui.state.selected_files = paths
        gui.state.input_path.set("; ".join(paths))
    else:
        gui.state.selected_files = []
        gui.state.input_path.set(paths[0])
    gui._input_source_paths[gui.state.input_source.get()] = gui.state.input_path.get().strip()
    gui._input_source_selected_files[gui.state.input_source.get()] = list(gui.state.selected_files)
    gui._refresh_input_label()

