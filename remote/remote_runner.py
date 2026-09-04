from __future__ import annotations

import os
import hashlib
import json
import posixpath
import shlex
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pipeline_runner import PROJECT_ROOT, _derive_subject_id, build_subject_id_map
from pipeline.docker_ops import license_check_script, license_check_tool
from pipeline.presets import PIPELINE_MODE_ALIASES, PRESET_CONFIGS
from pipeline.registry import is_tool_enabled
from remote.ssh_client import RemoteSSHClient, SSHConfig


LogCallback = Callable[[str], None]

_TERMINAL_REMOTE_JOBS: dict[tuple[str, str], dict[str, object]] = {}


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _parse_gpu_rows(raw: str) -> list[dict[str, object]]:
    """Parse `nvidia-smi --query-gpu=memory.free,memory.total,name` rows.

    Rows are '|'-joined by the probe; missing/malformed rows are skipped so a
    host without nvidia-smi yields [] (treated as "no GPU").
    """
    gpus: list[dict[str, object]] = []
    for row in str(raw or "").split("|"):
        parts = [part.strip() for part in row.split(",")]
        if len(parts) < 2:
            continue
        try:
            free_mib = int(parts[0])
            total_mib = int(parts[1])
        except ValueError:
            continue
        gpus.append(
            {
                "name": parts[2] if len(parts) > 2 else f"gpu_{len(gpus)}",
                "total_memory_mib": total_mib,
                "free_memory_mib": free_mib,
            }
        )
    return gpus


def _neuroflow_source_dir() -> Path | None:
    candidates: list[Path] = []
    for env_name in ("NEUROFLOW_SOURCE_DIR", "NEUROFLOW_PORTABLE_ROOT"):
        value = os.environ.get(env_name, "").strip()
        if not value:
            continue
        root = Path(value).expanduser()
        candidates.append(root if root.name == "NeuroFLOW-private" else root / "NeuroFLOW-private")
    candidates.extend(
        [
            PROJECT_ROOT / "NeuroFLOW-private",
            PROJECT_ROOT.parent / "NeuroFLOW-private",
            PROJECT_ROOT.parent.parent / "NeuroFLOW-private",
        ]
    )
    for candidate in candidates:
        if (candidate / "src" / "neuroflow").is_dir():
            return candidate
    return None


