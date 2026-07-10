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
from ui.tabs.progress_tab import build_progress_tab


class ProgressMixin:
    def _progress_job_identity(self, job: dict | None) -> str:
        if not job:
            return ""
        return str(job.get("remote_job_dir") or job.get("job_dir") or job.get("job_id") or "")

    def _progress_title_for_job(self, job: dict | None = None, fallback: str = "Run progress") -> str:
        if not job:
            return fallback
        target = str(job.get("target") or job.get("run_target") or "Job")
        label = str(job.get("job_id") or Path(str(job.get("remote_job_dir") or job.get("job_dir") or fallback)).name or fallback)
        state = str(job.get("state") or "").strip()
        title = f"{target}: {label}"
        if state and state != "unknown":
            title = f"{title} ({state})"
        return title

    def _unique_progress_title(self, title: str, context_id: str | None = None) -> str:
        base = truncate_middle(title, 34)
        used = {
            ctx.get("title", "")
            for cid, ctx in getattr(self, "progress_contexts", {}).items()
            if cid != context_id
        }
        if base not in used:
            return base
        idx = 2
        while f"{base} #{idx}" in used:
            idx += 1
        return f"{base} #{idx}"

    def _make_progress_context(self, title: str, job_identity: str = "") -> dict:
        if self.notebook is None:
            raise RuntimeError("Notebook is not initialized")
        context_id = f"progress-{len(self.progress_contexts) + 1}-{int(time.time() * 1000)}"
        title = self._unique_progress_title(title)
        context = {
            "id": context_id,
            "title": title,
            "tab_title": tk.StringVar(value=title),
            "job_identity": job_identity,
            "tab": ttk.Frame(self.notebook),
            "image_runs": {},
            "image_rows": {},
            "current_image_key": "",
            "active_image_key": "",
            "progress_selected_tools": {},
            "progress_log_visible": False,
            "current_total_images": 0,
            "current_success_images": 0,
            "current_failed_images": 0,
            "current_running_images": 0,
            "batch_total_text": tk.StringVar(value="Success: 0 / 0"),
            "batch_running_text": tk.StringVar(value="Running: 0"),
            "batch_failed_text": tk.StringVar(value="Failed: 0"),
            "detail_title": tk.StringVar(value="Select an input image"),
            "job_preset_text": tk.StringVar(value=""),
            "job_threads_text": tk.StringVar(value=""),
            "job_device_text": tk.StringVar(value=""),
        }
        build_progress_tab(context["tab"], self, context)
        self.progress_contexts[context_id] = context
        if job_identity:
            self.progress_context_by_job[job_identity] = context_id
        self.notebook.add(context["tab"], text=title)
        return context

    def _save_active_progress_context(self) -> None:
        context = self.progress_contexts.get(getattr(self, "active_progress_context_id", ""))
        if not context:
            return
        for name in (
            "image_runs",
            "image_rows",
            "current_image_key",
            "active_image_key",
            "progress_selected_tools",
            "progress_log_visible",
            "progress_log_card",
            "step_summary_rows",
            "image_list_canvas",
            "image_list_frame",
            "detail_chart",
            "gpu_chart",
            "progress_log_toggle_text",
            "progress_log_body",
            "log_text",
            "job_preset_text",
            "job_threads_text",
            "job_device_text",
        ):
            if hasattr(self, name):
                context[name] = getattr(self, name)

    def _activate_progress_context(self, context_id: str) -> dict | None:
        context = self.progress_contexts.get(context_id)
        if not context:
            return None
        if getattr(self, "active_progress_context_id", "") != context_id:
            self._save_active_progress_context()
        self.active_progress_context_id = context_id
        self.progress_tab = context["tab"]
        for name in (
            "image_runs",
            "image_rows",
            "current_image_key",
            "active_image_key",
            "progress_selected_tools",
            "progress_log_visible",
            "progress_log_card",
            "step_summary_rows",
            "image_list_canvas",
            "image_list_frame",
            "detail_chart",
            "gpu_chart",
            "progress_log_toggle_text",
            "progress_log_body",
            "log_text",
            "job_preset_text",
            "job_threads_text",
            "job_device_text",
        ):
            setattr(self, name, context.get(name))
        self._sync_progress_context_to_state(context)
        monitor = getattr(self, "job_monitors", {}).get(context_id)
        if monitor:
            self.active_job = monitor.get("active_job")
            self.remote_runner = monitor.get("remote_runner")
            self.job_log_offset = int(monitor.get("job_log_offset", 0) or 0)
            self.remote_poll_in_flight = bool(monitor.get("remote_poll_in_flight", False))
            self.job_poll_after_id = monitor.get("after_id")
        return context

    def _sync_progress_context_to_state(self, context: dict) -> None:
        self.state.current_total_images = int(context.get("current_total_images", 0) or 0)
        self.state.current_success_images = int(context.get("current_success_images", 0) or 0)
        self.state.current_failed_images = int(context.get("current_failed_images", 0) or 0)
        self.state.current_running_images = int(context.get("current_running_images", 0) or 0)
        self.state.batch_total_text.set(context["batch_total_text"].get())
        self.state.batch_running_text.set(context["batch_running_text"].get())
        self.state.batch_failed_text.set(context["batch_failed_text"].get())
        self.state.detail_title.set(context["detail_title"].get())

    def _current_progress_context(self) -> dict | None:
        return self.progress_contexts.get(getattr(self, "active_progress_context_id", ""))

    def _set_progress_count(self, name: str, value: int) -> None:
        context = self._current_progress_context()
        if context is not None:
            context[name] = value
        setattr(self.state, name, value)

    def _get_progress_count(self, name: str) -> int:
        context = self._current_progress_context()
        if context is not None:
            return int(context.get(name, 0) or 0)
        return int(getattr(self.state, name, 0) or 0)

    def _set_detail_title(self, value: str) -> None:
        context = self._current_progress_context()
        if context is not None:
            context["detail_title"].set(value)
        self.state.detail_title.set(value)

    def _set_current_image_key(self, value: str) -> None:
        self.current_image_key = value
        context = self._current_progress_context()
        if context is not None:
            context["current_image_key"] = value

    def _set_active_image_key(self, value: str) -> None:
        self.active_image_key = value
        context = self._current_progress_context()
        if context is not None:
            context["active_image_key"] = value

    def _on_notebook_tab_changed(self, _event=None) -> None:
        if self.notebook is None:
            return
        selected = str(self.notebook.select())
        for context_id, context in self.progress_contexts.items():
            if str(context.get("tab")) == selected:
                self._activate_progress_context(context_id)
                return

    def _close_progress_tab(self, context_id: str) -> None:
        context = self.progress_contexts.get(context_id)
        if not context or self.notebook is None:
            return
        monitor = getattr(self, "job_monitors", {}).get(context_id)
        if monitor and monitor.get("active_job") and not monitor.get("active_job", {}).get("done"):
            from tkinter import messagebox

            if not messagebox.askyesno("Close progress tab", "Close this progress tab? The background job will continue running."):
                return
            after_id = monitor.get("after_id")
            if after_id:
                try:
                    self.root.after_cancel(after_id)
                except Exception:
                    pass
            self.job_monitors.pop(context_id, None)
        identity = str(context.get("job_identity") or "")
        if identity:
            self.progress_context_by_job.pop(identity, None)
        was_active = self.active_progress_context_id == context_id
        try:
            self.notebook.forget(context["tab"])
        except Exception:
            pass
        try:
            context["tab"].destroy()
        except Exception:
            pass
        self.progress_contexts.pop(context_id, None)
        if was_active:
            self.active_progress_context_id = ""
            next_context = next(iter(self.progress_contexts), "")
            if next_context:
                self._activate_progress_context(next_context)
                self.notebook.select(self.progress_contexts[next_context]["tab"])
            elif self.config_tab is not None:
                self.progress_tab = None
                self.active_job = None
                self.remote_runner = None
                self.job_poll_after_id = None
                self.remote_poll_in_flight = False
                self.notebook.select(self.config_tab)

    def _ensure_progress_context(self, title: str, job_identity: str = "") -> dict:
        context_id = self.progress_context_by_job.get(job_identity, "") if job_identity else ""
        context = self.progress_contexts.get(context_id) if context_id else None
        if context is None:
            context = self._make_progress_context(title, job_identity)
        else:
            title = self._unique_progress_title(title, context_id=context_id)
            context["title"] = title
            context["tab_title"].set(title)
            if self.notebook is not None:
                self.notebook.tab(context["tab"], text=title)
        self._activate_progress_context(context["id"])
        return context

    def _rename_active_progress_tab(self, title: str, job_identity: str = "") -> None:
        context = self._current_progress_context()
        if not context or self.notebook is None:
            return
        title = self._unique_progress_title(title, context_id=context["id"])
        old_identity = str(context.get("job_identity") or "")
        if old_identity:
            self.progress_context_by_job.pop(old_identity, None)
        context["title"] = title
        context["tab_title"].set(title)
        context["job_identity"] = job_identity
        if job_identity:
            self.progress_context_by_job[job_identity] = context["id"]
        self.notebook.tab(context["tab"], text=title)

    def _toggle_progress_log(self) -> None:
        body = getattr(self, "progress_log_body", None)
        label = getattr(self, "progress_log_toggle_text", None)
        card = getattr(self, "progress_log_card", None)
        if body is None:
            return
        self.progress_log_visible = not self.progress_log_visible
        context = self._current_progress_context()
        if context is not None:
            context["progress_log_visible"] = self.progress_log_visible
        if self.progress_log_visible:
            if card is not None:
                card.pack_configure(fill=tk.BOTH, expand=True)
            body.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
            if label is not None:
                label.set("Hide Image Log")
        else:
            body.pack_forget()
            if card is not None:
                card.pack_configure(fill=tk.X, expand=False)
            if label is not None:
                label.set("Show Image Log")

    def _copy_progress_log(self) -> None:
        log = getattr(self, "log_text", None)
        if log is None:
            return
        text = log.get("1.0", tk.END).strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.state.status_text.set("Image log copied")

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
        self.notebook.select(self.progress_tab)

    def _prepare_progress_tab(self, files: list[str], selected_tools: dict[str, str] | None = None, title: str = "Run progress", job_identity: str = "", pipeline_mode: str = "", threads: int = 0, device: str = "") -> None:
        self._ensure_progress_context(title, job_identity)
        self.image_runs.clear()
        self.image_rows.clear()
        self._set_current_image_key("")
        self._set_active_image_key("")
        self.progress_selected_tools = dict(selected_tools or self.state.get_selected_tools())
        self._set_progress_count("current_total_images", len(files))
        self._set_progress_count("current_success_images", 0)
        self._set_progress_count("current_failed_images", 0)
        self._set_progress_count("current_running_images", 0)
        self._update_batch_summary()
        for child in self.image_list_frame.winfo_children():
            child.destroy()
        self._clear_log()
        self.detail_chart.reset()
        self.gpu_chart.reset()
        self._set_detail_title("Select an input image")
        self._reset_step_summary()
        if pipeline_mode:
            self.job_preset_text.set(pipeline_mode)
        if threads:
            self.job_threads_text.set(str(threads))
        if device:
            self.job_device_text.set(device.upper())
        for idx, path in enumerate(files, start=1):
            self._create_image_run(path, idx, len(files))
        if files:
            self._select_image(files[0])
        self._save_active_progress_context()

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
            "Failed": "failed",
            "Paused": "pause",
            "Skipped": "pending",
            "Pending": "pending",
        }.get(status, "pending")
        if status == "Running":
            return None
        return self._make_icon(icon_name)

    def _apply_step_row_widgets(self, widgets: dict, stage: str, step: dict) -> None:
        status = str(step.get("status") or "Pending")
        tool = str(step.get("tool") or self.progress_selected_tools.get(stage, ""))
        duration = step.get("duration_sec")
        if duration is None:
            duration = step.get("elapsed_sec")
        icon = self._step_icon(status)
        if status == "Running":
            widgets["icon"].configure(image=self._spinner_frame() or "", text="", foreground=self._step_status_color(status))
        else:
            widgets["icon"].configure(image=icon if icon is not None else "", text="")
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
            self._create_image_run(input_file, len(self.image_runs) + 1, max(self._get_progress_count("current_total_images"), len(self.image_runs) + 1))
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
        
        context_id = getattr(self, "active_progress_context_id", "")
        for widget in (container, row, top, center, icon_label, title, status_label, arrow_label, bar, sep):
            widget.bind("<Button-1>", lambda _e, key=input_file, cid=context_id: (self._activate_progress_context(cid), self._select_image(key)))
            
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
        self._set_current_image_key(input_file)
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
        self._set_detail_title(f"{run['idx']}/{run['total']} {run['name']} - {run.get('stage', run['status'])}")
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
            self._create_image_run(input_file, len(self.image_runs) + 1, max(self._get_progress_count("current_total_images"), len(self.image_runs) + 1))
        run = self.image_runs[input_file]
        
        if stage_text is not None:
            run["stage"] = stage_text
            run["stage_detail"] = stage_text
            
        if status is not None:
            run["status"] = status
            display_text = run.get("stage", status) if status == "Running" else status
            self.image_rows[input_file]["status"].configure(text=display_text)
            icon_img = self._get_status_icon(status)
            if status == "Running":
                self.image_rows[input_file]["icon"].configure(image=self._spinner_frame() or "", text="")
            elif icon_img:
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
            self._set_detail_title(f"{run['idx']}/{run['total']} {run['name']} - {run.get('stage', run.get('status', 'Queued'))}")

    def _update_batch_summary(self) -> None:
        success = self._get_progress_count("current_success_images")
        total = self._get_progress_count("current_total_images")
        running = self._get_progress_count("current_running_images")
        failed = self._get_progress_count("current_failed_images")
        context = self._current_progress_context()
        if context is not None:
            context["batch_total_text"].set(f"Success: {success} / {total}")
            context["batch_running_text"].set(f"Running: {running}")
            context["batch_failed_text"].set(f"Failed: {failed}")
        self.state.batch_total_text.set(f"Success: {success} / {total}")
        self.state.batch_running_text.set(f"Running: {running}")
        self.state.batch_failed_text.set(f"Failed: {failed}")

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
            total = int(event.get("total", max(self._get_progress_count("current_total_images"), idx)))
            self._set_progress_count("current_total_images", max(self._get_progress_count("current_total_images"), total))
            self._set_active_image_key(key)
            self._set_progress_count("current_running_images", 1)
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
            total = max(int(current_run.get("total", self._get_progress_count("current_total_images")) or 1), 1)
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
            self._set_progress_count("current_running_images", 0)
            if success:
                self._set_progress_count("current_success_images", self._get_progress_count("current_success_images") + 1)
                self._log(f"Remote image done: {event.get('subject_id', key)} | OK")
                self._update_image_run(key, status="Done", percent=100, stage_text="Completed")
            else:
                self._set_progress_count("current_failed_images", self._get_progress_count("current_failed_images") + 1)
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
        total = max(int(current_run.get("total", self._get_progress_count("current_total_images")) or 1), 1)
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
        if self.state.run_target.get() == "Server":
            self.state.server_text.set("Server: connected")
        else:
            self.state.server_text.set("Server: local")

    def _on_image_start(self, input_file: str, idx: int, total: int) -> None:
        self._set_active_image_key(input_file)
        self._log(f"Starting image {idx}/{total}: {input_file}")
        self._set_progress_count("current_running_images", 1)
        self._update_batch_summary()
        self._update_image_run(input_file, status="Running", percent=0, stage_text="Starting")
        self._select_image(input_file)
        self.metrics_queue.put((getattr(self, "active_progress_context_id", ""), getattr(self, "active_image_key", ""), 0.0, 0, 0.0, "new image"))

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
        self._set_progress_count("current_running_images", 0)
        if result.success:
            self._set_progress_count("current_success_images", self._get_progress_count("current_success_images") + 1)
            row_status = "Done"
            pct = 100
        else:
            self._set_progress_count("current_failed_images", self._get_progress_count("current_failed_images") + 1)
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
        self.metrics_queue.put((getattr(self, "active_progress_context_id", ""), target_key, cpu_pct, ram_bytes, gpu_pct, container_name))

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
        self._set_button_busy(getattr(self, "run_button", None), False)
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
            if isinstance(item, tuple) and len(item) == 3:
                context_id, image_key, line_str = item
                context = self.progress_contexts.get(str(context_id))
                if context is None:
                    continue
                if image_key and image_key in context.get("image_runs", {}):
                    run = context["image_runs"][image_key]
                    run["logs"].append(line_str)
                    run["logs"] = run["logs"][-2500:]
                if not image_key or image_key == context.get("current_image_key", ""):
                    self._append_log_to_context(context, line_str)
            elif isinstance(item, tuple):
                image_key, line_str = item
                if image_key and image_key in self.image_runs:
                    run = self.image_runs[image_key]
                    run["logs"].append(line_str)
                    run["logs"] = run["logs"][-2500:]

                if not image_key or image_key == self.current_image_key:
                    self._append_log(line_str)
            else:
                image_key, line_str = None, item
                self._append_log(line_str)

        while True:
            try:
                item = self.metrics_queue.get_nowait()
            except queue.Empty:
                break
            if len(item) == 6:
                context_id, image_key, cpu_pct, ram_bytes, gpu_pct, container_name = item
                context = self.progress_contexts.get(str(context_id))
                if context is None:
                    continue
                if not image_key or image_key == context.get("current_image_key", ""):
                    context["detail_chart"].add(cpu_pct, ram_bytes, container_name)
                    gpu = max(gpu_pct or 0.0, 0.0)
                    context["gpu_chart"].add(gpu, f"{gpu:.1f}%")
                    if context_id == self.active_progress_context_id:
                        cpu = max(cpu_pct or 0.0, 0.0)
                        ram_mib = (ram_bytes or 0) / (1024 * 1024)
                        self.state.cpu_text.set(f"CPU {cpu:.0f}%")
                        self.state.ram_text.set(f"RAM {ram_mib / 1024:.2f} GB" if ram_mib >= 1024 else f"RAM {ram_mib:.0f} MB")
            elif len(item) == 5:
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
        self.log_queue.put((getattr(self, "active_progress_context_id", ""), getattr(self, "active_image_key", ""), line))

    def _append_log_to_context(self, context: dict, line: str) -> None:
        log_text = context.get("log_text")
        if log_text is None:
            return
        log_text.configure(state=tk.NORMAL)
        log_text.insert(tk.END, line + "\n")
        log_text.see(tk.END)
        log_text.configure(state=tk.DISABLED)

    def _append_log(self, line: str) -> None:
        context = self._current_progress_context()
        if context is not None:
            self._append_log_to_context(context, line)
            return
        if getattr(self, "log_text", None) is None:
            return
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _clear_log(self) -> None:
        if getattr(self, "log_text", None) is None:
            return
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)
