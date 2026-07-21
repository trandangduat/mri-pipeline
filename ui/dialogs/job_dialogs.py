from __future__ import annotations

from remote.remote_runner import RemoteRunner, RemoteRunConfig
from ui.formatters import truncate_middle
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from tkinter import filedialog
from pathlib import Path
import threading
import json
import uuid
import stat
import posixpath
import urllib.request
import tarfile

from pipeline.config import PROJECT_ROOT
from remote.ssh_client import RemoteSSHClient

def show_attach_job_dialog(ctrl) -> None:
    target = ctrl.gui.state.run_target.get()
    known_jobs = ctrl._known_jobs()
    jobs: list[dict] = []
    load_remote_jobs = False
    ssh_config = None
    workspace = ctrl.gui.state.remote_workspace.get().strip() or "~/mri-remote-jobs"
    remote_python = ctrl.gui.state.remote_python.get().strip() or "python3"
    output_dir = ctrl.gui.state.output_dir.get().strip()
    if target == "Server":
        if not ctrl.gui.remote_ctrl._require_remote_connection("attaching remote jobs"):
            return
        if not ctrl._ensure_remote_auth_for_job_action("Attach job"):
            return
        ssh_config = ctrl._build_ssh_config()
        if ssh_config is None:
            return
        jobs = [
            entry for entry in known_jobs
            if entry.get("target") == "Server"
            and ctrl._same_remote_server(entry, ssh_config, workspace)
        ]
        load_remote_jobs = True
    elif target == "Local":
        jobs = [entry for entry in known_jobs if entry.get("target") == "Local"]
        jobs = ctrl._merge_job_lists(jobs, ctrl._running_local_jobs())
    if not jobs and not load_remote_jobs:
        ctrl._attach_manual_job_dialog()
        return

    dialog = tk.Toplevel(ctrl.gui.root)
    dialog.title("Background Jobs")
    dialog.geometry("980x560")
    dialog.minsize(900, 520)
    dialog.transient(ctrl.gui.root)
    dialog.grab_set()

    if target == "Server" and ssh_config is not None:
        server_label = f"Remote server: {ssh_config.username}@{ssh_config.host}:{int(ssh_config.port)} | workspace: {workspace}"
        server_icon = ctrl.gui._make_icon("success") if getattr(ctrl, "_make_icon", None) is not None else None
    else:
        server_label = "Current target: Local jobs"
        server_icon = ctrl.gui._make_icon("pending") if getattr(ctrl, "_make_icon", None) is not None else None
    server_row = ttk.Frame(dialog)
    server_row.pack(anchor=tk.W, fill=tk.X, padx=12, pady=(12, 6))
    if server_icon is not None:
        ttk.Label(server_row, image=server_icon).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Label(server_row, text=server_label, foreground="#1e293b", font=("Inter", 10, "bold")).pack(side=tk.LEFT, fill=tk.X, expand=True)

    selected_job_ids: set[str] = set()
    selection_initialized = False
    row_widgets: list[dict] = []
    deleted_job_ids: set[str] = set()

    selection_bar = ttk.Frame(dialog)
    selection_bar.pack(fill=tk.X, padx=16, pady=(0, 4))
    ttk.Button(selection_bar, text="Select All", command=lambda: (selected_job_ids.update(ctrl._job_identity(job) for job in jobs), render_jobs())).pack(side=tk.LEFT)
    ttk.Button(selection_bar, text="Unselect All", command=lambda: (selected_job_ids.clear(), render_jobs())).pack(side=tk.LEFT, padx=(8, 0))

    table_outer = ttk.Frame(dialog)
    table_outer.pack(fill=tk.BOTH, expand=True, padx=16, pady=(4, 8))
    table_canvas = tk.Canvas(table_outer, highlightthickness=0, bg="#ffffff")
    table_scroll = ttk.Scrollbar(table_outer, orient=tk.VERTICAL, command=table_canvas.yview)
    table = ttk.Frame(table_canvas)
    table_window = table_canvas.create_window((0, 0), window=table, anchor=tk.NW)

    def sync_table_region(_event=None) -> None:
        table_canvas.configure(scrollregion=table_canvas.bbox("all"))

    def sync_table_width(event) -> None:
        table_canvas.itemconfigure(table_window, width=event.width)

    table.bind("<Configure>", sync_table_region)
    table_canvas.bind("<Configure>", sync_table_width)
    table_canvas.configure(yscrollcommand=table_scroll.set)
    table_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    table_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    table.columnconfigure(1, minsize=110)
    table.columnconfigure(2, weight=3, minsize=420)
    table.columnconfigure(3, weight=2, minsize=330)
    ttk.Label(table, text="", width=4).grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=(0, 6))
    ttk.Label(table, text="State", font=("Inter", 9, "bold")).grid(row=0, column=1, sticky=tk.W, padx=8, pady=(0, 6))
    ttk.Label(table, text="Job", font=("Inter", 9, "bold")).grid(row=0, column=2, sticky=tk.W, padx=8, pady=(0, 6))
    ttk.Label(table, text="Output", font=("Inter", 9, "bold")).grid(row=0, column=3, sticky=tk.W, padx=8, pady=(0, 6))
    ttk.Separator(table, orient=tk.HORIZONTAL).grid(row=1, column=0, columnspan=4, sticky=tk.EW, pady=(0, 4))

    status_text = tk.StringVar(value="Loading remote jobs..." if load_remote_jobs else "")
    status_label = ttk.Label(dialog, textvariable=status_text, foreground="#64748b")
    if status_text.get():
        status_label.pack(anchor=tk.W, padx=16, pady=(0, 4))

    def set_status(text: str) -> None:
        status_text.set(text)
        if text:
            if not status_label.winfo_ismapped():
                status_label.pack(anchor=tk.W, padx=16, pady=(0, 4))
        else:
            status_label.pack_forget()

    def selected_jobs() -> list[dict]:
        return [job for job in jobs if ctrl._job_identity(job) in selected_job_ids]

    def selected_job() -> dict | None:
        selected = selected_jobs()
        return selected[0] if selected else None

    def set_selected(identity: str, selected: bool) -> None:
        if selected:
            selected_job_ids.add(identity)
        else:
            selected_job_ids.discard(identity)
        render_jobs()

    def select_one(identity: str) -> None:
        selected_job_ids.clear()
        selected_job_ids.add(identity)
        render_jobs()

    def attach_selected() -> None:
        job = selected_job()
        if not job:
            return
        dialog.destroy()
        ctrl._attach_registry_job(job)

    def state_color(state: str) -> str:
        return {
            "running": "#2563eb",
            "completed": "#16a34a",
            "success": "#16a34a",
            "failed": "#dc2626",
            "missing": "#dc2626",
            "paused": "#f97316",
            "unknown": "#64748b",
        }.get(state.lower(), "#475569")

    def draw_checkbox(canvas: tk.Canvas, selected: bool, bg: str) -> None:
        canvas.configure(bg=bg)
        canvas.delete("all")
        fill = "#0f73d1" if selected else bg
        outline = "#0f73d1" if selected else "#94a3b8"
        canvas.create_rectangle(3, 3, 21, 21, outline=outline, fill=fill, width=1)
        if selected:
            canvas.create_text(12, 12, text="✓", fill="#ffffff", font=("Inter", 11, "bold"))

    def render_jobs() -> None:
        nonlocal selection_initialized
        for widgets in row_widgets:
            for widget in reversed(widgets.get("widgets", [])):
                try:
                    widget.destroy()
                except tk.TclError:
                    pass
        row_widgets.clear()
        if jobs and not selection_initialized:
            selected_job_ids.add(ctrl._job_identity(jobs[0]))
            selection_initialized = True
        for idx, job in enumerate(jobs):
            identity = ctrl._job_identity(job)
            job_label = job.get("remote_job_dir") or job.get("job_dir") or job.get("job_id", "")
            row = 2 + idx * 2
            selected = identity in selected_job_ids
            bg = "#cbd5e1" if selected else "#fafafa"
            cells = []
            for col in range(4):
                cell = tk.Frame(table, padx=6, pady=5, bg=bg)
                cell.grid(row=row, column=col, sticky=tk.NSEW, padx=0, pady=1)
                cell.bind("<Button-1>", lambda _event, ident=identity: select_one(ident))
                cell.bind("<Double-1>", lambda _event, ident=identity: (select_one(ident), attach_selected()))
                cells.append(cell)
            check = tk.Canvas(cells[0], width=24, height=24, bg=bg, highlightthickness=0, bd=0)
            draw_checkbox(check, selected, bg)
            check.bind("<Button-1>", lambda _event, ident=identity, is_selected=selected: set_selected(ident, not is_selected))
            check.pack(anchor=tk.W)
            raw_state = str(job.get("state", ""))
            state_label = tk.Label(cells[1], text=raw_state, anchor=tk.W, bg=bg, fg=state_color(raw_state), font=("Inter", 9, "bold"))
            state_label.pack(fill=tk.BOTH, expand=True)
            job_label_widget = tk.Label(cells[2], text=str(job_label), anchor=tk.W, bg=bg, fg="#475569")
            job_label_widget.pack(fill=tk.BOTH, expand=True)
            output_label = tk.Label(cells[3], text=str(job.get("effective_output_dir") or job.get("output_dir", "")), anchor=tk.W, bg=bg, fg="#475569")
            output_label.pack(fill=tk.BOTH, expand=True)
            for label in (state_label, job_label_widget, output_label):
                label.bind("<Button-1>", lambda _event, ident=identity: select_one(ident))
                label.bind("<Double-1>", lambda _event, ident=identity: (select_one(ident), attach_selected()))
            sep = ttk.Separator(table, orient=tk.HORIZONTAL)
            sep.grid(row=row + 1, column=0, columnspan=4, sticky=tk.EW, pady=(2, 2))
            row_widgets.append({"widgets": [*cells, check, state_label, job_label_widget, output_label, sep]})

    render_jobs()

    buttons = ttk.Frame(dialog)
    buttons.pack(fill=tk.X, padx=16, pady=(6, 14))

    def action_button(parent: ttk.Frame, text: str, command, icon_name: str, style: str | None = None, side: str = tk.LEFT, padx=0, icon_color: str | None = None) -> ttk.Button:
        icon = ctrl.gui._make_icon(icon_name, icon_color) if getattr(ctrl, "_make_icon", None) is not None else None
        options = {"text": f" {text}" if icon is not None else text, "command": command}
        if style:
            options["style"] = style
        if icon is not None:
            options.update({"image": icon, "compound": tk.LEFT})
        button = ttk.Button(parent, **options)
        button.pack(side=side, padx=padx)
        return button

    def delete_selected() -> None:
        nonlocal jobs
        selected = selected_jobs()
        if not selected:
            return
        labels = [job.get("remote_job_dir") or job.get("job_dir") or job.get("job_id", "selected job") for job in selected]
        if not messagebox.askyesno("Delete jobs", f"Delete {len(selected)} selected job(s) and their folders?\n\n" + "\n".join(labels)):
            return
        deleted = 0
        for job in selected:
            if ctrl._delete_registry_job(job):
                identity = ctrl._job_identity(job)
                deleted_job_ids.add(identity)
                selected_job_ids.discard(identity)
                jobs = [entry for entry in jobs if ctrl._job_identity(entry) != identity]
                deleted += 1
        set_status(f"Deleted {deleted} job(s).")
        if jobs:
            render_jobs()
        else:
            dialog.destroy()

    def download_selected() -> None:
        selected = selected_jobs()
        if not selected:
            return
        dialog.destroy()
        ctrl._download_registry_jobs(selected)

    action_button(buttons, "Attach", attach_selected, "pin", style="Accent.TButton", icon_color="#ffffff")
    action_button(buttons, "Download Outputs", download_selected, "download", padx=(8, 0))
    action_button(buttons, "Delete", delete_selected, "trash", padx=(8, 0))
    action_button(buttons, "Manual Attach", lambda: (dialog.destroy(), ctrl._attach_manual_job_dialog()), "load", padx=(8, 0))

    if load_remote_jobs and ssh_config is not None:
        def worker() -> None:
            remote_jobs: list[dict] = []
            error: Exception | None = None
            try:
                runner = RemoteRunner(
                    RemoteRunConfig(
                        ssh=ssh_config,
                        remote_workspace=workspace,
                        remote_python=remote_python,
                        output_dir=output_dir,
                    ),
                    on_log=lambda _line: None,
                )
                listed_jobs = [job for job in runner.list_background_jobs() if job.get("state") == "running"]
                registry_by_dir = {
                    str(entry.get("remote_job_dir")): entry
                    for entry in list(jobs)
                    if entry.get("target") == "Server"
                    and ctrl._same_remote_server(entry, ssh_config, workspace)
                }
                for remote_job in listed_jobs:
                    remote_dir = str(remote_job.get("remote_job_dir", ""))
                    entry = dict(registry_by_dir.get(remote_dir, {}))
                    entry.update(remote_job)
                    entry["target"] = "Server"
                    entry["remote_job_dir"] = remote_dir
                    entry.setdefault("output_dir", output_dir)
                    entry["remote"] = {
                        "host": ssh_config.host,
                        "port": int(ssh_config.port),
                        "username": ssh_config.username,
                        "key_path": ssh_config.key_path,
                        "workspace": workspace,
                        "python": remote_python,
                    }
                    remote_jobs.append(entry)
            except Exception as exc:
                error = exc

            def finish() -> None:
                nonlocal jobs, load_remote_jobs
                if not dialog.winfo_exists():
                    return
                load_remote_jobs = False
                if error is not None:
                    set_status(f"Remote job scan failed: {type(error).__name__}: {error}")
                    render_jobs()
                    return
                filtered_remote_jobs = [job for job in remote_jobs if ctrl._job_identity(job) not in deleted_job_ids]
                jobs = ctrl._merge_job_lists(jobs, filtered_remote_jobs)
                set_status(f"Loaded {len(filtered_remote_jobs)} running remote job(s)." if filtered_remote_jobs else "")
                render_jobs()

            ctrl.gui.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

