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
import time

from pipeline.config import PROJECT_ROOT
from remote.ssh_client import RemoteSSHClient
from ui.events import EVENT_LOG_MESSAGE, ui_events

def show_attach_job_dialog(ctrl) -> None:
    target = ctrl.gui.state.run_target.get()
    registry = ctrl.gui.registry_ctrl

    def job_order_value(job: dict) -> float:
        try:
            return float(job.get("started_at") or 0)
        except (TypeError, ValueError):
            pass
        label = Path(str(job.get("remote_job_dir") or job.get("job_dir") or job.get("job_id") or "")).name
        parts = label.split("_")
        if len(parts) >= 3 and parts[-2].isdigit() and parts[-1].isdigit():
            try:
                return float(parts[-2] + parts[-1])
            except ValueError:
                return 0.0
        return 0.0

    def stable_job_order(items: list[dict]) -> list[dict]:
        return sorted(items, key=lambda job: (-job_order_value(job), registry._job_identity(job)))

    known_jobs = registry._known_jobs()
    jobs: list[dict] = []
    load_remote_jobs = False
    ssh_config = None
    workspace = ctrl.gui.state.remote_workspace.get().strip() or "~/mri-remote-jobs"
    remote_python = ctrl.gui.state.remote_python.get().strip() or "python3"
    output_dir = ctrl.gui.state.output_dir.get().strip()
    if target == "Server":
        if not ctrl.gui.remote_ctrl._require_remote_connection("attaching remote jobs"):
            return
        if not ctrl.ensure_remote_auth_for_job_action("Attach job"):
            return
        ssh_config = ctrl.build_ssh_config()
        if ssh_config is None:
            return
        jobs = [
            entry for entry in known_jobs
            if entry.get("target") == "Server"
            and registry._same_remote_server(entry, ssh_config, workspace)
        ]
        jobs = stable_job_order(jobs)
        load_remote_jobs = True
    elif target == "Local":
        jobs = [entry for entry in known_jobs if entry.get("target") == "Local"]
        jobs = registry._merge_job_lists(jobs, registry._running_local_jobs())
        jobs = stable_job_order(jobs)
    if not jobs and not load_remote_jobs:
        ctrl._attach_manual_job_dialog()
        return

    dialog = tk.Toplevel(ctrl.gui.root)
    dialog.title("Background Jobs")
    dialog.geometry("1100x760")
    dialog.minsize(980, 680)
    dialog.transient(ctrl.gui.root)
    dialog.grab_set()

    selected_job_ids: set[str] = set()
    selection_initialized = False
    row_widgets: list[dict] = []
    deleted_job_ids: set[str] = set()
    selection_summary_var = tk.StringVar(value="No jobs selected.")

    completed_count_var = tk.StringVar(value="0")
    running_count_var = tk.StringVar(value="0")
    failed_count_var = tk.StringVar(value="0")
    select_all_var = tk.BooleanVar(value=False)

    if target == "Server" and ssh_config is not None:
        server_title = "Remote server"
        server_value = f"{ssh_config.username}@{ssh_config.host}:{int(ssh_config.port)}"
        workspace_value = workspace
    else:
        server_title = "Current target"
        server_value = "Local jobs"
        workspace_value = ""

    def card(parent: tk.Widget, width: int | None = None) -> tk.Frame:
        frame = tk.Frame(parent, bg="#ffffff", highlightbackground="#dbe3ee", highlightthickness=1, bd=0)
        if width:
            frame.pack_propagate(False)
            frame.configure(width=width, height=94)
        return frame

    def card_label(parent: tk.Widget, text: str, **kwargs) -> tk.Label:
        options = {"bg": "#ffffff", "fg": "#1e293b", "font": ("Inter", 10)}
        options.update(kwargs)
        return tk.Label(parent, text=text, **options)

    summary = card(dialog)
    summary.pack(fill=tk.X, padx=14, pady=(12, 10))
    summary_inner = tk.Frame(summary, bg="#ffffff")
    summary_inner.pack(fill=tk.X, padx=14, pady=12)

    server_card = tk.Frame(summary_inner, bg="#ffffff")
    server_card.pack(side=tk.LEFT, fill=tk.X, expand=True)
    icon_wrap = tk.Frame(server_card, bg="#f1f5f9", width=38, height=38)
    icon_wrap.pack(side=tk.LEFT, padx=(0, 12))
    icon_wrap.pack_propagate(False)
    server_icon = ctrl.gui._make_icon("success", "#0f172a") if getattr(ctrl.gui, "_make_icon", None) is not None else None
    if server_icon is not None:
        tk.Label(icon_wrap, image=server_icon, bg="#f1f5f9").pack(expand=True)
    else:
        tk.Label(icon_wrap, text="OK", bg="#f1f5f9", fg="#0f172a", font=("Inter", 10, "bold")).pack(expand=True)
    server_text = tk.Frame(server_card, bg="#ffffff")
    server_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
    card_label(server_text, server_title, fg="#0f172a", font=("Inter", 9)).pack(anchor=tk.W)
    server_value_row = tk.Frame(server_text, bg="#ffffff")
    server_value_row.pack(anchor=tk.W, pady=(4, 0))
    card_label(server_value_row, server_value, font=("Inter", 10, "bold")).pack(side=tk.LEFT)
    if workspace_value:
        workspace_row = tk.Frame(server_text, bg="#ffffff")
        workspace_row.pack(anchor=tk.W, pady=(4, 0))
        card_label(workspace_row, "Workspace:", fg="#0f172a", font=("Inter", 9)).pack(side=tk.LEFT)
        card_label(workspace_row, f" {workspace_value}", fg="#0f172a", font=("Inter", 9)).pack(side=tk.LEFT)

    tk.Frame(summary_inner, width=1, bg="#dbe3ee").pack(side=tk.LEFT, fill=tk.Y, padx=14)

    output_card = tk.Frame(summary_inner, bg="#ffffff")
    output_card.pack(side=tk.LEFT, fill=tk.X, expand=True)
    output_icon_wrap = tk.Frame(output_card, bg="#f1f5f9", width=38, height=38)
    output_icon_wrap.pack(side=tk.LEFT, padx=(0, 12))
    output_icon_wrap.pack_propagate(False)
    output_icon = ctrl.gui._make_icon("load", "#0f172a") if getattr(ctrl.gui, "_make_icon", None) is not None else None
    if output_icon is not None:
        tk.Label(output_icon_wrap, image=output_icon, bg="#f1f5f9").pack(expand=True)
    else:
        tk.Label(output_icon_wrap, text="OUT", bg="#f1f5f9", fg="#0f172a", font=("Inter", 9, "bold")).pack(expand=True)
    output_text = tk.Frame(output_card, bg="#ffffff")
    output_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
    card_label(output_text, "Default output directory", fg="#0f172a", font=("Inter", 9)).pack(anchor=tk.W)
    output_value_row = tk.Frame(output_text, bg="#ffffff")
    output_value_row.pack(anchor=tk.W, pady=(8, 0))
    card_label(output_value_row, truncate_middle(output_dir, 54), fg="#0f172a", font=("Inter", 9, "bold")).pack(side=tk.LEFT)

    counters = card(summary_inner, width=240)
    counters.pack(side=tk.LEFT, fill=tk.Y, padx=(18, 0))
    counter_inner = tk.Frame(counters, bg="#ffffff")
    counter_inner.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

    def counter(parent: tk.Widget, value_var: tk.StringVar, label: str, color: str) -> None:
        group = tk.Frame(parent, bg="#ffffff")
        group.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        stack = tk.Frame(group, bg="#ffffff")
        stack.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        tk.Label(stack, textvariable=value_var, bg="#ffffff", fg="#0f172a", font=("Inter", 12, "bold")).pack()
        tk.Label(stack, text=label, bg="#ffffff", fg=color, font=("Inter", 10, "bold")).pack(pady=(4, 0))

    counter(counter_inner, completed_count_var, "Completed", "#16a34a")
    tk.Frame(counter_inner, width=1, bg="#e2e8f0").pack(side=tk.LEFT, fill=tk.Y, padx=10)
    counter(counter_inner, running_count_var, "Running", "#2563eb")
    tk.Frame(counter_inner, width=1, bg="#e2e8f0").pack(side=tk.LEFT, fill=tk.Y, padx=10)
    counter(counter_inner, failed_count_var, "Failed", "#dc2626")

    info_row = ttk.Frame(dialog)
    info_row.pack(fill=tk.X, padx=14, pady=(0, 8))
    ttk.Label(
        info_row,
        text="Select one or more background jobs, then attach, download outputs, or remove stale entries.",
        foreground="#0f172a",
        wraplength=780,
    ).pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Label(info_row, textvariable=selection_summary_var, foreground="#0f172a").pack(side=tk.RIGHT)

    table_outer = tk.Frame(dialog, bg="#ffffff", highlightbackground="#dbe3ee", highlightthickness=1, bd=0)
    table_outer.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 10))
    header_row = tk.Frame(table_outer, bg="#ffffff", height=38)
    header_row.pack(fill=tk.X)
    header_row.pack_propagate(False)
    header_row.columnconfigure(0, minsize=54)
    header_row.columnconfigure(1, minsize=112)
    header_row.columnconfigure(2, weight=1, minsize=360)
    header_row.columnconfigure(3, minsize=260)
    header_row.columnconfigure(4, minsize=44)
    ttk.Checkbutton(header_row, variable=select_all_var, command=lambda: toggle_all()).grid(row=0, column=0, sticky=tk.W, padx=(18, 0), pady=8)
    tk.Label(header_row, text="State", bg="#ffffff", fg="#0f172a", font=("Inter", 9, "bold"), anchor=tk.W).grid(row=0, column=1, sticky=tk.W, pady=10)
    tk.Label(header_row, text="Job", bg="#ffffff", fg="#0f172a", font=("Inter", 9, "bold"), anchor=tk.W).grid(row=0, column=2, sticky=tk.W, padx=(28, 12), pady=10)
    tk.Label(header_row, text="Started", bg="#ffffff", fg="#0f172a", font=("Inter", 9, "bold"), anchor=tk.W).grid(row=0, column=3, sticky=tk.W, pady=10)
    ttk.Separator(table_outer, orient=tk.HORIZONTAL).pack(fill=tk.X)

    table_canvas = tk.Canvas(table_outer, highlightthickness=0, bg="#ffffff")
    table_scroll = ttk.Scrollbar(table_outer, orient=tk.VERTICAL, command=table_canvas.yview)
    table = tk.Frame(table_canvas, bg="#ffffff")
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
        return [job for job in jobs if registry._job_identity(job) in selected_job_ids]

    def selected_job() -> dict | None:
        selected = selected_jobs()
        return selected[0] if selected else None

    def update_selection_styles() -> None:
        update_counts()
        select_all_var.set(bool(jobs and len(selected_job_ids) == len(jobs)))
        selection_summary_var.set(f"Selected {len(selected_job_ids)} of {len(jobs)} job(s)." if jobs else "No jobs found.")
        for entry in row_widgets:
            identity = str(entry.get("identity", ""))
            selected = identity in selected_job_ids
            bg = "#eff6ff" if selected else "#ffffff"
            check_var = entry.get("check_var")
            if isinstance(check_var, tk.BooleanVar):
                check_var.set(selected)
            for widget in entry.get("bg_widgets", []):
                try:
                    widget.configure(bg=bg)
                except tk.TclError:
                    pass

    def set_selected(identity: str, selected: bool) -> None:
        if selected:
            selected_job_ids.add(identity)
        else:
            selected_job_ids.discard(identity)
        update_selection_styles()

    def select_one(identity: str) -> None:
        selected_job_ids.clear()
        selected_job_ids.add(identity)
        update_selection_styles()

    def toggle_all() -> None:
        if select_all_var.get():
            selected_job_ids.update(registry._job_identity(job) for job in jobs)
        else:
            selected_job_ids.clear()
        update_selection_styles()

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

    def state_bg(state: str) -> str:
        return {
            "running": "#eff6ff",
            "completed": "#dcfce7",
            "success": "#dcfce7",
            "failed": "#fee2e2",
            "missing": "#fee2e2",
            "paused": "#ffedd5",
        }.get(state.lower(), "#f1f5f9")

    def display_state(state: str) -> str:
        value = (state or "unknown").strip().lower()
        return value[:1].upper() + value[1:]

    def job_basename(job_label: str) -> str:
        return Path(str(job_label)).name or str(job_label)

    def started_value(job: dict) -> float | None:
        raw = job.get("started_at")
        try:
            return float(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            pass
        label = Path(str(job.get("remote_job_dir") or job.get("job_dir") or job.get("job_id") or "")).name
        parts = label.split("_")
        if len(parts) >= 3 and parts[-2].isdigit() and parts[-1].isdigit():
            try:
                return time.mktime(time.strptime(parts[-2] + parts[-1], "%Y%m%d%H%M%S"))
            except ValueError:
                return None
        return None

    def format_started(job: dict) -> tuple[str, str]:
        started = started_value(job)
        if started is None:
            return "Unknown", ""
        main = time.strftime("%b %d, %H:%M:%S", time.localtime(started))
        delta = max(0, int(time.time() - started))
        if delta < 60:
            rel = "just now"
        elif delta < 3600:
            rel = f"{delta // 60}m ago"
        elif delta < 86400:
            rel = f"{delta // 3600}h ago"
        else:
            rel = f"{delta // 86400}d ago"
        return main, rel

    def update_counts() -> None:
        counts = {"completed": 0, "running": 0, "failed": 0}
        for job in jobs:
            state = str(job.get("state", "")).lower()
            if state in {"completed", "success"}:
                counts["completed"] += 1
            elif state == "running":
                counts["running"] += 1
            elif state in {"failed", "missing"}:
                counts["failed"] += 1
        completed_count_var.set(str(counts["completed"]))
        running_count_var.set(str(counts["running"]))
        failed_count_var.set(str(counts["failed"]))

    def bind_row_selection(widget: tk.Widget, identity: str) -> None:
        widget.bind("<Button-1>", lambda _event, ident=identity: select_one(ident))
        widget.bind("<Double-1>", lambda _event, ident=identity: (select_one(ident), attach_selected()))

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
            selected_job_ids.add(registry._job_identity(jobs[0]))
            selection_initialized = True
        update_counts()
        if jobs and len(selected_job_ids) == len(jobs):
            select_all_var.set(True)
        else:
            select_all_var.set(False)
        selection_summary_var.set(f"Selected {len(selected_job_ids)} of {len(jobs)} job(s)." if jobs else "No jobs found.")
        for idx, job in enumerate(jobs):
            identity = registry._job_identity(job)
            job_label = job.get("remote_job_dir") or job.get("job_dir") or job.get("job_id", "")
            selected = identity in selected_job_ids
            bg = "#eff6ff" if selected else "#ffffff"
            row = tk.Frame(table, bg=bg, height=58)
            row.pack(fill=tk.X)
            row.pack_propagate(False)
            bg_widgets = [row]
            row.columnconfigure(0, minsize=54)
            row.columnconfigure(1, minsize=112)
            row.columnconfigure(2, weight=1, minsize=360)
            row.columnconfigure(3, minsize=260)
            row.columnconfigure(4, minsize=44)
            bind_row_selection(row, identity)
            check_var = tk.BooleanVar(value=selected)
            check = ttk.Checkbutton(row, variable=check_var, command=lambda ident=identity, var=check_var: set_selected(ident, bool(var.get())))
            check.grid(row=0, column=0, sticky=tk.W, padx=(18, 0), pady=14)
            raw_state = str(job.get("state", ""))
            badge = tk.Frame(row, bg=state_bg(raw_state), width=96, height=28)
            badge.grid(row=0, column=1, sticky=tk.W, pady=14)
            badge.pack_propagate(False)
            bind_row_selection(badge, identity)
            badge_label = tk.Label(badge, text=display_state(raw_state), bg=state_bg(raw_state), fg=state_color(raw_state), font=("Inter", 9, "bold"))
            badge_label.pack(expand=True)
            bind_row_selection(badge_label, identity)

            job_block = tk.Frame(row, bg=bg)
            job_block.grid(row=0, column=2, sticky=tk.EW, padx=(28, 12), pady=9)
            bg_widgets.append(job_block)
            bind_row_selection(job_block, identity)
            job_top = tk.Frame(job_block, bg=bg)
            job_top.pack(anchor=tk.W)
            bg_widgets.append(job_top)
            bind_row_selection(job_top, identity)
            job_name = tk.Label(job_top, text=truncate_middle(job_basename(str(job_label)), 44), bg=bg, fg="#0f172a", font=("Inter", 10, "bold"))
            job_name.pack(side=tk.LEFT)
            bg_widgets.append(job_name)
            bind_row_selection(job_name, identity)
            job_path = tk.Label(job_block, text=truncate_middle(str(job_label), 68), bg=bg, fg="#475569", font=("Inter", 8))
            job_path.pack(anchor=tk.W, pady=(2, 0))
            bg_widgets.append(job_path)
            bind_row_selection(job_path, identity)

            started_main, started_rel = format_started(job)
            started_block = tk.Frame(row, bg=bg)
            started_block.grid(row=0, column=3, sticky=tk.W, padx=(0, 12), pady=7)
            bg_widgets.append(started_block)
            bind_row_selection(started_block, identity)
            started_label = tk.Label(started_block, text=started_main, bg=bg, fg="#0f172a", font=("Inter", 9), anchor=tk.W, justify=tk.LEFT)
            started_label.pack(anchor=tk.W)
            bg_widgets.append(started_label)
            bind_row_selection(started_label, identity)
            if started_rel:
                relative_label = tk.Label(started_block, text=started_rel, bg=bg, fg="#475569", font=("Inter", 8), anchor=tk.W, justify=tk.LEFT)
                relative_label.pack(anchor=tk.W, pady=(2, 0))
                bg_widgets.append(relative_label)
                bind_row_selection(relative_label, identity)
            menu_label = tk.Label(row, text="...", bg=bg, fg="#0f172a", font=("Inter", 12, "bold"))
            menu_label.grid(row=0, column=4, sticky=tk.E, padx=(0, 16))
            bg_widgets.append(menu_label)
            bind_row_selection(menu_label, identity)
            sep = tk.Frame(table, bg="#e2e8f0", height=1)
            sep.pack(fill=tk.X)
            row_widgets.append({"identity": identity, "widgets": [row, check, badge, job_block, started_block, sep], "bg_widgets": bg_widgets, "check_var": check_var})

    render_jobs()

    buttons = ttk.Frame(dialog)
    buttons.pack(fill=tk.X, padx=14, pady=(0, 14))

    def action_button(parent: ttk.Frame, text: str, command, icon_name: str, style: str | None = None, side: str = tk.LEFT, padx=0, icon_color: str | None = None) -> ttk.Button:
        icon = ctrl.gui._make_icon(icon_name, icon_color) if getattr(ctrl.gui, "_make_icon", None) is not None else None
        options = {"text": f" {text}" if icon is not None else text, "command": command}
        if style:
            options["style"] = style
        if icon is not None:
            options.update({"image": icon, "compound": tk.LEFT})
        button = ttk.Button(parent, **options)
        button.pack(side=side, padx=padx, ipady=3, ipadx=8)
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
            if registry._delete_registry_job(job):
                identity = registry._job_identity(job)
                deleted_job_ids.add(identity)
                selected_job_ids.discard(identity)
                jobs = [entry for entry in jobs if registry._job_identity(entry) != identity]
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
                    and registry._same_remote_server(entry, ssh_config, workspace)
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
                filtered_remote_jobs = [job for job in remote_jobs if registry._job_identity(job) not in deleted_job_ids]
                jobs = stable_job_order(registry._merge_job_lists(jobs, filtered_remote_jobs))
                set_status(f"Loaded {len(filtered_remote_jobs)} running remote job(s)." if filtered_remote_jobs else "")
                render_jobs()

            ctrl.gui.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

def show_download_outputs_dialog(ctrl, downloads: list[tuple[str, RemoteRunner, str | Path | None]]) -> bool:
    if not downloads:
        return False
    if ctrl.running:
        ctrl.gui.progress_ctrl._append_log("Remote task ignored: another task is already running.")
        return False

    total_jobs = len(downloads)
    ctrl.running = True
    ctrl.stop_requested.clear()
    ctrl.gui.state.remote_status.set("Remote: Download Outputs running...")
    if getattr(ctrl, "resume_button", None) is not None:
        ctrl.resume_button.configure(state=tk.DISABLED)
    if getattr(ctrl, "restart_button", None) is not None:
        ctrl.restart_button.configure(state=tk.DISABLED)
    if getattr(ctrl, "stop_button", None) is not None:
        ctrl.stop_button.configure(state=tk.DISABLED)
    if getattr(ctrl, "progress", None) is not None:
        ctrl.progress.start(10)

    dialog = tk.Toplevel(ctrl.gui.root)
    dialog.title("Download Outputs")
    dialog.geometry("1040x640")
    dialog.minsize(960, 600)
    dialog.transient(ctrl.gui.root)
    dialog.grab_set()

    current_var = tk.StringVar(value="Preparing remote download...")
    job_var = tk.StringVar(value=f"Jobs: 0/{total_jobs}")
    files_downloaded_var = tk.StringVar(value="0/?")
    status_var = tk.StringVar(value="Status: Preparing download...")
    progress_var = tk.DoubleVar(value=0)
    destination_var = tk.StringVar(value="Destination: Preparing local folder...")

    first_runner = downloads[0][1]
    ssh = getattr(getattr(first_runner, "config", None), "ssh", None)
    server_value = "Remote server"
    if ssh is not None:
        server_value = f"{getattr(ssh, 'username', '')}@{getattr(ssh, 'host', '')}:{int(getattr(ssh, 'port', 22))}"
    workspace_value = str(getattr(getattr(first_runner, "config", None), "remote_workspace", "") or "")

    def make_card(parent: tk.Widget, width: int | None = None) -> tk.Frame:
        frame = tk.Frame(parent, bg="#ffffff", highlightbackground="#dbe3ee", highlightthickness=1, bd=0)
        if width is not None:
            frame.configure(width=width, height=108)
            frame.pack_propagate(False)
            frame.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=(0, 10))
        else:
            frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        return frame

    def card_icon(parent: tk.Widget, icon_name: str, color: str, fallback: str) -> None:
        wrap = tk.Frame(parent, bg="#f1f5f9", width=36, height=36)
        wrap.pack(side=tk.LEFT, padx=(0, 10))
        wrap.pack_propagate(False)
        icon = ctrl.gui._make_icon(icon_name, color) if getattr(ctrl.gui, "_make_icon", None) is not None else None
        if icon is not None:
            tk.Label(wrap, image=icon, bg="#f1f5f9").pack(expand=True)
        else:
            tk.Label(wrap, text=fallback, bg="#f1f5f9", fg=color, font=("Inter", 9, "bold")).pack(expand=True)

    cards = ttk.Frame(dialog)
    cards.pack(fill=tk.X, padx=14, pady=(14, 10))

    server_card = make_card(cards, width=260)
    server_inner = tk.Frame(server_card, bg="#ffffff")
    server_inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
    card_icon(server_inner, "success", "#0f172a", "S")
    server_text = tk.Frame(server_inner, bg="#ffffff")
    server_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
    tk.Label(server_text, text="Remote server", bg="#ffffff", fg="#0f172a", font=("Inter", 9, "bold")).pack(anchor=tk.W)
    tk.Label(server_text, text=server_value, bg="#ffffff", fg="#0f172a", font=("Inter", 10, "bold")).pack(anchor=tk.W, pady=(3, 0))
    if workspace_value:
        workspace_row = tk.Frame(server_text, bg="#ffffff")
        workspace_row.pack(anchor=tk.W, pady=(3, 0))
        tk.Label(workspace_row, text="Workspace:", bg="#ffffff", fg="#0f172a", font=("Inter", 9)).pack(side=tk.LEFT)
        tk.Label(workspace_row, text=f" {workspace_value}", bg="#ffffff", fg="#0f172a", font=("Inter", 9)).pack(side=tk.LEFT)

    job_card = make_card(cards, width=430)
    job_inner = tk.Frame(job_card, bg="#ffffff")
    job_inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)
    card_icon(job_inner, "download", "#0f172a", "D")
    job_text = tk.Frame(job_inner, bg="#ffffff")
    job_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
    tk.Label(job_text, text="Download job", bg="#ffffff", fg="#0f172a", font=("Inter", 9, "bold")).pack(anchor=tk.W)
    tk.Label(job_text, textvariable=job_var, bg="#ffffff", fg="#0f172a", font=("Inter", 9), wraplength=360, justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 0))
    tk.Label(job_text, textvariable=destination_var, bg="#ffffff", fg="#475569", font=("Inter", 8), wraplength=360, justify=tk.LEFT).pack(anchor=tk.W, pady=(2, 0))

    files_card = tk.Frame(cards, bg="#ffffff", highlightbackground="#dbe3ee", highlightthickness=1, bd=0, width=260, height=108)
    files_card.pack(side=tk.LEFT, fill=tk.Y)
    files_card.pack_propagate(False)
    files_inner = tk.Frame(files_card, bg="#ffffff")
    files_inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
    card_icon(files_inner, "save", "#16a34a", "F")
    files_text = tk.Frame(files_inner, bg="#ffffff")
    files_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
    tk.Label(files_text, textvariable=files_downloaded_var, bg="#ffffff", fg="#0f172a", font=("Inter", 14, "bold")).pack(anchor=tk.W)
    tk.Label(files_text, text="Files downloaded", bg="#ffffff", fg="#16a34a", font=("Inter", 9, "bold")).pack(anchor=tk.W, pady=(2, 0))

    style = ttk.Style(dialog)
    style.configure("DownloadDialog.Horizontal.TProgressbar", thickness=14)
    progress = ttk.Progressbar(dialog, mode="determinate", maximum=100, variable=progress_var, style="DownloadDialog.Horizontal.TProgressbar")
    progress.pack(fill=tk.X, padx=14, pady=(0, 10))

    log_frame = ttk.Frame(dialog)
    log_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 8))
    log = tk.Text(log_frame, wrap=tk.WORD, height=15, font=("Inter", 10), state=tk.DISABLED)
    scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=log.yview)
    log.configure(yscrollcommand=scroll.set)
    log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)

    close_row = ttk.Frame(dialog)
    close_row.pack(fill=tk.X, padx=14, pady=(0, 14))
    status_label = ttk.Label(close_row, textvariable=status_var, foreground="#475569")
    status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
    close_button = ttk.Button(close_row, text="Close", state=tk.DISABLED, command=dialog.destroy)
    close_button.pack(side=tk.RIGHT)

    state = {"ok": False, "done": False, "files": 0, "total_files": 0}

    def set_status(text: str, color: str = "#475569") -> None:
        status_var.set(text)
        try:
            status_label.configure(foreground=color)
        except tk.TclError:
            pass

    def local_destination(runner: RemoteRunner, local_target_dir: str | Path | None) -> Path:
        target = Path(local_target_dir or runner.config.output_dir or (PROJECT_ROOT / "outputs"))
        if runner.config.download_subdir:
            target = target / runner.config.download_subdir
        return target

    def append_line(line: str) -> None:
        if not dialog.winfo_exists():
            return
        if line.startswith("Downloading file:"):
            state["files"] += 1
            total_files = int(state.get("total_files") or 0)
            files_downloaded_var.set(f"{state['files']}/{total_files or '?'}")
            if total_files:
                progress_var.set(min(99, (state["files"] / total_files) * 100))
            else:
                progress_var.set(min(96, max(float(progress_var.get()) + 5, state["files"] * 5)))
            source = line.split("->", 1)[0].replace("Downloading file:", "").strip()
            current_var.set("Downloading " + truncate_middle(source, 72))
            set_status(current_var.get(), "#2563eb")
        elif line.startswith("Skipping symlink:"):
            progress_var.set(min(96, max(float(progress_var.get()) + 2, 20)))
            current_var.set("Skipping symlink " + truncate_middle(line.replace("Skipping symlink:", "").strip(), 72))
            set_status(current_var.get(), "#f97316")
        elif line.startswith("Connecting SSH"):
            progress_var.set(max(float(progress_var.get()), 8))
            current_var.set("Connecting to remote server...")
            set_status("Status: Connecting to remote server...", "#2563eb")
        elif line.startswith("SSH connected"):
            progress_var.set(max(float(progress_var.get()), 18))
            current_var.set("Connected. Preparing output files...")
            set_status("Status: Connected. Preparing output files...", "#2563eb")
        elif line.startswith("Downloaded outputs to:"):
            current_var.set(line)
            set_status("Status: Download completed successfully.", "#16a34a")
        log.configure(state=tk.NORMAL)
        log.insert(tk.END, line + "\n")
        log.see(tk.END)
        log.configure(state=tk.DISABLED)

    def set_idle_state() -> None:
        ctrl.running = False
        ctrl.gui.state.remote_status.set("Remote: idle")
        if getattr(ctrl, "progress", None) is not None:
            ctrl.progress.stop()
        if getattr(ctrl, "resume_button", None) is not None:
            ctrl.resume_button.configure(state=tk.NORMAL)
        if getattr(ctrl, "restart_button", None) is not None:
            ctrl.restart_button.configure(state=tk.NORMAL)
        if getattr(ctrl, "stop_button", None) is not None:
            ctrl.stop_button.configure(state=tk.DISABLED)
        ctrl.gui._validate_configuration()

    def finish(ok: bool) -> None:
        state["ok"] = ok
        state["done"] = True
        if dialog.winfo_exists():
            close_button.configure(state=tk.NORMAL)
            if ok:
                progress_var.set(100)
                total_files = int(state.get("total_files") or state["files"])
                files_downloaded_var.set(f"{state['files']}/{total_files}")
                current_var.set("Download complete.")
                set_status("Status: Download completed successfully.", "#16a34a")
            else:
                current_var.set("Download failed. Check the log below.")
                set_status("Status: Download failed. Check the log below.", "#dc2626")
        set_idle_state()

    def worker() -> None:
        ok = True
        try:
            for idx, (label, runner, local_target_dir) in enumerate(downloads, start=1):
                message = f"Downloading outputs ({idx}/{total_jobs}): {label}"
                ui_events.emit(EVENT_LOG_MESSAGE, message)
                ctrl.gui.root.after(0, lambda m=message: append_line(m))
                ctrl.gui.root.after(0, lambda i=idx, l=label: job_var.set(f"Job {i}/{total_jobs}: {truncate_middle(str(l), 58)}"))
                ctrl.gui.root.after(0, lambda i=idx: progress_var.set(max(float(progress_var.get()), ((i - 1) / total_jobs) * 100)))
                old_log = runner.on_log

                def relay_log(line: str, previous_log=old_log) -> None:
                    previous_log(line)
                    ctrl.gui.root.after(0, lambda l=line: append_line(l))

                runner.on_log = relay_log
                try:
                    if not runner.config.download_subdir:
                        metadata = runner.read_remote_metadata()
                        if metadata.get("download_subdir"):
                            runner.config.download_subdir = str(metadata.get("download_subdir"))
                    destination = local_destination(runner, local_target_dir)
                    ctrl.gui.root.after(0, lambda d=destination: destination_var.set("Destination: " + truncate_middle(str(d), 76)))
                    ctrl.gui.root.after(0, lambda: set_status("Status: Counting files before download...", "#2563eb"))
                    total_for_job = runner.count_download_files()
                    state["total_files"] = int(state.get("total_files") or 0) + total_for_job
                    ctrl.gui.root.after(0, lambda total=state["total_files"]: files_downloaded_var.set(f"{state['files']}/{total}"))
                    local_path = runner.download_outputs(local_target_dir)
                finally:
                    runner.on_log = old_log
                downloaded_message = f"Downloaded outputs to: {local_path}"
                ui_events.emit(EVENT_LOG_MESSAGE, downloaded_message)
                ctrl.gui.root.after(0, lambda m=downloaded_message: append_line(m))
        except Exception as exc:
            ok = False
            err_msg = f"REMOTE DOWNLOAD ERROR: {type(exc).__name__}: {exc}"
            ui_events.emit(EVENT_LOG_MESSAGE, err_msg)
            ctrl.gui.root.after(0, lambda m=err_msg: append_line(m))
        finally:
            ctrl.gui.root.after(0, lambda success=ok: finish(success))

    def close_if_done() -> None:
        if state["done"]:
            dialog.destroy()

    dialog.protocol("WM_DELETE_WINDOW", close_if_done)
    threading.Thread(target=worker, daemon=True).start()
    ctrl.gui.root.wait_window(dialog)
    return bool(state["ok"])

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
    dialog.geometry("980x540")
    dialog.minsize(900, 500)
    dialog.transient(ctrl.gui.root)
    dialog.grab_set()

    ssh = getattr(getattr(runner, "config", None), "ssh", None)
    server_value = "Remote server"
    if ssh is not None:
        server_value = f"{getattr(ssh, 'username', '')}@{getattr(ssh, 'host', '')}:{int(getattr(ssh, 'port', 22))}"
    workspace_value = str(getattr(getattr(runner, "config", None), "remote_workspace", "") or "")

    current_var = tk.StringVar(value="Preparing remote connection...")
    job_var = tk.StringVar(value="Preparing job workspace...")
    files_copied_var = tk.StringVar(value="0/?")
    footer_var = tk.StringVar(value="Copying run configuration and license files to the remote workspace.")
    status_var = tk.StringVar(value="Status: Preparing copy...")

    def make_card(parent: tk.Widget, width: int | None = None) -> tk.Frame:
        frame = tk.Frame(parent, bg="#ffffff", highlightbackground="#dbe3ee", highlightthickness=1, bd=0)
        if width is not None:
            frame.configure(width=width, height=86)
            frame.pack_propagate(False)
            frame.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=(0, 10))
        else:
            frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        return frame

    def card_icon(parent: tk.Widget, icon_name: str, color: str, fallback: str) -> None:
        wrap = tk.Frame(parent, bg="#f1f5f9", width=36, height=36)
        wrap.pack(side=tk.LEFT, padx=(0, 10))
        wrap.pack_propagate(False)
        icon = ctrl.gui._make_icon(icon_name, color) if getattr(ctrl.gui, "_make_icon", None) is not None else None
        if icon is not None:
            tk.Label(wrap, image=icon, bg="#f1f5f9").pack(expand=True)
        else:
            tk.Label(wrap, text=fallback, bg="#f1f5f9", fg=color, font=("Inter", 9, "bold")).pack(expand=True)

    cards = ttk.Frame(dialog)
    cards.pack(fill=tk.X, padx=14, pady=(14, 10))

    server_card = make_card(cards, width=280)
    server_inner = tk.Frame(server_card, bg="#ffffff")
    server_inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
    card_icon(server_inner, "success", "#0f172a", "S")
    server_text = tk.Frame(server_inner, bg="#ffffff")
    server_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    tk.Label(server_text, text="Remote server", bg="#ffffff", fg="#0f172a", font=("Inter", 9, "bold")).pack(anchor=tk.W)
    tk.Label(server_text, text=server_value, bg="#ffffff", fg="#0f172a", font=("Inter", 10, "bold")).pack(anchor=tk.W, pady=(3, 0))
    if workspace_value:
        workspace_row = tk.Frame(server_text, bg="#ffffff")
        workspace_row.pack(anchor=tk.W, pady=(3, 0))
        tk.Label(workspace_row, text="Workspace:", bg="#ffffff", fg="#0f172a", font=("Inter", 9)).pack(side=tk.LEFT)
        tk.Label(workspace_row, text=f" {workspace_value}", bg="#ffffff", fg="#0f172a", font=("Inter", 9)).pack(side=tk.LEFT)

    job_card = make_card(cards, width=300)
    job_inner = tk.Frame(job_card, bg="#ffffff")
    job_inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
    card_icon(job_inner, "run", "#0f172a", "J")
    job_text = tk.Frame(job_inner, bg="#ffffff")
    job_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    tk.Label(job_text, text="Job", bg="#ffffff", fg="#0f172a", font=("Inter", 9, "bold")).pack(anchor=tk.W)
    tk.Label(job_text, textvariable=job_var, bg="#ffffff", fg="#0f172a", font=("Inter", 9), wraplength=270, justify=tk.LEFT).pack(anchor=tk.W, pady=(3, 0))

    files_card = tk.Frame(cards, bg="#ffffff", highlightbackground="#dbe3ee", highlightthickness=1, bd=0, width=250, height=86)
    files_card.pack(side=tk.LEFT, fill=tk.Y)
    files_card.pack_propagate(False)
    files_inner = tk.Frame(files_card, bg="#ffffff")
    files_inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
    card_icon(files_inner, "save", "#16a34a", "F")
    files_text = tk.Frame(files_inner, bg="#ffffff")
    files_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    tk.Label(files_text, textvariable=files_copied_var, bg="#ffffff", fg="#0f172a", font=("Inter", 14, "bold")).pack(anchor=tk.W)
    tk.Label(files_text, text="Files copied", bg="#ffffff", fg="#16a34a", font=("Inter", 9, "bold")).pack(anchor=tk.W, pady=(2, 0))

    progress_var = tk.DoubleVar(value=0)
    style = ttk.Style(dialog)
    style.configure("UploadDialog.Horizontal.TProgressbar", thickness=14)
    progress = ttk.Progressbar(dialog, mode="determinate", maximum=100, variable=progress_var, style="UploadDialog.Horizontal.TProgressbar")
    progress.pack(fill=tk.X, padx=14, pady=(0, 6))
    ttk.Label(dialog, textvariable=status_var, foreground="#475569").pack(anchor=tk.W, padx=14, pady=(0, 8))

    log_frame = ttk.Frame(dialog)
    log_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 8))
    log = tk.Text(log_frame, wrap=tk.WORD, height=15, font=("Inter", 10), state=tk.DISABLED)
    scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=log.yview)
    log.configure(yscrollcommand=scroll.set)
    log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)

    footer = ttk.Frame(dialog)
    footer.pack(fill=tk.X, padx=14, pady=(0, 14))
    ttk.Label(footer, textvariable=footer_var, foreground="#64748b").pack(side=tk.LEFT, fill=tk.X, expand=True)
    cancel_button = ttk.Button(footer, text="Cancel")
    cancel_button.pack(side=tk.RIGHT)

    state = {"ok": False, "done": False, "files": 0, "cancel_requested": False}
    old_log = runner.on_log

    def request_cancel() -> None:
        if state["done"]:
            dialog.destroy()
            return
        state["cancel_requested"] = True
        footer_var.set("Cancel requested. Waiting for the current remote file operation to finish...")
        status_var.set("Status: Cancel requested. Waiting for the current remote file operation to finish...")
        current_var.set("Cancel requested...")
        cancel_button.configure(state=tk.DISABLED)

    cancel_button.configure(command=request_cancel)
    dialog.protocol("WM_DELETE_WINDOW", request_cancel)

    def append_line(line: str) -> None:
        if not dialog.winfo_exists():
            return
        if line.startswith("Uploading file:"):
            state["files"] += 1
            files_copied_var.set(f"{state['files']}/?")
            progress_var.set(min(92, max(float(progress_var.get()) + 8, 50 + state["files"] * 8)))
            current_var.set("Copying " + truncate_middle(line.split("->", 1)[0].replace("Uploading file:", "").strip(), 70))
            status_var.set("Status: " + current_var.get())
        elif line.startswith("Connecting SSH"):
            progress_var.set(max(float(progress_var.get()), 8))
            current_var.set("Connecting to remote server...")
            status_var.set("Status: Connecting to remote server...")
        elif line.startswith("SSH connected"):
            progress_var.set(max(float(progress_var.get()), 18))
            current_var.set("Connected. Preparing remote workspace...")
            status_var.set("Status: Connected. Preparing remote workspace...")
        elif line.startswith("Remote job:"):
            remote_job = line.replace("Remote job:", "").strip()
            job_var.set(truncate_middle(remote_job, 58))
            progress_var.set(max(float(progress_var.get()), 30))
            current_var.set("Creating remote job workspace...")
            status_var.set("Status: Creating remote job workspace...")
        elif line.startswith("Preparing run configuration"):
            progress_var.set(max(float(progress_var.get()), 42))
            current_var.set("Preparing run configuration...")
            status_var.set("Status: Preparing run configuration...")
        elif line.startswith("Using shared remote pipeline code:"):
            progress_var.set(max(float(progress_var.get()), 55))
            current_var.set("Using shared remote pipeline code.")
            status_var.set("Status: Using shared remote pipeline code.")
        elif line.startswith("Uploading shared pipeline code once:"):
            progress_var.set(max(float(progress_var.get()), 55))
            current_var.set("Copying shared pipeline code for first use...")
            status_var.set("Status: Copying shared pipeline code for first use...")
        elif line.startswith("Uploading license files"):
            progress_var.set(max(float(progress_var.get()), 70))
            current_var.set("Uploading license files...")
            status_var.set("Status: Uploading license files...")
        elif line.startswith("Remote upload complete"):
            progress_var.set(100)
            current_var.set("Remote upload complete.")
            status_var.set("Status: Copy completed successfully.")
        elif line.endswith("...") or line.endswith("complete."):
            current_var.set(line)
        footer_var.set(current_var.get())
        log.configure(state=tk.NORMAL)
        log.insert(tk.END, line + "\n")
        log.see(tk.END)
        log.configure(state=tk.DISABLED)

    def worker() -> None:
        ok = True
        try:
            runner.on_log = lambda line: ctrl.gui.root.after(0, lambda l=line: append_line(l))
            runner.upload_job()
            if state["cancel_requested"]:
                ok = False
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
            if ok:
                ctrl.gui.root.after(0, lambda: progress_var.set(100))
                ctrl.gui.root.after(0, lambda: files_copied_var.set(f"{state['files']}/{state['files']}"))
                ctrl.gui.root.after(0, lambda: footer_var.set("Copy complete. Starting the remote job..."))
                ctrl.gui.root.after(0, lambda: status_var.set("Status: Copy completed successfully. Starting the remote job..."))
                ctrl.gui.root.after(0, lambda: current_var.set("Copy complete. Starting remote job..."))
                ctrl.gui.root.after(250, dialog.destroy)
            elif state["cancel_requested"]:
                ctrl.gui.root.after(0, lambda: footer_var.set("Copy cancelled. The remote job will not be started."))
                ctrl.gui.root.after(0, lambda: status_var.set("Status: Copy cancelled. The remote job will not be started."))
                ctrl.gui.root.after(0, lambda: cancel_button.configure(text="Close", state=tk.NORMAL))
            else:
                ctrl.gui.root.after(0, lambda: footer_var.set("Copy failed. Review the log, then close this window."))
                ctrl.gui.root.after(0, lambda: status_var.set("Status: Copy failed. Review the log, then close this window."))
                ctrl.gui.root.after(0, lambda: cancel_button.configure(text="Close", state=tk.NORMAL))

    threading.Thread(target=worker, daemon=True).start()
    ctrl.gui.root.wait_window(dialog)
    return state["ok"]
