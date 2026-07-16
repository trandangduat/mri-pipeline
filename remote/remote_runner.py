from __future__ import annotations

import os
import hashlib
import json
import posixpath
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pipeline_runner import PROJECT_ROOT, _derive_subject_id, build_subject_id_map, is_tool_enabled
from remote.ssh_client import RemoteSSHClient, SSHConfig


LogCallback = Callable[[str], None]


@dataclass
class RemoteRunConfig:
    ssh: SSHConfig
    remote_workspace: str = "~/mri-remote-jobs"
    remote_python: str = "python3"
    input_mode: str = "file"
    input_file: str = ""
    input_files: list[str] = field(default_factory=list)
    input_dir: str = ""
    output_dir: str = ""
    server_output_dir: str = ""
    license_dir: str = ""
    device: str = "cpu"
    threads: int = 4
    selected_tools: dict[str, str] = field(default_factory=dict)
    export_config: dict = field(default_factory=dict)
    stats_vector_config: dict = field(default_factory=dict)
    recursive: bool = True
    download_subdir: str = ""
    resume: bool = False
    restart: bool = False
    lazy_watch: bool = False


class RemoteRunner:
    def __init__(self, config: RemoteRunConfig, on_log: LogCallback | None = None) -> None:
        self.config = config
        self.on_log = on_log or (lambda _line: None)
        self.job_id = f"job_{time.strftime('%Y%m%d_%H%M%S')}"
        self.remote_job_dir = ""
        self.remote_output_dir = ""

    def remote_venv_display_path(self) -> str:
        return posixpath.join((self.config.remote_workspace or "~/mri-remote-jobs").rstrip("/"), ".venv")

    def _remote_code_dir(self, ssh: RemoteSSHClient | None = None) -> str:
        if ssh is not None:
            workspace = ssh.expand_path(self.config.remote_workspace)
        elif self.remote_job_dir:
            workspace = posixpath.dirname(self.remote_job_dir.rstrip("/"))
        else:
            workspace = (self.config.remote_workspace or "~/mri-remote-jobs").rstrip("/")
        return posixpath.join(workspace, "code")

    def _local_code_signature(self) -> str:
        hasher = hashlib.sha256()
        roots: list[Path] = [PROJECT_ROOT / "pipeline_runner.py", PROJECT_ROOT / "requirements.txt", PROJECT_ROOT / "normalize_volumes.py"]
        for folder, extensions in ((PROJECT_ROOT / "pipeline", {".py"}), (PROJECT_ROOT / "info", {".txt"})):
            if folder.exists():
                for root, dirs, files in os.walk(folder):
                    dirs[:] = [d for d in dirs if d != "__pycache__"]
                    for name in sorted(files):
                        path = Path(root) / name
                        if path.suffix in extensions:
                            roots.append(path)
        for path in sorted((p for p in roots if p.exists()), key=lambda p: p.relative_to(PROJECT_ROOT).as_posix()):
            rel = path.relative_to(PROJECT_ROOT).as_posix()
            hasher.update(rel.encode("utf-8"))
            hasher.update(path.read_bytes())
        return hasher.hexdigest()

    def test_ssh(self) -> None:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            ssh.run("uname -a && whoami && pwd", check=True)

    def check_python_details(self) -> dict[str, str | bool]:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            return self._check_python_details(ssh)

    def _check_python_details(self, ssh: RemoteSSHClient) -> dict[str, str | bool]:
        venv_dir = self._remote_venv_dir(ssh)
        venv_python = self._remote_venv_python(ssh)
        py_cmd = f"{shlex.quote(self.config.remote_python)} --version 2>&1"
        py_code, py_text = ssh.read_text(py_cmd)
        venv_code, _venv_text = ssh.read_text(f"test -x {shlex.quote(venv_python)}")
        venv_py_code, venv_py_text = ssh.read_text(f"{shlex.quote(venv_python)} --version 2>&1") if venv_code == 0 else (1, "Virtual environment not created")
        pip_code, pip_text = ssh.read_text(f"{shlex.quote(venv_python)} -m pip --version 2>&1") if venv_code == 0 else (1, "pip not available because venv is missing")
        python_text = py_text.strip() or "Python not found"
        venv_python_text = venv_py_text.strip() or "Venv Python not found"
        pip_text = pip_text.strip() or "pip not found"
        self.on_log(("Base Python OK: " if py_code == 0 else "Base Python missing: ") + python_text)
        self.on_log(f"Remote venv: {venv_dir}")
        self.on_log(("Venv Python OK: " if venv_py_code == 0 else "Venv Python missing: ") + venv_python_text)
        self.on_log(("Venv pip OK: " if pip_code == 0 else "Venv pip missing: ") + pip_text)
        return {
            "python_ok": venv_py_code == 0,
            "pip_ok": pip_code == 0,
            "base_python_ok": py_code == 0,
            "venv_exists": venv_code == 0,
            "venv_python_ok": venv_py_code == 0,
            "venv_pip_ok": pip_code == 0,
            "python_text": venv_python_text,
            "base_python_text": python_text,
            "venv_path": venv_dir,
            "pip_text": pip_text,
        }

    def _remote_venv_dir(self, ssh: RemoteSSHClient) -> str:
        workspace = ssh.expand_path(self.config.remote_workspace)
        return posixpath.join(workspace, ".venv")

    def _remote_venv_python(self, ssh: RemoteSSHClient) -> str:
        return posixpath.join(self._remote_venv_dir(ssh), "bin", "python")

    def _remote_venv_has_pip(self, ssh: RemoteSSHClient, venv_python: str) -> bool:
        return ssh.run(f"{shlex.quote(venv_python)} -m pip --version >/dev/null 2>&1", stream=False, check=False) == 0

    def _bootstrap_remote_venv_pip(self, ssh: RemoteSSHClient, venv_dir: str, venv_python: str) -> bool:
        if self._remote_venv_has_pip(ssh, venv_python):
            return True

        self.on_log("Installing pip in remote venv with ensurepip...")
        code = ssh.run(f"{shlex.quote(venv_python)} -m ensurepip --upgrade", stream=True, check=False)
        if code == 0 and self._remote_venv_has_pip(ssh, venv_python):
            return True

        self.on_log("Recreating remote venv because pip is unavailable...")
        ssh.run(f"rm -rf {shlex.quote(venv_dir)}", stream=True, check=False)
        code = ssh.run(f"{shlex.quote(self.config.remote_python)} -m venv {shlex.quote(venv_dir)}", stream=True, check=False)
        if code != 0:
            return False
        if self._remote_venv_has_pip(ssh, venv_python):
            return True

        self.on_log("Bootstrapping pip in remote venv with get-pip.py...")
        download_get_pip = "import urllib.request; urllib.request.urlretrieve('https://bootstrap.pypa.io/get-pip.py', '/tmp/get-pip.py')"
        code = ssh.run(
            f"{shlex.quote(venv_python)} -c {shlex.quote(download_get_pip)} && "
            f"{shlex.quote(venv_python)} /tmp/get-pip.py",
            stream=True,
            check=False,
        )
        return code == 0 and self._remote_venv_has_pip(ssh, venv_python)

    def _remote_venv_fix_hint(self, venv_dir: str) -> str:
        return (
            "Remote venv exists but pip is unavailable and automatic repair failed. "
            "Run on the server: `sudo apt-get update && sudo apt-get install -y python3-venv python3-pip`, "
            f"then `rm -rf {venv_dir}` and retry."
        )

    def ensure_remote_venv(self, ssh: RemoteSSHClient) -> str:
        workspace = ssh.expand_path(self.config.remote_workspace)
        ssh.mkdir_p(workspace)
        venv_dir = posixpath.join(workspace, ".venv")
        venv_python = posixpath.join(venv_dir, "bin", "python")
        if ssh.run(f"test -x {shlex.quote(venv_python)}", stream=False, check=False) != 0:
            self.on_log(f"Creating remote venv: {venv_dir}")
            code = ssh.run(f"{shlex.quote(self.config.remote_python)} -m venv {shlex.quote(venv_dir)}", stream=True, check=False)
            if code != 0:
                raise RuntimeError("Could not create remote venv. Install python3-venv on the server or set a valid base Python.")
        if not self._bootstrap_remote_venv_pip(ssh, venv_dir, venv_python):
            raise RuntimeError(self._remote_venv_fix_hint(venv_dir))
        self.on_log(f"Using remote venv Python: {venv_python}")
        return venv_python

    def check_python(self) -> bool:
        details = self.check_python_details()
        return bool(details["python_ok"] and details["pip_ok"])

    def install_python_requirements(self) -> bool:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            remote_code = self._remote_code_dir(ssh)
            self._ensure_shared_code(ssh)
            details = self._check_python_details(ssh)
            if not details["base_python_ok"]:
                self.on_log("Failed: Base Python is not installed or remote_python is invalid. Install Python on the server first.")
                return False
            venv_python = self.ensure_remote_venv(ssh)
            cmd = (
                f"cd {shlex.quote(remote_code)} && "
                f"{shlex.quote(venv_python)} -m pip install --disable-pip-version-check -r requirements.txt"
            )
            self.on_log("Installing packages into remote venv from requirements.txt...")
            code = ssh.run(cmd, stream=True, check=False)
            self.on_log("Installed: Python packages into remote venv" if code == 0 else "Failed: Python package install in remote venv.")
            return code == 0

    def check_image_statuses(self, images: list[str]) -> dict[str, bool]:
        statuses: dict[str, bool] = {}
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            for image in dict.fromkeys(images):
                code = ssh.run(f"docker image inspect {shlex.quote(image)} >/dev/null 2>&1", stream=False)
                statuses[image] = code == 0
                self.on_log(("Installed: " if code == 0 else "Missing: ") + image)
        return statuses

    def check_image_details(self, images: list[str]) -> dict[str, dict[str, int | bool | None]]:
        details: dict[str, dict[str, int | bool | None]] = {}
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            for image in dict.fromkeys(images):
                code, text = ssh.read_text(f"docker image inspect --format '{{{{.Size}}}}' {shlex.quote(image)} 2>/dev/null")
                installed = code == 0
                size: int | None = None
                if installed:
                    try:
                        size = int(text.strip().splitlines()[-1])
                    except (IndexError, ValueError):
                        size = None
                details[image] = {"installed": installed, "size": size}
                self.on_log(("Installed: " if installed else "Missing: ") + image)
        return details

    def remove_images(self, images: list[str]) -> dict[str, tuple[bool, str]]:
        results: dict[str, tuple[bool, str]] = {}
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            for image in dict.fromkeys(images):
                self.on_log(f"Deleting: {image}")
                code, text = ssh.read_text(f"docker image rm {shlex.quote(image)} 2>&1")
                ok = code == 0
                results[image] = (ok, text.strip())
                self.on_log(("Deleted: " if ok else "Failed: ") + image)
        return results

    def ensure_tool_images(self, tool_keys: list[str]) -> bool:
        tool_keys = [tool for tool in dict.fromkeys(tool_keys) if tool and is_tool_enabled(tool)]
        if not tool_keys:
            return True
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            remote_code = self._remote_code_dir(ssh)
            self._ensure_shared_code(ssh)
            venv_python = self.ensure_remote_venv(ssh)
            script = (
                "import sys\n"
                "from pipeline_runner import ensure_image, TOOL_DEFS\n"
                "ok = True\n"
                "for tool in sys.argv[1:]:\n"
                "    image = TOOL_DEFS.get(tool, {}).get('image', tool)\n"
                "    print(f'Downloading: {image}', flush=True)\n"
                "    result, err, _ = ensure_image(tool, on_build_log=lambda l: print(f'Docker: {l}', flush=True))\n"
                "    if result:\n"
                "        print(f'Installed: {image}', flush=True)\n"
                "    else:\n"
                "        print(f'Failed: {image} {err}', flush=True)\n"
                "        ok = False\n"
                "sys.exit(0 if ok else 2)\n"
            )
            cmd = [venv_python, "-c", script, *tool_keys]
            quoted = " ".join(shlex.quote(str(part)) for part in cmd)
            code = ssh.run(f"cd {shlex.quote(remote_code)} && PYTHONUNBUFFERED=1 {quoted}", stream=True)
            return code == 0

    def upload_job(self) -> str:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            workspace = ssh.expand_path(self.config.remote_workspace)
            self.remote_job_dir = posixpath.join(workspace, self.job_id)
            if self.config.server_output_dir:
                self.remote_output_dir = ssh.expand_path(self.config.server_output_dir)
            else:
                self.remote_output_dir = posixpath.join(self.remote_job_dir, "outputs")
            ssh.mkdir_p(workspace)
            ssh.mkdir_p(self.remote_output_dir)
            for sub in ("license",):
                ssh.mkdir_p(posixpath.join(self.remote_job_dir, sub))

            self.on_log(f"Remote job: {self.remote_job_dir}")
            self.on_log("Preparing run configuration...")
            self._upload_export_config(ssh)
            self._upload_stats_vector_config(ssh)
            self._upload_subject_id_map(ssh)
            self._ensure_shared_code(ssh)
            self.on_log("Using MRI input paths already on the server.")
            self.on_log("Uploading license files...")
            self._upload_license(ssh)
            self._write_job_config(ssh)
            self._write_job_metadata(ssh)
            self.on_log("Remote upload complete.")
            return self.remote_job_dir

    def attach_job(self, remote_job_dir: str, remote_output_dir: str = "") -> None:
        self.remote_job_dir = remote_job_dir.rstrip("/")
        self.remote_output_dir = remote_output_dir or posixpath.join(self.remote_job_dir, "outputs")

    def read_remote_metadata(self) -> dict:
        if not self.remote_job_dir:
            return {}
        metadata_path = posixpath.join(self.remote_job_dir, "job_metadata.json")
        with RemoteSSHClient(self.config.ssh, lambda _line: None) as ssh:
            try:
                with ssh.sftp.open(metadata_path, "r") as f:
                    data = f.read().decode(errors="replace")
                parsed = json.loads(data)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}

    def read_remote_job_config(self) -> dict:
        if not self.remote_job_dir:
            return {}
        config_path = posixpath.join(self.remote_job_dir, "job_config.json")
        with RemoteSSHClient(self.config.ssh, lambda _line: None) as ssh:
            try:
                with ssh.sftp.open(config_path, "r") as f:
                    data = f.read().decode(errors="replace")
                parsed = json.loads(data)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}

    def write_remote_job_config(self, config: dict) -> None:
        if not self.remote_job_dir:
            raise RuntimeError("No remote job is attached")
        config_path = posixpath.join(self.remote_job_dir, "job_config.json")
        with RemoteSSHClient(self.config.ssh, lambda _line: None) as ssh:
            with ssh.sftp.open(config_path, "w") as f:
                f.write(json.dumps(config, indent=2))

    def _write_job_metadata(self, ssh: RemoteSSHClient) -> None:
        remote_path = posixpath.join(self.remote_job_dir, "job_metadata.json")
        metadata = {
            "job_id": self.job_id,
            "remote_job_dir": self.remote_job_dir,
            "remote_output_dir": self.remote_output_dir,
            "remote_code_dir": self._remote_code_dir(ssh),
            "created_at": time.time(),
            "input_source": "Server",
            "input_mode": self.config.input_mode,
            "output_dir": self.config.output_dir,
            "download_subdir": self.config.download_subdir,
        }
        with ssh.sftp.open(remote_path, "w") as f:
            f.write(json.dumps(metadata, indent=2))

    def _remote_input_request(self) -> dict:
        subject_id_map: dict[str, str] = {}
        if self.config.input_mode == "file" and self.config.input_file:
            subject_id_map[self.config.input_file] = _derive_subject_id(self.config.input_file)
            return {
                "mode": "file",
                "input_file": self.config.input_file,
                "subject_id": subject_id_map[self.config.input_file],
                "subject_id_map": subject_id_map,
            }
        if self.config.input_mode == "files" and self.config.input_files:
            ids = build_subject_id_map(self.config.input_files, self.config.input_dir)
            for path in self.config.input_files:
                subject_id_map[path] = ids.get(path, _derive_subject_id(path))
            return {
                "mode": "files",
                "input_files": list(self.config.input_files),
                "input_dir": self.config.input_dir,
                "subject_id_map": subject_id_map,
            }
        return {
            "mode": "dir",
            "input_dir": self.config.input_dir,
            "recursive": self.config.recursive,
            "subject_id_map": subject_id_map,
        }

    def _write_job_config(self, ssh: RemoteSSHClient) -> None:
        remote_path = posixpath.join(self.remote_job_dir, "job_config.json")
        remote_request = {
            **self._remote_input_request(),
            "job_dir": self.remote_job_dir,
            "run_target": "Server",
            "output_dir": self.remote_output_dir,
            "effective_output_dir": self.remote_output_dir,
            "license_dir": posixpath.join(self.remote_job_dir, "license"),
            "device": self.config.device,
            "threads": int(self.config.threads),
            "selected_tools": self.config.selected_tools,
            "export_config": self.config.export_config or {},
            "stats_vector_config": self.config.stats_vector_config or {},
            "resume": bool(self.config.resume),
            "restart": bool(self.config.restart),
        }
        with ssh.sftp.open(remote_path, "w") as f:
            f.write(json.dumps(remote_request, indent=2))

    def _upload_export_config(self, ssh: RemoteSSHClient) -> None:
        remote_path = posixpath.join(self.remote_job_dir, "export_config.json")
        with ssh.sftp.open(remote_path, "w") as f:
            f.write(json.dumps(self.config.export_config or {}, indent=2))

    def _upload_stats_vector_config(self, ssh: RemoteSSHClient) -> None:
        remote_path = posixpath.join(self.remote_job_dir, "stats_vector_config.json")
        with ssh.sftp.open(remote_path, "w") as f:
            f.write(json.dumps(self.config.stats_vector_config or {}, indent=2))

    def _upload_subject_id_map(self, ssh: RemoteSSHClient) -> None:
        mapping = self._remote_input_request().get("subject_id_map", {})
        remote_path = posixpath.join(self.remote_job_dir, "subject_ids.json")
        with ssh.sftp.open(remote_path, "w") as f:
            f.write(json.dumps(mapping, indent=2))

    def start_remote_detached(self) -> str:
        if not self.remote_job_dir:
            self.upload_job()
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            if self.config.input_file or self.config.input_files or self.config.input_dir:
                self._write_job_config(ssh)
            remote_code = self._remote_code_dir(ssh)
            self._ensure_shared_code(ssh)
            venv_python = self.ensure_remote_venv(ssh)
            run_log = posixpath.join(self.remote_job_dir, "run.log")
            exit_code = posixpath.join(self.remote_job_dir, "exit_code.txt")
            pid_file = posixpath.join(self.remote_job_dir, "pid.txt")
            finished_at = posixpath.join(self.remote_job_dir, "finished_at.txt")
            stop_file = posixpath.join(self.remote_job_dir, "stop_requested")
            ssh.run(f"rm -f {shlex.quote(stop_file)} {shlex.quote(exit_code)} {shlex.quote(finished_at)} {shlex.quote(run_log)}", stream=False, check=False)
            ssh.run(
                f"df -h {shlex.quote(self.remote_job_dir)} {shlex.quote(posixpath.join(self.remote_job_dir, 'outputs'))} > {shlex.quote(posixpath.join(self.remote_job_dir, 'disk.log'))} 2>&1",
                stream=False,
                check=False,
            )
            config_path = posixpath.join(self.remote_job_dir, "job_config.json")
            launcher_log = posixpath.join(self.remote_job_dir, "launcher.log")
            cmd_args = [f"--job-config {shlex.quote(config_path)}"]
            if getattr(self.config, "lazy_watch", False):
                cmd_args.append("--lazy-watch")
            command = (
                f"cd {shlex.quote(remote_code)} && PYTHONPATH={shlex.quote(remote_code)}:$PYTHONPATH PYTHONUNBUFFERED=1 "
                f"{shlex.quote(venv_python)} -m pipeline.job_worker {' '.join(cmd_args)}"
            )
            worker_script = (
                "set +e; "
                f"printf '[%s] Remote launcher started\\n' \"$(date +%H:%M:%S)\" >> {shlex.quote(run_log)}; "
                f"{command} > {shlex.quote(launcher_log)} 2>&1; "
                "code=$?; "
                f"if [ $code -ne 0 ]; then "
                f"printf '[%s] Remote launcher failed with exit %s\\n' \"$(date +%H:%M:%S)\" \"$code\" >> {shlex.quote(run_log)}; "
                f"cat {shlex.quote(launcher_log)} >> {shlex.quote(run_log)} 2>/dev/null; "
                "fi; "
                f"echo $code > {shlex.quote(exit_code)}; date +%s > {shlex.quote(finished_at)}; exit $code"
            )
            quoted_worker = shlex.quote(worker_script)
            start_cmd = (
                "if command -v setsid >/dev/null 2>&1; then "
                f"setsid bash -lc {quoted_worker} >/dev/null 2>&1 < /dev/null & "
                "else "
                f"nohup bash -lc {quoted_worker} >/dev/null 2>&1 < /dev/null & "
                "fi; "
                f"echo $! > {shlex.quote(pid_file)}"
            )
            code = ssh.run(start_cmd, stream=False, check=False)
            if code != 0:
                raise RuntimeError(f"Failed to start detached remote job: exit {code}")
            self.on_log(f"Remote background job started: {self.remote_job_dir}")
            return self.remote_job_dir

    def remote_status(self) -> dict[str, str | int | bool]:
        if not self.remote_job_dir:
            return {"state": "not_started"}
        with RemoteSSHClient(self.config.ssh, lambda _line: None) as ssh:
            exit_path = posixpath.join(self.remote_job_dir, "exit_code.txt")
            pid_path = posixpath.join(self.remote_job_dir, "pid.txt")
            exit_code, exit_text = ssh.read_text(f"cat {shlex.quote(exit_path)} 2>/dev/null")
            pid_code, pid_text = ssh.read_text(f"cat {shlex.quote(pid_path)} 2>/dev/null")
            pid = pid_text.strip()
            if exit_code == 0 and exit_text.strip() != "":
                code = int(exit_text.strip().splitlines()[-1])
                return {"state": "completed" if code == 0 else "failed", "exit_code": code, "pid": pid, "remote_job_dir": self.remote_job_dir}
            if pid_code == 0 and pid:
                ps_code = ssh.run(f"kill -0 {shlex.quote(pid)} >/dev/null 2>&1", stream=False, check=False)
                if ps_code == 0:
                    return {"state": "running", "pid": pid, "remote_job_dir": self.remote_job_dir}
                return {"state": "failed", "exit_code": None, "pid": pid, "remote_job_dir": self.remote_job_dir, "error": "process exited before writing exit_code.txt"}
            return {"state": "uploaded", "remote_job_dir": self.remote_job_dir}

    def list_background_jobs(self) -> list[dict[str, str]]:
        with RemoteSSHClient(self.config.ssh, lambda _line: None) as ssh:
            workspace = ssh.expand_path(self.config.remote_workspace)
            cmd = (
                f"for d in {shlex.quote(workspace)}/job_*; do "
                "[ -d \"$d\" ] || continue; "
                "pid=$(cat \"$d/pid.txt\" 2>/dev/null || true); "
                "exit_code=$(cat \"$d/exit_code.txt\" 2>/dev/null || true); "
                "state=uploaded; "
                "if [ -n \"$exit_code\" ]; then "
                "if [ \"$exit_code\" = 0 ]; then state=completed; else state=failed; fi; "
                "elif [ -n \"$pid\" ] && kill -0 \"$pid\" 2>/dev/null; then state=running; "
                "elif [ -n \"$pid\" ]; then state=unknown; fi; "
                "printf '%s\\t%s\\t%s\\n' \"$state\" \"$pid\" \"$d\"; "
                "done"
            )
            code, text = ssh.read_text(cmd)
            if code != 0:
                return []
        jobs: list[dict[str, str]] = []
        for line in text.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            state, pid, remote_job_dir = parts
            jobs.append({"state": state, "pid": pid, "remote_job_dir": remote_job_dir})
        return jobs

    def read_remote_log_since(self, offset: int = 0) -> tuple[str, int]:
        if not self.remote_job_dir:
            return "", offset
        remote_log = posixpath.join(self.remote_job_dir, "run.log")
        launcher_log = posixpath.join(self.remote_job_dir, "launcher.log")
        with RemoteSSHClient(self.config.ssh, lambda _line: None) as ssh:
            try:
                with ssh.sftp.open(remote_log, "r") as f:
                    f.seek(offset)
                    data = f.read().decode(errors="replace")
                    return data, f.tell()
            except OSError:
                try:
                    with ssh.sftp.open(launcher_log, "r") as f:
                        f.seek(offset)
                        data = f.read().decode(errors="replace")
                        return data, f.tell()
                except OSError:
                    return "", offset

    def request_pause(self) -> None:
        if not self.remote_job_dir:
            raise RuntimeError("No remote job is running")
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            stop_file = posixpath.join(self.remote_job_dir, "stop_requested")
            ssh.run(f"mkdir -p {shlex.quote(self.remote_job_dir)} && touch {shlex.quote(stop_file)}", stream=False, check=False)
            self.on_log(f"Remote pause requested via stop file: {stop_file}")

    def download_outputs(self, local_target_dir: str | Path | None = None) -> Path:
        if not self.remote_job_dir:
            raise RuntimeError("No remote job has been run or attached yet")
        local_target = Path(local_target_dir or self.config.output_dir or (PROJECT_ROOT / "outputs"))
        if self.config.download_subdir:
            local_target = local_target / self.config.download_subdir
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            remote_outputs = self.remote_output_dir or posixpath.join(self.remote_job_dir, "outputs")
            ssh.download_dir(remote_outputs, local_target)
        return local_target

    def clean_remote(self) -> None:
        if not self.remote_job_dir:
            return
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            code = ssh.run(f"rm -rf {shlex.quote(self.remote_job_dir)}", check=False)
            if code != 0:
                raise RuntimeError(f"Could not delete remote job folder: {self.remote_job_dir}")

    def _ensure_shared_code(self, ssh: RemoteSSHClient) -> str:
        remote_code = self._remote_code_dir(ssh)
        signature = self._local_code_signature()
        manifest_path = posixpath.join(remote_code, "code_manifest.json")
        manifest_probe = 'import json,sys; print(json.load(open(sys.argv[1])).get("signature", ""))'
        ready_cmd = (
            f"test -f {shlex.quote(posixpath.join(remote_code, 'pipeline_runner.py'))} && "
            f"test -f {shlex.quote(posixpath.join(remote_code, 'pipeline', 'job_worker.py'))} && "
            f"test -f {shlex.quote(manifest_path)} && "
            f"{shlex.quote(self.config.remote_python)} -c {shlex.quote(manifest_probe)} {shlex.quote(manifest_path)}"
        )
        ready_code, ready_text = ssh.read_text(ready_cmd)
        if ready_code == 0 and ready_text.strip().splitlines()[-1:] == [signature]:
            self.on_log(f"Using shared remote pipeline code: {remote_code}")
            return remote_code

        self.on_log(f"Uploading shared pipeline code once: {remote_code}")
        self._upload_code(ssh, remote_code)
        with ssh.sftp.open(manifest_path, "w") as f:
            f.write(json.dumps({"signature": signature, "updated_at": time.time()}, indent=2))
        return remote_code

    def _upload_code(self, ssh: RemoteSSHClient, remote_code: str) -> None:
        ssh.mkdir_p(remote_code)
        ssh.upload_file(PROJECT_ROOT / "pipeline_runner.py", posixpath.join(remote_code, "pipeline_runner.py"))
        pipeline_pkg = PROJECT_ROOT / "pipeline"
        if pipeline_pkg.exists():
            ssh.upload_dir(pipeline_pkg, posixpath.join(remote_code, "pipeline"), skip_dirs={"__pycache__"}, allowed_extensions={".py"})
        req = PROJECT_ROOT / "requirements.txt"
        if req.exists():
            ssh.upload_file(req, posixpath.join(remote_code, "requirements.txt"))
        norm_vol = PROJECT_ROOT / "normalize_volumes.py"
        if norm_vol.exists():
            ssh.upload_file(norm_vol, posixpath.join(remote_code, "normalize_volumes.py"))
        info_dir = PROJECT_ROOT / "info"
        if info_dir.exists():
            ssh.upload_dir(info_dir, posixpath.join(remote_code, "info"), allowed_extensions={".txt"})

    def _upload_license(self, ssh: RemoteSSHClient) -> None:
        if not self.config.license_dir:
            return
        local_license = Path(self.config.license_dir)
        if not local_license.exists():
            self.on_log(f"License not found locally: {local_license}")
            return
            
        remote_license_dir = posixpath.join(self.remote_job_dir, "license")
        if local_license.is_file():
            self.on_log(f"Uploading license file: {local_license.name}")
            ssh.upload_file(local_license, posixpath.join(remote_license_dir, "license.txt"))
        else:
            self.on_log("Uploading license directory...")
            ssh.upload_dir(local_license, remote_license_dir, skip_dirs={"__pycache__"})

    def _tool_args(self) -> list[str]:
        args: list[str] = []
        option_map = {
            "reorientation": "--reorientation",
            "brain_extraction": "--brain-extraction",
            "segmentation": "--segmentation",
            "bias_correction": "--bias-correction",
            "template_registration": "--template-registration",
            "white_matter_segmentation": "--white-matter-segmentation",
            "surface_reconstruction": "--surface-reconstruction",
            "surface_registration": "--surface-registration",
            "stats_extraction": "--stats-extraction",
        }
        for stage, opt in option_map.items():
            value = self.config.selected_tools.get(stage)
            if value and is_tool_enabled(value):
                args += [opt, value]
        return args
