from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from typing import Callable

from .config import BuildLogCallback, PROJECT_ROOT, ProgressCallback, TOOL_DEFS, is_tool_enabled, tool_display_name
from .utils import _parse_docker_stats_line


log = logging.getLogger(__name__)


def image_exists(image: str) -> bool:
    try:
        proc = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, timeout=10)
        return proc.returncode == 0
    except Exception:
        return False


def image_size_bytes(image: str) -> int | None:
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", image, "--format", "{{.Size}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            return None
        return int(proc.stdout.strip())
    except Exception:
        return None


def format_image_size(size: int | None) -> str:
    if size is None or size < 0:
        return "-"
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def remove_image(image: str) -> tuple[bool, str]:
    try:
        proc = subprocess.run(["docker", "image", "rm", image], capture_output=True, text=True, timeout=300)
        if proc.returncode == 0:
            return True, ""
        return False, (proc.stderr or proc.stdout).strip()
    except Exception as exc:
        return False, str(exc)


def build_image(image: str, context_dir: str, on_progress: ProgressCallback | None = None, on_build_log: BuildLogCallback | None = None) -> bool:
    ctx = PROJECT_ROOT / context_dir
    if not ctx.exists():
        if on_progress:
            on_progress("build", "failed", 0, f"Dockerfile context not found: {ctx}")
        return False
    if on_progress:
        on_progress("build", "running", 0, f"Building {image}...")
    if on_build_log:
        on_build_log(f">>> docker build -t {image} {ctx}")
    try:
        proc = subprocess.Popen(["docker", "build", "-t", image, str(ctx)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        last_progress: dict[str, str] = {}
        raw = ""

        def flush_progress() -> None:
            for v in last_progress.values():
                if on_build_log:
                    on_build_log(v)
            last_progress.clear()

        for chunk in proc.stdout:
            raw += chunk
            while "\n" in raw or "\r" in raw:
                idx_n = raw.find("\n")
                idx_r = raw.find("\r")
                idx = min(i for i in (idx_n, idx_r) if i >= 0)
                line = raw[:idx].strip()
                raw = raw[idx + 1:]
                if not line:
                    continue
                if ("MB/s" in line or "GB/s" in line or "kB/s" in line) and "%" in line:
                    parts = line.split()
                    lid = parts[0] if parts and parts[0].startswith("#") else line[:20]
                    last_progress[lid] = line
                else:
                    flush_progress()
                    if on_build_log:
                        on_build_log(line)
        flush_progress()
        if raw.strip() and on_build_log:
            on_build_log(raw.strip())
        proc.wait()
        if proc.returncode == 0:
            if on_progress:
                on_progress("build", "success", 0, f"Built {image}")
            return True
        if on_progress:
            on_progress("build", "failed", 0, f"Build failed (exit {proc.returncode})")
        return False
    except Exception as exc:
        if on_progress:
            on_progress("build", "failed", 0, f"Build error: {exc}")
        return False


def _try_pull(image: str, on_progress: ProgressCallback | None = None, on_build_log: BuildLogCallback | None = None) -> bool:
    if on_progress:
        on_progress("build", "running", 0, f"Pulling {image}...")
    if on_build_log:
        on_build_log(f">>> docker pull {image}")
    try:
        proc = subprocess.Popen(["docker", "pull", image], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            line = line.strip()
            if line and on_build_log:
                on_build_log(line)
        proc.wait()
        return proc.returncode == 0
    except Exception:
        return False


def ensure_image(tool_key: str, on_progress: ProgressCallback | None = None, on_build_log: BuildLogCallback | None = None) -> tuple[bool, str, float]:
    tool = TOOL_DEFS.get(tool_key)
    if not tool:
        return False, f"Unknown tool: {tool_key}", 0.0
    if not is_tool_enabled(tool_key):
        return False, f"Tool is disabled because image is disabled: {tool_display_name(tool_key)} ({tool.get('image', '')})", 0.0

    image = tool["image"]
    total_build = 0.0
    base_image = tool.get("base_image")
    base_dockerfile = tool.get("base_dockerfile")
    if base_image and not image_exists(base_image):
        t0 = time.time()
        pulled = _try_pull(base_image, on_progress, on_build_log)
        total_build += time.time() - t0
        if not pulled:
            if base_dockerfile:
                t0 = time.time()
                if not build_image(base_image, base_dockerfile, on_progress, on_build_log):
                    return False, f"Failed to get base image {base_image}", total_build
                total_build += time.time() - t0
            else:
                return False, f"Base image {base_image} not available", total_build

    if not image_exists(image):
        t0 = time.time()
        pulled = _try_pull(image, on_progress, on_build_log)
        total_build += time.time() - t0
        if not pulled:
            dockerfile = tool.get("dockerfile")
            if dockerfile:
                t0 = time.time()
                if not build_image(image, dockerfile, on_progress, on_build_log):
                    return False, f"Failed to build {image}", total_build
                total_build += time.time() - t0
            else:
                return False, f"Image {image} not available", total_build
    return True, "", total_build


def _run_docker(
    image: str,
    args: list[str],
    mounts: list[tuple[str, str]] | dict[str, str],
    env: dict[str, str] | None = None,
    gpus: bool = False,
    timeout: int = 7200,
    container_name: str | None = None,
    on_metrics: Callable[[float | None, int | None, float, str], None] | None = None,
    command: list[str] | None = None,
    entrypoint: str | None = None,
) -> tuple[int, str, int | None, float | None]:
    cmd = ["docker", "run", "--rm"]
    if container_name:
        cmd += ["--name", container_name]
    if gpus:
        cmd += ["--gpus", "all"]
    mount_items = mounts.items() if isinstance(mounts, dict) else mounts
    for host_path, container_path in mount_items:
        cmd += ["-v", f"{os.path.abspath(host_path)}:{container_path}"]
    if env:
        for k, v in env.items():
            cmd += ["-e", f"{k}={v}"]
    if entrypoint is not None:
        cmd += ["--entrypoint", entrypoint]
    cmd.append(image)
    if command:
        cmd.extend(command)
    cmd += args
    log.info("Running: %s", " ".join(cmd))

    peak_ram = {"bytes": None}
    peak_cpu = {"pct": None}
    stop_monitor = threading.Event()
    t0 = time.time()

    def monitor_resources() -> None:
        if not container_name:
            return
        while not stop_monitor.is_set():
            try:
                stats = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}|{{.MemUsage}}", container_name], capture_output=True, text=True, timeout=5)
                if stats.returncode == 0 and stats.stdout.strip():
                    cpu, current = _parse_docker_stats_line(stats.stdout.strip().splitlines()[0])
                    if current is not None and (peak_ram["bytes"] is None or current > peak_ram["bytes"]):
                        peak_ram["bytes"] = current
                    if cpu is not None and (peak_cpu["pct"] is None or cpu > peak_cpu["pct"]):
                        peak_cpu["pct"] = cpu
                    if on_metrics:
                        on_metrics(cpu, current, time.time() - t0, container_name or "")
            except Exception:
                pass
            stop_monitor.wait(0.5)

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        monitor = threading.Thread(target=monitor_resources, daemon=True)
        monitor.start()
        try:
            output, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            if container_name:
                subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, text=True, timeout=30)
            output, _ = proc.communicate()
            return -1, f"{output or ''}\nDocker timed out after {timeout}s", peak_ram["bytes"], peak_cpu["pct"]
        finally:
            stop_monitor.set()
            monitor.join(timeout=2)
        return proc.returncode, output or "", peak_ram["bytes"], peak_cpu["pct"]
    except subprocess.TimeoutExpired:
        return -1, f"Docker timed out after {timeout}s", peak_ram["bytes"], peak_cpu["pct"]
    except FileNotFoundError:
        return -1, "docker not found - is Docker installed and in PATH?", peak_ram["bytes"], peak_cpu["pct"]
