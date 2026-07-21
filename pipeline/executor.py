from __future__ import annotations
import os
from pathlib import Path
import time
import shutil
from dataclasses import dataclass
from typing import Callable

from .config import ToolContext, PipelineConfig, TOOL_DEFS
from .docker_ops import _run_docker, DockerResourceMetrics
from .utils import _repair_host_permissions, _safe_container_name
from .discovery import _dicom_files_in_series, _first_dicom_file_in_series

@dataclass
class ExecutionResult:
    success: bool
    error: str
    output: str
    duration_sec: float
    metrics: DockerResourceMetrics | None
    container_name: str

class PipelineExecutor:
    """
    Deep module interface for executing pipeline tools.
    """
    def execute(
        self,
        tool_key: str,
        stage: str,
        input_file: str | None,
        subject_dir: str,
        config: PipelineConfig,
        logs_dir: str,
        memory_limit_bytes: int | None,
        on_metrics: Callable[[str, str, float, int | None, float, str], None] | None = None,
    ) -> ExecutionResult:
        tool = TOOL_DEFS[tool_key]
        
        # 1. Resolve Input Mounts
        if input_file is None:
            input_abs = Path(config.input_file).expanduser().resolve()
            dicom_files = _dicom_files_in_series(input_abs)
            docker_input_abs = _first_dicom_file_in_series(input_abs) or input_abs
            host_input_dir = str(input_abs.parent)
            input_rel = docker_input_abs.relative_to(input_abs.parent).as_posix()
            input_path = f"/input/{input_rel}"
            dicom_list_path = ""
            if dicom_files:
                dicom_list_file = Path(logs_dir) / "dicom_input_files.txt"
                dicom_list_file.write_text(
                    "\n".join(f"/input/{path.relative_to(input_abs.parent).as_posix()}" for path in dicom_files) + "\n",
                    encoding="utf-8",
                )
                dicom_list_path = "/work/logs/dicom_input_files.txt"
            mounts: list[tuple[str, str]] = [(host_input_dir, "/input")]
        else:
            rel = os.path.relpath(input_file, subject_dir)
            input_path = f"/work/{rel}"
            dicom_list_path = ""
            mounts = []

        # 2. Resolve Workspace Mounts
        mounts.append((subject_dir, "/output"))
        mounts.append((subject_dir, "/work"))
        
        license_mount: list[tuple[str, str]] = []
        if config.license_dir:
            lic_path = Path(config.license_dir).absolute()
            license_mount.append((str(lic_path), "/license/license.txt" if lic_path.is_file() else "/license"))
            
        if tool.get("needs_license") and license_mount:
            mounts.extend(license_mount)
            
        for rel, container in tool.get("extra_mounts", {}).items():
            host = os.path.join(subject_dir, "mri", rel)
            Path(host).mkdir(parents=True, exist_ok=True)
            mounts.append((host, container))
            
        norm_vol = Path(__file__).resolve().parent.parent / "normalize_volumes.py"
        if norm_vol.exists():
            mounts.append((str(norm_vol), "/app/normalize_volumes.py"))

        # 3. Resolve Commands
        args = ["--input", input_path, "--output-dir", "/output", "--work-dir", "/work", "--subject-id", config.subject_id, "--threads", str(config.threads), "--device", config.device]
        command = tool.get("command")

        if "command_builder" in tool:
            ctx = ToolContext(
                input_path=input_path,
                subject_id=config.subject_id,
                threads=config.threads,
                device=config.device,
                dicom_list_path=dicom_list_path,
            )
            actual_cmd = tool["command_builder"](ctx)
            command = [tool.get("shell", "bash"), "-c", actual_cmd]
            args = []

        # 4. Execute
        t0 = time.time()
        container_name = _safe_container_name("mri", config.subject_id, tool_key)

        def _metrics_relay(cpu_pct, ram_bytes, elapsed, _cn=container_name):
            if on_metrics:
                on_metrics(stage, tool_key, cpu_pct, ram_bytes, elapsed, _cn)

        code, output, metrics = _run_docker(
            image=tool["image"],
            args=args,
            mounts=mounts,
            gpus=(config.device == "gpu" or config.device == "cuda"),
            memory_bytes=memory_limit_bytes,
            container_name=container_name,
            command=command,
            entrypoint=tool.get("entrypoint"),
            on_metrics=_metrics_relay,
        )
        
        duration = time.time() - t0
        _repair_host_permissions(subject_dir, tool["image"])

        success = code == 0
        error = ""
        if not success:
            if not output.strip():
                try:
                    logs = [p for p in Path(logs_dir).glob("*.log") if p.name not in ("pipeline_metrics.log", "pipeline_state.json")]
                    if logs:
                        output = max(logs, key=lambda p: p.stat().st_mtime).read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
            tail = " | ".join(output.strip().splitlines()[-3:]) if output.strip() else "No output"
            error = f"exit code {code} ({tail})"
            lower_output = output.lower()
            if "error writing data" in lower_output or "no space left on device" in lower_output:
                try:
                    disk_hint = f"free disk at output: {shutil.disk_usage(subject_dir).free} bytes"
                except OSError:
                    disk_hint = "could not check free disk at output"
                error += f". Write failure hint: check remote disk space and output permissions ({disk_hint})"

        return ExecutionResult(
            success=success,
            error=error,
            output=output,
            duration_sec=duration,
            metrics=metrics,
            container_name=container_name
        )
