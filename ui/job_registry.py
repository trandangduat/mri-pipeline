from __future__ import annotations
import json
import os
import psutil
from pathlib import Path
from remote.remote_runner import RemoteRunner
import time
from tkinter import messagebox
from ui.events import ui_events, EVENT_LOG_MESSAGE
from pipeline.jobs import load_job_registry, save_job_registry, upsert_job_registry, read_json
from remote.remote_runner import RemoteRunConfig

class JobRegistryController:
    def __init__(self, gui):
        self.gui = gui
        
    def _job_identity(self, job: dict) -> str:

        return str(job.get("remote_job_dir") or job.get("job_dir") or job.get("job_id") or id(job))

    def _remove_job_registry_entry(self, job: dict) -> None:

        identity = self._job_identity(job)

        save_job_registry([entry for entry in load_job_registry() if self._job_identity(entry) != identity])

    def _delete_registry_job(self, job: dict) -> bool:

        if str(job.get("state", "")).lower() == "running":

            if not messagebox.askyesno("Delete running job", "This job appears to be running. Request stop and delete its folders anyway?"):

                return False

            self.gui.jobs_ctrl.pause_background_job(job)

    

        active_identity = self._job_identity(self.gui.jobs_ctrl.active_job.get("registry_entry") or self.gui.jobs_ctrl.active_job) if self.gui.jobs_ctrl.active_job else ""

        if active_identity and active_identity == self._job_identity(job):

            self.gui.jobs_ctrl.stop_current_job_monitor()

    

        try:

            if job.get("target") == "Server":

                runner = self.gui.jobs_ctrl.remote_runner_from_job_entry(job, read_metadata=False)

                if runner is None:

                    return False

                runner.clean_remote()

                download_subdir = str(job.get("download_subdir") or "").strip()

                output_dir = str(job.get("output_dir") or "").strip()

                if download_subdir and output_dir:

                    self.gui.jobs_ctrl.delete_download_subdir(output_dir, download_subdir)

            else:

                self.gui.jobs_ctrl.delete_local_job_folders(job)

            self._remove_job_registry_entry(job)

            ui_events.emit(EVENT_LOG_MESSAGE, f"Deleted job: {self._job_identity(job)}")

            return True

        except Exception as exc:

            messagebox.showerror("Delete job failed", f"Could not delete selected job:\n\n{type(exc).__name__}: {exc}")

            return False

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

    def _registry_entry_for_local_job(self, job_dir: Path, req: dict, pid: int | None = None, state: str = "running") -> dict:

        files = self.gui.progress_ctrl._input_files_for_progress(req)

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

    def _registry_entry_for_remote_job(self, runner: RemoteRunner, remote_dir: str, state: str = "running", run_request: dict | None = None) -> dict:

        cfg = runner.config

        files = []

        if cfg.input_mode == "file" and cfg.input_file:

            files = [cfg.input_file]

        elif cfg.input_mode == "files":

            files = list(cfg.input_files)

        elif cfg.input_dir:

            files = [cfg.input_dir]

        now = time.time()

        entry = {

            "job_id": Path(remote_dir).name,

            "target": "Server",

            "state": state,

            "remote_job_dir": remote_dir,

            "started_at": now,

            "updated_at": now,

            "output_dir": cfg.output_dir,

            "server_output_dir": cfg.server_output_dir,

            "remote_output_dir": runner.remote_output_dir,

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

        if run_request:

            entry["run_request"] = run_request

        return entry

    def _update_registry_for_active_job(self, state: str, exit_code=None) -> None:

        if not self.gui.jobs_ctrl.active_job:

            return

        entry = dict(self.gui.jobs_ctrl.active_job.get("registry_entry") or {})

        if not entry:

            entry = dict(self.gui.jobs_ctrl.active_job)

        entry.update({"state": state, "exit_code": exit_code, "updated_at": time.time()})

        upsert_job_registry(entry)

        self.gui.jobs_ctrl.active_job["registry_entry"] = entry

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

    def _same_remote_server(self, entry: dict, ssh_config, workspace: str | None = None) -> bool:

        host, port, username = ssh_config.host, int(ssh_config.port), ssh_config.username

        remote = dict(entry.get("remote") or {})

        if not remote:

            return False

        same_server = (

            str(remote.get("host", "")) == host

            and int(remote.get("port", 22) or 22) == port

            and str(remote.get("username", "")) == username

        )

        if not same_server:

            return False

        if workspace is None:

            return True

        remote_workspace = str(remote.get("workspace", "")).strip().rstrip("/")

        return remote_workspace == workspace.strip().rstrip("/")

    def _running_remote_jobs(self) -> list[dict] | None:

        jobs = self._remote_jobs_for_current_server()

        return None if jobs is None else [job for job in jobs if job.get("state") == "running"]

    def _remote_jobs_for_current_server(self) -> list[dict] | None:

        if not self.gui.remote_ctrl._require_remote_connection("checking remote background jobs"):

            return None

        if not self.gui.jobs_ctrl.ensure_remote_auth_for_job_action("Resume or Attach job"):

            return None

        ssh_config = self.gui.jobs_ctrl.build_ssh_config()

        if ssh_config is None:

            return None

        workspace = self.gui.state.remote_workspace.get().strip() or "~/mri-remote-jobs"

        runner = RemoteRunner(

            RemoteRunConfig(

                ssh=ssh_config,

                remote_workspace=workspace,

                remote_python=self.gui.state.remote_python.get().strip() or "python3",

                output_dir=self.gui.state.output_dir.get().strip(),

            ),

            on_log=self.gui.tools_ctrl._remote_log_event,

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

            and self._same_remote_server(entry, ssh_config, workspace)

        }

        jobs: list[dict] = []

        for remote_job in remote_jobs:

            remote_dir = str(remote_job.get("remote_job_dir", ""))

            entry = dict(registry_by_dir.get(remote_dir, {}))

            entry.update(remote_job)

            entry["target"] = "Server"

            entry["remote_job_dir"] = remote_dir

            entry.setdefault("output_dir", self.gui.state.output_dir.get().strip())

            entry["remote"] = {

                "host": ssh_config.host,

                "port": int(ssh_config.port),

                "username": ssh_config.username,

                "key_path": ssh_config.key_path,

                "workspace": workspace,

                "python": self.gui.state.remote_python.get().strip() or "python3",

            }

            jobs.append(entry)

        return jobs

    def _running_jobs_for_current_target(self) -> list[dict] | None:

        if self.gui.state.run_target.get() == "Server":

            return self._running_remote_jobs()

        return self._running_local_jobs()

    def _resumable_jobs_for_current_target(self) -> list[dict] | None:

        if self.gui.state.run_target.get() == "Server":

            jobs = self._remote_jobs_for_current_server()

            if jobs is None:

                return None

            return [job for job in jobs if job.get("target") == "Server" and job.get("state") != "running" and job.get("remote_job_dir")]

        return [

            job for job in self._known_jobs()

            if job.get("target") == "Local" and job.get("state") != "running" and job.get("job_dir")

        ]
