from __future__ import annotations

import os
import posixpath
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pipeline_runner import PROJECT_ROOT, TOOL_DEFS, is_tool_enabled
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

    def upload_job(self) -> str:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            workspace = ssh.expand_path(self.config.remote_workspace)
            self.remote_job_dir = posixpath.join(workspace, self.job_id)
            self.remote_output_dir = posixpath.join(self.remote_job_dir, "outputs")
            for sub in ("code", "input", "license", "outputs"):
                ssh.mkdir_p(posixpath.join(self.remote_job_dir, sub))

            self.on_log(f"Remote job: {self.remote_job_dir}")
            self._upload_code(ssh)
            self._upload_inputs(ssh)
            self._upload_license(ssh)
            return self.remote_job_dir

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
        local_target = Path(local_target_dir or self.config.output_dir or (PROJECT_ROOT / "outputs")) / f"remote_{self.job_id}"
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
            src = Path(self.config.input_file)
            ssh.upload_file(src, posixpath.join(remote_input, src.name))
        elif self.config.input_mode == "files":
            for idx, path in enumerate(self.config.input_files, start=1):
                src = Path(path)
                remote_name = f"{idx:04d}_{src.name}"
                ssh.upload_file(src, posixpath.join(remote_input, remote_name))
        else:
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
        cmd += ["--device", self.config.device]
        cmd += ["--threads", str(self.config.threads)]
        if self.config.resume:
            cmd.append("--resume")
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
