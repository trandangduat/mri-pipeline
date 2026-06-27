"""Progress rendering and event handling mixin for the MRI Pipeline GUI."""

from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from pipeline_runner import (
    STAGE_LABELS,
    STAGE_ORDER,
    BatchImageResult,
    _derive_subject_id,
    _discover_mri_files,
    tool_display_name,
)
from ui.formatters import format_bytes, format_duration, format_percent, truncate_middle


class ProgressMixin:
    def _toggle_progress_log(self) -> None:
        body = getattr(self, "progress_log_body", None)
        label = getattr(self, "progress_log_toggle_text", None)
        if body is None:
            return
        self.progress_log_visible = not self.progress_log_visible
        if self.progress_log_visible:
            body.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
            if label is not None:
                label.set("Hide Image Log")
        else:
            body.pack_forget()
            if label is not None:
                label.set("Show Image Log")

    def _input_files_for_progress(self, req: dict | None = None) -> list[str]:
        if req is None:
            req = self._build_run_request()
        if not req:
            return []
        if req["mode"] == "file":
            return [req["input_file"]]
        if req["mode"] == "files":
            return list(req["input_files"])
        if req.get("input_source") == "Server":
            return [req["input_dir"]]
        return _discover_mri_files(req["input_dir"], recursive=req.get("recursive", True))

    def _show_progress_tab(self) -> None:
        if self.notebook is None or self.progress_tab is None:
            return
        self.notebook.tab(self.progress_tab, state="normal")
        self.notebook.select(self.progress_tab)

    def _prepare_progress_tab(self, files: list[str], selected_tools: dict[str, str] | None = None) -> None:
        self.image_runs.clear()
        self.image_rows.clear()
        self.current_image_key = ""
        self.active_image_key = ""
        self.progress_selected_tools = dict(selected_tools or self.state.get_selected_tools())
        self.state.current_total_images = len(files)
        self.state.current_success_images = 0
        self.state.current_failed_images = 0
        self.state.current_running_images = 0
        self._update_batch_summary()
        for child in self.image_list_frame.winfo_children():
            child.destroy()
        self._clear_log()
        self.detail_chart.reset()
        self.gpu_chart.reset()
        self.state.detail_title.set("Select an input image")
        self._reset_step_summary()
        for idx, path in enumerate(files, start=1):
            self._create_image_run(path, idx, len(files))
        if files:
            self._select_image(files[0])

    def _make_step_state(self, stage: str) -> dict:
        tool = self.progress_selected_tools.get(stage, "")
        return {
            "stage": stage,
            "tool": tool,
            "status": "Skipped" if not tool else "Pending",
            "duration_sec": None,
            "elapsed_sec": None,
            "peak_ram_bytes": None,
            "peak_cpu_pct": None,
            "peak_gpu_pct": None,
            "error": "",
        }

    def _reset_step_summary(self) -> None:
        for stage, widgets in getattr(self, "step_summary_rows", {}).items():
            status = "Skipped" if not self.progress_selected_tools.get(stage) else "Pending"
            self._apply_step_row_widgets(widgets, stage, {"tool": self.progress_selected_tools.get(stage, ""), "status": status})

    def _step_status_color(self, status: str) -> str:
        return {
            "Done": "#16a34a",
            "Completed": "#16a34a",
            "Success": "#16a34a",
            "Running": "#2563eb",
            "Failed": "#dc2626",
            "Paused": "#f59e0b",
            "Skipped": "#64748b",
            "Pending": "#64748b",
        }.get(status, "#64748b")

    def _step_icon(self, status: str) -> tk.PhotoImage | None:
        icon_name = {
            "Done": "success",
            "Completed": "success",
            "Success": "success",
            "Running": "running",
            "Failed": "failed",
            "Paused": "pause",
            "Skipped": "pending",
            "Pending": "pending",
        }.get(status, "pending")
        if status == "Running" and self._spinner_frames:
            return self._spinner_frames[self._spinner_idx]
        return self._make_icon(icon_name)

    def _apply_step_row_widgets(self, widgets: dict, stage: str, step: dict) -> None:
        status = str(step.get("status") or "Pending")
        tool = str(step.get("tool") or self.progress_selected_tools.get(stage, ""))
        duration = step.get("duration_sec")
        if duration is None:
            duration = step.get("elapsed_sec")
        icon = self._step_icon(status)
        widgets["icon"].configure(image=icon if icon is not None else "")
        widgets["tool"].configure(text=tool_display_name(tool) if tool else "")
        widgets["status"].configure(text=status, foreground=self._step_status_color(status))
        widgets["duration"].configure(text=format_duration(duration))
        widgets["ram"].configure(text=format_bytes(step.get("peak_ram_bytes")))
        widgets["cpu"].configure(text=format_percent(step.get("peak_cpu_pct")))
        widgets["gpu"].configure(text=format_percent(step.get("peak_gpu_pct")))

    def _render_step_summary(self, run: dict) -> None:
        steps = run.get("steps", {}) if run else {}
        for stage, widgets in getattr(self, "step_summary_rows", {}).items():
            step = steps.get(stage) or self._make_step_state(stage)
            self._apply_step_row_widgets(widgets, stage, step)

    def _update_run_step(self, input_file: str, stage: str, **updates) -> None:
        if stage not in STAGE_ORDER:
            return
        if input_file not in self.image_runs:
            self._create_image_run(input_file, len(self.image_runs) + 1, max(self.state.current_total_images, len(self.image_runs) + 1))
        run = self.image_runs[input_file]
        step = run.setdefault("steps", {}).setdefault(stage, self._make_step_state(stage))
        if updates.get("tool"):
            step["tool"] = updates["tool"]
        for key, value in updates.items():
            if key == "tool" or value is None or value == "":
                continue
            if key in {"peak_ram_bytes", "peak_cpu_pct", "peak_gpu_pct"}:
                current = step.get(key)
                step[key] = max(float(current or 0), float(value)) if key != "peak_ram_bytes" else max(int(current or 0), int(value))
            else:
                step[key] = value
        if self.current_image_key == input_file:
            self._render_step_summary(run)

    def _create_image_run(self, input_file: str, idx: int, total: int) -> None:
        if input_file in self.image_runs:
            return
        name = _derive_subject_id(input_file)
        self.image_runs[input_file] = {
            "input_file": input_file,
            "name": name,
            "idx": idx,
            "total": total,
            "status": "Pending",
            "percent": 0.0,
            "logs": [],
            "cpu": [],
            "ram": [],
            "gpu": [],
            "container": "n/a",
            "stage": "Queued",
            "stage_detail": "Waiting to start",
            "steps": {stage: self._make_step_state(stage) for stage in STAGE_ORDER},
        }
        
        container = ttk.Frame(self.image_list_frame)
        container.pack(fill=tk.X)
        
        row = ttk.Frame(container)
        row.pack(fill=tk.X, padx=4, pady=4)
        
        top = ttk.Frame(row)
        top.pack(fill=tk.X, padx=4, pady=(4, 2))
        
        icon_img = self._get_status_icon("Pending")
        icon_label = ttk.Label(top, image=icon_img, width=3) if icon_img else ttk.Label(top, text="..", width=3)
        icon_label.pack(side=tk.LEFT, padx=(0, 8))
        
        center = ttk.Frame(top)
        center.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        
        display_name = truncate_middle(name, 25)
        title = ttk.Label(center, text=display_name, anchor=tk.W, font=("Inter", 9, "bold"))
        title.pack(fill=tk.X)

        status_label = ttk.Label(center, text="Pending", anchor=tk.W, foreground="#64748b")
        status_label.pack(fill=tk.X)

        # Add an arrow label for selection
        arrow_label = ttk.Label(top, text="", anchor=tk.E, font=("Inter", 12, "bold"))
        arrow_label.pack(side=tk.RIGHT, padx=(4, 0))
        
        var = tk.DoubleVar(value=0)
        bar = ttk.Progressbar(row, variable=var, maximum=100, mode="determinate")
        bar.pack(fill=tk.X, padx=4, pady=(0, 4))
        
        sep = ttk.Separator(container, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X)
        
        for widget in (container, row, top, center, icon_label, title, status_label, arrow_label, bar, sep):
            widget.bind("<Button-1>", lambda _e, key=input_file: self._select_image(key))
            
        self.image_rows[input_file] = {
            "container": container,
            "frame": row,
            "top": top,
            "center": center,
            "icon": icon_label,
            "title": title,
            "status": status_label,
            "arrow": arrow_label,
            "var": var,
        }

    def _select_image(self, input_file: str) -> None:
        if input_file not in self.image_runs:
            return
        self.current_image_key = input_file
        for key, row in self.image_rows.items():
            is_selected = key == input_file
            
            # Change background to darker when selected
            try:
                frame_style = "Selected.TFrame" if is_selected else "TFrame"
                label_style = "Selected.TLabel" if is_selected else "TLabel"
                
                row["container"].configure(style=frame_style)
                row["frame"].configure(style=frame_style)
                row["top"].configure(style=frame_style)
                row["center"].configure(style=frame_style)
                
                row["icon"].configure(style=label_style)
                row["title"].configure(style=label_style)
                row["status"].configure(style=label_style)
                row["arrow"].configure(style=label_style)
            except Exception as e:
                pass
            
            row["frame"].configure(relief="solid" if is_selected else "flat")
            row["arrow"].configure(text="›" if is_selected else "")
            
        run = self.image_runs[input_file]
        self.state.detail_title.set(f"{run['idx']}/{run['total']} {run['name']} - {run.get('stage', run['status'])}")
        self._render_selected_detail()

    def _render_selected_detail(self) -> None:
        run = self.image_runs.get(self.current_image_key)
        if not run:
            return
        self.detail_chart.reset()
        self.gpu_chart.reset()
        self.detail_chart.container_label.set(f"Container: {run.get('container', 'n/a')}")
        for cpu, ram, container in zip(run["cpu"], run["ram"], [run.get("container", "n/a")] * len(run["cpu"])):
            self.detail_chart.add(cpu, ram, container)
        for gpu in run["gpu"]:
            self.gpu_chart.add(gpu, f"{gpu:.1f}%")
        self._render_step_summary(run)
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, "\n".join(run["logs"][-2000:]))
        if run["logs"]:
            self.log_text.insert(tk.END, "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _update_image_run(
        self,
        input_file: str,
        status: str | None = None,
        percent: float | None = None,
        log_line: str | None = None,
        stage_text: str | None = None,
    ) -> None:
        if input_file not in self.image_runs:
            self._create_image_run(input_file, len(self.image_runs) + 1, max(self.state.current_total_images, len(self.image_runs) + 1))
        run = self.image_runs[input_file]
        
        if stage_text is not None:
            run["stage"] = stage_text
            run["stage_detail"] = stage_text
            
        if status is not None:
            run["status"] = status
            display_text = run.get("stage", status) if status == "Running" else status
            self.image_rows[input_file]["status"].configure(text=display_text)
            icon_img = self._get_status_icon(status)
            if icon_img:
                self.image_rows[input_file]["icon"].configure(image=icon_img, text="")
            else:
                self.image_rows[input_file]["icon"].configure(image="", text="•")
        elif stage_text is not None and run.get("status") == "Running":
            self.image_rows[input_file]["status"].configure(text=stage_text)

        if percent is not None:
            pct = max(0.0, min(100.0, percent))
            run["percent"] = pct
            self.image_rows[input_file]["var"].set(pct)
            
        if self.current_image_key == input_file:
            self.state.detail_title.set(f"{run['idx']}/{run['total']} {run['name']} - {run.get('stage', run.get('status', 'Queued'))}")

    def _update_batch_summary(self) -> None:
        self.state.batch_total_text.set(f"Success: {self.state.current_success_images} / {self.state.current_total_images}")
        self.state.batch_running_text.set(f"Running: {self.state.current_running_images}")
        self.state.batch_failed_text.set(f"Failed: {self.state.current_failed_images}")

    def _match_progress_input_key(self, event: dict) -> str:
        input_file = str(event.get("input_file", ""))
        if input_file in self.image_runs:
            return input_file
            
        # Match by idx for accurate mapping when multiple files have the same basename
        idx = event.get("idx")
        if idx is not None:
            idx_int = int(idx)
            for key, run in self.image_runs.items():
                if run.get("idx") == idx_int:
                    return key
                    
        remote_name = Path(input_file).name
        if len(remote_name) > 5 and remote_name[:4].isdigit() and remote_name[4] == "_":
            remote_name = remote_name[5:]
        for key, run in self.image_runs.items():
            if Path(key).name == remote_name or run.get("name") == remote_name:
                return key
        return input_file

    def _remote_log_event(self, line: str) -> None:
        self.root.after(0, lambda l=line: self._handle_remote_log_event(l))

    def _handle_background_log_chunk(self, data: str) -> None:
        for line in data.splitlines():
            if line.strip():
                self._handle_remote_log_event(line.rstrip())

    def _handle_remote_log_event(self, line: str) -> None:
        if not line.startswith("MRI_EVENT "):
            self._log(line)
            return
        try:
            event = json.loads(line[len("MRI_EVENT "):])
        except json.JSONDecodeError:
            self._log(line)
            return

        kind = event.get("kind")
        if kind == "image_start":
            key = self._match_progress_input_key(event)
            idx = int(event.get("idx", len(self.image_runs) + 1))
            total = int(event.get("total", max(self.state.current_total_images, idx)))
            self.state.current_total_images = max(self.state.current_total_images, total)
            self.active_image_key = key
            self.state.current_running_images = 1
            self._update_batch_summary()
            self._log(f"Remote image {idx}/{total} started: {key}")
            self._update_image_run(key, status="Running", percent=0, stage_text="Starting")
            self.root.after(0, lambda k=key: self._select_image(k))
        elif kind == "progress":
            pct = float(event.get("pct", 0)) * 100
            status = str(event.get("status", "running"))
            stage = str(event.get("stage", "pipeline"))
            msg = str(event.get("msg", ""))
            label = {"running": "Running", "success": "Running", "failed": "Failed", "paused": "Paused"}.get(status, status.capitalize())
            target_key = getattr(self, "active_image_key", "")
            current_run = self.image_runs.get(target_key, {}) if target_key else {}
            idx = int(current_run.get("idx", 1) or 1)
            total = max(int(current_run.get("total", self.state.current_total_images) or 1), 1)
            overall_pct = pct if stage == "batch" else (((idx - 1) + (pct / 100.0)) / total) * 100.0
            self.state.overall_progress_var.set(max(0, min(100, overall_pct)))
            self.state.overall_progress_text.set(f"{int(max(0, min(100, overall_pct)))}%")
            self.state.status_text.set(status.capitalize())
            prefix = "REMOTE " if self.state.run_target.get() == "Server" else ""
            self._log(f"{prefix}{status.upper()} {stage}: {msg}")
            if target_key:
                stage_name = STAGE_LABELS.get(stage, "Batch" if stage == "batch" else stage.replace("_", " ").title())
                stage_text = f"{stage_name} - {status.capitalize()}"
                image_pct = None if stage == "batch" else pct
                if stage in STAGE_ORDER:
                    step_status = {
                        "running": "Running",
                        "success": "Done",
                        "failed": "Failed",
                        "paused": "Paused",
                    }.get(status, status.capitalize())
                    self._update_run_step(target_key, stage, status=step_status)
                self._update_image_run(
                    target_key,
                    status=label,
                    percent=image_pct,
                    stage_text=stage_text,
                )
        elif kind == "image_done":
            key = self._match_progress_input_key(event)
            success = bool(event.get("success"))
            self.state.current_running_images = 0
            if success:
                self.state.current_success_images += 1
                self._log(f"Remote image done: {event.get('subject_id', key)} | OK")
                self._update_image_run(key, status="Done", percent=100, stage_text="Completed")
            else:
                self.state.current_failed_images += 1
                self._log(f"Remote image failed: {event.get('error', '')}")
                self._update_image_run(key, status="Failed", stage_text="Failed")
            self._update_batch_summary()
        elif kind == "image_preflight":
            self._log(f"Remote image preflight {event.get('status')}: {tool_display_name(str(event.get('tool', '')))}")
        elif kind == "step_result":
            key = self._match_progress_input_key(event)
            stage = str(event.get("stage", ""))
            success = bool(event.get("success"))
            status = "Done" if success else "Failed"
            self._update_run_step(
                key,
                stage,
                tool=str(event.get("tool", "")),
                status=status,
                duration_sec=float(event.get("duration_sec", 0.0) or 0.0),
                peak_ram_bytes=event.get("peak_ram_bytes"),
                peak_cpu_pct=event.get("peak_cpu_pct"),
                error=str(event.get("error", "")),
            )
        elif kind == "metrics":
            cpu_pct = event.get("cpu_pct")
            ram_bytes = event.get("ram_bytes")
            gpu_pct = event.get("gpu_pct")
            self._on_metrics(
                str(event.get("stage", "")),
                str(event.get("tool", "")),
                float(cpu_pct) if cpu_pct is not None else None,
                int(ram_bytes) if ram_bytes is not None else None,
                float(event.get("elapsed", 0.0) or 0.0),
                str(event.get("container_name", "")),
                float(gpu_pct or 0.0),
            )

    def _on_progress(self, stage: str, status: str, pct: float, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {status.upper()} {stage}: {msg}"
        self._log(line)
        pct_value = max(0, min(100, pct * 100))
        target_key = getattr(self, "active_image_key", "")
        current_run = self.image_runs.get(target_key, {}) if target_key else {}
        idx = int(current_run.get("idx", 1) or 1)
        total = max(int(current_run.get("total", self.state.current_total_images) or 1), 1)
        overall_pct = pct_value if stage == "batch" else (((idx - 1) + (pct_value / 100.0)) / total) * 100.0
        overall_pct = max(0, min(100, overall_pct))
        self.state.overall_progress_var.set(overall_pct)
        self.state.overall_progress_text.set(f"{int(overall_pct)}%")
        self.state.status_text.set(status.capitalize())
        if target_key:
            label = {
                "running": "Running",
                "success": "Running" if stage != "pipeline" else "Done",
                "failed": "Failed",
                "paused": "Paused",
            }.get(status, status.capitalize())
            stage_name = STAGE_LABELS.get(stage, "Batch" if stage == "batch" else stage.replace("_", " ").title())
            stage_text = f"{stage_name} - {status.capitalize()}"
            if stage in STAGE_ORDER:
                step_status = {
                    "running": "Running",
                    "success": "Done",
                    "failed": "Failed",
                    "paused": "Paused",
                }.get(status, status.capitalize())
                self._update_run_step(target_key, stage, status=step_status)
            self._update_image_run(
                target_key,
                status=label,
                percent=None if stage == "batch" else pct_value,
                stage_text=stage_text,
            )
        if stage in self.stage_items:
            label = {
                "running": "Running",
                "success": "Done",
                "failed": "Failed",
                "paused": "Paused",
            }.get(status, status.capitalize())
            if hasattr(self, "_set_step_status"):
                self._set_step_status(stage, label, pct)
        if self.state.run_target.get() == "Server":
            self.state.server_text.set("Server: connected")
        else:
            self.state.server_text.set("Server: local")

    def _on_image_start(self, input_file: str, idx: int, total: int) -> None:
        self.active_image_key = input_file
        self._log(f"Starting image {idx}/{total}: {input_file}")
        self.state.current_running_images = 1
        self._update_batch_summary()
        self._update_image_run(input_file, status="Running", percent=0, stage_text="Starting")
        self._select_image(input_file)
        self.metrics_queue.put((getattr(self, "active_image_key", ""), 0.0, 0, 0.0, "new image"))

    def _on_image_done(self, result: BatchImageResult, idx: int, total: int) -> None:
        status = "OK" if result.success else "FAILED"
        self._log(f"Done image {idx}/{total}: {result.subject_id} | {status}")
        for step in result.steps:
            self._update_run_step(
                result.input_file,
                step.stage,
                tool=step.tool,
                status="Done" if step.success else "Failed",
                duration_sec=step.duration_sec,
                peak_ram_bytes=step.peak_ram_bytes,
                peak_cpu_pct=step.peak_cpu_pct,
                error=step.error,
            )
        self.state.current_running_images = 0
        if result.success:
            self.state.current_success_images += 1
            row_status = "Done"
            pct = 100
        else:
            self.state.current_failed_images += 1
            row_status = "Failed"
            pct = self.image_runs.get(result.input_file, {}).get("percent", 0)
        self._update_batch_summary()
        self._update_image_run(result.input_file, status=row_status, percent=pct, stage_text="Completed" if result.success else "Failed")

    def _on_metrics(self, stage: str, tool: str, cpu_pct: float | None, ram_bytes: int | None, elapsed: float, container_name: str, gpu_pct: float | None = 0.0) -> None:
        target_key = getattr(self, "active_image_key", "")
        if target_key and target_key in self.image_runs:
            run = self.image_runs[target_key]
            run["cpu"].append(max(cpu_pct or 0.0, 0.0))
            run["ram"].append(ram_bytes or 0)
            run["gpu"].append(max(gpu_pct or 0.0, 0.0))
            run["container"] = container_name or "n/a"
            run["cpu"] = run["cpu"][-180:]
            run["ram"] = run["ram"][-180:]
            run["gpu"] = run["gpu"][-180:]
            if stage in STAGE_ORDER:
                self._update_run_step(
                    target_key,
                    stage,
                    tool=tool,
                    status="Running",
                    elapsed_sec=elapsed,
                    peak_ram_bytes=ram_bytes,
                    peak_cpu_pct=cpu_pct,
                    peak_gpu_pct=gpu_pct,
                )
        self.metrics_queue.put((target_key, cpu_pct, ram_bytes, gpu_pct, container_name))

    def _request_stop(self) -> None:
        self.stop_requested.set()
        if self.state.run_target.get() == "Server" and self.remote_runner and self.remote_runner.remote_job_dir:
            def request_remote_pause():
                try:
                    self.remote_runner.request_pause()
                except Exception as exc:
                    self._log(f"REMOTE PAUSE ERROR: {type(exc).__name__}: {exc}")

            threading.Thread(target=request_remote_pause, daemon=True).start()
            self._log("Remote pause requested. Server will pause after the current pipeline stage.")
            return
        if self.active_job and self.active_job.get("target") == "Local" and self.active_job.get("job_dir"):
            try:
                stop_file = Path(str(self.active_job["job_dir"])) / "stop_requested"
                stop_file.touch()
                self._log(f"Local pause requested via stop file: {stop_file}")
            except Exception as exc:
                self._log(f"LOCAL PAUSE ERROR: {type(exc).__name__}: {exc}")
            return
        self._log("Pause requested. The current Docker step will finish, then state will be saved as PAUSED.")

    def _set_idle_state(self) -> None:
        if hasattr(self, "progress"):
            self.progress.stop()
        self.running = False
        if hasattr(self, "run_button"):
            self.run_button.configure(state=tk.NORMAL if self._validate_configuration() else tk.DISABLED)
        if hasattr(self, "resume_button"):
            self.resume_button.configure(state=tk.NORMAL)
        if hasattr(self, "restart_button"):
            self.restart_button.configure(state=tk.NORMAL)
        if hasattr(self, "stop_button"):
            self.stop_button.configure(state=tk.DISABLED)
        self.state.status_text.set("Ready")
        self._log("Pipeline finished.")
        self._log("=" * 80)

    def _poll_queues(self) -> None:
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, tuple):
                image_key, line_str = item
            else:
                image_key, line_str = None, item

            if image_key and image_key in self.image_runs:
                run = self.image_runs[image_key]
                run["logs"].append(line_str)
                run["logs"] = run["logs"][-2500:]

            if not image_key or image_key == self.current_image_key:
                self._append_log(line_str)

        while True:
            try:
                item = self.metrics_queue.get_nowait()
            except queue.Empty:
                break
            if len(item) == 5:
                image_key, cpu_pct, ram_bytes, gpu_pct, container_name = item
            else:
                image_key, cpu_pct, ram_bytes, gpu_pct, container_name = None, item[0], item[1], item[2], item[3]
                
            if not image_key or image_key == self.current_image_key:
                if hasattr(self, "detail_chart"):
                    self.detail_chart.add(cpu_pct, ram_bytes, container_name)
                if hasattr(self, "gpu_chart"):
                    gpu = max(gpu_pct or 0.0, 0.0)
                    self.gpu_chart.add(gpu, f"{gpu:.1f}%")
                cpu = max(cpu_pct or 0.0, 0.0)
                ram_mib = (ram_bytes or 0) / (1024 * 1024)
                self.state.cpu_text.set(f"CPU {cpu:.0f}%")
                self.state.ram_text.set(f"RAM {ram_mib / 1024:.2f} GB" if ram_mib >= 1024 else f"RAM {ram_mib:.0f} MB")

        self.root.after(100, self._poll_queues)

    def _log(self, line: str) -> None:
        self.log_queue.put((getattr(self, "active_image_key", ""), line))

    def _append_log(self, line: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)
