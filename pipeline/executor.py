from __future__ import annotations
import os
import time
import subprocess
import threading
import logging
import math
from dataclasses import dataclass
from typing import Callable
from abc import ABC, abstractmethod

from .utils import _parse_docker_stats_line
from pipeline.win_process import no_window_kwargs

log = logging.getLogger(__name__)

@dataclass
class DockerResourceMetrics:
    peak_ram_bytes: int | None = None
    avg_ram_bytes: int | None = None
    p95_ram_bytes: int | None = None
    peak_cpu_pct: float | None = None
    avg_cpu_pct: float | None = None
    p95_cpu_pct: float | None = None

@dataclass
class ExecutionRequest:
    image: str
    args: list[str]
    mounts: list[tuple[str, str]]
    command: list[str] | None = None
    entrypoint: str | None = None
    env: dict[str, str] | None = None
    gpus: bool = False
    memory_bytes: int | None = None
    container_name: str | None = None
    timeout: int = 7200
    should_stop: Callable[[], bool] | None = None
    gpu_device_id: str | None = None
    cpu_thread_limit: int | None = None
    output_capture: object | None = None

@dataclass
class ExecutionResult:
    success: bool
    error: str
    output: str
    duration_sec: float
    metrics: DockerResourceMetrics | None
    container_name: str | None = None
    return_code: int = 0


class BaseExecutor(ABC):
    @abstractmethod
    def execute(
        self,
        req: ExecutionRequest,
        on_metrics: Callable[[float | None, int | None, float, str], None] | None = None,
    ) -> ExecutionResult:
        pass


def _mean(values: list[int] | list[float]) -> float | None:
    return (sum(values) / len(values)) if values else None

def _p95(values: list[int] | list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))
    return ordered[index]

def _resource_metrics(ram_samples: list[int], cpu_samples: list[float]) -> DockerResourceMetrics:
    avg_ram = _mean(ram_samples)
    p95_ram = _p95(ram_samples)
    avg_cpu = _mean(cpu_samples)
    p95_cpu = _p95(cpu_samples)
    return DockerResourceMetrics(
        peak_ram_bytes=max(ram_samples) if ram_samples else None,
        avg_ram_bytes=round(avg_ram) if avg_ram is not None else None,
        p95_ram_bytes=round(p95_ram) if p95_ram is not None else None,
        peak_cpu_pct=max(cpu_samples) if cpu_samples else None,
        avg_cpu_pct=avg_cpu,
        p95_cpu_pct=p95_cpu,
    )


