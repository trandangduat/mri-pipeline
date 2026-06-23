from __future__ import annotations

import os
import json
import posixpath
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pipeline_runner import PROJECT_ROOT, TOOL_DEFS, _derive_subject_id, _discover_mri_files, build_subject_id_map, is_tool_enabled
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
    license_dir: str = ""
    device: str = "cpu"
    threads: int = 4
    selected_tools: dict[str, str] = field(default_factory=dict)
    export_config: dict = field(default_factory=dict)
    stats_vector_config: dict = field(default_factory=dict)
    recursive: bool = True
    download_subdir: str = ""
    resume: bool = False


class RemoteRunner:
    def __init__(self, config: RemoteRunConfig, on_log: LogCallback | None = None) -> None:
        self.config = config
        self.on_log = on_log or (lambda _line: None)
        self.job_id = f"job_{time.strftime('%Y%m%d_%H%M%S')}"
        self.remote_job_dir = ""
        self.remote_output_dir = ""

    def test_ssh(self) -> None:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            ssh.run("uname -a && whoami && pwd", check=True)

    def check_docker(self) -> None:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            ssh.run("docker ps", check=True)

    def check_python_details(self) -> dict[str, str | bool]:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            return self._check_python_details(ssh)

    def _check_python_details(self, ssh: RemoteSSHClient) -> dict[str, str | bool]:
        py_cmd = f"{shlex.quote(self.config.remote_python)} --version 2>&1"
        pip_cmd = f"{shlex.quote(self.config.remote_python)} -m pip --version 2>&1"
        py_code, py_text = ssh.read_text(py_cmd)
        pip_code, pip_text = ssh.read_text(pip_cmd)
        python_text = py_text.strip() or "Python not found"
        pip_text = pip_text.strip() or "pip not found"
        self.on_log(("Python OK: " if py_code == 0 else "Python missing: ") + python_text)
        self.on_log(("pip OK: " if pip_code == 0 else "pip missing: ") + pip_text)
        return {
            "python_ok": py_code == 0,
            "pip_ok": pip_code == 0,
            "python_text": python_text,
            "pip_text": pip_text,
        }

    def check_python(self) -> bool:
        details = self.check_python_details()
        return bool(details["python_ok"] and details["pip_ok"])

    def install_python_requirements(self) -> bool:
        if not self.remote_job_dir:
            self.upload_job()
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            remote_code = posixpath.join(self.remote_job_dir, "code")
            details = self._check_python_details(ssh)
            if not details["python_ok"]:
                self.on_log("Failed: Python is not installed or remote_python is invalid. Install Python on the server first.")
                return False
            if not details["pip_ok"]:
                self.on_log("Installing pip with ensurepip...")
                ensurepip_cmd = f"{shlex.quote(self.config.remote_python)} -m ensurepip --user --upgrade >/tmp/mri_ensurepip.log 2>&1"
                ensurepip_code = ssh.run(ensurepip_cmd, stream=False, check=False)
                if ensurepip_code != 0:
                    self.on_log("Failed: pip is missing and ensurepip could not install it. Install python3-pip on the server first.")
                    return False
            cmd = (
                f"cd {shlex.quote(remote_code)} && "
                f"{shlex.quote(self.config.remote_python)} -m pip install --user -r requirements.txt >/tmp/mri_requirements.log 2>&1"
            )
            self.on_log("Installing packages from requirements.txt...")
            code = ssh.run(cmd, stream=False, check=False)
            self.on_log("Installed: Python packages from requirements.txt" if code == 0 else "Failed: Python package install. See /tmp/mri_requirements.log on server.")
            return code == 0

    def check_images(self) -> list[str]:
        required = self.required_images()
        missing: list[str] = []
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            for image in required:
                code = ssh.run(f"docker image inspect {shlex.quote(image)} >/dev/null 2>&1", stream=False)
                if code == 0:
                    self.on_log(f"OK image: {image}")
                else:
                    self.on_log(f"MISSING image: {image}")
                    missing.append(image)
        return missing

    def check_image_statuses(self, images: list[str]) -> dict[str, bool]:
        statuses: dict[str, bool] = {}
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            for image in dict.fromkeys(images):
                code = ssh.run(f"docker image inspect {shlex.quote(image)} >/dev/null 2>&1", stream=False)
                statuses[image] = code == 0
                self.on_log(("Installed: " if code == 0 else "Missing: ") + image)
        return statuses

    def ensure_tool_images(self, tool_keys: list[str]) -> bool:
        tool_keys = [tool for tool in dict.fromkeys(tool_keys) if tool and is_tool_enabled(tool)]
        if not tool_keys:
            return True
        if not self.remote_job_dir:
            self.upload_job()
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            remote_code = posixpath.join(self.remote_job_dir, "code")
            script = (
                "import sys\n"
                "from pipeline_runner import ensure_image, TOOL_DEFS\n"
                "ok = True\n"
                "for tool in sys.argv[1:]:\n"
                "    image = TOOL_DEFS.get(tool, {}).get('image', tool)\n"
                "    print(f'Downloading: {image}', flush=True)\n"
                "    result, err, _ = ensure_image(tool)\n"
                "    if result:\n"
                "        print(f'Installed: {image}', flush=True)\n"
                "    else:\n"
                "        print(f'Failed: {image} {err}', flush=True)\n"
                "        ok = False\n"
                "sys.exit(0 if ok else 2)\n"
            )
            cmd = [self.config.remote_python, "-c", script, *tool_keys]
            quoted = " ".join(shlex.quote(str(part)) for part in cmd)
            code = ssh.run(f"cd {shlex.quote(remote_code)} && PYTHONUNBUFFERED=1 {quoted}", stream=True)
            return code == 0

    def upload_job(self) -> str:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            workspace = ssh.expand_path(self.config.remote_workspace)
            self.remote_job_dir = posixpath.join(workspace, self.job_id)
            self.remote_output_dir = posixpath.join(self.remote_job_dir, "outputs")
            for sub in ("code", "input", "license", "outputs"):
                ssh.mkdir_p(posixpath.join(self.remote_job_dir, sub))

            self.on_log(f"Remote job: {self.remote_job_dir}")
            self._upload_export_config(ssh)
            self._upload_stats_vector_config(ssh)
            self._upload_subject_id_map(ssh)
            self._upload_code(ssh)
            self._upload_inputs(ssh)
            self._upload_license(ssh)
            self._write_job_metadata(ssh)
            return self.remote_job_dir

    def attach_job(self, remote_job_dir: str) -> None:
        self.remote_job_dir = remote_job_dir.rstrip("/")
        self.remote_output_dir = posixpath.join(self.remote_job_dir, "outputs")

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

    def _write_job_metadata(self, ssh: RemoteSSHClient) -> None:
        remote_path = posixpath.join(self.remote_job_dir, "job_metadata.json")
        metadata = {
            "job_id": self.job_id,
            "remote_job_dir": self.remote_job_dir,
            "remote_output_dir": self.remote_output_dir,
            "created_at": time.time(),
            "input_mode": self.config.input_mode,
            "output_dir": self.config.output_dir,
            "download_subdir": self.config.download_subdir,
        }
        with ssh.sftp.open(remote_path, "w") as f:
            f.write(json.dumps(metadata, indent=2))

    def _upload_export_config(self, ssh: RemoteSSHClient) -> None:
        remote_path = posixpath.join(self.remote_job_dir, "export_config.json")
        with ssh.sftp.open(remote_path, "w") as f:
            f.write(json.dumps(self.config.export_config or {}, indent=2))

    def _upload_stats_vector_config(self, ssh: RemoteSSHClient) -> None:
        remote_path = posixpath.join(self.remote_job_dir, "stats_vector_config.json")
        with ssh.sftp.open(remote_path, "w") as f:
            f.write(json.dumps(self.config.stats_vector_config or {}, indent=2))

    def _upload_subject_id_map(self, ssh: RemoteSSHClient) -> None:
        remote_input = posixpath.join(self.remote_job_dir, "input")
        mapping: dict[str, str] = {}
        if self.config.input_mode == "file" and self.config.input_file:
            src = Path(self.config.input_file)
            mapping[posixpath.join(remote_input, src.name)] = _derive_subject_id(str(src))
        elif self.config.input_mode == "files" and self.config.input_files:
            ids = build_subject_id_map(self.config.input_files, self.config.input_dir)
            for idx, path in enumerate(self.config.input_files, start=1):
                src = Path(path)
                remote_name = f"{idx:04d}_{src.name}"
                mapping[posixpath.join(remote_input, remote_name)] = ids.get(path, _derive_subject_id(path))
        elif self.config.input_dir:
            files = _discover_mri_files(self.config.input_dir, recursive=self.config.recursive)
            ids = build_subject_id_map(files, self.config.input_dir)
            root = Path(self.config.input_dir).resolve()
            for path in files:
                src = Path(path).resolve()
                rel = src.relative_to(root).as_posix()
                mapping[posixpath.join(remote_input, rel)] = ids.get(path, _derive_subject_id(path))

        remote_path = posixpath.join(self.remote_job_dir, "subject_ids.json")
        with ssh.sftp.open(remote_path, "w") as f:
            f.write(json.dumps(mapping, indent=2))

    def run_remote(self) -> int:
        if not self.remote_job_dir:
            self.upload_job()
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            ssh.run(f"rm -f {shlex.quote(posixpath.join(self.remote_job_dir, 'stop_requested'))}", stream=False, check=False)
            ssh.run(
                f"df -h {shlex.quote(self.remote_job_dir)} {shlex.quote(posixpath.join(self.remote_job_dir, 'outputs'))}",
                stream=True,
                check=False,
            )
            command = self._remote_command()
            return ssh.run(command, stream=True)

    def start_remote_detached(self) -> str:
        if not self.remote_job_dir:
            self.upload_job()
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
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
            worker_script = (
                f"{self._remote_command()} > {shlex.quote(run_log)} 2>&1; "
                f"code=$?; echo $code > {shlex.quote(exit_code)}; date +%s > {shlex.quote(finished_at)}; exit $code"
            )
            start_cmd = f"nohup bash -lc {shlex.quote(worker_script)} >/dev/null 2>&1 & echo $! > {shlex.quote(pid_file)}"
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
                return {"state": "running" if ps_code == 0 else "unknown", "pid": pid, "remote_job_dir": self.remote_job_dir}
            return {"state": "uploaded", "remote_job_dir": self.remote_job_dir}

    def read_remote_log_since(self, offset: int = 0) -> tuple[str, int]:
        if not self.remote_job_dir:
            return "", offset
        remote_log = posixpath.join(self.remote_job_dir, "run.log")
        with RemoteSSHClient(self.config.ssh, lambda _line: None) as ssh:
            try:
                with ssh.sftp.open(remote_log, "r") as f:
                    f.seek(offset)
                    data = f.read().decode(errors="replace")
                    return data, f.tell()
            except OSError:
                return "", offset

    def ensure_images(self) -> bool:
        if not self.remote_job_dir:
            self.upload_job()
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            remote_code = posixpath.join(self.remote_job_dir, "code")
            cmd = [self.config.remote_python, "pipeline_runner.py", "--ensure-images-only", "--json-events"]
            cmd += self._tool_args()
            quoted = " ".join(shlex.quote(str(part)) for part in cmd)
            code = ssh.run(f"cd {shlex.quote(remote_code)} && PYTHONUNBUFFERED=1 {quoted}", stream=True)
            if code != 0:
                self.on_log(f"Remote image preflight failed with exit code {code}")
            return code == 0

    def request_pause(self) -> None:
        if not self.remote_job_dir:
            raise RuntimeError("No remote job is running")
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            stop_file = posixpath.join(self.remote_job_dir, "stop_requested")
            ssh.run(f"mkdir -p {shlex.quote(self.remote_job_dir)} && touch {shlex.quote(stop_file)}", stream=False, check=False)
            self.on_log(f"Remote pause requested via stop file: {stop_file}")

    def download_outputs(self, local_target_dir: str | Path | None = None) -> Path:
        if not self.remote_job_dir:
            raise RuntimeError("No remote job has been uploaded/run yet")
        local_target = Path(local_target_dir or self.config.output_dir or (PROJECT_ROOT / "outputs"))
        if self.config.download_subdir:
            local_target = local_target / self.config.download_subdir
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            ssh.download_dir(posixpath.join(self.remote_job_dir, "outputs"), local_target)
        return local_target

    def clean_remote(self) -> None:
        if not self.remote_job_dir:
            return
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            ssh.run(f"rm -rf {shlex.quote(self.remote_job_dir)}", check=False)

    def required_images(self) -> list[str]:
        images: list[str] = []
        for tool_key in self.config.selected_tools.values():
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

    def _upload_code(self, ssh: RemoteSSHClient) -> None:
        remote_code = posixpath.join(self.remote_job_dir, "code")
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

    def _upload_inputs(self, ssh: RemoteSSHClient) -> None:
        remote_input = posixpath.join(self.remote_job_dir, "input")
        if self.config.input_mode == "file":
            if not self.config.input_file:
                return
            src = Path(self.config.input_file)
            ssh.upload_file(src, posixpath.join(remote_input, src.name))
        elif self.config.input_mode == "files":
            if not self.config.input_files:
                return
            for idx, path in enumerate(self.config.input_files, start=1):
                src = Path(path)
                remote_name = f"{idx:04d}_{src.name}"
                ssh.upload_file(src, posixpath.join(remote_input, remote_name))
        else:
            if not self.config.input_dir:
                return
            self.on_log("Uploading input directory recursively (only MRI files)...")
            ssh.upload_dir(self.config.input_dir, remote_input, skip_dirs={"__pycache__", "venv", ".venv", ".git", ".idea", ".vscode"}, allowed_extensions={".nii", ".nii.gz", ".mgz", ".mgh", ".dcm"})

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

    def _remote_command(self) -> str:
        remote_code = posixpath.join(self.remote_job_dir, "code")
        remote_input = posixpath.join(self.remote_job_dir, "input")
        remote_output = posixpath.join(self.remote_job_dir, "outputs")
        remote_license = posixpath.join(self.remote_job_dir, "license")

        cmd = [self.config.remote_python, "pipeline_runner.py", "--json-events"]
        if self.config.input_mode == "file":
            input_name = Path(self.config.input_file).name
            cmd += ["--input-file", posixpath.join(remote_input, input_name)]
        else:
            cmd += ["--input-dir", remote_input]

        cmd += ["--output-dir", remote_output]
        cmd += ["--license-dir", remote_license]
        cmd += ["--export-config", posixpath.join(self.remote_job_dir, "export_config.json")]
        cmd += ["--stats-vector-config", posixpath.join(self.remote_job_dir, "stats_vector_config.json")]
        cmd += ["--subject-id-map", posixpath.join(self.remote_job_dir, "subject_ids.json")]
        cmd += ["--device", self.config.device]
        cmd += ["--threads", str(self.config.threads)]
        if self.config.resume:
            cmd.append("--resume")
        if not self.config.recursive:
            cmd.append("--non-recursive")
        cmd += ["--stop-file", posixpath.join(self.remote_job_dir, "stop_requested")]

        cmd += self._tool_args()

        quoted = " ".join(shlex.quote(str(part)) for part in cmd)
        return f"cd {shlex.quote(remote_code)} && PYTHONUNBUFFERED=1 {quoted}"

    def _tool_args(self) -> list[str]:
        args: list[str] = []
        option_map = {
            "reorientation": "--reorientation",
            "brain_extraction": "--brain-extraction",
            "segmentation": "--segmentation",
            "bias_correction": "--bias-correction",
            "template_registration": "--template-registration",
            "white_matter_segmentation": "--white-matter-segmentation",
            "stats_extraction": "--stats-extraction",
        }
        for stage, opt in option_map.items():
            value = self.config.selected_tools.get(stage)
            if value and is_tool_enabled(value):
                args += [opt, value]
        return args
