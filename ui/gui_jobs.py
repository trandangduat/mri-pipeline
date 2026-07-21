from __future__ import annotations
from ui.events import ui_events, EVENT_LOG_MESSAGE
"""Background job and remote-runner mixin for the MRI Pipeline GUI."""


import os
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from pipeline.jobs import load_job_registry, read_json, save_job_registry, upsert_job_registry, write_json
from pipeline.config import (
    PROJECT_ROOT,
    STAGE_ORDER,
    TOOL_DEFS,
    enabled_tools_for_stage,
    is_tool_enabled,
    tool_display_name,
)
from pipeline.discovery import (
    _derive_subject_id,
    _discover_mri_files,
    build_subject_id_map,
)
from remote.remote_runner import RemoteRunConfig, RemoteRunner
from remote.ssh_client import SSHConfig


class JobsController:
    def __init__(self, gui):
        self.gui = gui
        
        # Jobs state
        self.active_job = None
        self.job_poll_after_id = None
        self.job_log_offset = 0
        self.job_monitors = {}
        self.remote_poll_in_flight = False
        
        # UI Elements
        self._attach_loading_active = False
        self._attach_loading_dialog = None
        self._attach_loading_spinner_label = None
        self._attach_busy_button_states = {}
    def _attach_job_dialog(self) -> None:
        from ui.dialogs.job_dialogs import show_attach_job_dialog
        show_attach_job_dialog(self)


    def _remote_key_file_exists(self, key_path: str) -> bool:
        if not key_path.strip():
            return False
        try:
            return Path(key_path).expanduser().is_file()
        except OSError:
            return False

    def _ensure_remote_auth_for_job_action(self, action: str) -> bool:
        password = self.gui.state.remote_password.get()
        key_path = self.gui.state.remote_key_path.get().strip()
        if password:
            if key_path and not self._remote_key_file_exists(key_path):
                self.gui.state.remote_key_path.set("")
            return True
        if self._remote_key_file_exists(key_path):
            return True

        if key_path:
            self.gui.state.remote_key_path.set("")
        if getattr(self, "notebook", None) is not None and getattr(self, "config_tab", None) is not None:
            self.gui.notebook.select(self.gui.config_tab)
        messagebox.showwarning(
            "Missing SSH authentication",
            f"Chưa có mật khẩu hoặc file SSH key hợp lệ để {action}.\n\nVui lòng quay lại Pipeline configuration, bổ sung Password hoặc SSH Key rồi thử lại.",
        )
        return False


    def _delete_path_if_exists(self, path: Path) -> None:
        if not path.exists():
            return
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    def _local_job_config_for_delete(self, job: dict) -> dict:
        job_dir = Path(str(job.get("job_dir", ""))) if job.get("job_dir") else None
        config = read_json(job_dir / "job_config.json", {}) if job_dir else {}
        return config or dict(job.get("run_request") or {})

    def _input_files_from_job_config(self, config: dict, job: dict) -> list[str]:
        mode = config.get("mode")
        if mode == "file" and config.get("input_file"):
            return [str(config.get("input_file"))]
        if mode == "files":
            return [str(path) for path in config.get("input_files", [])]
        if config.get("input_source") != "Server" and config.get("input_dir"):
            try:
                return _discover_mri_files(str(config.get("input_dir")), recursive=config.get("recursive", True))
            except Exception:
                pass
        return [str(path) for path in job.get("input_files", [])]

    def _delete_local_output_folders_for_job(self, job: dict, config: dict) -> None:
        effective_output = config.get("effective_output_dir") or job.get("effective_output_dir") or config.get("output_dir") or job.get("output_dir")
        if not effective_output:
            return
        output_dir = Path(str(effective_output))
        if config.get("is_batch") and output_dir.name.startswith("batch_"):
            self._delete_path_if_exists(output_dir)
            return

        files = self._input_files_from_job_config(config, job)
        subject_id_map = config.get("subject_id_map") if isinstance(config.get("subject_id_map"), dict) else {}
        if not subject_id_map and files:
            subject_id_map = build_subject_id_map(files, str(config.get("input_dir", "")))

        subject_ids: list[str] = []
        if config.get("subject_id"):
            subject_ids.append(str(config.get("subject_id")))
        for input_file in files:
            subject_id = subject_id_map.get(input_file) or _derive_subject_id(input_file, str(config.get("input_dir", "")))
            if subject_id and subject_id not in subject_ids:
                subject_ids.append(subject_id)
        for subject_id in subject_ids:
            self._delete_path_if_exists(output_dir / subject_id)

    def _delete_local_job_folders(self, job: dict) -> None:
        config = self._local_job_config_for_delete(job)
        self._delete_local_output_folders_for_job(job, config)
        raw_job_dir = str(job.get("job_dir") or config.get("job_dir") or "").strip()
        if raw_job_dir:
            self._delete_path_if_exists(Path(raw_job_dir))



    def _is_background_monitor_active(self) -> bool:
        return bool(self.active_job and not self.active_job.get("done"))

    def _can_start_new_pipeline(self) -> bool:
        return not self.gui.pipeline_ctrl.running or self._is_background_monitor_active()

    def _stop_current_job_monitor(self) -> None:
        was_monitoring = self._is_background_monitor_active()
        if self.job_poll_after_id:
            try:
                self.gui.root.after_cancel(self.job_poll_after_id)
            except Exception:
                pass
        self.job_poll_after_id = None
        self.remote_poll_in_flight = False
        self.active_job = None
        self.job_log_offset = 0
        if was_monitoring:
            self.gui.pipeline_ctrl.running = False

    def _register_job_monitor_for_active_context(self) -> None:
        context_id = getattr(self, "active_progress_context_id", "")
        if not context_id or not self.active_job:
            return
        self.job_monitors[context_id] = {
            "context_id": context_id,
            "active_job": self.active_job,
            "remote_runner": self.gui.pipeline_ctrl.remote_runner if self.active_job.get("target") == "Server" else None,
            "job_log_offset": int(self.job_log_offset or 0),
            "after_id": None,
            "remote_poll_in_flight": False,
        }

    def _load_job_monitor(self, context_id: str) -> dict | None:
        monitor = self.job_monitors.get(context_id)
        if not monitor:
            return None
        self.gui.progress_ctrl._activate_progress_context(context_id)
        self.active_job = monitor.get("active_job")
        self.gui.pipeline_ctrl.remote_runner = monitor.get("remote_runner")
        self.job_log_offset = int(monitor.get("job_log_offset", 0) or 0)
        self.remote_poll_in_flight = bool(monitor.get("remote_poll_in_flight", False))
        self.job_poll_after_id = monitor.get("after_id")
        return monitor

    def _save_job_monitor(self, monitor: dict) -> None:
        monitor["active_job"] = self.active_job
        monitor["remote_runner"] = self.gui.pipeline_ctrl.remote_runner if self.active_job and self.active_job.get("target") == "Server" else monitor.get("remote_runner")
        monitor["job_log_offset"] = int(self.job_log_offset or 0)
        monitor["remote_poll_in_flight"] = bool(self.remote_poll_in_flight)
        if monitor.get("context_id") == getattr(self, "active_progress_context_id", ""):
            self.job_poll_after_id = monitor.get("after_id")

    def _attach_manual_job_dialog(self) -> None:
        if self.gui.state.run_target.get() == "Server":
            if not self.gui.remote_ctrl._require_remote_connection("attaching a remote job"):
                return
            if not self._ensure_remote_auth_for_job_action("Attach job"):
                return
            remote_dir = simpledialog.askstring("Attach remote job", "Remote job directory:", parent=self.gui.root)
            if remote_dir:
                self._attach_registry_job({"target": "Server", "remote_job_dir": remote_dir.strip(), "state": "unknown"})
            return
        job_dir = filedialog.askdirectory(title="Attach local job", initialdir=str(Path(self.gui.state.output_dir.get()) / "jobs"))
        if job_dir:
            self._attach_registry_job({"target": "Local", "job_dir": job_dir, "state": "unknown"})

    def _set_attach_buttons_busy(self, busy: bool) -> None:
        if busy:
            states: list[tuple[tk.Widget, str]] = []

            def disable_buttons(widget: tk.Widget) -> None:
                for child in widget.winfo_children():
                    if isinstance(child, (tk.Button, ttk.Button)):
                        try:
                            states.append((child, str(child.cget("state"))))
                            child.configure(state=tk.DISABLED)
                        except tk.TclError:
                            pass
                    disable_buttons(child)

            disable_buttons(self.gui.root)
            self._attach_busy_button_states = states
            return

        for widget, state in getattr(self, "_attach_busy_button_states", []):
            try:
                if widget.winfo_exists():
                    widget.configure(state=state)
            except tk.TclError:
                pass
        self._attach_busy_button_states = []

    def _sync_attach_toolbar_state(self) -> None:
        if self._is_background_monitor_active():
            if getattr(self, "resume_button", None) is not None:
                self.gui.pipeline_ctrl.resume_button.configure(state=tk.DISABLED)
            if getattr(self, "restart_button", None) is not None:
                self.gui.pipeline_ctrl.restart_button.configure(state=tk.DISABLED)
            if getattr(self, "stop_button", None) is not None:
                self.gui.pipeline_ctrl.stop_button.configure(state=tk.NORMAL)
        else:
            self.gui._validate_configuration()

    def _finish_attach_loading(self) -> None:
        dialog = getattr(self, "_attach_loading_dialog", None)
        try:
            if dialog is not None and dialog.winfo_exists():
                dialog.grab_release()
                dialog.destroy()
        except tk.TclError:
            pass
        self._attach_loading_dialog = None
        self._attach_loading_spinner_label = None
        self._attach_loading_active = False
        self._set_attach_buttons_busy(False)
        self._sync_attach_toolbar_state()

    def _show_attach_loading(self, job: dict) -> tuple[tk.Toplevel, ttk.Label]:
        label = job.get("remote_job_dir") or job.get("job_dir") or job.get("job_id") or "selected job"
        dialog = tk.Toplevel(self.gui.root)
        dialog.withdraw()
        dialog.title("Attaching job")
        dialog.transient(self.gui.root)
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)

        body = ttk.Frame(dialog, padding=18)
        body.pack(fill=tk.BOTH, expand=True)
        header = ttk.Frame(body)
        header.pack(fill=tk.X)
        spinner = ttk.Label(header, image=self.gui._spinner_frame() or "", width=2)
        spinner.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(header, text="Attaching job...", font=("Inter", 11, "bold")).pack(side=tk.LEFT)
        ttk.Label(body, text=str(label), foreground="#64748b", wraplength=460).pack(anchor=tk.W, pady=(4, 12))

        dialog.update_idletasks()
        x = self.gui.root.winfo_rootx() + max(0, (self.gui.root.winfo_width() - dialog.winfo_width()) // 2)
        y = self.gui.root.winfo_rooty() + max(0, (self.gui.root.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
        dialog.deiconify()
        dialog.lift(self.gui.root)
        dialog.wait_visibility()
        dialog.grab_set()
        dialog.focus_set()
        return dialog, spinner

    def _attach_registry_job(self, job: dict) -> None:
        attached = False
        self._set_attach_buttons_busy(True)
        shown_at = 0.0
        try:
            dialog, spinner = self._show_attach_loading(job)
            self._attach_loading_dialog = dialog
            self._attach_loading_spinner_label = spinner
            self._attach_loading_active = True
            shown_at = time.monotonic()
            self.gui.root.update()
            attached = self._attach_registry_job_loaded(job)
        finally:
            if shown_at:
                end_time = shown_at + 0.4
                while time.monotonic() < end_time:
                    try:
                        if not dialog.winfo_exists():
                            break
                        self.gui.root.update()
                    except tk.TclError:
                        break
                    time.sleep(0.02)
            self._finish_attach_loading()

    def _attach_registry_job_loaded(self, job: dict) -> bool:
        target = job.get("target")
        selected_tools = dict((job.get("run_request") or {}).get("selected_tools") or {})
        config: dict = {}
        if target == "Server":
            runner = self._remote_runner_from_job_entry(job, read_metadata=False)
            if runner is None:
                return False
            self.gui.pipeline_ctrl.remote_runner = runner
            self.gui.state.run_target.set("Server")
            self.gui._on_run_target_changed()
            input_files = list(job.get("input_files") or [])
            self.active_job = {"target": "Server", "remote_job_dir": runner.remote_job_dir, "done": False, "registry_entry": job}
        else:
            job_dir = Path(str(job.get("job_dir", "")))
            config = read_json(job_dir / "job_config.json", {})
            input_files = list(job.get("input_files") or []) or (self.gui.progress_ctrl._input_files_for_progress(config) if config else [])
            selected_tools = dict(config.get("selected_tools") or selected_tools)
            self.active_job = {"target": "Local", "job_dir": str(job_dir), "done": False, "registry_entry": job}
            self.gui.state.run_target.set("Local")
            self.gui._on_run_target_changed()
        self.job_log_offset = 0
        title = self.gui.progress_ctrl._progress_title_for_job(job, fallback="Attached job")
        identity = self.gui.progress_ctrl._progress_job_identity(job)
        run_req = job.get("run_request") or config

        existing_ctx_id = self.gui.progress_ctrl.progress_context_by_job.get(identity) if identity else ""
        existing_ctx = self.gui.progress_ctrl.progress_contexts.get(existing_ctx_id) if existing_ctx_id else None
        if existing_ctx is not None:
            self.gui.progress_ctrl._activate_progress_context(existing_ctx["id"])
            self.gui.progress_ctrl._show_progress_tab()
            self._register_job_monitor_for_active_context()
            if target != "Server":
                self._load_local_progress_state(Path(str(job.get("job_dir", ""))), config)
            self._enter_background_monitor_state("Attaching background job...")
            self._schedule_job_poll(delay_ms=0)
            return True

        self.gui.progress_ctrl._prepare_progress_tab(
            input_files,
            selected_tools or self.gui.state.get_selected_tools(),
            title=title,
            job_identity=identity,
            pipeline_mode=run_req.get("pipeline_mode", ""),
            threads=int(run_req.get("threads", 0) or 0),
            device=run_req.get("device", ""),
        )
        self.gui.progress_ctrl._show_progress_tab()
        self._register_job_monitor_for_active_context()
        if target != "Server":
            self._load_local_progress_state(Path(str(job.get("job_dir", ""))), config)
        self._enter_background_monitor_state("Attaching background job...")
        self._schedule_job_poll(delay_ms=0)
        return True

    def _remote_runner_from_job_entry(self, job: dict, read_metadata: bool = True) -> RemoteRunner | None:
        remote = dict(job.get("remote") or {})
        if remote and not self.gui.remote_ctrl._server_connected():
            self.gui.state.remote_host.set(remote.get("host", self.gui.state.remote_host.get()))
            self.gui.state.remote_port.set(int(remote.get("port", self.gui.state.remote_port.get() or 22)))
            self.gui.state.remote_username.set(remote.get("username", self.gui.state.remote_username.get()))
            self.gui.state.remote_key_path.set(remote.get("key_path", self.gui.state.remote_key_path.get()))
            self.gui.state.remote_workspace.set(remote.get("workspace", self.gui.state.remote_workspace.get()))
            self.gui.state.remote_python.set(remote.get("python", self.gui.state.remote_python.get()))
        if not self.gui.remote_ctrl._require_remote_connection("using remote job actions"):
            return None
        if not self._ensure_remote_auth_for_job_action("server job action"):
            return None
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return None
        runner = RemoteRunner(
            RemoteRunConfig(
                ssh=ssh_config,
                remote_workspace=self.gui.state.remote_workspace.get().strip() or "~/mri-remote-jobs",
                remote_python=self.gui.state.remote_python.get().strip() or "python3",
                output_dir=str(job.get("output_dir") or self.gui.state.output_dir.get().strip()),
                server_output_dir=str(job.get("server_output_dir") or ""),
                download_subdir=str(job.get("download_subdir") or ""),
            ),
            on_log=self.gui.tools_ctrl._remote_log_event,
        )
        remote_dir = str(job.get("remote_job_dir") or "").strip()
        if not remote_dir:
            messagebox.showerror("Missing remote job", "Selected registry entry has no remote job directory.")
            return None
        runner.attach_job(remote_dir, str(job.get("remote_output_dir") or ""))
        if read_metadata:
            metadata = runner.read_remote_metadata()
            if metadata.get("download_subdir"):
                runner.config.download_subdir = str(metadata.get("download_subdir"))
        return runner

    def _load_local_progress_state(self, job_dir: Path, config: dict) -> None:
        if not config or not self.gui.progress_ctrl.image_runs:
            return
        output_dir = Path(str(config.get("effective_output_dir") or config.get("output_dir") or ""))
        input_files = list(self.gui.progress_ctrl.image_runs.keys())
        subject_id_map = config.get("subject_id_map") if isinstance(config.get("subject_id_map"), dict) else {}
        if not subject_id_map and input_files:
            subject_id_map = build_subject_id_map(input_files, config.get("input_dir", ""))

        success_count = 0
        failed_count = 0
        running_count = 0
        for input_file, run in self.gui.progress_ctrl.image_runs.items():
            subject_id = subject_id_map.get(input_file) or config.get("subject_id") or _derive_subject_id(input_file, config.get("input_dir", ""))
            state_path = output_dir / subject_id / "logs" / "pipeline_state.json"
            state = read_json(state_path, {})
            stages = state.get("stages", {}) if isinstance(state.get("stages"), dict) else {}
            for stage, step_state in stages.items():
                if stage not in STAGE_ORDER or not isinstance(step_state, dict):
                    continue
                raw_status = str(step_state.get("status", "")).lower()
                status = {"completed": "Done", "running": "Running", "failed": "Failed"}.get(raw_status, raw_status.capitalize() or "Pending")
                self.gui.progress_ctrl._update_run_step(
                    input_file,
                    stage,
                    tool=str(step_state.get("tool", "")),
                    status=status,
                    duration_sec=step_state.get("duration_sec"),
                    error=str(step_state.get("error", "")),
                )
            pipeline_status = str(state.get("status", "")).lower()
            active_steps = [step for step in run.get("steps", {}).values() if step.get("status") != "Skipped"]
            completed_steps = sum(1 for step in active_steps if step.get("status") == "Done")
            percent = min(100.0, (completed_steps / max(1, len(active_steps))) * 100.0)
            if pipeline_status == "success":
                success_count += 1
                self.gui.progress_ctrl._update_image_run(input_file, status="Done", percent=100, stage_text="Completed")
            elif pipeline_status == "failed":
                failed_count += 1
                self.gui.progress_ctrl._update_image_run(input_file, status="Failed", percent=percent, stage_text="Failed")
            elif pipeline_status in {"running", "paused"}:
                running_count += 1 if pipeline_status == "running" else 0
                if pipeline_status == "running":
                    self.gui.progress_ctrl._set_active_image_key(input_file)
                self.gui.progress_ctrl._update_image_run(input_file, status="Running" if pipeline_status == "running" else "Paused", percent=percent, stage_text=pipeline_status.capitalize())
            elif stages:
                self.gui.progress_ctrl._update_image_run(input_file, percent=percent)

        self.gui.progress_ctrl._set_progress_count("current_success_images", success_count)
        self.gui.progress_ctrl._set_progress_count("current_failed_images", failed_count)
        self.gui.progress_ctrl._set_progress_count("current_running_images", running_count)
        self.gui.progress_ctrl._update_batch_summary()
        if self.gui.progress_ctrl.current_image_key in self.gui.progress_ctrl.image_runs:
            self.gui.progress_ctrl._render_selected_detail()

    def _download_registry_job(self, job: dict) -> None:
        self._download_registry_jobs([job])

    def _download_registry_jobs(self, jobs: list[dict]) -> None:
        if not jobs:
            return
        if len(jobs) == 1:
            job = jobs[0]
            if job.get("target") == "Server":
                runner = self._remote_runner_from_job_entry(job)
                if runner is None:
                    return
                self.gui.pipeline_ctrl.remote_runner = runner
                self.gui.pipeline_ctrl._remote_download_outputs()
                return
            output_dir = job.get("effective_output_dir") or job.get("output_dir")
            ui_events.emit(EVENT_LOG_MESSAGE, f"Local outputs are already available in: {output_dir}")
            return

        local_jobs = [job for job in jobs if job.get("target") != "Server"]
        for job in local_jobs:
            output_dir = job.get("effective_output_dir") or job.get("output_dir")
            ui_events.emit(EVENT_LOG_MESSAGE, f"Local outputs are already available in: {output_dir}")

        remote_jobs = [job for job in jobs if job.get("target") == "Server"]
        if not remote_jobs:
            return
        if self.gui.pipeline_ctrl.running:
            self.gui.progress_ctrl._append_log("Remote task ignored: another task is already running.")
            return

        runners: list[tuple[dict, RemoteRunner]] = []
        for job in remote_jobs:
            runner = self._remote_runner_from_job_entry(job, read_metadata=False)
            if runner is None:
                return
            runners.append((job, runner))

        def task() -> None:
            total = len(runners)
            for idx, (job, runner) in enumerate(runners, start=1):
                label = job.get("remote_job_dir") or job.get("job_id") or f"job {idx}"
                ui_events.emit(EVENT_LOG_MESSAGE, f"Downloading outputs ({idx}/{total}): {label}")
                if not runner.config.download_subdir:
                    metadata = runner.read_remote_metadata()
                    if metadata.get("download_subdir"):
                        runner.config.download_subdir = str(metadata.get("download_subdir"))
                local_path = runner.download_outputs(job.get("output_dir") or self.gui.state.output_dir.get())
                ui_events.emit(EVENT_LOG_MESSAGE, f"Downloaded outputs to: {local_path}")

        self.gui.pipeline_ctrl._run_remote_task(f"Download Outputs ({len(runners)} jobs)", task)

    def _enter_background_monitor_state(self, title: str) -> None:
        self.gui.pipeline_ctrl.running = True
        self.gui.pipeline_ctrl.stop_requested.clear()
        if getattr(self, "resume_button", None) is not None:
            self.gui.pipeline_ctrl.resume_button.configure(state=tk.DISABLED)
        if getattr(self, "restart_button", None) is not None:
            self.gui.pipeline_ctrl.restart_button.configure(state=tk.DISABLED)
        if getattr(self, "stop_button", None) is not None:
            self.gui.pipeline_ctrl.stop_button.configure(state=tk.NORMAL)
        if getattr(self, "progress", None) is not None:
            self.gui.progress.start(10)
        self.gui.state.status_text.set("Running in background")
        ui_events.emit(EVENT_LOG_MESSAGE, title)
        self.gui._validate_configuration()













    def _resume_job_dialog(self, job: dict) -> None:
        from ui.dialogs.job_dialogs import show_resume_job_dialog
        show_resume_job_dialog(self, job)

    def _pause_background_job(self, job: dict) -> bool:
        target = job.get("target")
        if target == "Server":
            runner = self._remote_runner_from_job_entry(job)
            if runner is None:
                return False
            try:
                runner.request_pause()
                ui_events.emit(EVENT_LOG_MESSAGE, f"Remote pause requested: {runner.remote_job_dir}")
                return True
            except Exception as exc:
                messagebox.showerror("Remote pause failed", f"Could not pause remote job:\n\n{type(exc).__name__}: {exc}")
                return False

        raw_job_dir = str(job.get("job_dir", "")).strip()
        if not raw_job_dir:
            return False
        job_dir = Path(raw_job_dir)
        try:
            stop_file = job_dir / "stop_requested"
            stop_file.parent.mkdir(parents=True, exist_ok=True)
            stop_file.touch()
            ui_events.emit(EVENT_LOG_MESSAGE, f"Local pause requested: {stop_file}")
            return True
        except Exception as exc:
            messagebox.showerror("Local pause failed", f"Could not pause local job:\n\n{type(exc).__name__}: {exc}")
            return False

    def _confirm_start_with_existing_jobs(self) -> bool:
        candidates = self.gui.registry_ctrl._running_jobs_for_current_target()
        if candidates is None:
            return False
        if not candidates:
            return True
        job = candidates[0]
        choice = self._choose_start_with_existing_jobs(candidates)
        if choice == "attach":
            self._attach_registry_job(job)
            return False
        if choice == "pause":
            paused = all(self._pause_background_job(candidate) for candidate in candidates)
            if paused:
                self._stop_current_job_monitor()
            return paused
        if choice == "parallel":
            self._stop_current_job_monitor()
            return True
        return False

    def _choose_start_with_existing_jobs(self, candidates: list[dict]) -> str:
        dialog = tk.Toplevel(self.gui.root)
        dialog.title("Background Pipeline Running")
        dialog.geometry("760x280")
        dialog.transient(self.gui.root)
        dialog.grab_set()

        target = self.gui.state.run_target.get()
        first = candidates[0].get("remote_job_dir") or candidates[0].get("job_dir") or candidates[0].get("job_id", "background job")
        more = f"\nAlso found {len(candidates) - 1} other running job(s) for this target." if len(candidates) > 1 else ""
        ttk.Label(
            dialog,
            text=f"A {target} pipeline is already running in the background:\n\n{first}{more}\n\nWhat do you want to do?",
            justify=tk.LEFT,
            wraplength=720,
        ).pack(anchor=tk.W, padx=14, pady=(14, 10))

        result = tk.StringVar(value="cancel")

        def choose(value: str) -> None:
            result.set(value)
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.pack(fill=tk.X, padx=14, pady=(6, 14))
        ttk.Button(buttons, text="Attach Old Job", command=lambda: choose("attach")).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Pause Old and Start New", command=lambda: choose("pause")).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Start New Alongside", style="Accent.TButton", command=lambda: choose("parallel")).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Cancel", command=lambda: choose("cancel")).pack(side=tk.RIGHT)
        dialog.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))
        self.gui.root.wait_window(dialog)
        return result.get()

    def _resume_pipeline(self) -> None:
        if self.gui.pipeline_ctrl.running:
            return
        candidates = self.gui.registry_ctrl._running_jobs_for_current_target()
        if candidates:
            self._attach_registry_job(candidates[0])
            return
        resumable = self.gui.registry_ctrl._resumable_jobs_for_current_target()
        if resumable is None:
            return
        if len(resumable) == 1:
            self._resume_registry_job(resumable[0])
            return
        if resumable:
            self._resume_job_dialog(resumable)
            return
        self.gui.pipeline_ctrl._start_pipeline(resume=True, restart=False)

    def _resume_registry_job(self, job: dict) -> None:
        if job.get("target") == "Server":
            self._resume_remote_registry_job(job)
        else:
            self._resume_local_registry_job(job)

    def _resume_local_registry_job(self, job: dict) -> None:
        job_dir = Path(str(job.get("job_dir", "")))
        config_path = job_dir / "job_config.json"
        config = read_json(config_path, {})
        if not config:
            messagebox.showerror("Resume failed", f"Cannot read local job config:\n{config_path}")
            return
        config["resume"] = True
        config["restart"] = False
        write_json(config_path, config)
        for name in ("stop_requested", "exit_code.txt"):
            try:
                (job_dir / name).unlink()
            except FileNotFoundError:
                pass

        cmd = [sys.executable, "-m", "pipeline.job_worker", "--job-config", str(config_path)]
        kwargs = {
            "cwd": str(PROJECT_ROOT),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd, **kwargs)
        write_json(job_dir / "launcher_status.json", {"pid": proc.pid, "started_at": time.time(), "command": cmd, "resume": True})
        write_json(job_dir / "job_status.json", {"state": "running", "pid": proc.pid, "job_dir": str(job_dir), "output_dir": config.get("output_dir", ""), "updated_at": time.time()})

        entry = dict(job)
        entry.update({"state": "running", "pid": proc.pid, "updated_at": time.time(), "run_request": config})
        upsert_job_registry(entry)
        self.active_job = {"target": "Local", "job_dir": str(job_dir), "pid": proc.pid, "done": False, "registry_entry": entry}
        self.job_log_offset = 0
        self.gui.progress_ctrl._prepare_progress_tab(
            self.gui.progress_ctrl._input_files_for_progress(config),
            config.get("selected_tools") or self.gui.state.get_selected_tools(),
            title=self.gui.progress_ctrl._progress_title_for_job(entry, fallback="Resumed local job"),
            job_identity=self.gui.progress_ctrl._progress_job_identity(entry),
            pipeline_mode=config.get("pipeline_mode", ""),
            threads=int(config.get("threads", 0) or 0),
            device=config.get("device", ""),
        )
        self.gui.progress_ctrl._show_progress_tab()
        self._load_local_progress_state(job_dir, config)
        self._register_job_monitor_for_active_context()
        self._enter_background_monitor_state("Resuming local background job...")
        ui_events.emit(EVENT_LOG_MESSAGE, f"Local background job resumed: {job_dir}")
        self._schedule_job_poll(delay_ms=0)

    def _resume_remote_registry_job(self, job: dict) -> None:
        runner = self._remote_runner_from_job_entry(job)
        if runner is None:
            return
        config = runner.read_remote_job_config()
        if not config:
            messagebox.showerror("Resume failed", f"Cannot read remote job config:\n{runner.remote_job_dir}/job_config.json")
            return
        config["resume"] = True
        config["restart"] = False
        runner.write_remote_job_config(config)
        runner.config.resume = True
        runner.config.restart = False
        self.gui.pipeline_ctrl.remote_runner = runner
        self.gui.state.run_target.set("Server")
        self.gui._on_run_target_changed()
        remote_dir = runner.start_remote_detached()
        entry = dict(job)
        entry.update({"state": "running", "remote_job_dir": remote_dir, "updated_at": time.time(), "run_request": config})
        upsert_job_registry(entry)
        self.active_job = {"target": "Server", "remote_job_dir": remote_dir, "done": False, "registry_entry": entry}
        self.job_log_offset = 0
        self.gui.progress_ctrl._prepare_progress_tab(
            list(job.get("input_files") or []) or self.gui.progress_ctrl._input_files_for_progress(config),
            config.get("selected_tools") or self.gui.state.get_selected_tools(),
            title=self.gui.progress_ctrl._progress_title_for_job(entry, fallback="Resumed remote job"),
            job_identity=self.gui.progress_ctrl._progress_job_identity(entry),
            pipeline_mode=config.get("pipeline_mode", ""),
            threads=int(config.get("threads", 0) or 0),
            device=config.get("device", ""),
        )
        self.gui.progress_ctrl._show_progress_tab()
        self._register_job_monitor_for_active_context()
        self._enter_background_monitor_state("Resuming remote background job...")
        self.gui._validate_configuration()
        ui_events.emit(EVENT_LOG_MESSAGE, f"Remote background job resumed: {remote_dir}")
        self._schedule_job_poll(delay_ms=0)

    def _build_ssh_config(self) -> SSHConfig | None:
        host = self.gui.state.remote_host.get().strip()
        username = self.gui.state.remote_username.get().strip()
        if not host or not username:
            messagebox.showerror("Missing remote server", "Cần nhập Host/IP và Username của remote server.")
            return None

        return SSHConfig(
            host=host,
            port=int(self.gui.state.remote_port.get()),
            username=username,
            password=self.gui.state.remote_password.get(),
            key_path=self.gui.state.remote_key_path.get().strip(),
        )

    def _build_remote_runner(self, resume: bool = False, req: dict | None = None) -> RemoteRunner | None:
        req = req or self.gui.pipeline_ctrl._build_run_request()
        if req is None:
            return None
        if not self.gui.remote_ctrl._require_remote_connection("running on the remote server"):
            return None

        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return None

        remote_config = RemoteRunConfig(
            ssh=ssh_config,
            remote_workspace=self.gui.state.remote_workspace.get().strip() or "~/mri-remote-jobs",
            remote_python=self.gui.state.remote_python.get().strip() or "python3",
            input_mode=req["mode"],
            input_file=req.get("input_file", ""),
            input_files=req.get("input_files", []),
            input_dir=req.get("input_dir", ""),
            output_dir=req["output_dir"],
            server_output_dir=req.get("server_output_dir", ""),
            license_dir=req["license_dir"],
            device=req["device"],
            threads=req["threads"],
            ram_percent=req.get("ram_percent", 100),
            selected_tools=req["selected_tools"],
            export_config=req["export_config"],
            stats_vector_config=req["stats_vector_config"],
            recursive=req.get("recursive", True),
            download_subdir=req.get("batch_output_name", "") if req.get("is_batch") else "",
            resume=resume,
            lazy_watch=req.get("lazy_watch", False),
        )
        return RemoteRunner(remote_config, on_log=self.gui.tools_ctrl._remote_log_event)

    def _schedule_job_poll(self, delay_ms: int = 1500, context_id: str | None = None) -> None:
        context_id = context_id or getattr(self, "active_progress_context_id", "")
        monitor = self.job_monitors.get(context_id) if context_id else None
        if monitor is None:
            if self.job_poll_after_id:
                try:
                    self.gui.root.after_cancel(self.job_poll_after_id)
                except Exception:
                    pass
            self.job_poll_after_id = self.gui.root.after(delay_ms, self._poll_active_job)
            return
        if monitor.get("after_id"):
            try:
                self.gui.root.after_cancel(monitor["after_id"])
            except Exception:
                pass
        monitor["after_id"] = self.gui.root.after(delay_ms, lambda cid=context_id: self._poll_active_job(cid))
        if context_id == getattr(self, "active_progress_context_id", ""):
            self.job_poll_after_id = monitor["after_id"]

    def _poll_active_job(self, context_id: str | None = None) -> None:
        monitor = self._load_job_monitor(context_id) if context_id else None
        if context_id and monitor is None:
            return
        if not self.active_job:
            if monitor is not None:
                monitor["after_id"] = None
                self._save_job_monitor(monitor)
            else:
                self.job_poll_after_id = None
            if getattr(self, "_attach_loading_active", False):
                self._finish_attach_loading()
            return
        try:
            target = self.active_job.get("target")
            if target == "Server":
                self._start_remote_poll_worker(context_id)
                if monitor is not None:
                    self._save_job_monitor(monitor)
                return
            else:
                done = self._poll_local_background_job()
        except Exception as exc:
            ui_events.emit(EVENT_LOG_MESSAGE, f"BACKGROUND POLL ERROR: {type(exc).__name__}: {exc}")
            done = False

        if done:
            self.active_job["done"] = True
            if monitor is not None:
                monitor["after_id"] = None
                self._save_job_monitor(monitor)
            self.job_poll_after_id = None
            self.gui.progress_ctrl._set_idle_state()
            if getattr(self, "_attach_loading_active", False):
                self._finish_attach_loading()
            return
        if monitor is not None:
            self._save_job_monitor(monitor)
        self._schedule_job_poll(context_id=context_id)
        if getattr(self, "_attach_loading_active", False):
            self._finish_attach_loading()

    def _start_remote_poll_worker(self, context_id: str | None = None) -> None:
        monitor = self.job_monitors.get(context_id) if context_id else None
        if monitor is not None and monitor.get("remote_poll_in_flight"):
            return
        if monitor is None and self.remote_poll_in_flight:
            return
        if not self.gui.pipeline_ctrl.remote_runner:
            self.gui.progress_ctrl._set_idle_state()
            if getattr(self, "_attach_loading_active", False):
                self._finish_attach_loading()
            return
        self.remote_poll_in_flight = True
        if monitor is not None:
            monitor["remote_poll_in_flight"] = True
        runner = self.gui.pipeline_ctrl.remote_runner
        offset = self.job_log_offset

        def worker() -> None:
            data = ""
            new_offset = offset
            status: dict = {"state": "running"}
            error: Exception | None = None
            try:
                data, new_offset = runner.read_remote_log_since(offset)
                status = runner.remote_status()
                if str(status.get("state", "")) in {"completed", "failed"}:
                    final_data, final_offset = runner.read_remote_log_since(new_offset)
                    if final_data:
                        data += final_data
                        new_offset = final_offset
            except Exception as exc:
                error = exc
            self.gui.root.after(0, lambda r=runner, cid=context_id: self._finish_remote_poll(r, data, new_offset, status, error, cid))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_remote_poll(self, runner: RemoteRunner, data: str, new_offset: int, status: dict, error: Exception | None, context_id: str | None = None) -> None:
        monitor = self._load_job_monitor(context_id) if context_id else None
        expected_runner = monitor.get("remote_runner") if monitor is not None else self.gui.pipeline_ctrl.remote_runner
        if runner is not expected_runner:
            return
        finish_attach_loading = bool(getattr(self, "_attach_loading_active", False))
        self.remote_poll_in_flight = False
        if monitor is not None:
            monitor["remote_poll_in_flight"] = False
        if not self.active_job or self.active_job.get("target") != "Server":
            if monitor is not None:
                monitor["after_id"] = None
                self._save_job_monitor(monitor)
            else:
                self.job_poll_after_id = None
            if finish_attach_loading:
                self._finish_attach_loading()
            return
        if error is not None:
            ui_events.emit(EVENT_LOG_MESSAGE, f"BACKGROUND POLL ERROR: {type(error).__name__}: {error}")
            if monitor is not None:
                self._save_job_monitor(monitor)
            self._schedule_job_poll(context_id=context_id)
            if finish_attach_loading:
                self._finish_attach_loading()
            return
        self.job_log_offset = new_offset
        self.gui.progress_ctrl._handle_background_log_chunk(data)
        state = str(status.get("state", "running"))
        if state in {"completed", "failed"}:
            ui_events.emit(EVENT_LOG_MESSAGE, f"Remote background job finished with exit code {status.get('exit_code')}")
            if status.get("error"):
                ui_events.emit(EVENT_LOG_MESSAGE, f"Remote background job error: {status.get('error')}")
            if state == "failed":
                for key, run in self.gui.progress_ctrl.image_runs.items():
                    for stage, step in (run.get("steps") or {}).items():
                        if step.get("status") == "Running":
                            self.gui.progress_ctrl._update_run_step(key, stage, status="Failed")
                    if run.get("status") in {"Pending", "Running"}:
                        stage_text = "Remote job failed before this image started" if run.get("status") == "Pending" else "Remote job failed"
                        self.gui.progress_ctrl._update_image_run(key, status="Failed", stage_text=stage_text)
                self.gui.progress_ctrl._set_progress_count("current_running_images", 0)
                failed_count = sum(1 for run in self.gui.progress_ctrl.image_runs.values() if run.get("status") == "Failed")
                self.gui.progress_ctrl._set_progress_count("current_failed_images", failed_count)
                self.gui.progress_ctrl._update_batch_summary()
            ui_events.emit(EVENT_LOG_MESSAGE, "Use Download Outputs to copy remote outputs to the local output folder.")
            self.gui.registry_ctrl._update_registry_for_active_job(state, status.get("exit_code"))
            self.active_job["done"] = True
            if monitor is not None:
                monitor["after_id"] = None
                self._save_job_monitor(monitor)
            self.job_poll_after_id = None
            self.gui.progress_ctrl._set_idle_state()
            if finish_attach_loading:
                self._finish_attach_loading()
            return
        self.gui.state.status_text.set("Running in background")
        self.gui.state.remote_status.set(f"Remote: {state}")
        if monitor is not None:
            self._save_job_monitor(monitor)
        self._schedule_job_poll(context_id=context_id)
        if finish_attach_loading:
            self._finish_attach_loading()

    def _poll_local_background_job(self) -> bool:
        if not self.active_job:
            return True
        job_dir = Path(str(self.active_job.get("job_dir", "")))
        log_path = job_dir / "run.log"
        if log_path.exists():
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self.job_log_offset)
                data = f.read()
                self.job_log_offset = f.tell()
            self.gui.progress_ctrl._handle_background_log_chunk(data)

        status = read_json(job_dir / "job_status.json", {})
        state = str(status.get("state", "running"))
        exit_path = job_dir / "exit_code.txt"
        if exit_path.exists() or state in {"completed", "failed"}:
            code = status.get("exit_code")
            if code is None and exit_path.exists():
                code = exit_path.read_text(encoding="utf-8", errors="replace").strip()
            ui_events.emit(EVENT_LOG_MESSAGE, f"Local background job finished with exit code {code}")
            self.gui.registry_ctrl._update_registry_for_active_job("completed" if str(code) == "0" else "failed", code)
            return True
        self.gui.state.status_text.set("Running in background")
        return False
