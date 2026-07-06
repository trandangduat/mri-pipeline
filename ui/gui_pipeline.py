"""Pipeline startup, execution, and utility-task mixin for the MRI Pipeline GUI."""

from __future__ import annotations

import os
import posixpath
import shutil
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
    TOOL_DEFS,
    ExportConfig,
    PipelineConfig,
    StatsVectorConfig,
    _derive_subject_id,
    _discover_mri_files,
    build_subject_id_map,
    is_tool_enabled,
    run_batch_pipeline,
    run_pipeline,
)
from remote.remote_runner import RemoteRunConfig, RemoteRunner
from remote.ssh_client import RemoteSSHClient
from ui.formatters import truncate_middle


class PipelineMixin:
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
            text="Shared pipeline code is reused from the remote workspace when available. This job copies run configuration, license files, and local MRI inputs when needed.",
            wraplength=720,
        ).pack(anchor=tk.W, pady=(4, 0))

        current_var = tk.StringVar(value="Preparing remote connection...")
        count_var = tk.StringVar(value="Files copied: 0")
        ttk.Label(dialog, textvariable=current_var, font=("Inter", 10, "bold")).pack(anchor=tk.W, padx=14, pady=(4, 2))
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

        if self.state.run_target.get() == "Server":
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
            self._prepare_progress_tab(self._input_files_for_progress(run_request), run_request.get("selected_tools"), title="Server: starting")
            self._show_progress_tab()
            self._start_remote_pipeline(resume=resume, restart=restart, runner=runner)
            return

        run_request = self._build_run_request()
        if run_request is None:
            return
        run_request["resume"] = resume
        run_request["restart"] = restart

        self._prepare_progress_tab(self._input_files_for_progress(run_request), run_request.get("selected_tools"), title="Local: starting")
        self._show_progress_tab()

        self.running = True
        self.stop_requested.clear()
        self.run_button.configure(state=tk.DISABLED)
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

    def _start_remote_pipeline(self, resume: bool = False, restart: bool = False, runner: RemoteRunner | None = None) -> None:
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
        entry = self._registry_entry_for_remote_job(runner, remote_dir)
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
        input_source = "Server" if self.state.run_target.get() == "Server" else "Local"
        if self.state.input_source.get() != input_source:
            self.state.input_source.set(input_source)
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
            "effective_output_dir": str(Path(output_dir) / batch_output_name) if batch_output_name else output_dir,
            "is_batch": is_batch,
            "batch_output_name": batch_output_name,
            "license_dir": self.state.license_dir.get().strip(),
            "device": self.state.device.get(),
            "threads": int(self.state.threads.get()),
            "selected_tools": selected_tools,
            "export_config": self.state.get_export_config(),
            "stats_vector_config": self.state.get_stats_vector_config(),
            "input_source": input_source,
            "remote_input_dir": "",
        }

        if self.state.run_target.get() != "Server" and input_source != "Local":
            messagebox.showerror("Invalid input", "Local runs can only use local input data.")
            return None

        if input_source == "Server":
            if mode == "file":
                path = self.state.selected_files[0] if self.state.selected_files else raw_input
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
            if not Path(path).is_file():
                messagebox.showerror("Invalid input", f"Không tồn tại file: {path}")
                return None
            base["input_file"] = path
        elif mode == "files":
            files = self.state.selected_files or [p.strip() for p in raw_input.split(";") if p.strip()]
            missing = [p for p in files if not Path(p).is_file()]
            if not files or missing:
                messagebox.showerror("Invalid input", "Danh sách file không hợp lệ.")
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
                        messagebox.showerror("Invalid server input", f"Server input phải là file MRI, nhưng đây là folder:\n{path}")
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
        if hasattr(self, "run_button"):
            self.run_button.configure(state=tk.DISABLED)
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
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return

        def task():
            try:
                def set_testing():
                    self.state.remote_status.set("Testing SSH connection...")
                    self._set_remote_status_icon("running")
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
                    self.state.remote_status.set("SSH Connection Successful")
                    self._set_remote_status_icon("success")
                    self._set_thread_max(max_threads)
                    if hasattr(self, "remote_status_label"):
                        self.remote_status_label.configure(foreground="#16a34a") # green
                self.root.after(0, set_success)
            except Exception as exc:
                err_msg = f"SSH Connection Failed: {exc}"
                def set_failed(m=err_msg):
                    self.state.remote_status.set(m)
                    self._set_remote_status_icon("failed")
                    self._set_thread_max(None)
                    if hasattr(self, "remote_status_label"):
                        self.remote_status_label.configure(foreground="#dc2626") # red
                self.root.after(0, set_failed)

        threading.Thread(target=task, daemon=True).start()

    def _remote_check_docker(self) -> None:
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return

        def task():
            runner = RemoteRunner(RemoteRunConfig(ssh=ssh_config), on_log=self._log)
            runner.check_docker()
        self._run_remote_task("Check Docker", task)

    def _remote_check_images(self) -> None:
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return
        selected_tools = self.state.get_selected_tools()

        def task():
            runner = RemoteRunner(RemoteRunConfig(ssh=ssh_config, selected_tools=selected_tools), on_log=self._log)
            missing = runner.check_images()
            if missing:
                self._log("Missing remote images:")
                for image in missing:
                    self._log(f"  - {image}")
            else:
                self._log("All required remote images are available.")
        self._run_remote_task("Check Images", task)

    def _check_environment(self) -> None:
        if self.state.run_target.get() == "Server":
            self._remote_check_docker()
            return

        def task():
            self._log(">>> docker ps")
            proc = subprocess.run(["docker", "ps"], capture_output=True, text=True, timeout=30)
            if proc.stdout.strip():
                self._log(proc.stdout.strip())
            if proc.stderr.strip():
                self._log(proc.stderr.strip())
            self._log(f"docker ps exit code: {proc.returncode}")

            self._log(">>> checking required local images")
            for image in self._required_images_for_current_tools():
                inspect = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, timeout=20)
                self._log(("OK" if inspect.returncode == 0 else "MISSING") + f" image: {image}")

        self._run_local_utility_task("Check Environment", task)

    def _download_outputs_action(self) -> None:
        if self.state.run_target.get() == "Server":
            self._remote_download_outputs()
        else:
            self._log(f"Local outputs are already in: {self.state.output_dir.get()}")

    def _required_images_for_current_tools(self) -> list[str]:
        images: list[str] = []
        for tool_key in self.state.get_selected_tools().values():
            if not tool_key or not is_tool_enabled(tool_key):
                continue
            tool = TOOL_DEFS.get(tool_key)
            if not tool:
                continue
            for key in ("base_image", "image"):
                image = tool.get(key)
                if image and image not in images:
                    images.append(image)
        return images

    def _run_local_utility_task(self, title: str, task) -> None:
        if self.running:
            self._append_log("Task ignored: another task is already running.")
            return
        self.running = True
        if hasattr(self, "progress"):
            self.progress.start(10)
        self.state.status_text.set(title)
        self._append_log("=" * 80)
        self._append_log(f"Task started: {title}")

        def worker():
            try:
                task()
                self.log_queue.put(f"Task completed: {title}")
            except Exception as exc:
                self.log_queue.put(f"TASK ERROR [{title}]: {type(exc).__name__}: {exc}")
            finally:
                self.root.after(0, self._set_idle_state)

        threading.Thread(target=worker, daemon=True).start()

    def _remote_upload_job(self) -> None:
        runner = self._build_remote_runner()
        if not runner:
            return

        def task():
            runner.upload_job()
            self.remote_runner = runner
            self._log(f"Uploaded remote job: {runner.remote_job_dir}")
        self._run_remote_task("Upload Job", task)

    def _remote_run(self, resume: bool = False) -> None:
        runner = self.remote_runner or self._build_remote_runner(resume=resume)
        if not runner:
            return
        runner.config.resume = resume
        self.remote_runner = runner
        self._prepare_progress_tab(self._input_files_for_progress(), self.state.get_selected_tools(), title="Server: starting")
        self._show_progress_tab()
        self._enter_background_monitor_state("Starting remote background job...")
        remote_dir = runner.start_remote_detached()
        entry = self._registry_entry_for_remote_job(runner, remote_dir)
        upsert_job_registry(entry)
        self._rename_active_progress_tab(self._progress_title_for_job(entry, fallback="Remote job"), self._progress_job_identity(entry))
        self._log(f"Remote background job started: {remote_dir}")
        self.active_job = {"target": "Server", "remote_job_dir": remote_dir, "done": False, "registry_entry": entry}
        self.job_log_offset = 0
        self._register_job_monitor_for_active_context()
        self._validate_configuration()
        self._schedule_job_poll(delay_ms=0)

    def _remote_download_outputs(self) -> None:
        def task():
            if not self.remote_runner:
                self._log("No remote job is available. Run or upload a remote job first.")
                return
            local_path = self.remote_runner.download_outputs(self.state.output_dir.get())
            self._log(f"Downloaded outputs to: {local_path}")
        self._run_remote_task("Download Outputs", task)

    def _remote_clean_job(self) -> None:
        def task():
            if not self.remote_runner:
                self._log("No remote job is available to clean.")
                return
            self.remote_runner.clean_remote()
            self._log("Remote job cleaned.")
            self.remote_runner = None
        self._run_remote_task("Clean Remote Job", task)

    def _common_input_root(self, files: list[str]) -> str:
        parents = [str(Path(f).resolve().parent) for f in files]
        try:
            return os.path.commonpath(parents)
        except ValueError:
            return str(Path(files[0]).resolve().parent)

    def _run_worker(self, req: dict) -> None:
        try:
            if req.get("restart"):
                self._delete_restart_outputs(req)
            if req["mode"] == "file":
                self._run_single(req)
            elif req["mode"] == "files":
                self._run_multiple(req)
            else:
                self._run_batch(req)
        except Exception as exc:
            self._log(f"ERROR: {exc}")
        finally:
            self.root.after(0, self._set_idle_state)

    def _delete_restart_outputs(self, req: dict) -> None:
        output_dir = Path(req.get("effective_output_dir", req["output_dir"])).resolve()
        subject_ids: list[str] = []

        if req["mode"] == "file":
            subject_ids = [_derive_subject_id(req["input_file"])]
        elif req["mode"] == "files":
            subject_ids = list(build_subject_id_map(req["input_files"], req["input_dir"]).values())
        else:
            files = _discover_mri_files(req["input_dir"], recursive=req["recursive"])
            subject_ids = list(build_subject_id_map(files, req["input_dir"]).values())

        for subject_id in subject_ids:
            subject_dir = output_dir / subject_id
            if subject_dir.exists():
                self._log(f"Restart: removing {subject_dir}")
                shutil.rmtree(subject_dir)

    def _run_single(self, req: dict) -> None:
        input_file = req["input_file"]
        subject_id = _derive_subject_id(input_file)
        self.root.after(0, lambda: self._on_image_start(input_file, 1, 1))
        config = PipelineConfig(
            input_file=input_file,
            output_dir=req.get("effective_output_dir", req["output_dir"]),
            subject_id=subject_id,
            license_dir=req["license_dir"],
            device=req["device"],
            threads=req["threads"],
            resume=req.get("resume", False),
            export_config=ExportConfig.from_dict(req.get("export_config")),
            stats_vector_config=StatsVectorConfig.from_dict(req.get("stats_vector_config")),
            selected_tools=req["selected_tools"],
        )
        results = run_pipeline(
            config,
            on_progress=self._on_progress,
            on_build_log=self._log,
            on_metrics=self._on_metrics,
            should_stop=self.stop_requested.is_set,
        )
        ok = bool(results) and all(step.success for step in results)
        for step in results:
            self._update_run_step(
                input_file,
                step.stage,
                tool=step.tool,
                status="Done" if step.success else "Failed",
                duration_sec=step.duration_sec,
                peak_ram_bytes=step.peak_ram_bytes,
                peak_cpu_pct=step.peak_cpu_pct,
                error=step.error,
            )
        self._log(f"Single file finished: {subject_id} | status={'OK' if ok else 'FAILED'}")
        self._set_progress_count("current_running_images", 0)
        if ok:
            self._set_progress_count("current_success_images", self._get_progress_count("current_success_images") + 1)
            self._update_image_run(input_file, status="Done", percent=100, stage_text="Completed")
        else:
            self._set_progress_count("current_failed_images", self._get_progress_count("current_failed_images") + 1)
            self._update_image_run(input_file, status="Failed", stage_text="Failed")
        self._update_batch_summary()

    def _run_multiple(self, req: dict) -> None:
        files = req["input_files"]
        self._log(f"Selected {len(files)} files")
        if req.get("is_batch"):
            self._log(f"Batch outputs will be saved to: {req.get('effective_output_dir')}")
        run_batch_pipeline(
            input_dir=req["input_dir"],
            output_dir=req.get("effective_output_dir", req["output_dir"]),
            license_dir=req["license_dir"],
            device=req["device"],
            threads=req["threads"],
            resume=req.get("resume", False),
            selected_tools=req["selected_tools"],
            export_config=ExportConfig.from_dict(req.get("export_config")),
            stats_vector_config=StatsVectorConfig.from_dict(req.get("stats_vector_config")),
            recursive=True,
            input_files=files,
            on_progress=self._on_progress,
            on_build_log=self._log,
            on_image_start=self._on_image_start,
            on_image_done=self._on_image_done,
            on_metrics=self._on_metrics,
            should_stop=self.stop_requested.is_set,
        )

    def _run_batch(self, req: dict) -> None:
        files = _discover_mri_files(req["input_dir"], recursive=req["recursive"])
        self._log(f"Found {len(files)} MRI files")
        if not files:
            return
        self._log(f"Batch outputs will be saved to: {req.get('effective_output_dir')}")
        run_batch_pipeline(
            input_dir=req["input_dir"],
            output_dir=req.get("effective_output_dir", req["output_dir"]),
            license_dir=req["license_dir"],
            device=req["device"],
            threads=req["threads"],
            resume=req.get("resume", False),
            selected_tools=req["selected_tools"],
            export_config=ExportConfig.from_dict(req.get("export_config")),
            stats_vector_config=StatsVectorConfig.from_dict(req.get("stats_vector_config")),
            recursive=req["recursive"],
            input_files=files,
            on_progress=self._on_progress,
            on_build_log=self._log,
            on_image_start=self._on_image_start,
            on_image_done=self._on_image_done,
            on_metrics=self._on_metrics,
            should_stop=self.stop_requested.is_set,
        )
