"""Pipeline startup, execution, and utility-task mixin for the MRI Pipeline GUI."""

from __future__ import annotations

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
from pipeline_runner import (
    PROJECT_ROOT,
    STAGE_ORDER,
    _is_supported_mri_input,
)
from pipeline.utils import _is_dicom_series_dir, _discover_mri_files
from remote.remote_runner import RemoteRunConfig, RemoteRunner
from remote.ssh_client import RemoteSSHClient
from ui.formatters import truncate_middle


class PipelineMixin:
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

    def _upload_remote_job_with_dialog(self, runner: RemoteRunner) -> bool:
        dialog = tk.Toplevel(self.root)
        dialog.title("Copy files to remote server")
        dialog.geometry("760x500")
        dialog.transient(self.root)
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
        self._remote_upload_spinner_label = ttk.Label(current_row, image=self._spinner_frame() or "", width=2)
        self._remote_upload_spinner_label.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(current_row, textvariable=current_var, font=("Inter", 10, "bold")).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(dialog, textvariable=count_var).pack(anchor=tk.W, padx=14, pady=(0, 8))

        progress = ttk.Progressbar(dialog, mode="indeterminate")
        progress.pack(fill=tk.X, padx=14, pady=(0, 10))
        progress.start(10)

        log = tk.Text(dialog, wrap=tk.WORD, height=15, font=("JetBrains Mono", 10), state=tk.DISABLED)
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
                runner.on_log = lambda line: self.root.after(0, lambda l=line: append_line(l))
                runner.upload_job()
            except Exception as exc:
                ok = False
                err_msg = f"REMOTE UPLOAD ERROR: {type(exc).__name__}: {exc}"
                self.root.after(0, lambda m=err_msg: append_line(m))
                self.root.after(0, lambda: current_var.set("Copy failed. Check the log below."))
            finally:
                runner.on_log = old_log
                state["ok"] = ok
                state["done"] = True
                self.root.after(0, lambda: setattr(self, "_remote_upload_spinner_label", None))
                self.root.after(0, progress.stop)
                if ok:
                    self.root.after(0, lambda: current_var.set("Copy complete. Starting remote job..."))
                    self.root.after(250, dialog.destroy)
                else:
                    self.root.after(0, lambda: ttk.Button(dialog, text="Close", command=dialog.destroy).pack(anchor=tk.E, padx=14, pady=(0, 14)))

        threading.Thread(target=worker, daemon=True).start()
        self.root.wait_window(dialog)
        return state["ok"]

    def _start_pipeline(self, resume: bool = False, restart: bool = False) -> None:
        if not self._can_start_new_pipeline():
            return

        if not self._validate_configuration():
            messagebox.showerror("Configuration incomplete", self.state.config_status.get())
            return

        if not self._confirm_start_with_existing_jobs():
            return

        starter_button = getattr(self, "restart_button" if restart else "resume_button", None) if (restart or resume) else None
        if starter_button is not None:
            self._set_button_busy(starter_button, True, "Starting")
        started = False
        try:
            if self.state.run_target.get() == "Server":
                if self.state.input_source.get() == "Local":
                    self._start_lazy_upload_pipeline(resume, restart, starter_button)
                    return
                
                run_request = self._build_run_request()
                if run_request is None:
                    return
                runner = self.remote_runner if resume and self.remote_runner else self._build_remote_runner(resume=resume, req=run_request)
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
                self._prepare_progress_tab(
                    self._input_files_for_progress(run_request),
                    run_request.get("selected_tools"),
                    title="Server: starting",
                    pipeline_mode=run_request.get("pipeline_mode", ""),
                    threads=int(run_request.get("threads", 0) or 0),
                    device=run_request.get("device", ""),
                )
                self._show_progress_tab()
                self._start_remote_pipeline(resume=resume, restart=restart, runner=runner, run_request=run_request)
                started = True
                if starter_button is not None:
                    self._set_button_busy(starter_button, False)
                self._validate_configuration()
                return

            run_request = self._build_run_request()
            if run_request is None:
                return
            run_request["resume"] = resume
            run_request["restart"] = restart

            self._prepare_progress_tab(
                self._input_files_for_progress(run_request),
                run_request.get("selected_tools"),
                title="Local: starting",
                pipeline_mode=run_request.get("pipeline_mode", ""),
                threads=int(run_request.get("threads", 0) or 0),
                device=run_request.get("device", ""),
            )
            self._show_progress_tab()

            self.running = True
            self.stop_requested.clear()
            if hasattr(self, "resume_button"):
                self.resume_button.configure(state=tk.DISABLED)
            if hasattr(self, "restart_button"):
                self.restart_button.configure(state=tk.DISABLED)
            if hasattr(self, "stop_button"):
                self.stop_button.configure(state=tk.NORMAL)
            if hasattr(self, "progress"):
                self.progress.start(10)
            self.detail_chart.reset()
            self.gpu_chart.reset()
            self.state.overall_progress_var.set(0)
            self.state.overall_progress_text.set("0%")
            self.state.status_text.set("Running")
            for stage in STAGE_ORDER:
                if hasattr(self, "_set_step_status"):
                    self._set_step_status(stage, "Ready", 0)
            self._clear_log()
            self._log("=" * 80)
            if restart:
                self._log("Restart mode: existing subject outputs will be removed before running.")
            elif resume:
                self._log("Resume mode: completed stages in pipeline_state.json will be skipped.")
            self._log("Starting pipeline...")
            self._start_local_background_pipeline(run_request)
            started = True
            if starter_button is not None:
                self._set_button_busy(starter_button, False)
            self._validate_configuration()
        finally:
            if not started:
                if starter_button is not None:
                    self._set_button_busy(starter_button, False)
                self._validate_configuration()

    def _start_lazy_upload_pipeline(self, resume: bool, restart: bool, starter_button: tk.Widget | None) -> None:
        run_request = self._build_run_request()
        if run_request is None:
            if starter_button is not None:
                self._set_button_busy(starter_button, False)
            return

        run_request["lazy_watch"] = True
        run_request["resume"] = resume
        run_request["restart"] = restart
        
        server_output_dir = self.state.server_output_dir.get().strip() or "~/mri-server-outputs"
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
                self._set_button_busy(starter_button, False)
            return

        run_request["input_dir"] = remote_lazy_dir
        run_request["input_source"] = "Server"
        if mode == "file":
            run_request["mode"] = "dir"
            run_request["recursive"] = False

        runner = self.remote_runner if resume and self.remote_runner else self._build_remote_runner(resume=resume, req=run_request)
        if not runner:
            if starter_button is not None:
                self._set_button_busy(starter_button, False)
            return
            
        if restart:
            self.remote_runner = None
            
        runner.config.resume = resume
        runner.config.restart = restart
        
        self.remote_runner = runner
        self._prepare_progress_tab(
            self._input_files_for_progress(run_request),
            run_request.get("selected_tools"),
            title="Server: starting (Lazy Upload)",
            pipeline_mode=run_request.get("pipeline_mode", ""),
            threads=int(run_request.get("threads", 0) or 0),
            device=run_request.get("device", ""),
        )
        self._show_progress_tab()
        self._start_remote_pipeline(resume=resume, restart=restart, runner=runner, run_request=run_request)
        
        if starter_button is not None:
            self._set_button_busy(starter_button, False)
        self._validate_configuration()
        
        def upload_worker() -> None:
            try:
                ssh_config = self._build_ssh_config()
                with RemoteSSHClient(ssh_config, self._log) as ssh:
                    ssh.mkdir_p(remote_lazy_dir)
                    for idx, local_file in enumerate(local_files):
                        self._log(f"Lazy Upload: Copying {local_file.name} ({idx+1}/{len(local_files)})...")
                        remote_tmp = posixpath.join(remote_lazy_dir, local_file.name + ".tmp")
                        remote_final = posixpath.join(remote_lazy_dir, local_file.name)
                        ssh.sftp.put(str(local_file), remote_tmp)
                        ssh.sftp.rename(remote_tmp, remote_final)
                        self._log(f"Lazy Upload: {local_file.name} ready on server.")
                        if getattr(self, "stop_requested", threading.Event()).is_set():
                            self._log("Lazy Upload: Stopped early by user.")
                            break
                    ssh.run(f"touch {shlex.quote(remote_lazy_dir + '/.upload_done')}", stream=False, check=False)
                    self._log("Lazy Upload: All files uploaded. Waiting for server to finish processing...")
            except Exception as e:
                self._log(f"Lazy Upload Error: {e}")
                
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
        entry = self._registry_entry_for_local_job(job_dir, run_request, proc.pid)
        upsert_job_registry(entry)
        self._rename_active_progress_tab(self._progress_title_for_job(entry, fallback="Local job"), self._progress_job_identity(entry))
        self._log(f"Local background job started: {job_dir}")
        self._log("You can close the GUI. The local worker process will keep running.")
        self.active_job = {"target": "Local", "job_dir": str(job_dir), "pid": proc.pid, "done": False, "registry_entry": entry}
        self.job_log_offset = 0
        self._register_job_monitor_for_active_context()
        self._validate_configuration()
        self._schedule_job_poll(delay_ms=0)

    def _start_remote_pipeline(self, resume: bool = False, restart: bool = False, runner: RemoteRunner | None = None, run_request: dict | None = None) -> None:
        runner = runner or (self.remote_runner if resume and self.remote_runner else self._build_remote_runner(resume=resume))
        if not runner:
            return
        if resume and self.remote_runner is None:
            self._log("No previous remote job is loaded in this GUI session; creating a new remote job instead.")
        if restart:
            self.remote_runner = None
        runner.config.resume = resume
        runner.config.restart = restart
        self.remote_runner = runner
        self._enter_background_monitor_state("Starting remote background job...")
        remote_dir = runner.start_remote_detached()
        entry = self._registry_entry_for_remote_job(runner, remote_dir, run_request=run_request)
        upsert_job_registry(entry)
        self._rename_active_progress_tab(self._progress_title_for_job(entry, fallback="Remote job"), self._progress_job_identity(entry))
        self._log(f"Remote background job started: {remote_dir}")
        self._log("You can close the GUI. Reopen and attach this remote job to monitor or download outputs.")
        self.active_job = {"target": "Server", "remote_job_dir": remote_dir, "done": False, "registry_entry": entry}
        self.job_log_offset = 0
        self._register_job_monitor_for_active_context()
        self._validate_configuration()
        self._schedule_job_poll(delay_ms=0)

    def _build_run_request(self) -> dict | None:
        mode = self.state.input_mode.get()
        input_source = self.state.input_source.get()
        raw_input = self.state.input_path.get().strip()
        if not raw_input:
            messagebox.showerror("Missing input", "Chưa chọn file hoặc folder MRI.")
            return None
        if input_source == "Server" and self.state.run_target.get() != "Server":
            messagebox.showerror("Invalid input", "Server input requires Run on = Server.")
            return None

        selected_tools = self._selected_tools() if hasattr(self, "_selected_tools") else self.state.get_selected_tools()
        is_batch = mode == "dir"
        output_dir = self.state.output_dir.get().strip()
        batch_output_name = f"batch_{time.strftime('%Y%m%d_%H%M%S')}" if is_batch else ""
        base = {
            "mode": mode,
            "output_dir": output_dir,
            "server_output_dir": self.state.server_output_dir.get().strip(),
            "effective_output_dir": str(Path(output_dir) / batch_output_name) if batch_output_name else output_dir,
            "is_batch": is_batch,
            "batch_output_name": batch_output_name,
            "license_dir": self.state.license_dir.get().strip(),
            "device": self.state.device.get(),
            "threads": int(self.state.threads.get()),
            "ram_percent": int(self.state.ram_percent.get()),
            "selected_tools": selected_tools,
            "export_config": self.state.get_export_config(),
            "stats_vector_config": self.state.get_stats_vector_config(),
            "input_source": input_source,
            "pipeline_mode": self.state.pipeline_mode.get(),
        }

        if self.state.run_target.get() != "Server" and input_source != "Local":
            messagebox.showerror("Invalid input", "Local runs can only use local input data.")
            return None

        if input_source == "Server":
            if mode == "file":
                path = self.state.selected_files[0] if self.state.selected_files else raw_input
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
                files = self.state.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
                if not files:
                    messagebox.showerror("Invalid input", "Danh sách file server không hợp lệ.")
                    return None
                base["input_files"] = files
                base["input_dir"] = self._common_remote_input_root(files)
            else:
                if self.state.selected_files:
                    base["mode"] = "files"
                    base["input_files"] = list(self.state.selected_files)
                    base["input_dir"] = self._common_remote_input_root(self.state.selected_files)
                else:
                    base["input_dir"] = raw_input
                    base["recursive"] = not self.state.non_recursive.get()
            if not self._validate_remote_input_request(base):
                return None
            return base

        if mode == "file":
            path = self.state.selected_files[0] if self.state.selected_files else raw_input
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
            files = self.state.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
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
            if self.state.selected_files:
                base["mode"] = "files"
                base["input_files"] = self.state.selected_files
                base["input_dir"] = self._common_input_root(self.state.selected_files)
            else:
                base["input_dir"] = raw_input
                base["recursive"] = not self.state.non_recursive.get()

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

        ssh_config = self._build_ssh_config()
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
            self._append_log("Remote task ignored: another task is already running.")
            return
        self.running = True
        self.state.remote_status.set(f"Remote: {title} running...")
        self.stop_requested.clear()
        if hasattr(self, "resume_button"):
            self.resume_button.configure(state=tk.DISABLED)
        if hasattr(self, "restart_button"):
            self.restart_button.configure(state=tk.DISABLED)
        if hasattr(self, "stop_button"):
            self.stop_button.configure(state=tk.NORMAL if enable_pause else tk.DISABLED)
        if hasattr(self, "progress"):
            self.progress.start(10)
        if clear_log:
            self._clear_log()
            self.detail_chart.reset()
            self.gpu_chart.reset()
            self.state.overall_progress_var.set(0)
            self.state.overall_progress_text.set("0%")
            self.state.status_text.set("Running")
            for stage in STAGE_ORDER:
                if hasattr(self, "_set_step_status"):
                    self._set_step_status(stage, "Ready", 0)
        self._append_log("=" * 80)
        self._append_log(f"Remote task started: {title}")

        def worker():
            try:
                task()
                self.log_queue.put(f"Remote task completed: {title}")
            except Exception as exc:
                self.log_queue.put(f"REMOTE ERROR [{title}]: {type(exc).__name__}: {exc}")
            finally:
                self.root.after(0, lambda: self.state.remote_status.set("Remote: idle"))
                self.root.after(0, self._set_idle_state)

        threading.Thread(target=worker, daemon=True).start()

    def _remote_test_ssh(self) -> None:
        if self.state.run_target.get() != "Server":
            return
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return
        thread_signature = self._current_remote_connection_signature()
        if thread_signature is None:
            return
        self.remote_connecting = True
        self._sync_remote_connection_controls()

        def task():
            try:
                def set_testing():
                    self._cancel_remote_health_check()
                    self.state.remote_status.set("Connecting to server...")
                    self._set_remote_status_icon("running")
                    self._connected_remote_signature = None
                    self._remote_thread_max_signature = None
                    self._set_thread_max(None, pending=True)
                    self._reset_remote_tool_image_state()
                    if hasattr(self, "remote_status_label"):
                        self.remote_status_label.configure(foreground="")
                self.root.after(0, set_testing)
                runner = RemoteRunner(RemoteRunConfig(ssh=ssh_config), on_log=lambda x: None)
                runner.test_ssh()
                try:
                    max_threads = self._read_remote_thread_max(ssh_config)
                except Exception:
                    max_threads = None
                def set_success():
                    self.remote_connecting = False
                    if thread_signature != self._current_remote_connection_signature():
                        self._sync_remote_connection_controls()
                        return
                    self._connected_remote_signature = thread_signature
                    self.state.remote_status.set("Remote: connected")
                    self._set_remote_status_icon("success")
                    self._remote_thread_max_signature = thread_signature if max_threads else None
                    self._set_thread_max(max_threads)
                    self._sync_remote_connection_controls()
                    self._schedule_remote_health_check()
                    if hasattr(self, "remote_status_label"):
                        self.remote_status_label.configure(foreground="#16a34a") # green
                self.root.after(0, set_success)
            except Exception as exc:
                err_msg = f"Remote connection failed: {exc}"
                def set_failed(m=err_msg):
                    self.remote_connecting = False
                    self._connected_remote_signature = None
                    self.state.remote_status.set(m)
                    self._set_remote_status_icon("failed")
                    self._remote_thread_max_signature = None
                    self._set_thread_max(None)
                    self._sync_remote_connection_controls()
                    if hasattr(self, "remote_status_label"):
                        self.remote_status_label.configure(foreground="#dc2626") # red
                self.root.after(0, set_failed)

        threading.Thread(target=task, daemon=True).start()

    def _remote_download_outputs(self) -> None:
        def task():
            if not self.remote_runner:
                self._log("No remote job is available. Run or attach a remote job first.")
                return
            local_path = self.remote_runner.download_outputs(self.state.output_dir.get())
            self._log(f"Downloaded outputs to: {local_path}")
        self._run_remote_task("Download Outputs", task)

    def _common_input_root(self, files: list[str]) -> str:
        parents = [str(Path(f).resolve().parent) for f in files]
        try:
            return os.path.commonpath(parents)
        except ValueError:
            return str(Path(files[0]).resolve().parent)