def _manifest_path_key(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


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
    ram_percent: int = 100
    selected_tools: dict[str, str] = field(default_factory=dict)
    export_config: dict = field(default_factory=dict)
    stats_vector_config: dict = field(default_factory=dict)
    recursive: bool = True
    download_subdir: str = ""
    resume: bool = False
    restart: bool = False
    lazy_watch: bool = False
    lazy_upload: bool = False
    input_source: str = "Server"
    input_server_dir: str = ""
    pipeline_mode: str = "Custom"
    neuroflow_enabled: bool = False
    neuroflow_max_concurrent_tasks: int = 2
    neuroflow_max_retries: int = 3
    neuroflow_warmup_enabled: bool = True
    neuroflow_warmup_initial_concurrency: int = 2
    neuroflow_warmup_safe_successes: int = 3
    neuroflow_preserve_oom_bounds: bool = True
    neuroflow_estimation_mode: str = "balanced"
    neuroflow_max_io_heavy_tasks: int = 2
    neuroflow_machine_profile_id: str = "application_default"
    neuroflow_preset_file: str = ""
    neuroflow_profile_file: str = ""


class RemoteRunner:
    def __init__(self, config: RemoteRunConfig, on_log: LogCallback | None = None) -> None:
        self.config = config
        self.on_log = on_log or (lambda _line: None)
        self.job_id = f"job_{time.strftime('%Y%m%d_%H%M%S')}"
        self.remote_job_dir = ""
        self.remote_output_dir = ""
        self._expanded_staging_root = ""
        self._license_staged = False

    def remote_venv_display_path(self) -> str:
        return posixpath.join((self.config.remote_workspace or "~/mri-remote-jobs").rstrip("/"), ".venv")

    def _remote_code_dir(self, ssh: RemoteSSHClient | None = None) -> str:
        if ssh is not None:
            workspace = self._remote_workspace(ssh)
        elif self.remote_job_dir:
            workspace = posixpath.dirname(self.remote_job_dir.rstrip("/"))
        else:
            workspace = (self.config.remote_workspace or "~/mri-remote-jobs").rstrip("/")
        return posixpath.join(workspace, "code")

    def _remote_workspace(self, ssh: RemoteSSHClient) -> str:
        workspace = posixpath.normpath(ssh.expand_path(self.config.remote_workspace or "~/mri-remote-jobs").rstrip("/"))
        if workspace in {"", ".", "/"}:
            raise ValueError(f"Security error: Invalid remote workspace: {self.config.remote_workspace}")
        return workspace

    def _remote_path(self, ssh: RemoteSSHClient, remote_path: str) -> str:
        path = posixpath.normpath(ssh.expand_path(str(remote_path or "").strip()).rstrip("/"))
        if path in {"", ".", "/"}:
            raise ValueError(f"Security error: Invalid remote path: {remote_path}")
        return path

    def _require_workspace_child(self, ssh: RemoteSSHClient, remote_path: str, label: str) -> str:
        workspace = self._remote_workspace(ssh)
        path = self._remote_path(ssh, remote_path)
        if path == workspace:
            raise ValueError(f"Security error: Refusing to use workspace root for {label}: {remote_path}")
        if not path.startswith(workspace + "/"):
            raise ValueError(
                f"Security error: {label} is outside of designated workspace. "
                f"Path: {remote_path}, Workspace: {self.config.remote_workspace}"
            )
        return path

    def _job_child_path(self, ssh: RemoteSSHClient, *parts: str) -> str:
        job_dir = str(self.remote_job_dir or "").strip()
        if job_dir.startswith("remote_"):
            job_dir = job_dir[len("remote_"):]
        if not job_dir.startswith("/") and not job_dir.startswith("~"):
            workspace = self._remote_workspace(ssh)
            job_dir = posixpath.join(workspace, job_dir)
        job_dir = self._require_workspace_child(ssh, job_dir, "remote job directory")
        self.remote_job_dir = job_dir
        return self._require_workspace_child(ssh, posixpath.join(job_dir, *parts), "remote job file")

    def _local_code_signature(self) -> str:
        hasher = hashlib.sha256()
        roots: list[Path] = [PROJECT_ROOT / "pipeline_runner.py", PROJECT_ROOT / "requirements.txt", PROJECT_ROOT / "normalize_volumes.py"]
        for folder, extensions in (
            (PROJECT_ROOT / "pipeline", {".py"}),
            (PROJECT_ROOT / "info", {".txt"}),
        ):
            if folder.exists():
                for root, dirs, files in os.walk(folder):
                    dirs[:] = [d for d in dirs if d != "__pycache__"]
                    for name in sorted(files):
                        path = Path(root) / name
                        if path.suffix in extensions:
                            roots.append(path)
        neuroflow = _neuroflow_source_dir()
        neuroflow_configs = PROJECT_ROOT / "configs" / "neuroflow"
        for folder, extensions in (
            (neuroflow / "src" if neuroflow else Path(), {".py", ".typed"}),
            (neuroflow_configs, {".yaml", ".yml", ".json"}),
        ):
            if folder.exists():
                for root, dirs, files in os.walk(folder):
                    dirs[:] = [d for d in dirs if d not in {"__pycache__", ".pytest_cache"}]
                    for name in sorted(files):
                        path = Path(root) / name
                        if path.suffix in extensions:
                            roots.append(path)
        neuroflow_pyproject = neuroflow / "pyproject.toml" if neuroflow else None
        if neuroflow_pyproject and neuroflow_pyproject.exists():
            roots.append(neuroflow_pyproject)
        for path in sorted((p for p in roots if p.exists()), key=_manifest_path_key):
            rel = _manifest_path_key(path)
            hasher.update(rel.encode("utf-8"))
            hasher.update(path.read_bytes())
        return hasher.hexdigest()

    def test_ssh(self) -> None:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            ssh.run("uname -a && whoami && pwd", check=True)

    def remote_hardware_info(self) -> dict[str, object]:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            code, text = ssh.read_text(
                "printf 'hostname='; hostname; "
                "printf '\\nlogical_cores='; getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || printf 0; "
                "printf '\\nphys_pages='; getconf _PHYS_PAGES 2>/dev/null || printf 0; "
                "printf '\\npage_size='; getconf PAGE_SIZE 2>/dev/null || printf 0; "
                "printf '\\ngpus='; nvidia-smi --query-gpu=memory.free,memory.total,name "
                "--format=csv,noheader,nounits 2>/dev/null | tr '\\n' '|'; printf '\\n';"
            )
            if code != 0:
                return {"hostname": "", "logical_cores": None, "total_ram_bytes": None, "gpus": []}
            values: dict[str, str] = {}
            for line in text.splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip()
            logical_cores = _positive_int(values.get("logical_cores"))
            phys_pages = _positive_int(values.get("phys_pages"))
            page_size = _positive_int(values.get("page_size"))
            total_ram_bytes = phys_pages * page_size if phys_pages and page_size else None
            return {
                "hostname": values.get("hostname", ""),
                "logical_cores": logical_cores,
                "total_ram_bytes": total_ram_bytes,
                "gpus": _parse_gpu_rows(values.get("gpus", "")),
            }

    def check_python_details(self) -> dict[str, str | bool]:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            return self._check_python_details(ssh)

    def _check_python_details(self, ssh: RemoteSSHClient) -> dict[str, str | bool]:
        venv_dir = self._remote_venv_dir(ssh)
        venv_python = self._remote_venv_python(ssh)
        py_cmd = self._python_shell_command(self.config.remote_python, "--version") + " 2>&1"
        py_code, py_text = ssh.read_text(py_cmd)
        venv_code, _venv_text = ssh.read_text(f"test -x {shlex.quote(venv_python)}")
        venv_py_code, venv_py_text = ssh.read_text(
            self._python_shell_command(venv_python, "--version") + " 2>&1"
        ) if venv_code == 0 else (1, "Virtual environment not created")
        pip_code, pip_text = ssh.read_text(
            self._python_shell_command(venv_python, "-m", "pip", "--version") + " 2>&1"
        ) if venv_code == 0 else (1, "pip not available because venv is missing")
        neuroflow_python_ok = True
        neuroflow_dependency_ok = True
        neuroflow_python_text = "Not required"
        neuroflow_dependency_text = "Not required"
        if self.config.neuroflow_enabled:
            base_version = self._remote_python_version(ssh, self.config.remote_python)
            fallback_version = None
            fallback_name = ""
            for candidate in ("python3.12", "python3.11", self._managed_python(ssh), "python3"):
                fallback_version = self._remote_python_version(ssh, candidate)
                if fallback_version is not None and fallback_version >= (3, 11):
                    fallback_name = candidate
                    break
            venv_version = self._remote_python_version(ssh, venv_python) if venv_code == 0 else None
            neuroflow_python_ok = (
                (base_version is not None and base_version >= (3, 11))
                or (fallback_version is not None and fallback_version >= (3, 11))
                or (venv_version is not None and venv_version >= (3, 11))
            )
            sources = []
            if base_version is not None:
                sources.append(f"Remote Python={base_version[0]}.{base_version[1]}")
            if fallback_name and fallback_version is not None:
                sources.append(f"{fallback_name}={fallback_version[0]}.{fallback_version[1]}")
            if venv_version is not None:
                sources.append(f"venv={venv_version[0]}.{venv_version[1]}")
            neuroflow_python_text = ", ".join(sources) or "Python 3.11+ not found; Create / Update Environment can install a managed Python 3.11"
            dep_check = "import yaml, jsonschema"
            dep_code, dep_text = ssh.read_text(
                self._python_shell_command(venv_python, "-c", dep_check) + " 2>&1"
            ) if venv_code == 0 else (1, "Virtual environment not created")
            neuroflow_dependency_ok = dep_code == 0
            neuroflow_dependency_text = "PyYAML/jsonschema OK" if dep_code == 0 else (dep_text.strip() or "PyYAML/jsonschema missing")
        python_text = py_text.strip() or "Python not found"
        venv_python_text = venv_py_text.strip() or "Venv Python not found"
        pip_text = pip_text.strip() or "pip not found"
        self.on_log(("Base Python OK: " if py_code == 0 else "Base Python missing: ") + python_text)
        self.on_log(f"Remote venv: {venv_dir}")
        self.on_log(("Venv Python OK: " if venv_py_code == 0 else "Venv Python missing: ") + venv_python_text)
        self.on_log(("Venv pip OK: " if pip_code == 0 else "Venv pip missing: ") + pip_text)
        if self.config.neuroflow_enabled:
            self.on_log(("NeuroFLOW Python OK: " if neuroflow_python_ok else "NeuroFLOW Python missing: ") + neuroflow_python_text)
            self.on_log(("NeuroFLOW deps OK: " if neuroflow_dependency_ok else "NeuroFLOW deps missing: ") + neuroflow_dependency_text)
        return {
            "python_ok": venv_py_code == 0,
            "pip_ok": pip_code == 0,
            "base_python_ok": py_code == 0,
            "venv_exists": venv_code == 0,
            "venv_python_ok": venv_py_code == 0,
            "venv_pip_ok": pip_code == 0,
            "neuroflow_python_ok": neuroflow_python_ok,
            "neuroflow_dependency_ok": neuroflow_dependency_ok,
            "neuroflow_python_text": neuroflow_python_text,
            "neuroflow_dependency_text": neuroflow_dependency_text,
            "python_text": venv_python_text,
            "base_python_text": python_text,
            "venv_path": venv_dir,
            "pip_text": pip_text,
        }

    def _remote_venv_dir(self, ssh: RemoteSSHClient) -> str:
        workspace = self._remote_workspace(ssh)
        return posixpath.join(workspace, ".venv")

    def _remote_venv_python(self, ssh: RemoteSSHClient) -> str:
        return posixpath.join(self._remote_venv_dir(ssh), "bin", "python")

    def _managed_python_dir(self, ssh: RemoteSSHClient) -> str:
        workspace = self._remote_workspace(ssh)
        return self._require_workspace_child(ssh, posixpath.join(workspace, "python311"), "managed Python")

    def _managed_python(self, ssh: RemoteSSHClient) -> str:
        return posixpath.join(self._managed_python_dir(ssh), "bin", "python")

    def _managed_micromamba_dir(self, ssh: RemoteSSHClient) -> str:
        workspace = self._remote_workspace(ssh)
        return self._require_workspace_child(ssh, posixpath.join(workspace, "micromamba"), "managed micromamba")

    def _python_shell_command(self, python_cmd: str, *args: str) -> str:
        command = " ".join([python_cmd, *(shlex.quote(arg) for arg in args)]).strip()
        return f"bash -lc {shlex.quote(command)}"

    def _remote_python_version(self, ssh: RemoteSSHClient, python_cmd: str) -> tuple[int, int] | None:
        probe = "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        code, text = ssh.read_text(self._python_shell_command(python_cmd, "-c", probe) + " 2>/dev/null")
        if code != 0:
            return None
        try:
            major, minor = text.strip().splitlines()[-1].split(".", 1)
            return int(major), int(minor)
        except (IndexError, ValueError):
            return None

    def _ensure_managed_python311(self, ssh: RemoteSSHClient) -> str:
        python_dir = self._managed_python_dir(ssh)
        python_bin = posixpath.join(python_dir, "bin", "python")
        version = self._remote_python_version(ssh, python_bin)
        if version is not None and version >= (3, 11):
            return python_bin

        micromamba_dir = self._managed_micromamba_dir(ssh)
        micromamba_bin = posixpath.join(micromamba_dir, "bin", "micromamba")
        self.on_log(f"Installing managed Python 3.11 in remote workspace: {python_dir}")
        safe_python_dir = self._require_workspace_child(ssh, python_dir, "managed Python")
        safe_micromamba_dir = self._require_workspace_child(ssh, micromamba_dir, "managed micromamba")
        ssh.run(f"rm -rf {shlex.quote(safe_python_dir)}", stream=True, check=False)
        script = (
            "set -e; "
            f"mkdir -p {shlex.quote(safe_micromamba_dir)}; "
            f"if [ ! -x {shlex.quote(micromamba_bin)} ]; then "
            "command -v curl >/dev/null 2>&1 || { echo 'curl is required to install managed Python 3.11' >&2; exit 10; }; "
            f"curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C {shlex.quote(safe_micromamba_dir)} bin/micromamba; "
            "fi; "
            f"{shlex.quote(micromamba_bin)} create -y -p {shlex.quote(safe_python_dir)} python=3.11 pip; "
            f"{shlex.quote(python_bin)} --version"
        )
        code = ssh.run(f"bash -lc {shlex.quote(script)}", stream=True, check=False)
        if code != 0:
            raise RuntimeError("Could not install managed Python 3.11 in the remote workspace. Ensure the server has internet access, curl, tar, and bzip2 support.")
        version = self._remote_python_version(ssh, python_bin)
        if version is None or version < (3, 11):
            raise RuntimeError("Managed Python 3.11 installation completed but the interpreter could not be verified.")
        return python_bin

    def _neuroflow_base_python(self, ssh: RemoteSSHClient) -> str:
        candidates = [self.config.remote_python, "python3.12", "python3.11", self._managed_python(ssh), "python3"]
        for candidate in dict.fromkeys(candidate for candidate in candidates if candidate):
            version = self._remote_python_version(ssh, candidate)
            if version is not None and version >= (3, 11):
                return candidate
        return self._ensure_managed_python311(ssh)

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
        venv_dir = self._require_workspace_child(ssh, venv_dir, "remote venv")
        ssh.run(f"rm -rf {shlex.quote(venv_dir)}", stream=True, check=False)
        base_python = self._neuroflow_base_python(ssh) if self.config.neuroflow_enabled else self.config.remote_python
        code = ssh.run(self._python_shell_command(base_python, "-m", "venv", venv_dir), stream=True, check=False)
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
        workspace = self._remote_workspace(ssh)
        ssh.mkdir_p(workspace)
        venv_dir = posixpath.join(workspace, ".venv")
        venv_python = posixpath.join(venv_dir, "bin", "python")
        base_python = self._neuroflow_base_python(ssh) if self.config.neuroflow_enabled else self.config.remote_python
        if ssh.run(f"test -x {shlex.quote(venv_python)}", stream=False, check=False) != 0:
            self.on_log(f"Creating remote venv: {venv_dir}")
            code = ssh.run(self._python_shell_command(base_python, "-m", "venv", venv_dir), stream=True, check=False)
            if code != 0:
                raise RuntimeError("Could not create remote venv. Install python3-venv on the server or set a valid base Python.")
        elif self.config.neuroflow_enabled:
            venv_version = self._remote_python_version(ssh, venv_python)
            if venv_version is None or venv_version < (3, 11):
                self.on_log(
                    "Recreating remote venv with Python 3.11+ because NeuroFLOW is enabled."
                )
                safe_venv_dir = self._require_workspace_child(ssh, venv_dir, "remote venv")
                ssh.run(f"rm -rf {shlex.quote(safe_venv_dir)}", stream=True, check=False)
                code = ssh.run(self._python_shell_command(base_python, "-m", "venv", safe_venv_dir), stream=True, check=False)
                if code != 0:
                    raise RuntimeError(
                        "Could not create a Python 3.11+ remote venv for NeuroFLOW. "
                        "Install python3.11-venv on the server or set Remote Python to a valid Python 3.11+ executable."
                    )
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
            if not details["base_python_ok"] and not self.config.neuroflow_enabled:
                self.on_log("Failed: Base Python is not installed or remote_python is invalid. Install Python on the server first.")
                return False
            venv_python = self.ensure_remote_venv(ssh)
            cmd = (
                f"cd {shlex.quote(remote_code)} && "
                f"{shlex.quote(venv_python)} -m pip install --disable-pip-version-check -r requirements.txt"
            )
            self.on_log("Installing packages into remote venv from requirements.txt...")
            code = ssh.run(cmd, stream=True, check=False)
            if code != 0:
                self.on_log("Failed: Python package install in remote venv.")
                return False
            self.on_log("Installed: Python packages into remote venv")
            self._ensure_neuroflow_dependencies(ssh, venv_python, remote_code)
            return True

    def _ensure_neuroflow_dependencies(self, ssh: RemoteSSHClient, venv_python: str, remote_code: str) -> None:
        if not self.config.neuroflow_enabled:
            return
        remote_code = self._require_workspace_child(ssh, remote_code, "remote code directory")
        neuroflow_src = posixpath.join(remote_code, "NeuroFLOW-private", "src")
        neuroflow_project = posixpath.join(remote_code, "NeuroFLOW-private")
        pyproject = posixpath.join(neuroflow_project, "pyproject.toml")

        check_config_deps = "import yaml, jsonschema"
        if ssh.run(f"{shlex.quote(venv_python)} -c {shlex.quote(check_config_deps)} >/dev/null 2>&1", stream=False, check=False) != 0:
            self.on_log("Installing NeuroFLOW configuration dependencies into remote venv...")
            packages = " ".join(shlex.quote(package) for package in ("PyYAML>=6", "jsonschema>=4"))
            code = ssh.run(
                f"{shlex.quote(venv_python)} -m pip install --disable-pip-version-check {packages}",
                stream=True,
                check=False,
            )
            if code != 0:
                raise RuntimeError("Could not install NeuroFLOW dependencies on the remote server.")

        check_neuroflow = "import neuroflow"
        if ssh.run(f"PYTHONPATH={shlex.quote(neuroflow_src)}:$PYTHONPATH {shlex.quote(venv_python)} -c {shlex.quote(check_neuroflow)} >/dev/null 2>&1", stream=False, check=False) == 0:
            return

        if ssh.run(f"test -f {shlex.quote(pyproject)}", stream=False, check=False) == 0:
            self.on_log("Installing NeuroFLOW scheduler package into remote venv...")
            code = ssh.run(
                f"{shlex.quote(venv_python)} -m pip install --disable-pip-version-check -e {shlex.quote(neuroflow_project)}",
                stream=True,
                check=False,
            )
            if code == 0 and ssh.run(f"{shlex.quote(venv_python)} -c {shlex.quote(check_neuroflow)} >/dev/null 2>&1", stream=False, check=False) == 0:
                return

        raise RuntimeError(
            "NeuroFLOW scheduler package is missing on the remote server. "
            "Place NeuroFLOW-private in the portable app folder or set NEUROFLOW_SOURCE_DIR before starting a NeuroFLOW job, "
            "then retry so it can be uploaded to the remote workspace."
        )

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

    def upload_job(self) -> str:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            workspace = self._initialize_remote_job(ssh)
            if self.config.server_output_dir:
                # User-supplied outputs root: create if missing, no containment.
                self.remote_output_dir = self._remote_path(ssh, self.config.server_output_dir)
            else:
                self.remote_output_dir = self._require_workspace_child(ssh, posixpath.join(self.remote_job_dir, "outputs"), "remote output directory")
            ssh.mkdir_p(self.remote_output_dir)
            if self.config.lazy_upload:
                staging_root = self.config.input_server_dir.strip() or posixpath.join("~/mri-uploads", self.job_id)
                self._expanded_staging_root = ssh.expand_path(staging_root)
                ssh.mkdir_p(self._expanded_staging_root)

            self.on_log(f"Remote job: {self.remote_job_dir}")
            self.on_log("Preparing run configuration...")
            self._upload_export_config(ssh)
            self._upload_stats_vector_config(ssh)
            self._upload_subject_id_map(ssh)
            self._upload_neuroflow_configs(ssh)
            self._ensure_shared_code(ssh)
            if self.config.lazy_upload:
                self.on_log("Inputs will be uploaded lazily as the scheduler schedules them.")
            else:
                self.on_log("Using MRI input paths already on the server.")
            if license_check_tool(self.config.selected_tools) is not None and not self._license_staged:
                self.on_log("Uploading license files...")
                self._upload_license(ssh)
            self._write_job_config(ssh)
            self.on_log("Remote upload complete.")
            return self.remote_job_dir

    def stage_freesurfer_license(self) -> None:
        """Stage the local license before any job configuration is uploaded."""
        if license_check_tool(self.config.selected_tools) is None:
            return

        raw_license = self.config.license_dir.strip()
        if not raw_license:
            raise FileNotFoundError("FreeSurfer license file is required for the selected pipeline tools.")
        local_license = Path(raw_license).expanduser()
        if not local_license.exists():
            raise FileNotFoundError(f"License not found locally: {local_license}")

        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            self._initialize_remote_job(ssh)
            self._upload_license(ssh)
            self._license_staged = True

    def _initialize_remote_job(self, ssh: RemoteSSHClient) -> str:
        workspace = self._remote_workspace(ssh)
        self.remote_job_dir = self._require_workspace_child(
            ssh,
            posixpath.join(workspace, self.job_id),
            "remote job directory",
        )
        ssh.mkdir_p(workspace)
        ssh.mkdir_p(self.remote_job_dir)
        ssh.mkdir_p(posixpath.join(self.remote_job_dir, "license"))
        return workspace

    def attach_job(self, remote_job_dir: str, remote_output_dir: str = "") -> None:
        self.remote_job_dir = remote_job_dir.rstrip("/")
        self.remote_output_dir = remote_output_dir or posixpath.join(self.remote_job_dir, "outputs")

    def lazy_source_paths(self) -> dict[str, str]:
        """staging -> local mapping for lazy-upload orchestration (empty unless lazy)."""
        if not self.config.lazy_upload:
            return {}
        request = self._base_remote_input_request()
        rewritten = self._rewrite_inputs_for_lazy_upload(request)
        return dict(rewritten.get("source_paths", {}))

    def check_freesurfer_license(self) -> tuple[bool, str]:
        selected = license_check_tool(self.config.selected_tools)
        if selected is None:
            return True, "No FreeSurfer license is required for the selected tools."
        if not self.remote_job_dir:
            return False, "Remote job directory is not ready for the FreeSurfer license check."

        _tool_key, image = selected
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            license_dir = self._job_child_path(ssh, "license")
            command = (
                f"docker run --rm --entrypoint /bin/bash -v {shlex.quote(license_dir)}:/license:ro "
                f"{shlex.quote(image)} -lc {shlex.quote(license_check_script())}"
            )
            code = ssh.run(command, stream=False, check=False)
        if code == 0:
            return True, "FreeSurfer license check passed."
        return False, "FreeSurfer license check failed on the remote server."

    def read_remote_metadata(self) -> dict:
        if not self.remote_job_dir:
            return {}
        with RemoteSSHClient(self.config.ssh, lambda _line: None) as ssh:
            metadata_path = self._job_child_path(ssh, "job_metadata.json")
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
        with RemoteSSHClient(self.config.ssh, lambda _line: None) as ssh:
            config_path = self._job_child_path(ssh, "job_config.json")
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
        with RemoteSSHClient(self.config.ssh, lambda _line: None) as ssh:
            config_path = self._job_child_path(ssh, "job_config.json")
            ssh.write_text_file(config_path, json.dumps(config, indent=2))

    def _write_job_metadata(self, ssh: RemoteSSHClient) -> None:
        remote_path = self._job_child_path(ssh, "job_metadata.json")
        metadata = {
            "job_id": self.job_id,
            "remote_job_dir": self.remote_job_dir,
            "remote_output_dir": self.remote_output_dir,
            "remote_code_dir": self._remote_code_dir(ssh),
            "created_at": time.time(),
            "input_source": "Local" if self.config.lazy_upload else "Server",
            "input_mode": self.config.input_mode,
            "output_dir": self.config.output_dir,
            "download_subdir": self.config.download_subdir,
        }
        ssh.write_text_file(remote_path, json.dumps(metadata, indent=2))

    def _lazy_staging_path(self, local_path: str, subject_id: str) -> str:
        """Job-scoped staging path: <input_server_dir>/<job_id>/<subject>/<filename>."""
        base = self._expanded_staging_root or posixpath.join("~/mri-uploads", self.job_id)
        return posixpath.join(base, subject_id, Path(local_path).name)

    def _rewrite_inputs_for_lazy_upload(self, request: dict) -> dict:
        """Rewrite input paths to their server staging locations.

        Keeps the original structure (worker-side behavior identical to a
        Server-source run) and adds `source_paths` mapping staging -> local
        plus a `lazy_upload` flag for the client orchestrator.
        """
        rewritten = dict(request)
        source_paths: dict[str, str] = {}
        if rewritten.get("mode") == "file":
            local = str(rewritten.get("input_file", ""))
            staged = self._lazy_staging_path(local, str(rewritten.get("subject_id", "")))
            source_paths[staged] = local
            rewritten["input_file"] = staged
            map_key = local
            if map_key in rewritten.get("subject_id_map", {}):
                rewritten["subject_id_map"][staged] = rewritten["subject_id_map"].pop(map_key)
        else:
            files = [str(path) for path in rewritten.get("input_files", [])]
            staged_files = []
            id_map = dict(rewritten.get("subject_id_map", {}))
            for local in files:
                staged = self._lazy_staging_path(local, id_map.get(local, _derive_subject_id(local)))
                staged_files.append(staged)
                source_paths[staged] = local
                if local in id_map:
                    id_map[staged] = id_map.pop(local)
            rewritten["input_files"] = staged_files
            rewritten["subject_id_map"] = id_map
        rewritten["lazy_upload"] = True
        rewritten["source_paths"] = source_paths
        return rewritten

    def _base_remote_input_request(self) -> dict:
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
        if self.config.input_mode == "dir" and self.config.input_files:
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

    def _remote_input_request(self) -> dict:
        request = self._base_remote_input_request()
        if self.config.lazy_upload:
            request = self._rewrite_inputs_for_lazy_upload(request)
        return request

    def _write_job_config(self, ssh: RemoteSSHClient) -> None:
        remote_path = self._job_child_path(ssh, "job_config.json")
        remote_request = {
            **self._remote_input_request(),
            "job_dir": self.remote_job_dir,
            "run_target": "Server",
            "output_dir": self.remote_output_dir,
            "effective_output_dir": self.remote_output_dir,
            "license_dir": posixpath.join(self.remote_job_dir, "license"),
            "device": self.config.device,
            "threads": int(self.config.threads),
            "ram_percent": int(self.config.ram_percent),
            "selected_tools": self.config.selected_tools,
            "export_config": self.config.export_config or {},
            "stats_vector_config": self.config.stats_vector_config or {},
            "resume": bool(self.config.resume),
            "restart": bool(self.config.restart),
            "pipeline_mode": self.config.pipeline_mode,
            "neuroflow_enabled": bool(self.config.neuroflow_enabled),
            "neuroflow_max_concurrent_tasks": int(self.config.neuroflow_max_concurrent_tasks),
            "neuroflow_max_retries": int(self.config.neuroflow_max_retries),
            "neuroflow_warmup_enabled": bool(self.config.neuroflow_warmup_enabled),
            "neuroflow_warmup_initial_concurrency": int(self.config.neuroflow_warmup_initial_concurrency),
            "neuroflow_warmup_safe_successes": int(self.config.neuroflow_warmup_safe_successes),
            "neuroflow_preserve_oom_bounds": bool(self.config.neuroflow_preserve_oom_bounds),
            "neuroflow_estimation_mode": str(self.config.neuroflow_estimation_mode),
            "neuroflow_max_io_heavy_tasks": int(self.config.neuroflow_max_io_heavy_tasks),
            "neuroflow_machine_profile_id": self.config.neuroflow_machine_profile_id,
            "neuroflow_preset_file": self._job_child_path(ssh, "neuroflow_preset.yaml") if self.config.neuroflow_preset_file else "",
            "neuroflow_profile_file": self._job_child_path(ssh, "neuroflow_profile.yaml") if self.config.neuroflow_profile_file else "",
        }
        ssh.write_text_file(remote_path, json.dumps(remote_request, indent=2))

    def _upload_export_config(self, ssh: RemoteSSHClient) -> None:
        remote_path = self._job_child_path(ssh, "export_config.json")
        ssh.write_text_file(remote_path, json.dumps(self.config.export_config or {}, indent=2))

    def _upload_stats_vector_config(self, ssh: RemoteSSHClient) -> None:
        remote_path = self._job_child_path(ssh, "stats_vector_config.json")
        ssh.write_text_file(remote_path, json.dumps(self.config.stats_vector_config or {}, indent=2))

    def _upload_neuroflow_configs(self, ssh: RemoteSSHClient) -> None:
        if not self.config.neuroflow_enabled:
            return

        for field_name, remote_name in (
            ("neuroflow_preset_file", "neuroflow_preset.yaml"),
            ("neuroflow_profile_file", "neuroflow_profile.yaml"),
        ):
            raw_path = str(getattr(self.config, field_name, "") or "").strip()
            if not raw_path:
                continue
            local_path = Path(raw_path).expanduser()
            if not local_path.is_file():
                raise FileNotFoundError(f"NeuroFLOW configuration not found locally: {local_path}")
            self.on_log(f"Uploading NeuroFLOW {field_name.removeprefix('neuroflow_').removesuffix('_file')} configuration: {local_path.name}")
            ssh.upload_file(local_path, self._job_child_path(ssh, remote_name))

    def _upload_subject_id_map(self, ssh: RemoteSSHClient) -> None:
        mapping = self._remote_input_request().get("subject_id_map", {})
        remote_path = self._job_child_path(ssh, "subject_ids.json")
        ssh.write_text_file(remote_path, json.dumps(mapping, indent=2))

    def start_remote_detached(self) -> str:
        if not self.remote_job_dir:
            self.upload_job()
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            self.remote_job_dir = self._require_workspace_child(ssh, self.remote_job_dir, "remote job directory")
            if self.remote_output_dir:
                self.remote_output_dir = self._require_workspace_child(ssh, self.remote_output_dir, "remote output directory")
            if self.config.input_file or self.config.input_files or self.config.input_dir:
                self._write_job_config(ssh)
            remote_code = self._remote_code_dir(ssh)
            self._ensure_shared_code(ssh)
            venv_python = self.ensure_remote_venv(ssh)
            self._ensure_neuroflow_dependencies(ssh, venv_python, remote_code)
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
                f"cd {shlex.quote(remote_code)} && PYTHONPATH={shlex.quote(remote_code)}:"
                f"{shlex.quote(posixpath.join(remote_code, 'NeuroFLOW-private', 'src'))}:$PYTHONPATH PYTHONUNBUFFERED=1 "
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

    def remote_status(self) -> dict[str, str | int | float | bool | None]:
        if not self.remote_job_dir:
            return {"state": "not_started"}
        with RemoteSSHClient(self.config.ssh, lambda _line: None) as ssh:
            exit_path = self._job_child_path(ssh, "exit_code.txt")
            pid_path = self._job_child_path(ssh, "pid.txt")
            status_path = self._job_child_path(ssh, "job_status.json")
            stop_path = self._job_child_path(ssh, "stop_requested")
            exit_code, exit_text = ssh.read_text(f"cat {shlex.quote(exit_path)} 2>/dev/null")
            pid_code, pid_text = ssh.read_text(f"cat {shlex.quote(pid_path)} 2>/dev/null")
            status_code, status_text = ssh.read_text(f"cat {shlex.quote(status_path)} 2>/dev/null")
            stop_code, _ = ssh.read_text(f"test -f {shlex.quote(stop_path)} && echo 1")
            has_stop_requested = (stop_code == 0)
            status_data: dict = {}
            if status_code == 0 and status_text.strip():
                try:
                    parsed = json.loads(status_text)
                    status_data = parsed if isinstance(parsed, dict) else {}
                except json.JSONDecodeError:
                    status_data = {}
            pid = pid_text.strip()
            base_status = {
                "pid": pid or status_data.get("pid"),
                "remote_job_dir": self.remote_job_dir,
                "started_at": status_data.get("started_at"),
                "finished_at": status_data.get("finished_at"),
                "duration_sec": status_data.get("duration_sec"),
                "error": status_data.get("error"),
            }
            if exit_code == 0 and exit_text.strip() != "":
                code = int(exit_text.strip().splitlines()[-1])
                is_stopped = has_stop_requested or status_data.get("state") == "stopped"
                return {**base_status, "state": "stopped" if is_stopped else ("completed" if code == 0 else "failed"), "exit_code": code}
            if pid_code == 0 and pid:
                ps_code = ssh.run(f"kill -0 {shlex.quote(pid)} >/dev/null 2>&1", stream=False, check=False)
                if ps_code == 0:
                    return {**base_status, "state": "running", "pid": pid}
                is_stopped = has_stop_requested or status_data.get("state") == "stopped"
                return {**base_status, "state": "stopped" if is_stopped else "failed", "exit_code": None, "pid": pid, "error": "process exited before writing exit_code.txt"}
            state = str(status_data.get("state") or ("stopped" if has_stop_requested else "uploaded"))
            return {**base_status, "state": state}

    def list_background_jobs(self) -> list[dict[str, object]]:
        host_key = self.config.ssh.host
        with RemoteSSHClient(self.config.ssh, lambda _line: None) as ssh:
            workspace = self._remote_workspace(ssh)
            script = "\n".join(
                [
                    "import glob, json, os, re",
                    f"ws = {json.dumps(workspace)}",
                    "jobs = []",
                    "for d in sorted(glob.glob(os.path.join(ws, 'job_*')), reverse=True):",
                    "    if not os.path.isdir(d):",
                    "        continue",
                    "    cfg, meta, st = {}, {}, {}",
                    "    for fn, var in (('job_config.json', cfg), ('job_metadata.json', meta), ('job_status.json', st)):",
                    "        try:",
                    "            with open(os.path.join(d, fn), 'r', encoding='utf-8') as f:",
                    "                var.update(json.load(f))",
                    "        except Exception:",
                    "            pass",
                    "    pid = ''",
                    "    exit_code = None",
                    "    try:",
                    "        with open(os.path.join(d, 'pid.txt'), 'r', encoding='utf-8') as f:",
                    "            pid = f.read().strip()",
                    "    except Exception:",
                    "        pass",
                    "    try:",
                    "        with open(os.path.join(d, 'exit_code.txt'), 'r', encoding='utf-8') as f:",
                    "            exit_code = int(f.read().strip())",
                    "    except Exception:",
                    "        pass",
                    "    if not cfg:",
                    "        continue",
                    "    has_stop_requested = os.path.exists(os.path.join(d, 'stop_requested'))",
                    "    state = 'uploaded'",
                    "    if exit_code is not None:",
                    "        if has_stop_requested or st.get('state') == 'stopped':",
                    "            state = 'stopped'",
                    "        else:",
                    "            state = 'completed' if exit_code == 0 else 'failed'",
                    "    elif pid:",
                    "        try:",
                    "            os.kill(int(pid), 0)",
                    "            state = 'running'",
                    "        except Exception:",
                    "            state = 'stopped' if (has_stop_requested or st.get('state') == 'stopped') else 'failed'",
                    "    elif st.get('state'):",
                    "        state = str(st.get('state'))",
                    "    elif has_stop_requested:",
                    "        state = 'stopped'",
                    "    tools = cfg.get('selected_tools') or {}",
                    "    scheduled_tools = [t for t in tools.values() if t and str(t).lower() not in ('none', 'null', 'disabled', '')]",
                    "    has_scheduled = len(scheduled_tools) > 0",
                    "    batch_summary = None",
                    "    sum_file = os.path.join(d, 'job_summary.json')",
                    "    if os.path.exists(sum_file):",
                    "        try:",
                    "            with open(sum_file, 'r', encoding='utf-8') as sf:",
                    "                s_data = json.load(sf)",
                    "                if isinstance(s_data, dict) and 'total' in s_data:",
                    "                    batch_summary = {",
                    "                        'total': int(s_data.get('total', 0)),",
                    "                        'success': int(s_data.get('success', 0)),",
                    "                        'failed': int(s_data.get('failed', 0)),",
                    "                        'running': int(s_data.get('running', 0)),",
                    "                        'pending': int(s_data.get('pending', 0)),",
                    "                    }",
                    "                    if 'stopped' in s_data or int(s_data.get('stopped', 0)) > 0 or state == 'stopped':",
                    "                        batch_summary['stopped'] = int(s_data.get('stopped', 0))",
                    "                        batch_summary['interrupted'] = int(s_data.get('stopped', 0))",
                    "        except Exception:",
                    "            pass",
                    "    if batch_summary is None:",
                    "        image_states, event_total = {}, 0",
                    "        try:",
                    "            with open(os.path.join(d, 'events.jsonl'), 'r', encoding='utf-8') as f:",
                    "                for _line_no, line in enumerate(f):",
                    "                    if _line_no >= 50000:",
                    "                        break",
                    "                    try:",
                    "                        event = json.loads(line)",
                    "                    except Exception:",
                    "                        continue",
                    "                    kind = str(event.get('kind', ''))",
                    "                    if kind not in ('image_start', 'image_done'):",
                    "                        continue",
                    "                    try: event_total = max(event_total, int(event.get('total') or 0))",
                    "                    except (TypeError, ValueError): pass",
                    "                    input_file = str(event.get('input_file') or '')",
                    "                    if input_file:",
                    "                        ev_status = str(event.get('status') or '').lower()",
                    "                        log_text = str(event.get('log_text') or '')",
                    "                        if ev_status == 'stopped':",
                    "                            image_states[input_file] = 'stopped'",
                    "                        elif kind == 'image_start':",
                    "                            image_states[input_file] = 'running'",
                    "                        elif kind == 'image_done':",
                    "                            is_ok = bool(event.get('success'))",
                    "                            if is_ok and log_text and has_scheduled:",
                    "                                ok_lines = [l for l in log_text.splitlines() if ('- OK' in l or '- SUCCESS' in l)]",
                    "                                if len(ok_lines) < len(scheduled_tools):",
                    "                                    is_ok = False",
                    "                            if is_ok:",
                    "                                image_states[input_file] = 'success'",
                    "                            elif state == 'stopped' or ev_status == 'stopped':",
                    "                                image_states[input_file] = 'stopped'",
                    "                            else:",
                    "                                image_states[input_file] = 'failed'",
                    "        except Exception:",
                    "            pass",
                    "        input_files = cfg.get('input_files') or ([cfg.get('input_file')] if cfg.get('input_file') else [])",
                    "        total = max(len(input_files), event_total, len(image_states), 1 if state != 'uploaded' else 0)",
                    "        if state == 'completed':",
                    "            for k in list(image_states.keys()):",
                    "                if image_states[k] != 'failed':",
                    "                    image_states[k] = 'success'",
                    "        elif state == 'stopped':",
                    "            for k, v in list(image_states.items()):",
                    "                if v != 'success':",
                    "                    image_states[k] = 'stopped'",
                    "        success = sum(value == 'success' for value in image_states.values())",
                    "        failed = sum(value == 'failed' for value in image_states.values())",
                    "        running = sum(value == 'running' for value in image_states.values()) if state == 'running' else 0",
                    "        stopped = sum(value == 'stopped' for value in image_states.values()) + (max(0, total - len(image_states)) if state == 'stopped' else 0)",
                    "        if state == 'completed' and success == 0 and failed == 0 and stopped == 0:",
                    "            success = total",
                    "        if state == 'stopped' and stopped == 0 and success == 0 and failed == 0:",
                    "            stopped = total",
                    "        pending = max(0, total - success - failed - running - stopped)",
                    "        batch_summary = {'total': total, 'success': success, 'failed': failed, 'running': running, 'pending': pending}",
                    "        if stopped > 0 or state == 'stopped':",
                    "            batch_summary['stopped'] = stopped",
                    "            batch_summary['interrupted'] = stopped",
                    "        if exit_code is not None or state in ('completed', 'failed', 'stopped'):",
                    "            try:",
                    "                with open(sum_file + '.tmp', 'w', encoding='utf-8') as sf:",
                    "                    json.dump(batch_summary, sf)",
                    "                os.replace(sum_file + '.tmp', sum_file)",
                    "            except Exception:",
                    "                pass",
                    "    input_files = cfg.get('input_files') or ([cfg.get('input_file')] if cfg.get('input_file') else [])",
                    "    folder = os.path.basename(d)",
                    "    meta_job_id = str(meta.get('job_id') or '')",
                    "    job_id = meta_job_id if meta_job_id.startswith('remote_') else 'remote_' + folder",
                    "    jobs.append({",
                    "        'job_id': job_id,",
                    "        'remote_job_dir': d,",
                    "        'state': state,",
                    "        'pid': pid,",
                    "        'exit_code': exit_code,",
                    "        'started_at': st.get('started_at') or meta.get('created_at') or 0,",
                    "        'finished_at': st.get('finished_at'),",
                    "        'output_dir': cfg.get('output_dir') or meta.get('output_dir') or '',",
                    "        'effective_output_dir': cfg.get('effective_output_dir') or cfg.get('output_dir') or meta.get('output_dir') or '',",
                    "        'download_subdir': meta.get('download_subdir') or '',",
                    "        'input_files': input_files,",
                    "        'batch_summary': batch_summary,",
                    "        'run_request_summary': cfg,",
                    "    })",
                    "print(json.dumps(jobs))",
                ]
            )
            code, text = ssh.read_text(f"python3 -c {shlex.quote(script)} 2>/dev/null")
            if code == 0 and text.strip():
                try:
                    parsed = json.loads(text.strip().splitlines()[-1])
                    if isinstance(parsed, list):
                        result_jobs: list[dict[str, object]] = []
                        for j in parsed:
                            j_id = str(j.get("job_id", ""))
                            state = str(j.get("state", ""))
                            if state in {"completed", "failed", "stopped"}:
                                _TERMINAL_REMOTE_JOBS[(host_key, j_id)] = j
                            result_jobs.append(j)
                        return result_jobs
                except Exception:
                    pass

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
        jobs: list[dict[str, object]] = []
        for line in text.splitlines():
            parts = line.split("\t", 2)
            if len(parts) != 3:
                continue
            state, pid, remote_job_dir = parts
            j_id = f"remote_{posixpath.basename(remote_job_dir)}"
            job_dict = {
                "job_id": j_id,
                "state": state,
                "pid": pid,
                "remote_job_dir": remote_job_dir,
            }
            if state in {"completed", "failed", "stopped"}:
                _TERMINAL_REMOTE_JOBS[(host_key, j_id)] = job_dict
            jobs.append(job_dict)
        return jobs

    def read_remote_events(self, offset: int = 0, limit: int = 0) -> dict[str, object]:
        if not self.remote_job_dir:
            return {"ok": True, "events": [], "warnings": [], "next_offset": offset, "events_file_found": False}
        # Unbounded reads (limit<=0) transfer the whole file on every Jobs
        # monitor open; cap so initial loads stay fast. Delta polls use a
        # near-EOF offset and are unaffected.
        max_events = limit if limit > 0 else 10000
        max_events = max(1, min(int(max_events), 10000))
        with RemoteSSHClient(self.config.ssh, lambda _line: None) as ssh:
            # 1. Fast server-side python execution
            try:
                events_path = self._job_child_path(ssh, "events.jsonl")
                script = "\n".join([
                    "import json, os, sys",
                    f"path = {json.dumps(events_path)}",
                    f"offset = {int(offset)}",
                    f"limit = {int(max_events)}",
                    "if not os.path.exists(path):",
                    "    print(json.dumps({'ok': True, 'events': [], 'warnings': [], 'next_offset': offset, 'events_file_found': False}))",
                    "    sys.exit(0)",
                    "lifecycle = []",
                    "next_offset = offset",
                    "with open(path, 'r', encoding='utf-8', errors='replace') as f:",
                    "    f.seek(offset)",
                    "    while True:",
                    "        line = f.readline()",
                    "        if not line:",
                    "            break",
                    "        next_offset = f.tell()",
                    "        line = line.strip()",
                    "        if not line:",
                    "            continue",
                    "        try:",
                    "            ev = json.loads(line)",
                    "        except Exception:",
                    "            continue",
                    "        if ev.get('kind') == 'metrics':",
                    "            continue",
                    "        lifecycle.append(ev)",
                    "        if limit > 0 and len(lifecycle) >= limit:",
                    "            break",
                    "print(json.dumps({'ok': True, 'events': lifecycle, 'warnings': [], 'next_offset': next_offset, 'events_file_found': True}))",
                ])
                code, out = ssh.read_text(f"python3 -c {shlex.quote(script)} 2>/dev/null")
                if code == 0 and out.strip():
                    try:
                        res = json.loads(out.strip().splitlines()[-1])
                        if isinstance(res, dict) and "ok" in res:
                            return res
                    except Exception:
                        pass
            except Exception:
                pass

            # 2. SFTP fallback for legacy environments or test mocks
            try:
                events_path = self._job_child_path(ssh, "events.jsonl")
                with ssh.sftp.open(events_path, "r") as f:
                    f.seek(offset)
                    events: list[object] = []
                    next_offset = offset
                    for line in f:
                        next_offset = f.tell()
                        line_str = line.decode("utf-8", errors="replace").strip() if isinstance(line, bytes) else str(line).strip()
                        if line_str:
                            try:
                                ev = json.loads(line_str)
                                if ev.get("kind") != "metrics":
                                    events.append(ev)
                            except Exception:
                                pass
                        if len(events) >= max_events:
                            break
                    return {"ok": True, "events": events, "warnings": [], "next_offset": next_offset, "events_file_found": True}
            except (FileNotFoundError, OSError):
                return {"ok": True, "events": [], "warnings": [], "next_offset": offset, "events_file_found": False}
            except Exception as exc:
                return {"ok": False, "error": str(exc), "events": [], "warnings": [], "next_offset": offset}

    def read_remote_metrics(
        self,
        offset: int = 0,
        limit: int = 0,
        subject_id: str = "",
        input_file: str = "",
    ) -> dict[str, object]:
        if not self.remote_job_dir:
            return {"ok": True, "events": [], "warnings": [], "next_offset": offset, "source": None}
        max_events = limit if limit > 0 else 2000
        max_events = max(1, min(int(max_events), 5000))
        subject_id = str(subject_id or "").strip()
        input_file = str(input_file or "").strip()
        with RemoteSSHClient(self.config.ssh, lambda _line: None) as ssh:
            # 1. Fast server-side python extraction. metrics.jsonl (new jobs)
            # is preferred; events.jsonl (old jobs) is only a fallback. The
            # first existing file wins and the loop MUST break, otherwise the
            # second file resets `events` and discards metrics.jsonl results.
            try:
                # Resolve through the validated workspace child path so the
                # embedded job_dir is absolute and containment-checked, exactly
                # like read_remote_events does (raw remote_job_dir may be
                # relative or use ~).
                job_dir = posixpath.dirname(self._job_child_path(ssh, "events.jsonl"))
                script = "\n".join([
                    "import json, os, sys",
                    f"job_dir = {json.dumps(job_dir)}",
                    f"offset = {int(offset)}",
                    f"limit = {int(max_events)}",
                    f"subject_id = {json.dumps(subject_id)}",
                    f"input_file = {json.dumps(input_file)}",
                    "source = None",
                    "events = []",
                    "next_offset = offset",
                    "for fname in ('metrics.jsonl', 'events.jsonl'):",
                    "    fpath = os.path.join(job_dir, fname)",
                    "    if not os.path.exists(fpath):",
                    "        continue",
                    "    source = fname",
                    "    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:",
                    "        try:",
                    "            f.seek(offset)",
                    "        except Exception:",
                    "            pass",
                    "        while True:",
                    "            line = f.readline()",
                    "            if not line:",
                    "                break",
                    "            next_offset = f.tell()",
                    "            line = line.strip()",
                    "            if not line:",
                    "                continue",
                    "            try:",
                    "                ev = json.loads(line)",
                    "                if fname != 'metrics.jsonl' and ev.get('kind') != 'metrics':",
                    "                    continue",
                    "                if (subject_id or input_file) and not (",
                    "                    (subject_id and str(ev.get('subject_id') or '') == subject_id) or",
                    "                    (input_file and str(ev.get('input_file') or '') == input_file)",
                    "                ):",
                    "                    continue",
                    "                events.append(ev)",
                    "            except Exception:",
                    "                continue",
                    "            if len(events) >= limit:",
                    "                break",
                    "    break",
                    "print(json.dumps({'ok': True, 'events': events, 'warnings': [], 'next_offset': next_offset, 'source': source}))",
                ])
                code, out = ssh.read_text(f"python3 -c {shlex.quote(script)} 2>/dev/null")
                if code == 0 and out.strip():
                    try:
                        res = json.loads(out.strip().splitlines()[-1])
                        if isinstance(res, dict) and "ok" in res:
                            return res
                    except Exception:
                        pass
            except Exception:
                pass

            # 2. SFTP fallback (already prefers metrics.jsonl via early return)
            for fname in ("metrics.jsonl", "events.jsonl"):
                try:
                    fpath = self._job_child_path(ssh, fname)
                    with ssh.sftp.open(fpath, "r") as f:
                        f.seek(offset)
                        events: list[object] = []
                        next_offset = offset
                        for line in f:
                            next_offset = f.tell()
                            line_str = line.decode("utf-8", errors="replace").strip() if isinstance(line, bytes) else str(line).strip()
                            if line_str:
                                try:
                                    ev = json.loads(line_str)
                                    if fname != "metrics.jsonl" and ev.get("kind") != "metrics":
                                        continue
                                    if (subject_id or input_file) and not (
                                        (subject_id and str(ev.get("subject_id") or "") == subject_id)
                                        or (input_file and str(ev.get("input_file") or "") == input_file)
                                    ):
                                        continue
                                    events.append(ev)
                                except Exception:
                                    pass
                            if len(events) >= max_events:
                                break
                        return {"ok": True, "events": events, "warnings": [], "next_offset": next_offset, "source": fname}
                except (FileNotFoundError, OSError):
                    continue
                except Exception as exc:
                    return {"ok": False, "error": str(exc), "events": [], "warnings": [], "next_offset": offset, "source": None}
            return {"ok": True, "events": [], "warnings": [], "next_offset": offset, "source": None}

    def read_remote_log_since(self, offset: int = 0, max_bytes: int = 65536) -> tuple[str, int]:
        if not self.remote_job_dir:
            return "", offset
        byte_limit = max(1, min(int(max_bytes), 1_000_000))
        with RemoteSSHClient(self.config.ssh, lambda _line: None) as ssh:
            remote_log = self._job_child_path(ssh, "run.log")
            launcher_log = self._job_child_path(ssh, "launcher.log")
            fallback_offset = offset
            for path in (remote_log, launcher_log):
                try:
                    with ssh.sftp.open(path, "r") as f:
                        f.seek(offset)
                        data = f.read(byte_limit)
                        fallback_offset = f.tell()
                        if data:
                            text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else str(data)
                            return text, fallback_offset
                except OSError:
                    continue
            return "", fallback_offset

    def request_pause(self) -> None:
        if not self.remote_job_dir:
            raise RuntimeError("No remote job is running")
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            self.remote_job_dir = self._require_workspace_child(ssh, self.remote_job_dir, "remote job directory")
            stop_file = self._job_child_path(ssh, "stop_requested")
            ssh.run(
                f"mkdir -p {shlex.quote(self.remote_job_dir)} && touch {shlex.quote(stop_file)}",
                stream=False,
                check=False,
                timeout=self.config.ssh.timeout,
            )
            self.on_log(f"Remote pause requested via stop file: {stop_file}")

    def download_outputs(self, local_target_dir: str | Path | None = None) -> Path:
        if not self.remote_job_dir:
            raise RuntimeError("No remote job has been run or attached yet")
        local_target = Path(local_target_dir or self.config.output_dir or (PROJECT_ROOT / "outputs"))
        if self.config.download_subdir:
            local_target = local_target / self.config.download_subdir
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            remote_outputs = self._require_workspace_child(ssh, self.remote_output_dir or posixpath.join(self.remote_job_dir, "outputs"), "remote output directory")
            ssh.download_dir(remote_outputs, local_target)
            self._download_job_artifacts(ssh, local_target)
        return local_target

    def count_download_files(self) -> int:
        if not self.remote_job_dir:
            raise RuntimeError("No remote job has been run or attached yet")
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            remote_outputs = self._require_workspace_child(ssh, self.remote_output_dir or posixpath.join(self.remote_job_dir, "outputs"), "remote output directory")
            return self._count_remote_files(ssh, remote_outputs) + self._count_job_artifacts(ssh)

    def _count_remote_files(self, ssh: RemoteSSHClient, remote_dir: str) -> int:
        total = 0
        for item in ssh.sftp.listdir_attr(remote_dir):
            remote_path = posixpath.join(remote_dir, item.filename)
            if stat.S_ISLNK(item.st_mode):
                continue
            if stat.S_ISDIR(item.st_mode):
                total += self._count_remote_files(ssh, remote_path)
            else:
                total += 1
        return total

    def _count_job_artifacts(self, ssh: RemoteSSHClient) -> int:
        total = 0
        for name in self._job_artifact_names():
            remote_file = self._job_child_path(ssh, name)
            try:
                ssh.sftp.stat(remote_file)
                total += 1
            except OSError:
                pass
        return total

    def _download_job_artifacts(self, ssh: RemoteSSHClient, local_target: Path) -> None:
        for name in self._job_artifact_names():
            remote_file = self._job_child_path(ssh, name)
            ssh.download_file_if_exists(remote_file, local_target / name)

    def _job_artifact_names(self) -> tuple[str, ...]:
        return (
            "neuroflow_observations.tsv",
            "neuroflow_observations.jsonl",
            "neuroflow_workspace.sqlite",
            "job_config.json",
            "job_metadata.json",
            "job_status.json",
            "events.jsonl",
            "run.log",
            "launcher.log",
            "exit_code.txt",
            "finished_at.txt",
        )

    def clean_remote(self) -> None:
        if not self.remote_job_dir:
            return

        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            self.remote_job_dir = self._require_workspace_child(ssh, self.remote_job_dir, "remote job directory")
            code = ssh.run(f"rm -rf {shlex.quote(self.remote_job_dir)}", check=False)
            if code != 0:
                raise RuntimeError(f"Could not delete remote job folder: {self.remote_job_dir}")

    def sync_code(self) -> str:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            return self._ensure_shared_code(ssh)

    def sync_venv(self) -> str:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            remote_code = self._remote_code_dir(ssh)
            venv_python = self.ensure_remote_venv(ssh)
            self._ensure_neuroflow_dependencies(ssh, venv_python, remote_code)
            return venv_python

    def _ensure_shared_code(self, ssh: RemoteSSHClient) -> str:
        remote_code = self._require_workspace_child(ssh, self._remote_code_dir(ssh), "remote code directory")
        signature = self._local_code_signature()
        manifest_path = posixpath.join(remote_code, "code_manifest.json")
        ready_cmd = (
            f"test -f {shlex.quote(posixpath.join(remote_code, 'pipeline_runner.py'))} && "
            f"test -f {shlex.quote(posixpath.join(remote_code, 'pipeline', 'job_worker.py'))} && "
            f"cat {shlex.quote(manifest_path)} 2>/dev/null"
        )
        ready_code, ready_text = ssh.read_text(ready_cmd)
        if ready_code == 0 and ready_text.strip():
            try:
                manifest_data = json.loads(ready_text)
                if manifest_data.get("signature") == signature:
                    self.on_log(f"Using shared remote pipeline code: {remote_code}")
                    return remote_code
            except (json.JSONDecodeError, ValueError):
                pass

        self.on_log(f"Uploading shared pipeline code once: {remote_code}")
        self._upload_code(ssh, remote_code)
        ssh.write_text_file(manifest_path, json.dumps({"signature": signature, "updated_at": time.time()}, indent=2))
        return remote_code

    def _upload_code(self, ssh: RemoteSSHClient, remote_code: str) -> None:
        remote_code = self._require_workspace_child(ssh, remote_code, "remote code directory")
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
        mni_atlas_dir = PROJECT_ROOT / "assets" / "atlases" / "mni"
        if mni_atlas_dir.exists():
            ssh.upload_dir(
                mni_atlas_dir,
                posixpath.join(remote_code, "assets", "atlases", "mni"),
                skip_dirs={"__pycache__"},
                allowed_extensions={".nii.gz", ".txt", ".csv", ".md"},
                skip_existing_matching_size=True,
            )
        surface_atlas_dir = PROJECT_ROOT / "assets" / "atlases" / "surface"
        if surface_atlas_dir.exists():
            ssh.upload_dir(
                surface_atlas_dir,
                posixpath.join(remote_code, "assets", "atlases", "surface"),
                skip_dirs={"__pycache__"},
                allowed_extensions={".gcs", ".annot"},
                skip_existing_matching_size=True,
            )
        neuroflow = _neuroflow_source_dir()
        if neuroflow and neuroflow.exists():
            remote_neuroflow = posixpath.join(remote_code, "NeuroFLOW-private")
            pyproject = neuroflow / "pyproject.toml"
            if pyproject.exists():
                ssh.upload_file(pyproject, posixpath.join(remote_neuroflow, "pyproject.toml"))
            src_dir = neuroflow / "src"
            if src_dir.exists():
                ssh.upload_dir(
                    src_dir,
                    posixpath.join(remote_neuroflow, "src"),
                    skip_dirs={"__pycache__", ".pytest_cache"},
                    allowed_extensions={".py", ".typed"},
                )
        neuroflow_configs = PROJECT_ROOT / "configs" / "neuroflow"
        if neuroflow_configs.exists():
            ssh.upload_dir(
                neuroflow_configs,
                posixpath.join(remote_code, "configs", "neuroflow"),
                skip_dirs={"__pycache__", ".pytest_cache"},
                allowed_extensions={".yaml", ".yml", ".json"},
            )

    def _upload_license(self, ssh: RemoteSSHClient) -> None:
        if not self.config.license_dir:
            return
        local_license = Path(self.config.license_dir).expanduser()
        if not local_license.exists():
            raise FileNotFoundError(f"License not found locally: {local_license}")
            
        remote_license_dir = posixpath.join(self.remote_job_dir, "license")
        remote_license_dir = self._require_workspace_child(ssh, remote_license_dir, "remote license directory")
        if local_license.is_file():
            self.on_log(f"Uploading license file: {local_license.name}")
            ssh.upload_file(local_license, posixpath.join(remote_license_dir, "license.txt"))
        else:
            self.on_log("Uploading license directory...")
            ssh.upload_dir(local_license, remote_license_dir, skip_dirs={"__pycache__"})

    @staticmethod
    def image_pull_key(image: str) -> str:
        return hashlib.sha256(image.encode("utf-8")).hexdigest()

    @staticmethod
    def remote_pull_paths(image: str) -> dict[str, str]:
        key = RemoteRunner.image_pull_key(image)
        base = f"/tmp/neuroflow-image-pulls/{key}"
        return {"json": f"{base}.json", "log": f"{base}.log", "sh": f"{base}.sh"}

    def check_image_states(self, images: list[str]) -> dict[str, dict[str, object]]:
        states: dict[str, dict[str, object]] = {}
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            for image in dict.fromkeys(images):
                states[image] = self._check_single_image_state(ssh, image)
        return states

    def _check_single_image_state(self, ssh: RemoteSSHClient, image: str) -> dict[str, object]:
        code = ssh.run(f"docker image inspect {shlex.quote(image)} >/dev/null 2>&1", stream=False)
        if code == 0:
            return {"status": "Installed", "pull_status": None}

        paths = self.remote_pull_paths(image)
        json_code, json_text = ssh.read_text(f"cat {shlex.quote(paths['json'])} 2>/dev/null")
        if json_code != 0 or not json_text.strip():
            return {"status": "Missing", "pull_status": None}

        try:
            track = json.loads(json_text.strip())
        except (json.JSONDecodeError, ValueError):
            return {"status": "Missing", "pull_status": None}

        pull_status = str(track.get("status", "")).lower()
        pid = str(track.get("pid", "")).strip()

        if pull_status == "pulling" and pid:
            alive = ssh.run(f"kill -0 {shlex.quote(pid)} >/dev/null 2>&1", stream=False, check=False)
            if alive == 0:
                marker = f"neuroflow-image-pull-{self.image_pull_key(image)}"
                ps_code, ps_text = ssh.read_text(f"ps -p {shlex.quote(pid)} -o args= 2>/dev/null")
                if ps_code == 0 and marker in ps_text:
                    return {
                        "status": "Downloading",
                        "pull_status": "pulling",
                        "pull_pid": track.get("pid"),
                        "pull_started_at": track.get("started_at"),
                        "pull_updated_at": track.get("updated_at"),
                        "pull_error": None,
                    }

        if pull_status == "success":
            return {"status": "Missing", "pull_status": None}

        return {
            "status": "Missing",
            "pull_status": pull_status if pull_status in {"failed", "stale"} else None,
            "pull_pid": track.get("pid"),
            "pull_started_at": track.get("started_at"),
            "pull_updated_at": track.get("updated_at"),
            "pull_error": track.get("error"),
        }

    def start_remote_image_pull(self, image: str) -> dict[str, object]:
        with RemoteSSHClient(self.config.ssh, self.on_log) as ssh:
            code = ssh.run(f"docker image inspect {shlex.quote(image)} >/dev/null 2>&1", stream=False)
            if code == 0:
                return {"ok": True, "target": "Server", "image": image, "status": "installed", "already_running": False}

            existing = self._check_single_image_state(ssh, image)
            if existing.get("pull_status") == "pulling":
                return {
                    "ok": True,
                    "target": "Server",
                    "image": image,
                    "status": "pulling",
                    "already_running": True,
                    "pull_pid": existing.get("pull_pid"),
                }

            paths = self.remote_pull_paths(image)
            key = self.image_pull_key(image)
            marker = f"neuroflow-image-pull-{key}"
            quoted_image = shlex.quote(image)

            ssh.run("mkdir -p /tmp/neuroflow-image-pulls && chmod 1777 /tmp/neuroflow-image-pulls || true", stream=False, check=False)

            shell_script = f"""\
set +e
pid=$$
started=$(date +%s)
cat > {shlex.quote(paths['json'])}.tmp <<JSONEOF
{{"image": {json.dumps(image)}, "status": "pulling", "pid": $pid, "started_at": $started, "updated_at": $started, "exit_code": null, "error": null, "log_path": {json.dumps(paths['log'])}}}
JSONEOF
mv {shlex.quote(paths['json'])}.tmp {shlex.quote(paths['json'])}
docker pull {quoted_image} >> {shlex.quote(paths['log'])} 2>&1
code=$?
updated=$(date +%s)
if [ $code -eq 0 ]; then
  status="success"
  err="null"
else
  status="failed"
  err="\\\"Pull failed (exit $code)\\\""
fi
cat > {shlex.quote(paths['json'])}.tmp <<JSONEOF2
{{"image": {json.dumps(image)}, "status": "$status", "pid": $pid, "started_at": $started, "updated_at": $updated, "exit_code": $code, "error": $err, "log_path": {json.dumps(paths['log'])}}}
JSONEOF2
mv {shlex.quote(paths['json'])}.tmp {shlex.quote(paths['json'])}
exit $code
"""
            ssh.run(f"cat > {shlex.quote(paths['sh'])} <<'SCREOF'\n{shell_script}\nSCREOF", stream=False, check=False)
            ssh.run(f"chmod +x {shlex.quote(paths['sh'])}", stream=False, check=False)

            sh_path = paths['sh']
            start_cmd = (
                f"nohup bash -c 'exec -a {shlex.quote(marker)} bash {shlex.quote(sh_path)}' "
                f">/dev/null 2>&1 < /dev/null &"
            )
            ssh.run(start_cmd, stream=False, check=False)

            self.on_log(f"Started detached remote image pull: {image}")
            return {
                "ok": True,
                "target": "Server",
                "image": image,
                "status": "pulling",
                "already_running": False,
            }

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
        mode = PIPELINE_MODE_ALIASES.get(self.config.pipeline_mode, self.config.pipeline_mode)
        if mode != "Custom" and mode in PRESET_CONFIGS:
            selected_tools = PRESET_CONFIGS[mode]["tools"]
        else:
            selected_tools = self.config.selected_tools
        for stage, opt in option_map.items():
            value = selected_tools.get(stage)
            if value and is_tool_enabled(value):
                args += [opt, value]
        return args
