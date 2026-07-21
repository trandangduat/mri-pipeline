from __future__ import annotations

import logging
import math
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .config import BuildLogCallback, PROJECT_ROOT, ProgressCallback
from .registry import TOOL_DEFS, is_tool_enabled, tool_display_name


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