def show_resume_job_dialog(ctrl, jobs: list[dict]) -> None:
    dialog = tk.Toplevel(ctrl.gui.root)
    dialog.title("Resume Background Job")
    dialog.geometry("900x420")
    dialog.transient(ctrl.gui.root)
    dialog.grab_set()

    ttk.Label(dialog, text="Select a previous job to resume in the same job/output directory.").pack(anchor=tk.W, padx=12, pady=(12, 6))
    columns = ("target", "state", "job", "output")
    tree = ttk.Treeview(dialog, columns=columns, show="headings", height=12)
    for col, text, width in (
        ("target", "Target", 80),
        ("state", "State", 90),
        ("job", "Job", 360),
        ("output", "Output", 300),
    ):
        tree.heading(col, text=text)
        tree.column(col, width=width, anchor=tk.W)
    tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

    item_to_job: dict[str, dict] = {}
    for idx, job in enumerate(jobs):
        job_label = job.get("remote_job_dir") or job.get("job_dir") or job.get("job_id", "")
        item = tree.insert("", tk.END, values=(job.get("target", ""), job.get("state", ""), job_label, job.get("effective_output_dir") or job.get("output_dir", "")))
        item_to_job[item] = job
        if idx == 0:
            tree.selection_set(item)

    def selected_job() -> dict | None:
        selection = tree.selection()
        return item_to_job.get(selection[0]) if selection else None

    def resume_selected() -> None:
        job = selected_job()
        if not job:
            return
        dialog.destroy()
        ctrl._resume_registry_job(job)

    buttons = ttk.Frame(dialog)
    buttons.pack(fill=tk.X, padx=12, pady=(4, 12))
    ttk.Button(buttons, text="Resume Selected", style="Accent.TButton", command=resume_selected).pack(side=tk.LEFT)
    ttk.Button(buttons, text="View / Attach", command=lambda: (dialog.destroy(), ctrl._attach_registry_job(selected_job())) if selected_job() else None).pack(side=tk.LEFT, padx=(8, 0))
    ttk.Button(buttons, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)
    tree.bind("<Double-1>", lambda _event: resume_selected())