class LocalDockerExecutor(BaseExecutor):
    def execute(
        self,
        req: ExecutionRequest,
        on_metrics: Callable[[float | None, int | None, float, str], None] | None = None,
    ) -> ExecutionResult:
        cmd = ["docker", "run", "--rm"]
        if req.container_name:
            cmd += ["--name", req.container_name]
        if req.gpus:
            cmd += ["--gpus", f"device={req.gpu_device_id}" if req.gpu_device_id is not None else "all"]
        if req.cpu_thread_limit is not None:
            if req.cpu_thread_limit < 1:
                raise ValueError("CPU thread limit must be positive")
            cmd += ["--cpus", str(req.cpu_thread_limit)]
        if req.memory_bytes and req.memory_bytes > 0:
            cmd += ["--memory", f"{int(req.memory_bytes)}b"]
        for host_path, container_path in req.mounts:
            cmd += ["-v", f"{os.path.abspath(host_path)}:{container_path}"]
        if req.env:
            for k, v in req.env.items():
                cmd += ["-e", f"{k}={v}"]
        if req.entrypoint is not None:
            cmd += ["--entrypoint", req.entrypoint]
        cmd.append(req.image)
        if req.command:
            cmd.extend(req.command)
        cmd += req.args
        log.info("Running: %s", " ".join(cmd))

        ram_samples: list[int] = []
        cpu_samples: list[float] = []
        stop_monitor = threading.Event()
        t0 = time.time()

        def monitor_resources() -> None:
            if not req.container_name:
                return
            while not stop_monitor.is_set():
                try:
                    stats = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}|{{.MemUsage}}", req.container_name], capture_output=True, text=True, timeout=5, **no_window_kwargs())
                    if stats.returncode == 0 and stats.stdout.strip():
                        cpu, current = _parse_docker_stats_line(stats.stdout.strip().splitlines()[0])
                        if current is not None:
                            ram_samples.append(current)
                        if cpu is not None:
                            cpu_samples.append(cpu)
                        if on_metrics:
                            on_metrics(cpu, current, time.time() - t0, req.container_name or "")
                except Exception:
                    pass
                stop_monitor.wait(2.0)

        try:
            streaming = req.output_capture is not None
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=not streaming, **no_window_kwargs())
            tail = bytearray()
            reader = None
            if streaming:
                def read_output():
                    try:
                        while True:
                            chunk = proc.stdout.read1(65536)
                            if not chunk:
                                break
                            req.output_capture.write(chunk)
                            tail.extend(chunk)
                            if len(tail) > 65536:
                                del tail[:-65536]
                    except Exception as exc:
                        req.output_capture.meta['coverage'] = 'partial'
                        req.output_capture.meta['capture_error'] = str(exc)
                reader = threading.Thread(target=read_output, daemon=True)
                reader.start()
            monitor = threading.Thread(target=monitor_resources, daemon=True)
            monitor.start()
            stopped = False
            timed_out = False
            return_code = -1
            try:
                deadline = t0 + req.timeout
                while True:
                    try:
                        timeout = min(0.5, max(0.01, deadline - time.time()))
                        if streaming:
                            proc.wait(timeout=timeout)
                            output = ""
                        else:
                            output, _ = proc.communicate(timeout=timeout)
                        return_code = proc.returncode
                        break
                    except subprocess.TimeoutExpired:
                        if req.should_stop and req.should_stop():
                            stopped = True
                            if req.container_name:
                                subprocess.run(["docker", "rm", "-f", req.container_name], capture_output=True, text=True, timeout=30, **no_window_kwargs())
                            else:
                                proc.kill()
                            if streaming:
                                proc.wait(timeout=30)
                                output = ""
                            else:
                                output, _ = proc.communicate(timeout=30)
                            return_code = proc.returncode if proc.returncode is not None else -1
                            break
                        if time.time() >= deadline:
                            timed_out = True
                            proc.kill()
                            if req.container_name:
                                subprocess.run(["docker", "rm", "-f", req.container_name], capture_output=True, text=True, timeout=30, **no_window_kwargs())
                            if streaming:
                                proc.wait()
                                output = ""
                            else:
                                output, _ = proc.communicate()
                            output = f"{output or ''}\nDocker timed out after {req.timeout}s"
                            return_code = -1
                            break
            finally:
                stop_monitor.set()
                monitor.join(timeout=2)
                if reader is not None:
                    reader.join(timeout=5)
                    if reader.is_alive():
                        req.output_capture.meta['coverage'] = 'partial'
                        req.output_capture.meta['capture_error'] = 'Output reader did not finish'
                    output = bytes(tail).decode('utf-8', errors='replace')
                    if timed_out:
                        output += f"\nDocker timed out after {req.timeout}s"
                
            metrics = _resource_metrics(ram_samples, cpu_samples)
            return ExecutionResult(
                success=(return_code == 0),
                error="stopped by request" if stopped else ("" if return_code == 0 else f"exit code {return_code}"),
                output=output or "",
                duration_sec=time.time() - t0,
                metrics=metrics,
                container_name=req.container_name,
                return_code=return_code
            )
        except subprocess.TimeoutExpired:
            if req.output_capture:
                req.output_capture.finish(False, 'Docker timeout', -1)
            return ExecutionResult(False, f"Docker timed out after {req.timeout}s", "", time.time() - t0, _resource_metrics(ram_samples, cpu_samples), req.container_name, -1)
        except FileNotFoundError:
            if req.output_capture:
                req.output_capture.finish(False, 'docker not found', None)
            return ExecutionResult(False, "docker not found - is Docker installed and in PATH?", "", time.time() - t0, _resource_metrics(ram_samples, cpu_samples), req.container_name, -1)
        except Exception as exc:
            if req.output_capture:
                req.output_capture.finish(False, str(exc), None)
            raise
