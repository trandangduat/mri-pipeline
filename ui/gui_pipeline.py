from __future__ import annotations
from ui.events import ui_events, EVENT_LOG_MESSAGE
"""Pipeline startup, execution, and utility-task mixin for the MRI Pipeline GUI."""


import os
import posixpath
import shlex
import stat
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from pipeline.jobs import create_local_job_dir, upsert_job_registry, write_json
from pipeline.config import PROJECT_ROOT
from pipeline.registry import STAGE_ORDER
from pipeline.discovery import _is_supported_mri_input, _is_dicom_series_dir, _discover_mri_files
from remote.remote_runner import RemoteRunConfig, RemoteRunner
from remote.ssh_client import RemoteSSHClient
from ui.formatters import truncate_middle


class PipelineController:

    def register_remote_host_entry(self, entry):
        self.remote_host_entry = entry

    def register_remote_username_entry(self, entry):
        self.remote_username_entry = entry

    def register_remote_port_entry(self, entry):
        self.remote_port_entry = entry

    def register_remote_workspace_entry(self, entry):
        self.remote_workspace_entry = entry

    def register_remote_password_entry(self, entry):
        self.remote_password_entry = entry

    def __init__(self, gui):
        self.gui = gui
        
        # Pipeline state
        self.running = False
        import threading
        self.stop_requested = threading.Event()
        self.remote_connecting = False
        self.remote_health_after_id = None
        self.remote_health_in_flight = False
        self.remote_runner = None
        
        # UI Elements
        self.remote_frame = None
        self.remote_body = None
        self.remote_pack_options = None
        self.remote_status_icon_label = None
        self.remote_host_entry = None
        self.remote_port_entry = None
        self.remote_username_entry = None
        self.remote_password_entry = None
        self.remote_key_entry = None
        self.remote_key_button = None
        self.remote_save_button = None
        self.remote_clear_button = None
        self.remote_test_button = None
        self.remote_connect_button = None
        self.remote_disconnect_button = None
        self.resume_button = None
        self.restart_button = None
        self.restart_tooltip = None
        self.stop_button = None
        self.stop_tooltip = None
        self._remote_upload_spinner_label = None
        self._remote_health_spinner_label = None
    def _remote_is_dicom_name(self, name: str) -> bool:
        return name.lower().endswith((".dcm", ".dicom", ".ima"))

    def _remote_dir_contains_dicom(self, ssh: RemoteSSHClient, remote_path: str) -> bool:
        try:
            for item in ssh.sftp.listdir_attr(remote_path):
                if item.filename.startswith("."):
                    continue
                if not stat.S_ISDIR(item.st_mode) and self._remote_is_dicom_name(item.filename):
                    return True
        except OSError:
            return False
        return False

    def _upload_remote_job_with_dialog(self, runner) -> bool:
        from ui.dialogs.job_dialogs import show_upload_remote_job_dialog
        return show_upload_remote_job_dialog(self, runner)

    def _start_pipeline(self, resume: bool = False, restart: bool = False) -> None:
        if not self.gui.jobs_ctrl._can_start_new_pipeline():
            return

        if not self.gui._validate_configuration():
            messagebox.showerror("Configuration incomplete", self.gui.state.config_status.get())
            return

        if not self.gui.jobs_ctrl._confirm_start_with_existing_jobs():
            return

        starter_button = getattr(self, "restart_button" if restart else "resume_button", None) if (restart or resume) else None
        if starter_button is not None:
            self.gui._set_button_busy(starter_button, True, "Starting")
        started = False
        try:
            if self.gui.state.run_target.get() == "Server":
                if self.gui.state.input_source.get() == "Local":
                    self._start_lazy_upload_pipeline(resume, restart, starter_button)
                    return
                
                run_request = self._build_run_request()
                if run_request is None:
                    return
                runner = self.remote_runner if resume and self.remote_runner else self.gui.jobs_ctrl._build_remote_runner(resume=resume, req=run_request)
                if not runner:
                    return
                if restart:
                    self.remote_runner = None
                runner.config.resume = resume
                runner.config.restart = restart
                if not runner.remote_job_dir and not self._upload_remote_job_with_dialog(runner):
                    messagebox.showerror("Remote upload failed", "Could not copy files to the remote server. Pipeline was not started.")
                    return
                self.remote_runner = runner
                self.gui.progress_ctrl._prepare_progress_tab(
                    self.gui.progress_ctrl._input_files_for_progress(run_request),
                    run_request.get("selected_tools"),
                    title="Server: starting",
                    pipeline_mode=run_request.get("pipeline_mode", ""),
                    threads=int(run_request.get("threads", 0) or 0),
                    device=run_request.get("device", ""),
                )
                self.gui.progress_ctrl._show_progress_tab()
                self._start_remote_pipeline(resume=resume, restart=restart, runner=runner, run_request=run_request)
                started = True
                if starter_button is not None:
                    self.gui._set_button_busy(starter_button, False)
                self.gui._validate_configuration()
                return

            run_request = self._build_run_request()
            if run_request is None:
                return
            run_request["resume"] = resume
            run_request["restart"] = restart

            self.gui.progress_ctrl._prepare_progress_tab(
                self.gui.progress_ctrl._input_files_for_progress(run_request),
                run_request.get("selected_tools"),
                title="Local: starting",
                pipeline_mode=run_request.get("pipeline_mode", ""),
                threads=int(run_request.get("threads", 0) or 0),
                device=run_request.get("device", ""),
            )
            self.gui.progress_ctrl._show_progress_tab()

            self.running = True
            self.stop_requested.clear()
            if getattr(self, "resume_button", None) is not None:
                self.resume_button.configure(state=tk.DISABLED)
            if getattr(self, "restart_button", None) is not None:
                self.restart_button.configure(state=tk.DISABLED)
            if getattr(self, "stop_button", None) is not None:
                self.stop_button.configure(state=tk.NORMAL)
            if getattr(self, "progress", None) is not None:
                self.progress.start(10)
            self.gui.progress_ctrl.detail_chart.reset()
            self.gui.progress_ctrl.gpu_chart.reset()
            self.gui.state.overall_progress_var.set(0)
            self.gui.state.overall_progress_text.set("0%")
            self.gui.state.status_text.set("Running")
            self.gui.progress_ctrl._clear_log()
            ui_events.emit(EVENT_LOG_MESSAGE, "=" * 80)
            if restart:
                ui_events.emit(EVENT_LOG_MESSAGE, "Restart mode: existing subject outputs will be removed before running.")
            elif resume:
                ui_events.emit(EVENT_LOG_MESSAGE, "Resume mode: completed stages in pipeline_state.json will be skipped.")
            ui_events.emit(EVENT_LOG_MESSAGE, "Starting pipeline...")
            self._start_local_background_pipeline(run_request)
            started = True
            if starter_button is not None:
                self.gui._set_button_busy(starter_button, False)
            self.gui._validate_configuration()
        finally:
            if not started:
                if starter_button is not None:
                    self.gui._set_button_busy(starter_button, False)
                self.gui._validate_configuration()

    def _start_lazy_upload_pipeline(self, resume: bool, restart: bool, starter_button: tk.Widget | None) -> None:
        run_request = self._build_run_request()
        if run_request is None:
            if starter_button is not None:
                self.gui._set_button_busy(starter_button, False)
            return

        run_request["lazy_watch"] = True
        run_request["resume"] = resume
        run_request["restart"] = restart
        
        server_output_dir = self.gui.state.server_output_dir.get().strip() or "~/mri-server-outputs"
        remote_lazy_dir = posixpath.join(server_output_dir, "lazy_input", time.strftime('%Y%m%d_%H%M%S'))
        
        mode = run_request.get("mode")
        if mode == "file":
            local_files = [Path(run_request["input_file"])]
        elif mode == "files":
            local_files = [Path(f) for f in run_request.get("input_files", [])]
        else:
            local_files = [Path(f) for f in _discover_mri_files(run_request.get("input_dir", ""), recursive=run_request.get("recursive", True))]
            
        if not local_files:
            messagebox.showerror("Error", "No local MRI files found to upload.")
            if starter_button is not None:
                self.gui._set_button_busy(starter_button, False)
            return

        run_request["input_dir"] = remote_lazy_dir
        run_request["input_source"] = "Server"
        if mode == "file":
            run_request["mode"] = "dir"
            run_request["recursive"] = False

        runner = self.remote_runner if resume and self.remote_runner else self.gui.jobs_ctrl._build_remote_runner(resume=resume, req=run_request)
        if not runner:
            if starter_button is not None:
                self.gui._set_button_busy(starter_button, False)
            return
            
        if restart:
            self.remote_runner = None
            
        runner.config.resume = resume
        runner.config.restart = restart
        
        self.remote_runner = runner
        self.gui.progress_ctrl._prepare_progress_tab(
            self.gui.progress_ctrl._input_files_for_progress(run_request),
            run_request.get("selected_tools"),
            title="Server: starting (Lazy Upload)",
            pipeline_mode=run_request.get("pipeline_mode", ""),
            threads=int(run_request.get("threads", 0) or 0),
            device=run_request.get("device", ""),
        )
        self.gui.progress_ctrl._show_progress_tab()
        self._start_remote_pipeline(resume=resume, restart=restart, runner=runner, run_request=run_request)
        
        if starter_button is not None:
            self.gui._set_button_busy(starter_button, False)
        self.gui._validate_configuration()
        
        def upload_worker() -> None:
            try:
                ssh_config = self.gui.remote_ctrl._ssh_config_from_current_remote()
                if ssh_config is None:
                    return
                with RemoteSSHClient(ssh_config, self.gui.progress_ctrl._log) as ssh:
                    ssh.mkdir_p(remote_lazy_dir)
                    
                    valid_parents = [f.parent for f in local_files if f.exists()]
                    if valid_parents:
                        try:
                            common_parent = Path(os.path.commonpath([str(p) for p in valid_parents]))
                        except ValueError:
                            common_parent = valid_parents[0]
                    else:
                        common_parent = None

                    def upload_item(item_path: Path, item_rel: str) -> bool:
                        if getattr(self, "stop_requested", threading.Event()).is_set():
                            return False
                        remote_tmp = posixpath.join(remote_lazy_dir, item_rel + ".tmp")
                        remote_final = posixpath.join(remote_lazy_dir, item_rel)
                        if item_path.is_file():
                            ssh.mkdir_p(posixpath.dirname(remote_final))
                            ssh.sftp.put(str(item_path), remote_tmp)
                            ssh.sftp.rename(remote_tmp, remote_final)
                        elif item_path.is_dir():
                            ssh.mkdir_p(remote_final)
                            for child in item_path.iterdir():
                                if not upload_item(child, item_rel + "/" + child.name):
                                    return False
                        return True

                    for idx, local_file in enumerate(local_files):
                        ui_events.emit(EVENT_LOG_MESSAGE, f"Lazy Upload: Copying {local_file.name} ({idx+1}/{len(local_files)})...")
                        
                        if common_parent:
                            try:
                                rel_path = local_file.relative_to(common_parent).as_posix()
                            except ValueError:
                                rel_path = local_file.name
                        else:
                            rel_path = local_file.name
                            
                        if not upload_item(local_file, rel_path):
                            ui_events.emit(EVENT_LOG_MESSAGE, "Lazy Upload: Stopped early by user.")
                            break
                        ui_events.emit(EVENT_LOG_MESSAGE, f"Lazy Upload: {local_file.name} ready on server.")
                    else:
                        ssh.run(f"touch {shlex.quote(remote_lazy_dir + '/.upload_done')}", stream=False, check=False)
                        ui_events.emit(EVENT_LOG_MESSAGE, "Lazy Upload: All files uploaded. Waiting for server to finish processing...")
            except Exception as e:
                ui_events.emit(EVENT_LOG_MESSAGE, f"Lazy Upload Error: {e}")
                
        threading.Thread(target=upload_worker, daemon=True).start()

    def _start_local_background_pipeline(self, run_request: dict) -> None:
        job_dir = create_local_job_dir(run_request.get("output_dir") or PROJECT_ROOT / "outputs")
        run_request = dict(run_request)
        run_request["job_dir"] = str(job_dir)
        run_request["run_target"] = "Local"
        config_path = job_dir / "job_config.json"
        write_json(config_path, run_request)

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
        write_json(job_dir / "launcher_status.json", {"pid": proc.pid, "started_at": time.time(), "command": cmd})
        entry = self.gui.registry_ctrl._registry_entry_for_local_job(job_dir, run_request, proc.pid)
        upsert_job_registry(entry)
        self.gui.progress_ctrl._rename_active_progress_tab(self.gui.progress_ctrl._progress_title_for_job(entry, fallback="Local job"), self.gui.progress_ctrl._progress_job_identity(entry))
        ui_events.emit(EVENT_LOG_MESSAGE, f"Local background job started: {job_dir}")
        ui_events.emit(EVENT_LOG_MESSAGE, "You can close the GUI. The local worker process will keep running.")
        self.gui.jobs_ctrl.active_job = {"target": "Local", "job_dir": str(job_dir), "pid": proc.pid, "done": False, "registry_entry": entry}
        self.gui.jobs_ctrl.job_log_offset = 0
        self.gui.jobs_ctrl._register_job_monitor_for_active_context()
        self.gui._validate_configuration()
        self.gui.jobs_ctrl._schedule_job_poll(delay_ms=0)

    def _start_remote_pipeline(self, resume: bool = False, restart: bool = False, runner: RemoteRunner | None = None, run_request: dict | None = None) -> None:
        runner = runner or (self.remote_runner if resume and self.remote_runner else self.gui.jobs_ctrl._build_remote_runner(resume=resume))
        if not runner:
            return
        if resume and self.remote_runner is None:
            ui_events.emit(EVENT_LOG_MESSAGE, "No previous remote job is loaded in this GUI session; creating a new remote job instead.")
        if restart:
            self.remote_runner = None
        runner.config.resume = resume
        runner.config.restart = restart
        self.remote_runner = runner
        self.gui.jobs_ctrl._enter_background_monitor_state("Starting remote background job...")
        remote_dir = runner.start_remote_detached()
        entry = self.gui.registry_ctrl._registry_entry_for_remote_job(runner, remote_dir, run_request=run_request)
        upsert_job_registry(entry)
        self.gui.progress_ctrl._rename_active_progress_tab(self.gui.progress_ctrl._progress_title_for_job(entry, fallback="Remote job"), self.gui.progress_ctrl._progress_job_identity(entry))
        ui_events.emit(EVENT_LOG_MESSAGE, f"Remote background job started: {remote_dir}")
        ui_events.emit(EVENT_LOG_MESSAGE, "You can close the GUI. Reopen and attach this remote job to monitor or download outputs.")
        self.gui.jobs_ctrl.active_job = {"target": "Server", "remote_job_dir": remote_dir, "done": False, "registry_entry": entry}
        self.gui.jobs_ctrl.job_log_offset = 0
        self.gui.jobs_ctrl._register_job_monitor_for_active_context()
        self.gui._validate_configuration()
        self.gui.jobs_ctrl._schedule_job_poll(delay_ms=0)

    def _build_run_request(self) -> dict | None:
        mode = self.gui.state.input_mode.get()
        input_source = self.gui.state.input_source.get()
        raw_input = self.gui.state.input_path.get().strip()
        if not raw_input:
            messagebox.showerror("Missing input", "Chưa chọn file hoặc folder MRI.")
            return None
        if input_source == "Server" and self.gui.state.run_target.get() != "Server":
            messagebox.showerror("Invalid input", "Server input requires Run on = Server.")
            return None

        selected_tools = self.gui._selected_tools() if hasattr(self, "_selected_tools") else self.gui.state.get_selected_tools()
        is_batch = mode == "dir"
        output_dir = self.gui.state.output_dir.get().strip()
        batch_output_name = f"batch_{time.strftime('%Y%m%d_%H%M%S')}" if is_batch else ""
        base = {
            "mode": mode,
            "output_dir": output_dir,
            "server_output_dir": self.gui.state.server_output_dir.get().strip(),
            "effective_output_dir": str(Path(output_dir) / batch_output_name) if batch_output_name else output_dir,
            "is_batch": is_batch,
            "batch_output_name": batch_output_name,
            "license_dir": self.gui.state.license_dir.get().strip(),
            "device": self.gui.state.device.get(),
            "threads": int(self.gui.state.threads.get()),
            "ram_percent": int(self.gui.state.ram_percent.get()),
            "selected_tools": selected_tools,
            "export_config": self.gui.state.get_export_config(),
            "stats_vector_config": self.gui.state.get_stats_vector_config(),
            "input_source": input_source,
            "pipeline_mode": self.gui.state.pipeline_mode.get(),
        }

        if self.gui.state.run_target.get() != "Server" and input_source != "Local":
            messagebox.showerror("Invalid input", "Local runs can only use local input data.")
            return None

        if input_source == "Server":
            if mode == "file":
                path = self.gui.state.selected_files[0] if self.gui.state.selected_files else raw_input
                if path.lower().endswith((".dcm", ".dicom", ".ima")):
                    parent = str(Path(path).parent)
                    base["mode"] = "dir"
                    base["is_batch"] = False
                    base["input_dir"] = parent
                    base["input_file"] = parent
                    base["recursive"] = False
                else:
                    base["input_file"] = path
            elif mode == "files":
                files = self.gui.state.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
                if not files:
                    messagebox.showerror("Invalid input", "Danh sách file server không hợp lệ.")
                    return None
                base["input_files"] = files
                base["input_dir"] = self._common_remote_input_root(files)
            else:
                if self.gui.state.selected_files:
                    base["mode"] = "files"
                    base["input_files"] = list(self.gui.state.selected_files)
                    base["input_dir"] = self._common_remote_input_root(self.gui.state.selected_files)
                else:
                    base["input_dir"] = raw_input
                    base["recursive"] = not self.gui.state.non_recursive.get()
            if not self._validate_remote_input_request(base):
                return None
            return base

        if mode == "file":
            path = self.gui.state.selected_files[0] if self.gui.state.selected_files else raw_input
            if not _is_supported_mri_input(path):
                messagebox.showerror("Invalid input", f"Không tồn tại file MRI hoặc folder DICOM: {path}")
                return None
            p = Path(path).expanduser()
            if p.is_file() and p.suffix.lower() in (".dcm", ".dicom", ".ima"):
                parent = p.parent
                if _is_dicom_series_dir(parent):
                    base["mode"] = "dir"
                    base["is_batch"] = False
                    base["input_dir"] = str(parent)
                    base["input_file"] = str(parent)
                    base["recursive"] = False
                    return base
            base["input_file"] = path
        elif mode == "files":
            files = self.gui.state.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
            missing = [p for p in files if not _is_supported_mri_input(p)]
            if not files or missing:
                messagebox.showerror("Invalid input", "Danh sách file MRI/folder DICOM không hợp lệ.")
                return None
            base["input_files"] = files
            base["input_dir"] = self._common_input_root(files)
        else:
            if not Path(raw_input).is_dir():
                messagebox.showerror("Invalid input", f"Không tồn tại folder: {raw_input}")
                return None
            if self.gui.state.selected_files:
                base["mode"] = "files"
                base["input_files"] = self.gui.state.selected_files
                base["input_dir"] = self._common_input_root(self.gui.state.selected_files)
            else:
                base["input_dir"] = raw_input
                base["recursive"] = not self.gui.state.non_recursive.get()

        return base

    def _validate_remote_input_request(self, req: dict) -> bool:
        paths: list[tuple[str, str]] = []
        mode = req.get("mode")
        if mode == "file":
            paths = [(str(req.get("input_file", "")).strip(), "file")]
        elif mode == "files":
            paths = [(str(path).strip(), "file") for path in req.get("input_files", [])]
        else:
            paths = [(str(req.get("input_dir", "")).strip(), "dir")]

        missing_selection = [path for path, _kind in paths if not path or path == "~"]
        if missing_selection:
            messagebox.showerror(
                "Missing server input",
                "Chọn data MRI trên server hoặc upload input lên server trước khi Run.",
            )
            return False

        ssh_config = self.gui.remote_ctrl._ssh_config_from_current_remote()
        if ssh_config is None:
            return False
        try:
            with RemoteSSHClient(ssh_config, lambda _line: None) as ssh:
                for path, kind in paths:
                    remote_path = ssh.expand_path(path)
                    attrs = ssh.sftp.stat(remote_path)
                    is_dir = stat.S_ISDIR(attrs.st_mode)
                    if kind == "file" and is_dir:
                        if not self._remote_dir_contains_dicom(ssh, remote_path):
                            messagebox.showerror("Invalid server input", f"Server input phải là file MRI hoặc folder DICOM, nhưng folder này không chứa DICOM trực tiếp:\n{path}")
                            return False
                    if kind == "dir" and not is_dir:
                        messagebox.showerror("Invalid server input", f"Server input phải là folder, nhưng đây là file:\n{path}")
                        return False
        except FileNotFoundError:
            messagebox.showerror("Invalid server input", "Không tìm thấy input trên server. Hãy Browse Server hoặc upload input trước khi Run.")
            return False
        except OSError as exc:
            messagebox.showerror("Invalid server input", f"Không thể kiểm tra input trên server:\n\n{type(exc).__name__}: {exc}")
            return False
        except Exception as exc:
            messagebox.showerror("Server input check failed", f"Không thể kết nối/kiểm tra server input:\n\n{type(exc).__name__}: {exc}")
            return False
        return True

    def _common_remote_input_root(self, files: list[str]) -> str:
        parents = [posixpath.dirname(path.rstrip("/")) or "/" for path in files]
        try:
            return posixpath.commonpath(parents)
        except ValueError:
            return parents[0] if parents else "/"

    def _run_remote_task(self, title: str, task, clear_log: bool = False, enable_pause: bool = False) -> None:
        if self.running:
            self.gui.progress_ctrl._append_log("Remote task ignored: another task is already running.")
            return
        self.running = True
        self.gui.state.remote_status.set(f"Remote: {title} running...")
        self.stop_requested.clear()
        if getattr(self, "resume_button", None) is not None:
            self.resume_button.configure(state=tk.DISABLED)
        if getattr(self, "restart_button", None) is not None:
            self.restart_button.configure(state=tk.DISABLED)
        if getattr(self, "stop_button", None) is not None:
            self.stop_button.configure(state=tk.NORMAL if enable_pause else tk.DISABLED)
        if getattr(self, "progress", None) is not None:
            self.progress.start(10)
        if clear_log:
            self.gui.progress_ctrl._clear_log()
            self.gui.progress_ctrl.detail_chart.reset()
            self.gui.progress_ctrl.gpu_chart.reset()
            self.gui.state.overall_progress_var.set(0)
            self.gui.state.overall_progress_text.set("0%")
            self.gui.state.status_text.set("Running")
        self.gui.progress_ctrl._append_log("=" * 80)
        self.gui.progress_ctrl._append_log(f"Remote task started: {title}")

        def worker():
            try:
                task()
                self.gui.log_queue.put(f"Remote task completed: {title}")
            except Exception as exc:
                self.gui.log_queue.put(f"REMOTE ERROR [{title}]: {type(exc).__name__}: {exc}")
            finally:
                self.gui.root.after(0, lambda: self.gui.state.remote_status.set("Remote: idle"))
                self.gui.root.after(0, self.gui.progress_ctrl._set_idle_state)

        threading.Thread(target=worker, daemon=True).start()

    def _remote_test_ssh(self) -> None:
        if self.gui.state.run_target.get() != "Server":
            return
        ssh_config = self.gui.remote_ctrl._ssh_config_from_current_remote()
        if ssh_config is None:
            return
        thread_signature = self.gui.remote_ctrl._current_remote_connection_signature()
        if thread_signature is None:
            return
        self.remote_connecting = True
        self.gui.remote_ctrl._sync_remote_connection_controls()

        def task():
            try:
                def set_testing():
                    self.gui.remote_ctrl._cancel_remote_health_check()
                    self.gui.state.remote_status.set("Connecting to server...")
                    self.gui.remote_ctrl._set_remote_status_icon("running")
                    self.gui._connected_remote_signature = None
                    self.gui._remote_thread_max_signature = None
                    self.gui._set_thread_max(None, pending=True)
                    self.gui.remote_ctrl._reset_remote_tool_image_state()
                    if getattr(self, "remote_status_label", None) is not None:
                        self.remote_status_label.configure(foreground="")
                self.gui.root.after(0, set_testing)
                runner = RemoteRunner(RemoteRunConfig(ssh=ssh_config), on_log=lambda x: None)
                runner.test_ssh()
                try:
                    max_threads = self.gui.remote_ctrl._read_remote_thread_max(ssh_config)
                except Exception:
                    max_threads = None
                def set_success():
                    self.remote_connecting = False
                    if thread_signature != self.gui.remote_ctrl._current_remote_connection_signature():
                        self.gui.remote_ctrl._sync_remote_connection_controls()
                        return
                    self.gui._connected_remote_signature = thread_signature
                    self.gui.state.remote_status.set("Remote: connected")
                    self.gui.remote_ctrl._set_remote_status_icon("success")
                    self.gui._remote_thread_max_signature = thread_signature if max_threads else None
                    self.gui._set_thread_max(max_threads)
                    self.gui.remote_ctrl._sync_remote_connection_controls()
                    self.gui.remote_ctrl._schedule_remote_health_check()
                    if getattr(self, "remote_status_label", None) is not None:
                        self.remote_status_label.configure(foreground="#16a34a") # green
                self.gui.root.after(0, set_success)
            except Exception as exc:
                err_msg = f"Remote connection failed: {exc}"
                def set_failed(m=err_msg):
                    self.remote_connecting = False
                    self.gui._connected_remote_signature = None
                    self.gui.state.remote_status.set(m)
                    self.gui.remote_ctrl._set_remote_status_icon("failed")
                    self.gui._remote_thread_max_signature = None
                    self.gui._set_thread_max(None)
                    self.gui.remote_ctrl._sync_remote_connection_controls()
                    if getattr(self, "remote_status_label", None) is not None:
                        self.remote_status_label.configure(foreground="#dc2626") # red
                self.gui.root.after(0, set_failed)

        threading.Thread(target=task, daemon=True).start()

    def _remote_download_outputs(self) -> None:
        def task():
            if not self.remote_runner:
                ui_events.emit(EVENT_LOG_MESSAGE, "No remote job is available. Run or attach a remote job first.")
                return
            local_path = self.remote_runner.download_outputs(self.gui.state.output_dir.get())
            ui_events.emit(EVENT_LOG_MESSAGE, f"Downloaded outputs to: {local_path}")
        self._run_remote_task("Download Outputs", task)

    def _common_input_root(self, files: list[str]) -> str:
        parents = [str(Path(f).resolve().parent) for f in files]
        try:
            return os.path.commonpath(parents)
        except ValueError:
            return str(Path(files[0]).resolve().parent)
