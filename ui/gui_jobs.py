"""Background job and remote-runner mixin for the MRI Pipeline GUI."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from pipeline.jobs import load_job_registry, read_json, upsert_job_registry, write_json
from pipeline_runner import (
    PROJECT_ROOT,
    STAGE_ORDER,
    _derive_subject_id,
    _discover_mri_files,
    build_subject_id_map,
)
from remote.remote_runner import RemoteRunConfig, RemoteRunner
from remote.ssh_client import SSHConfig


class JobsMixin:
    def _attach_job_dialog(self) -> None:
        jobs = self._known_jobs()
        if self.state.run_target.get() == "Server" and self.state.remote_host.get().strip() and self.state.remote_username.get().strip():
            live_jobs = self._running_remote_jobs()
            if live_jobs is None:
                return
            jobs = self._merge_job_lists(jobs, live_jobs)
        elif self.state.run_target.get() == "Local":
            jobs = self._merge_job_lists(jobs, self._running_local_jobs())
        if not jobs:
            self._attach_manual_job_dialog()
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Background Jobs")
        dialog.geometry("900x420")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Select a background job to view progress/logs or download completed remote outputs.").pack(anchor=tk.W, padx=12, pady=(12, 6))
        columns = ("target", "state", "job", "output")
        tree = ttk.Treeview(dialog, columns=columns, show="headings", height=12)
        tree.heading("target", text="Target")
        tree.heading("state", text="State")
        tree.heading("job", text="Job")
        tree.heading("output", text="Output")
        tree.column("target", width=80, anchor=tk.W)
        tree.column("state", width=90, anchor=tk.W)
        tree.column("job", width=360, anchor=tk.W)
        tree.column("output", width=300, anchor=tk.W)
        tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        item_to_job: dict[str, dict] = {}
        for idx, job in enumerate(jobs):
            job_label = job.get("remote_job_dir") or job.get("job_dir") or job.get("job_id", "")
            item = tree.insert("", tk.END, values=(job.get("target", ""), job.get("state", ""), job_label, job.get("effective_output_dir") or job.get("output_dir", "")))
            item_to_job[item] = job
            if idx == 0:
                tree.selection_set(item)

        buttons = ttk.Frame(dialog)
        buttons.pack(fill=tk.X, padx=12, pady=(4, 12))

        def selected_job() -> dict | None:
            selection = tree.selection()
            if not selection:
                return None
            return item_to_job.get(selection[0])

        def attach_selected() -> None:
            job = selected_job()
            if not job:
                return
            dialog.destroy()
            self._attach_registry_job(job)

        def download_selected() -> None:
            job = selected_job()
            if not job:
                return
            dialog.destroy()
            self._download_registry_job(job)

        ttk.Button(buttons, text="View / Attach", style="Accent.TButton", command=attach_selected).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Download Outputs", command=download_selected).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Manual Attach", command=lambda: (dialog.destroy(), self._attach_manual_job_dialog())).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)
        tree.bind("<Double-1>", lambda _event: attach_selected())

    def _job_identity(self, job: dict) -> str:
        return str(job.get("remote_job_dir") or job.get("job_dir") or job.get("job_id") or id(job))

    def _merge_job_lists(self, *job_lists: list[dict]) -> list[dict]:
        merged: dict[str, dict] = {}
        for jobs in job_lists:
            for job in jobs:
                key = self._job_identity(job)
                if key in merged:
                    merged[key].update(job)
                else:
                    merged[key] = dict(job)
        return list(merged.values())

    def _is_background_monitor_active(self) -> bool:
        return bool(self.active_job and not self.active_job.get("done"))

    def _can_start_new_pipeline(self) -> bool:
        return not self.running or self._is_background_monitor_active()

    def _stop_current_job_monitor(self) -> None:
        was_monitoring = self._is_background_monitor_active()
        if self.job_poll_after_id:
            try:
                self.root.after_cancel(self.job_poll_after_id)
            except Exception:
                pass
        self.job_poll_after_id = None
        self.remote_poll_in_flight = False
        self.active_job = None
        self.job_log_offset = 0
        if was_monitoring:
            self.running = False

    def _attach_manual_job_dialog(self) -> None:
        if self.state.run_target.get() == "Server":
            remote_dir = simpledialog.askstring("Attach remote job", "Remote job directory:", parent=self.root)
            if remote_dir:
                self._attach_registry_job({"target": "Server", "remote_job_dir": remote_dir.strip(), "state": "unknown"})
            return
        job_dir = filedialog.askdirectory(title="Attach local job", initialdir=str(Path(self.state.output_dir.get()) / "jobs"))
        if job_dir:
            self._attach_registry_job({"target": "Local", "job_dir": job_dir, "state": "unknown"})

    def _attach_registry_job(self, job: dict) -> None:
        self._stop_current_job_monitor()
        target = job.get("target")
        selected_tools = dict((job.get("run_request") or {}).get("selected_tools") or {})
        config: dict = {}
        if target == "Server":
            runner = self._remote_runner_from_job_entry(job, read_metadata=False)
            if runner is None:
                return
            self.remote_runner = runner
            self.state.run_target.set("Server")
            self._on_run_target_changed()
            input_files = list(job.get("input_files") or [])
            self.active_job = {"target": "Server", "remote_job_dir": runner.remote_job_dir, "done": False, "registry_entry": job}
        else:
            job_dir = Path(str(job.get("job_dir", "")))
            config = read_json(job_dir / "job_config.json", {})
            input_files = list(job.get("input_files") or []) or (self._input_files_for_progress(config) if config else [])
            selected_tools = dict(config.get("selected_tools") or selected_tools)
            self.active_job = {"target": "Local", "job_dir": str(job_dir), "done": False, "registry_entry": job}
            self.state.run_target.set("Local")
            self._on_run_target_changed()
        self.job_log_offset = 0
        self._prepare_progress_tab(input_files, selected_tools or self.state.get_selected_tools())
        self._show_progress_tab()
        self.state.detail_title.set("Attaching job...")
        self._enter_background_monitor_state("Attaching background job...")
        if target != "Server":
            self._load_local_progress_state(Path(str(job.get("job_dir", ""))), config)
        self._schedule_job_poll(delay_ms=0)

    def _remote_runner_from_job_entry(self, job: dict, read_metadata: bool = True) -> RemoteRunner | None:
        remote = dict(job.get("remote") or {})
        if remote:
            self.state.remote_host.set(remote.get("host", self.state.remote_host.get()))
            self.state.remote_port.set(int(remote.get("port", self.state.remote_port.get() or 22)))
            self.state.remote_username.set(remote.get("username", self.state.remote_username.get()))
            self.state.remote_key_path.set(remote.get("key_path", self.state.remote_key_path.get()))
            self.state.remote_workspace.set(remote.get("workspace", self.state.remote_workspace.get()))
            self.state.remote_python.set(remote.get("python", self.state.remote_python.get()))
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return None
        runner = RemoteRunner(
            RemoteRunConfig(
                ssh=ssh_config,
                remote_workspace=self.state.remote_workspace.get().strip() or "~/mri-remote-jobs",
                remote_python=self.state.remote_python.get().strip() or "python3",
                output_dir=str(job.get("output_dir") or self.state.output_dir.get().strip()),
                download_subdir=str(job.get("download_subdir") or ""),
            ),
            on_log=self._remote_log_event,
        )
        remote_dir = str(job.get("remote_job_dir") or "").strip()
        if not remote_dir:
            messagebox.showerror("Missing remote job", "Selected registry entry has no remote job directory.")
            return None
        runner.attach_job(remote_dir)
        if read_metadata:
            metadata = runner.read_remote_metadata()
            if metadata.get("download_subdir"):
                runner.config.download_subdir = str(metadata.get("download_subdir"))
        return runner

    def _load_local_progress_state(self, job_dir: Path, config: dict) -> None:
        if not config or not self.image_runs:
            return
        output_dir = Path(str(config.get("effective_output_dir") or config.get("output_dir") or ""))
        input_files = list(self.image_runs.keys())
        subject_id_map = config.get("subject_id_map") if isinstance(config.get("subject_id_map"), dict) else {}
        if not subject_id_map and input_files:
            subject_id_map = build_subject_id_map(input_files, config.get("input_dir", ""))

        success_count = 0
        failed_count = 0
        running_count = 0
        for input_file, run in self.image_runs.items():
            subject_id = subject_id_map.get(input_file) or config.get("subject_id") or _derive_subject_id(input_file, config.get("input_dir", ""))
            state_path = output_dir / subject_id / "logs" / "pipeline_state.json"
            state = read_json(state_path, {})
            stages = state.get("stages", {}) if isinstance(state.get("stages"), dict) else {}
            for stage, step_state in stages.items():
                if stage not in STAGE_ORDER or not isinstance(step_state, dict):
                    continue
                raw_status = str(step_state.get("status", "")).lower()
                status = {"completed": "Done", "running": "Running", "failed": "Failed"}.get(raw_status, raw_status.capitalize() or "Pending")
                self._update_run_step(
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
                self._update_image_run(input_file, status="Done", percent=100, stage_text="Completed")
            elif pipeline_status == "failed":
                failed_count += 1
                self._update_image_run(input_file, status="Failed", percent=percent, stage_text="Failed")
            elif pipeline_status in {"running", "paused"}:
                running_count += 1 if pipeline_status == "running" else 0
                self.active_image_key = input_file if pipeline_status == "running" else self.active_image_key
                self._update_image_run(input_file, status="Running" if pipeline_status == "running" else "Paused", percent=percent, stage_text=pipeline_status.capitalize())
            elif stages:
                self._update_image_run(input_file, percent=percent)

        self.state.current_success_images = success_count
        self.state.current_failed_images = failed_count
        self.state.current_running_images = running_count
        self._update_batch_summary()
        if self.current_image_key in self.image_runs:
            self._render_selected_detail()

    def _download_registry_job(self, job: dict) -> None:
        if job.get("target") == "Server":
            runner = self._remote_runner_from_job_entry(job)
            if runner is None:
                return
            self.remote_runner = runner
            self._remote_download_outputs()
            return
        output_dir = job.get("effective_output_dir") or job.get("output_dir")
        self._log(f"Local outputs are already available in: {output_dir}")

    def _enter_background_monitor_state(self, title: str) -> None:
        self.running = True
        self.stop_requested.clear()
        if hasattr(self, "run_button"):
            self.run_button.configure(state=tk.DISABLED)
        if hasattr(self, "resume_button"):
            self.resume_button.configure(state=tk.DISABLED)
        if hasattr(self, "restart_button"):
            self.restart_button.configure(state=tk.DISABLED)
        if hasattr(self, "stop_button"):
            self.stop_button.configure(state=tk.NORMAL)
        if hasattr(self, "progress"):
            self.progress.start(10)
        self.state.status_text.set("Running in background")
        self._log(title)
        self._validate_configuration()

    def _registry_entry_for_local_job(self, job_dir: Path, req: dict, pid: int | None = None, state: str = "running") -> dict:
        files = self._input_files_for_progress(req)
        now = time.time()
        return {
            "job_id": job_dir.name,
            "target": "Local",
            "state": state,
            "job_dir": str(job_dir),
            "pid": pid,
            "started_at": now,
            "updated_at": now,
            "output_dir": req.get("output_dir", ""),
            "effective_output_dir": req.get("effective_output_dir", req.get("output_dir", "")),
            "download_subdir": req.get("batch_output_name", "") if req.get("is_batch") else "",
            "input_files": files,
            "run_request": req,
        }

    def _registry_entry_for_remote_job(self, runner: RemoteRunner, remote_dir: str, state: str = "running") -> dict:
        cfg = runner.config
        files = []
        if cfg.input_mode == "file" and cfg.input_file:
            files = [cfg.input_file]
        elif cfg.input_mode == "files":
            files = list(cfg.input_files)
        elif cfg.input_source == "Server" and cfg.input_dir:
            files = [cfg.input_dir]
        elif cfg.input_dir:
            try:
                files = _discover_mri_files(cfg.input_dir, recursive=cfg.recursive)
            except Exception:
                files = []
        now = time.time()
        return {
            "job_id": Path(remote_dir).name,
            "target": "Server",
            "state": state,
            "remote_job_dir": remote_dir,
            "started_at": now,
            "updated_at": now,
            "output_dir": cfg.output_dir,
            "download_subdir": cfg.download_subdir,
            "input_files": files,
            "remote": {
                "host": cfg.ssh.host,
                "port": int(cfg.ssh.port),
                "username": cfg.ssh.username,
                "key_path": cfg.ssh.key_path,
                "workspace": cfg.remote_workspace,
                "python": cfg.remote_python,
            },
        }

    def _update_registry_for_active_job(self, state: str, exit_code=None) -> None:
        if not self.active_job:
            return
        entry = dict(self.active_job.get("registry_entry") or {})
        if not entry:
            entry = dict(self.active_job)
        entry.update({"state": state, "exit_code": exit_code, "updated_at": time.time()})
        upsert_job_registry(entry)
        self.active_job["registry_entry"] = entry

    def _pid_is_running(self, pid: int | str | None) -> bool:
        if not pid:
            return False
        try:
            pid_int = int(pid)
            if pid_int <= 0:
                return False
            os.kill(pid_int, 0)
            return True
        except Exception:
            return False

    def _refresh_registry_entry_status(self, entry: dict) -> dict:
        entry = dict(entry)
        if entry.get("target") != "Local":
            return entry
        job_dir = Path(str(entry.get("job_dir", "")))
        if not job_dir.exists():
            entry["state"] = "missing"
            return entry
        status = read_json(job_dir / "job_status.json", {})
        exit_path = job_dir / "exit_code.txt"
        if exit_path.exists() or status.get("state") in {"completed", "failed"}:
            code = status.get("exit_code")
            if code is None and exit_path.exists():
                code = exit_path.read_text(encoding="utf-8", errors="replace").strip()
            entry["state"] = "completed" if str(code) == "0" else "failed"
            entry["exit_code"] = code
        elif self._pid_is_running(status.get("pid") or entry.get("pid")):
            entry["state"] = "running"
        elif entry.get("state") == "running":
            entry["state"] = "unknown"
        entry["updated_at"] = time.time()
        return entry

    def _known_jobs(self) -> list[dict]:
        jobs = [self._refresh_registry_entry_status(entry) for entry in load_job_registry()]
        for entry in jobs:
            upsert_job_registry(entry)
        return jobs

    def _running_local_jobs(self) -> list[dict]:
        return [entry for entry in self._known_jobs() if entry.get("target") == "Local" and entry.get("state") == "running"]

    def _same_remote_server(self, entry: dict, host: str, port: int, username: str, workspace: str) -> bool:
        remote = dict(entry.get("remote") or {})
        if not remote:
            return False
        return (
            str(remote.get("host", "")) == host
            and int(remote.get("port", 22) or 22) == port
            and str(remote.get("username", "")) == username
            and str(remote.get("workspace", "~/mri-remote-jobs")) == workspace
        )

    def _running_remote_jobs(self) -> list[dict] | None:
        jobs = self._remote_jobs_for_current_server()
        return None if jobs is None else [job for job in jobs if job.get("state") == "running"]

    def _remote_jobs_for_current_server(self) -> list[dict] | None:
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            registry_jobs = [entry for entry in self._known_jobs() if entry.get("target") == "Server"]
            return registry_jobs or None
        workspace = self.state.remote_workspace.get().strip() or "~/mri-remote-jobs"
        runner = RemoteRunner(
            RemoteRunConfig(
                ssh=ssh_config,
                remote_workspace=workspace,
                remote_python=self.state.remote_python.get().strip() or "python3",
                output_dir=self.state.output_dir.get().strip(),
            ),
            on_log=self._remote_log_event,
        )
        try:
            remote_jobs = runner.list_background_jobs()
        except Exception as exc:
            messagebox.showerror("Remote check failed", f"Could not check remote background jobs:\n\n{type(exc).__name__}: {exc}")
            return None

        registry_by_dir = {
            str(entry.get("remote_job_dir")): entry
            for entry in self._known_jobs()
            if entry.get("target") == "Server"
            and self._same_remote_server(entry, ssh_config.host, int(ssh_config.port), ssh_config.username, workspace)
        }
        jobs: list[dict] = []
        for remote_job in remote_jobs:
            remote_dir = str(remote_job.get("remote_job_dir", ""))
            entry = dict(registry_by_dir.get(remote_dir, {}))
            entry.update(remote_job)
            entry["target"] = "Server"
            entry["remote_job_dir"] = remote_dir
            entry.setdefault("output_dir", self.state.output_dir.get().strip())
            entry["remote"] = {
                "host": ssh_config.host,
                "port": int(ssh_config.port),
                "username": ssh_config.username,
                "key_path": ssh_config.key_path,
                "workspace": workspace,
                "python": self.state.remote_python.get().strip() or "python3",
            }
            jobs.append(entry)
        return jobs

    def _running_jobs_for_current_target(self) -> list[dict] | None:
        if self.state.run_target.get() == "Server":
            return self._running_remote_jobs()
        return self._running_local_jobs()

    def _resumable_jobs_for_current_target(self) -> list[dict] | None:
        if self.state.run_target.get() == "Server":
            jobs = self._remote_jobs_for_current_server()
            if jobs is None:
                return None
            return [job for job in jobs if job.get("target") == "Server" and job.get("state") != "running" and job.get("remote_job_dir")]
        return [
            job for job in self._known_jobs()
            if job.get("target") == "Local" and job.get("state") != "running" and job.get("job_dir")
        ]

    def _resume_job_dialog(self, jobs: list[dict]) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Resume Background Job")
        dialog.geometry("900x420")
        dialog.transient(self.root)
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
            self._resume_registry_job(job)

        buttons = ttk.Frame(dialog)
        buttons.pack(fill=tk.X, padx=12, pady=(4, 12))
        ttk.Button(buttons, text="Resume Selected", style="Accent.TButton", command=resume_selected).pack(side=tk.LEFT)
        ttk.Button(buttons, text="View / Attach", command=lambda: (dialog.destroy(), self._attach_registry_job(selected_job())) if selected_job() else None).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Close", command=dialog.destroy).pack(side=tk.RIGHT)
        tree.bind("<Double-1>", lambda _event: resume_selected())

    def _pause_background_job(self, job: dict) -> bool:
        target = job.get("target")
        if target == "Server":
            runner = self._remote_runner_from_job_entry(job)
            if runner is None:
                return False
            try:
                runner.request_pause()
                self._log(f"Remote pause requested: {runner.remote_job_dir}")
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
            self._log(f"Local pause requested: {stop_file}")
            return True
        except Exception as exc:
            messagebox.showerror("Local pause failed", f"Could not pause local job:\n\n{type(exc).__name__}: {exc}")
            return False

    def _confirm_start_with_existing_jobs(self) -> bool:
        candidates = self._running_jobs_for_current_target()
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
        dialog = tk.Toplevel(self.root)
        dialog.title("Background Pipeline Running")
        dialog.geometry("760x280")
        dialog.transient(self.root)
        dialog.grab_set()

        target = self.state.run_target.get()
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
        self.root.wait_window(dialog)
        return result.get()

    def _resume_pipeline(self) -> None:
        if self.running:
            return
        candidates = self._running_jobs_for_current_target()
        if candidates:
            self._attach_registry_job(candidates[0])
            return
        resumable = self._resumable_jobs_for_current_target()
        if resumable is None:
            return
        if len(resumable) == 1:
            self._resume_registry_job(resumable[0])
            return
        if resumable:
            self._resume_job_dialog(resumable)
            return
        self._start_pipeline(resume=True, restart=False)

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
        self._prepare_progress_tab(self._input_files_for_progress(config), config.get("selected_tools") or self.state.get_selected_tools())
        self._show_progress_tab()
        self._load_local_progress_state(job_dir, config)
        self._enter_background_monitor_state("Resuming local background job...")
        self._log(f"Local background job resumed: {job_dir}")
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
        self.remote_runner = runner
        self.state.run_target.set("Server")
        self._on_run_target_changed()
        self._prepare_progress_tab(list(job.get("input_files") or []) or self._input_files_for_progress(config), config.get("selected_tools") or self.state.get_selected_tools())
        self._show_progress_tab()
        self._enter_background_monitor_state("Resuming remote background job...")
        remote_dir = runner.start_remote_detached()
        entry = dict(job)
        entry.update({"state": "running", "remote_job_dir": remote_dir, "updated_at": time.time(), "run_request": config})
        upsert_job_registry(entry)
        self.active_job = {"target": "Server", "remote_job_dir": remote_dir, "done": False, "registry_entry": entry}
        self.job_log_offset = 0
        self._validate_configuration()
        self._log(f"Remote background job resumed: {remote_dir}")
        self._schedule_job_poll(delay_ms=0)

    def _build_ssh_config(self) -> SSHConfig | None:
        host = self.state.remote_host.get().strip()
        username = self.state.remote_username.get().strip()
        if not host or not username:
            messagebox.showerror("Missing remote server", "Cần nhập Host/IP và Username của remote server.")
            return None

        return SSHConfig(
            host=host,
            port=int(self.state.remote_port.get()),
            username=username,
            password=self.state.remote_password.get(),
            key_path=self.state.remote_key_path.get().strip(),
        )

    def _build_remote_runner(self, resume: bool = False, req: dict | None = None) -> RemoteRunner | None:
        req = req or self._build_run_request()
        if req is None:
            return None

        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return None

        remote_config = RemoteRunConfig(
            ssh=ssh_config,
            remote_workspace=self.state.remote_workspace.get().strip() or "~/mri-remote-jobs",
            remote_python=self.state.remote_python.get().strip() or "python3",
            input_source=req.get("input_source", "Local"),
            input_mode=req["mode"],
            input_file=req.get("input_file", ""),
            input_files=req.get("input_files", []),
            input_dir=req.get("input_dir", ""),
            output_dir=req["output_dir"],
            license_dir=req["license_dir"],
            device=req["device"],
            threads=req["threads"],
            selected_tools=req["selected_tools"],
            export_config=req["export_config"],
            stats_vector_config=req["stats_vector_config"],
            recursive=req.get("recursive", True),
            download_subdir=req.get("batch_output_name", "") if req.get("is_batch") else "",
            resume=resume,
        )
        return RemoteRunner(remote_config, on_log=self._remote_log_event)

    def _schedule_job_poll(self, delay_ms: int = 1500) -> None:
        if self.job_poll_after_id:
            try:
                self.root.after_cancel(self.job_poll_after_id)
            except Exception:
                pass
        self.job_poll_after_id = self.root.after(delay_ms, self._poll_active_job)

    def _poll_active_job(self) -> None:
        if not self.active_job:
            self.job_poll_after_id = None
            return
        try:
            target = self.active_job.get("target")
            if target == "Server":
                self._start_remote_poll_worker()
                return
            else:
                done = self._poll_local_background_job()
        except Exception as exc:
            self._log(f"BACKGROUND POLL ERROR: {type(exc).__name__}: {exc}")
            done = False

        if done:
            self.active_job["done"] = True
            self.job_poll_after_id = None
            self._set_idle_state()
            return
        self._schedule_job_poll()

    def _start_remote_poll_worker(self) -> None:
        if self.remote_poll_in_flight:
            return
        if not self.remote_runner:
            self._set_idle_state()
            return
        self.remote_poll_in_flight = True
        runner = self.remote_runner
        offset = self.job_log_offset

        def worker() -> None:
            data = ""
            new_offset = offset
            status: dict = {"state": "running"}
            error: Exception | None = None
            try:
                data, new_offset = runner.read_remote_log_since(offset)
                status = runner.remote_status()
            except Exception as exc:
                error = exc
            self.root.after(0, lambda r=runner: self._finish_remote_poll(r, data, new_offset, status, error))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_remote_poll(self, runner: RemoteRunner, data: str, new_offset: int, status: dict, error: Exception | None) -> None:
        if runner is not self.remote_runner:
            return
        self.remote_poll_in_flight = False
        if not self.active_job or self.active_job.get("target") != "Server":
            self.job_poll_after_id = None
            return
        if error is not None:
            self._log(f"BACKGROUND POLL ERROR: {type(error).__name__}: {error}")
            self._schedule_job_poll()
            return
        self.job_log_offset = new_offset
        self._handle_background_log_chunk(data)
        state = str(status.get("state", "running"))
        if state in {"completed", "failed"}:
            self._log(f"Remote background job finished with exit code {status.get('exit_code')}")
            if status.get("error"):
                self._log(f"Remote background job error: {status.get('error')}")
            if state == "failed":
                for key, run in self.image_runs.items():
                    if run.get("status") == "Pending":
                        self._update_image_run(key, status="Failed", stage_text="Remote job failed before this image started")
            self._log("Use Download Outputs to copy remote outputs to the local output folder.")
            self._update_registry_for_active_job(state, status.get("exit_code"))
            self.active_job["done"] = True
            self.job_poll_after_id = None
            self._set_idle_state()
            return
        self.state.status_text.set("Running in background")
        self.state.remote_status.set(f"Remote: {state}")
        self._schedule_job_poll()

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
            self._handle_background_log_chunk(data)

        status = read_json(job_dir / "job_status.json", {})
        state = str(status.get("state", "running"))
        exit_path = job_dir / "exit_code.txt"
        if exit_path.exists() or state in {"completed", "failed"}:
            code = status.get("exit_code")
            if code is None and exit_path.exists():
                code = exit_path.read_text(encoding="utf-8", errors="replace").strip()
            self._log(f"Local background job finished with exit code {code}")
            self._update_registry_for_active_job("completed" if str(code) == "0" else "failed", code)
            return True
        self.state.status_text.set("Running in background")
        return False

    def _poll_remote_background_job(self) -> bool:
        if not self.remote_runner:
            return True
        data, self.job_log_offset = self.remote_runner.read_remote_log_since(self.job_log_offset)
        self._handle_background_log_chunk(data)
        status = self.remote_runner.remote_status()
        state = str(status.get("state", "running"))
        if state in {"completed", "failed"}:
            self._log(f"Remote background job finished with exit code {status.get('exit_code')}")
            if status.get("error"):
                self._log(f"Remote background job error: {status.get('error')}")
            if state == "failed":
                for key, run in self.image_runs.items():
                    if run.get("status") == "Pending":
                        self._update_image_run(key, status="Failed", stage_text="Remote job failed before this image started")
            self._log("Use Download Outputs to copy remote outputs to the local output folder.")
            self._update_registry_for_active_job(state, status.get("exit_code"))
            return True
        self.state.status_text.set("Running in background")
        self.state.remote_status.set(f"Remote: {state}")
        return False