def show_upload_remote_job_dialog(ctrl, runner: RemoteRunner) -> bool:
    dialog = tk.Toplevel(ctrl.gui.root)
    dialog.title("Copy files to remote server")
    dialog.geometry("760x500")
    dialog.transient(ctrl.gui.root)
    dialog.grab_set()

    header = ttk.Frame(dialog, padding=(14, 14, 14, 8))
    header.pack(fill=tk.X)
    ttk.Label(header, text="Copying files to remote server", font=("Inter", 12, "bold")).pack(anchor=tk.W)
    ttk.Label(
        header,
        text="Shared pipeline code is reused from the remote workspace when available. This job copies run configuration and license files; MRI inputs must already be selected from server paths.",
        wraplength=720,
    ).pack(anchor=tk.W, pady=(4, 0))

    current_var = tk.StringVar(value="Preparing remote connection...")
    count_var = tk.StringVar(value="Files copied: 0")
    current_row = ttk.Frame(dialog)
    current_row.pack(fill=tk.X, padx=14, pady=(4, 2))
    ctrl._remote_upload_spinner_label = ttk.Label(current_row, image=ctrl.gui._spinner_frame() or "", width=2)
    ctrl._remote_upload_spinner_label.pack(side=tk.LEFT, padx=(0, 8))
    ttk.Label(current_row, textvariable=current_var, font=("Inter", 10, "bold")).pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Label(dialog, textvariable=count_var).pack(anchor=tk.W, padx=14, pady=(0, 8))

    progress = ttk.Progressbar(dialog, mode="indeterminate")
    progress.pack(fill=tk.X, padx=14, pady=(0, 10))
    progress.start(10)

    log = tk.Text(dialog, wrap=tk.WORD, height=15, font=("Inter", 10), state=tk.DISABLED)
    scroll = ttk.Scrollbar(dialog, orient=tk.VERTICAL, command=log.yview)
    log.configure(yscrollcommand=scroll.set)
    log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(14, 0), pady=(0, 14))
    scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 14), pady=(0, 14))

    state = {"ok": False, "done": False, "files": 0}
    old_log = runner.on_log

    def append_line(line: str) -> None:
        if line.startswith("Uploading file:"):
            state["files"] += 1
            count_var.set(f"Files copied: {state['files']}")
            current_var.set("Copying " + truncate_middle(line.split("->", 1)[0].replace("Uploading file:", "").strip(), 70))
        elif line.startswith("Remote job:"):
            current_var.set("Creating remote job workspace...")
        elif line.startswith("Using shared remote pipeline code:"):
            current_var.set("Using shared remote pipeline code.")
        elif line.startswith("Uploading shared pipeline code once:"):
            current_var.set("Copying shared pipeline code for first use...")
        elif line.endswith("...") or line.endswith("complete."):
            current_var.set(line)
        log.configure(state=tk.NORMAL)
        log.insert(tk.END, line + "\n")
        log.see(tk.END)
        log.configure(state=tk.DISABLED)

    def worker() -> None:
        ok = True
        try:
            runner.on_log = lambda line: ctrl.gui.root.after(0, lambda l=line: append_line(l))
            runner.upload_job()
        except Exception as exc:
            ok = False
            err_msg = f"REMOTE UPLOAD ERROR: {type(exc).__name__}: {exc}"
            ctrl.gui.root.after(0, lambda m=err_msg: append_line(m))
            ctrl.gui.root.after(0, lambda: current_var.set("Copy failed. Check the log below."))
        finally:
            runner.on_log = old_log
            state["ok"] = ok
            state["done"] = True
            ctrl.gui.root.after(0, lambda: setattr(ctrl, "_remote_upload_spinner_label", None))
            ctrl.gui.root.after(0, progress.stop)
            if ok:
                ctrl.gui.root.after(0, lambda: current_var.set("Copy complete. Starting remote job..."))
                ctrl.gui.root.after(250, dialog.destroy)
            else:
                ctrl.gui.root.after(0, lambda: ttk.Button(dialog, text="Close", command=dialog.destroy).pack(anchor=tk.E, padx=14, pady=(0, 14)))

    threading.Thread(target=worker, daemon=True).start()
    ctrl.gui.root.wait_window(dialog)
    return state["ok"]
