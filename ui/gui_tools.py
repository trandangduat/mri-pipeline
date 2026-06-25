"""Tool/image management mixin for the MRI Pipeline GUI."""

from __future__ import annotations

import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from pipeline_runner import (
    PROJECT_ROOT,
    STAGE_LABELS,
    TOOL_DEFS,
    ensure_image,
    image_exists,
    is_tool_enabled,
    tool_display_name,
    tool_key_from_display,
)
from remote.remote_runner import RemoteRunConfig, RemoteRunner
from ui.components.dialogs import append_dialog_log, build_image_dialog


class ToolsMixin:
    def _check_images_action(self) -> None:
        if not self._validate_configuration():
            messagebox.showerror("Configuration incomplete", self.state.config_status.get())
            return
        if self.state.run_target.get() == "Server":
            runner = self._build_remote_runner()
            if runner and self._ensure_remote_images_with_dialog(runner):
                self.remote_runner = runner
                self._log("Remote image preflight completed successfully.")
        else:
            if self._ensure_local_images_with_dialog():
                self._log("Local image preflight completed successfully.")

    def _tool_image(self, tool_key: str) -> str:
        return str(TOOL_DEFS.get(tool_key, {}).get("image", ""))

    def _all_enabled_images(self) -> list[str]:
        images: list[str] = []
        for tool_key, tool in TOOL_DEFS.items():
            if not is_tool_enabled(tool_key):
                continue
            image = str(tool.get("image", ""))
            if image and image not in images:
                images.append(image)
        return images

    def _tool_status(self, tool_key: str, target: str | None = None) -> str:
        if not tool_key:
            return "Skipped"
        if not is_tool_enabled(tool_key):
            return "Disabled"
        image = self._tool_image(tool_key)
        if not image:
            return "Unknown"
        target = target or self.state.run_target.get()
        return self.tool_image_statuses.setdefault(target, {}).get(image, "Unknown")

    def _status_label_text(self, status: str) -> str:
        return "Not checked" if status == "Unknown" else status

    def _tool_status_icon(self, status: str) -> str:
        return {
            "Installed": "✓",
            "Missing": "✕",
            "Downloading": "↓",
            "Checking": "…",
            "Disabled": "",
            "Skipped": "",
            "Error": "!",
            "Unknown": "?",
        }.get(status, "?")

    def _tool_check_text(self, tool_key: str) -> str:
        return "[x]" if tool_key in self.tools_checked_tools else "[ ]"

    def _tool_status_icon_image(self, status: str) -> tk.PhotoImage | None:
        icon_name = {
            "Installed": "success",
            "Missing": "failed",
            "Downloading": "running",
            "Checking": "running",
            "Error": "failed",
            "Disabled": None,
            "Skipped": None,
            "Unknown": "pending",
        }.get(status, "pending")
        if not icon_name:
            return None
        key = f"tool_status_{icon_name}"
        if key in self.toolbar_icons:
            return self.toolbar_icons[key]
        icon_path = Path(__file__).parent / "icons" / f"{icon_name}.png"
        if not icon_path.exists():
            return None
        try:
            img = tk.PhotoImage(file=str(icon_path))
            self.toolbar_icons[key] = img
            return img
        except Exception:
            return None

    def _tools_checkbox_enabled(self, tool_key: str, status: str | None = None) -> bool:
        if not is_tool_enabled(tool_key):
            return False
        status = status or self._tool_status(tool_key)
        return status != "Installed"

    def _update_tools_download_button(self) -> None:
        button = getattr(self, "tools_download_button", None)
        if button is None:
            return
        enabled = any(self._tools_checkbox_enabled(tool) for tool in self.tools_checked_tools)
        button.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def _status_color(self, status: str) -> str:
        return {
            "Installed": "#16a34a",
            "Missing": "#dc2626",
            "Downloading": "#2563eb",
            "Checking": "#2563eb",
            "Disabled": "#64748b",
            "Skipped": "#64748b",
            "Error": "#dc2626",
        }.get(status, "#64748b")

    def _set_image_status(self, target: str, image: str, status: str) -> None:
        if not image:
            return
        self.tool_image_statuses.setdefault(target, {})[image] = status
        self._refresh_tools_tree()
        self._update_config_tool_status_labels()

    def _refresh_tools_tree(self) -> None:
        table = getattr(self, "tools_table_frame", None)
        if table is None:
            return
        target = self.state.run_target.get()
        for idx, (tool_key, tool) in enumerate(TOOL_DEFS.items(), start=0):
            row = 2 + idx * 2
            stage = str(tool.get("stage", ""))
            image = str(tool.get("image", ""))
            status = self._tool_status(tool_key, target)
            enabled = self._tools_checkbox_enabled(tool_key, status)
            if not enabled:
                self.tools_checked_tools.discard(tool_key)
            var = self.tools_check_vars.get(tool_key)
            if var is None:
                var = tk.BooleanVar(value=tool_key in self.tools_checked_tools)
                self.tools_check_vars[tool_key] = var
            var.set(tool_key in self.tools_checked_tools)

            def on_check(key=tool_key, check_var=var) -> None:
                if check_var.get():
                    self.tools_checked_tools.add(key)
                else:
                    self.tools_checked_tools.discard(key)
                self._refresh_tools_tree()
                self._update_tools_download_button()

            widgets = self.tools_row_widgets.get(tool_key)
            if widgets is None:
                cells = []
                for col in range(5):
                    cell = tk.Frame(table, padx=4, pady=2, bg="#fafafa")
                    cell.grid(row=row, column=col, sticky=tk.NSEW, padx=0, pady=1)
                    cells.append(cell)
                check = ttk.Checkbutton(
                    cells[0],
                    variable=var,
                    command=on_check,
                )
                check.pack(anchor=tk.W)
                stage_label = tk.Label(cells[1], anchor=tk.W, bg="#fafafa", fg="#111827")
                stage_label.pack(fill=tk.BOTH, expand=True)
                tool_label = tk.Label(cells[2], anchor=tk.W, bg="#fafafa", fg="#111827")
                tool_label.pack(fill=tk.BOTH, expand=True)
                image_label = tk.Label(cells[3], anchor=tk.W, bg="#fafafa", fg="#475569")
                image_label.pack(fill=tk.BOTH, expand=True)
                status_label = tk.Label(cells[4], text="", anchor=tk.CENTER, bg="#fafafa", fg="#111827")
                status_label.pack(anchor=tk.W)
                
                sep = ttk.Separator(table, orient=tk.HORIZONTAL)
                sep.grid(row=row+1, column=0, columnspan=5, sticky=tk.EW, pady=(2, 2))
                
                widgets = {
                    "cells": cells,
                    "check": check,
                    "stage": stage_label,
                    "tool": tool_label,
                    "image": image_label,
                    "status": status_label,
                    "sep": sep,
                }
                self.tools_row_widgets[tool_key] = widgets

            row_selected = tool_key in self.tools_checked_tools
            bg = "#cbd5e1" if row_selected else "#fafafa"
            for cell in widgets["cells"]:
                cell.configure(bg=bg)
                
            style = ttk.Style()
            style.configure("Selected.TCheckbutton", background="#cbd5e1")
            style.configure("Unselected.TCheckbutton", background="#fafafa")
            check_style = "Selected.TCheckbutton" if row_selected else "Unselected.TCheckbutton"
            
            widgets["check"].configure(state=tk.NORMAL if enabled else tk.DISABLED, style=check_style)
            widgets["stage"].configure(text=STAGE_LABELS.get(stage, stage), bg=bg)
            widgets["tool"].configure(text=tool_display_name(tool_key), bg=bg)
            widgets["image"].configure(text=image, bg=bg)
            icon = self._tool_status_icon_image(status)
            if icon is not None:
                widgets["status"].configure(image=icon, text=f"  {status}", compound=tk.LEFT, bg=bg, fg=self._status_color(status), font=("Inter", 9))
            else:
                widgets["status"].configure(image="", text=self._tool_status_icon(status), compound=tk.CENTER, bg=bg, fg=self._status_color(status), font=("Inter", 10, "bold"))
            self.tools_status_icon_labels[tool_key] = widgets["status"]
        self._update_tools_download_button()

    def _on_tools_tree_click(self, event) -> None:
        tree = getattr(self, "tools_tree", None)
        if tree is None:
            return
        region = tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        column = tree.identify_column(event.x)
        if column != "#1":
            return
        item = tree.identify_row(event.y)
        if not item or item not in TOOL_DEFS or not is_tool_enabled(item):
            return
        if item in self.tools_checked_tools:
            self.tools_checked_tools.remove(item)
        else:
            self.tools_checked_tools.add(item)
        self._refresh_tools_tree()
        return "break"

    def _toggle_tools_log(self) -> None:
        body = getattr(self, "tools_log_body", None)
        label = getattr(self, "tools_log_toggle_text", None)
        if body is None:
            return
        self.tools_log_visible = not self.tools_log_visible
        if self.tools_log_visible:
            body.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
            if label is not None:
                label.set("Hide Image Log")
        else:
            body.pack_forget()
            if label is not None:
                label.set("Show Image Log")

    def _append_tools_log(self, line: str) -> None:
        log = getattr(self, "tools_log_text", None)
        if log is None:
            return
        log.configure(state=tk.NORMAL)
        log.insert(tk.END, line + "\n")
        log.see(tk.END)
        log.configure(state=tk.DISABLED)

    def _selected_tool_rows(self) -> list[str]:
        return [tool for tool in self.tools_checked_tools if tool in TOOL_DEFS]

    def _build_image_remote_runner(self) -> RemoteRunner | None:
        ssh_config = self._build_ssh_config()
        if ssh_config is None:
            return None
        return RemoteRunner(
            RemoteRunConfig(
                ssh=ssh_config,
                remote_workspace=self.state.remote_workspace.get().strip() or "~/mri-remote-jobs",
                remote_python=self.state.remote_python.get().strip() or "python3",
                output_dir=self.state.output_dir.get().strip(),
                license_dir=self.state.license_dir.get().strip(),
                export_config=self.state.get_export_config(),
                stats_vector_config=self.state.get_stats_vector_config(),
                selected_tools={},
            ),
            on_log=self._tools_remote_log_event,
        )

    def _tools_remote_log_event(self, line: str) -> None:
        keep = (
            "Connecting SSH", "SSH connected", "Base Python", "Remote venv:", "Venv Python", "Venv pip",
            "Creating remote venv", "Using remote venv", "Installing", "Installed:", "Missing:", "Downloading:", "Failed:",
            "Requirement", "Collecting", "Using cached", "Downloading ", "Successfully", "ERROR:", "WARNING:",
        )
        if line.startswith(keep):
            self.root.after(0, lambda l=line: self._append_tools_log(l))
        status_prefixes = {
            "Downloading: ": "Downloading",
            "Installed: ": "Installed",
            "Missing: ": "Missing",
            "Failed: ": "Error",
        }
        for prefix, status in status_prefixes.items():
            if line.startswith(prefix):
                image = line[len(prefix):].strip().split()[0]
                self.root.after(0, lambda i=image, s=status: self._set_image_status("Server", i, s))
                break

    def _set_python_env_status(self, status: str) -> None:
        self.python_env_status.set(status)
        label = getattr(self, "python_env_status_label", None)
        icon_label = getattr(self, "python_env_status_icon_label", None)
        lower = status.lower()
        if "checking" in lower or "installing" in lower:
            color = "#2563eb"
            icon_name = "running"
        elif "ok" in lower or "ready" in lower or "installed" in lower:
            color = "#16a34a"
            icon_name = "success"
        elif "not checked" in lower:
            color = "#64748b"
            icon_name = "pending"
        elif "missing" in lower or "failed" in lower or "error" in lower or "incomplete" in lower or "not configured" in lower:
            color = "#dc2626"
            icon_name = "failed"
        else:
            color = "#64748b"
            icon_name = "pending"
        if label is not None:
            label.configure(foreground=color)
        if icon_label is not None:
            icon = self._make_icon(icon_name)
            icon_label.configure(image=icon if icon is not None else "")

    def _check_python_environment(self) -> None:
        target = self.state.run_target.get()
        self._set_python_env_status("Checking...")
        self._append_tools_log(f"Checking Python: {target}")

        def worker() -> None:
            if target == "Local":
                try:
                    version = subprocess.run([sys.executable, "--version"], capture_output=True, text=True, timeout=30)
                    pip = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, text=True, timeout=30)
                    py_text = (version.stdout or version.stderr).strip() or "Python not found"
                    pip_text = (pip.stdout or pip.stderr).strip() or "pip not found"
                    python_ok = version.returncode == 0
                    pip_ok = pip.returncode == 0
                    self.root.after(0, lambda t=py_text, ok=python_ok: self._append_tools_log(("Python OK: " if ok else "Python missing: ") + t))
                    self.root.after(0, lambda t=pip_text, ok=pip_ok: self._append_tools_log(("pip OK: " if ok else "pip missing: ") + t))
                    if python_ok and pip_ok:
                        status = "Local: Python OK, pip OK"
                    elif python_ok:
                        status = "Local: Python OK, pip missing"
                    else:
                        status = "Local: Python missing"
                    self.root.after(0, lambda s=status: self._set_python_env_status(s))
                except Exception as exc:
                    self.root.after(0, lambda e=exc: self._append_tools_log(f"Python check failed: {type(e).__name__}: {e}"))
                    self.root.after(0, lambda: self._set_python_env_status("Local: Error"))
                return

            runner = self._build_image_remote_runner()
            if runner is None:
                self.root.after(0, lambda: self._set_python_env_status("Not configured"))
                return
            try:
                details = runner.check_python_details()
                venv_path = str(details.get("venv_path") or "")
                base_ok = bool(details.get("base_python_ok"))
                venv_exists = bool(details.get("venv_exists"))
                python_ok = bool(details.get("venv_python_ok"))
                pip_ok = bool(details.get("venv_pip_ok"))
                if python_ok and pip_ok:
                    status = "Server: venv ready"
                elif not base_ok:
                    status = "Server: base Python missing"
                elif not venv_exists:
                    status = "Server: venv not created"
                else:
                    status = "Server: venv incomplete"
                self.root.after(0, lambda p=venv_path: self.python_env_hint.set(p))
                self.root.after(0, lambda s=status: self._set_python_env_status(s))
            except Exception as exc:
                self.root.after(0, lambda e=exc: self._append_tools_log(f"Python check failed: {type(e).__name__}: {e}"))
                self.root.after(0, lambda: self._set_python_env_status("Server: Error"))

        threading.Thread(target=worker, daemon=True).start()

    def _install_python_requirements(self) -> None:
        target = self.state.run_target.get()
        requirements = PROJECT_ROOT / "requirements.txt"
        if not requirements.exists():
            messagebox.showerror("Missing requirements", f"requirements.txt not found: {requirements}")
            return
        self._set_python_env_status("Installing...")
        action = "Installing Python packages from requirements.txt"
        if target == "Server":
            action = f"Creating/updating remote venv and packages: {self._remote_venv_display_path()}"
        self._append_tools_log(f"{action}: {target}")

        def worker() -> None:
            if target == "Local":
                try:
                    pip_check = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, text=True, timeout=30)
                    if pip_check.returncode != 0:
                        self.root.after(0, lambda: self._append_tools_log("pip missing: trying ensurepip..."))
                        subprocess.run([sys.executable, "-m", "ensurepip", "--user", "--upgrade"], capture_output=True, text=True, timeout=120)
                    proc = subprocess.run(
                        [sys.executable, "-m", "pip", "install", "--user", "-r", str(requirements)],
                        capture_output=True,
                        text=True,
                        timeout=900,
                    )
                    ok = proc.returncode == 0
                    msg = "Python packages installed: Local" if ok else "Python packages failed: Local"
                    self.root.after(0, lambda m=msg: self._append_tools_log(m))
                    if not ok:
                        tail = " | ".join((proc.stderr or proc.stdout).strip().splitlines()[-3:])
                        self.root.after(0, lambda t=tail: self._append_tools_log(f"pip error: {t}"))
                    self.root.after(0, lambda: self._set_python_env_status("Local: Python packages installed" if ok else "Local: Package install failed"))
                except Exception as exc:
                    self.root.after(0, lambda e=exc: self._append_tools_log(f"Install failed: {type(e).__name__}: {e}"))
                    self.root.after(0, lambda: self._set_python_env_status("Local: Package install failed"))
                return

            runner = self._build_image_remote_runner()
            if runner is None:
                self.root.after(0, lambda: self._set_python_env_status("Not configured"))
                return
            try:
                ok = runner.install_python_requirements()
                msg = "Remote venv packages installed: Server" if ok else "Remote venv package install failed: Server"
                self.root.after(0, lambda m=msg: self._append_tools_log(m))
                self.root.after(0, lambda: self._set_python_env_status("Server: venv ready" if ok else "Server: venv package install failed"))
            except Exception as exc:
                self.root.after(0, lambda e=exc: self._append_tools_log(f"Install failed: {type(e).__name__}: {e}"))
                self.root.after(0, lambda: self._set_python_env_status("Server: Package install failed"))

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_tool_image_statuses(self) -> None:
        target = self.state.run_target.get()
        images = self._all_enabled_images()
        if not images:
            self._append_tools_log("No enabled tool images to check.")
            return
        for image in images:
            self.tool_image_statuses.setdefault(target, {})[image] = "Checking"
        self._refresh_tools_tree()
        self._update_config_tool_status_labels()

        def worker() -> None:
            if target == "Local":
                for image in images:
                    self.root.after(0, lambda i=image: self._append_tools_log(f"Checking: {i}"))
                    status = "Installed" if image_exists(image) else "Missing"
                    self.root.after(0, lambda i=image, s=status: self._set_image_status("Local", i, s))
                    self.root.after(0, lambda i=image, s=status: self._append_tools_log(f"{s}: {i}"))
                return

            runner = self._build_image_remote_runner()
            if runner is None:
                for image in images:
                    self.root.after(0, lambda i=image: self._set_image_status("Server", i, "Unknown"))
                return
            try:
                statuses = runner.check_image_statuses(images)
                for image, installed in statuses.items():
                    status = "Installed" if installed else "Missing"
                    self.root.after(0, lambda i=image, s=status: self._set_image_status("Server", i, s))
            except Exception as exc:
                self.root.after(0, lambda e=exc: self._append_tools_log(f"Error: {type(e).__name__}: {e}"))
                for image in images:
                    self.root.after(0, lambda i=image: self._set_image_status("Server", i, "Error"))

        threading.Thread(target=worker, daemon=True).start()

    def _ensure_tool_images(self, tool_keys: list[str]) -> None:
        target = self.state.run_target.get()
        tool_keys = [tool for tool in dict.fromkeys(tool_keys) if tool in TOOL_DEFS and is_tool_enabled(tool)]
        if not tool_keys:
            self._append_tools_log("No enabled tools selected.")
            return
        for tool_key in tool_keys:
            self._set_image_status(target, self._tool_image(tool_key), "Downloading")

        def worker() -> None:
            if target == "Local":
                for tool_key in tool_keys:
                    image = self._tool_image(tool_key)
                    self.root.after(0, lambda i=image: self._append_tools_log(f"Downloading: {i}"))
                    ok, err, _ = ensure_image(tool_key, on_build_log=None)
                    status = "Installed" if ok or image_exists(image) else "Error"
                    self.root.after(0, lambda i=image, s=status: self._set_image_status("Local", i, s))
                    msg = f"Installed: {image}" if status == "Installed" else f"Failed: {image} {err}"
                    self.root.after(0, lambda m=msg: self._append_tools_log(m))
                return

            runner = self._build_image_remote_runner()
            if runner is None:
                for tool_key in tool_keys:
                    self.root.after(0, lambda i=self._tool_image(tool_key): self._set_image_status("Server", i, "Unknown"))
                return
            try:
                ok = runner.ensure_tool_images(tool_keys)
                images = [self._tool_image(tool) for tool in tool_keys]
                statuses = runner.check_image_statuses(images)
                for image, installed in statuses.items():
                    status = "Installed" if installed else ("Missing" if ok else "Error")
                    self.root.after(0, lambda i=image, s=status: self._set_image_status("Server", i, s))
            except Exception as exc:
                self.root.after(0, lambda e=exc: self._append_tools_log(f"Error: {type(e).__name__}: {e}"))
                for tool_key in tool_keys:
                    self.root.after(0, lambda i=self._tool_image(tool_key): self._set_image_status("Server", i, "Error"))

        threading.Thread(target=worker, daemon=True).start()

    def _ensure_checked_tool_images(self) -> None:
        self._ensure_tool_images(self._selected_tool_rows())

    def _select_all_tool_images(self) -> None:
        target = self.state.run_target.get()
        self.tools_checked_tools = {
            tool for tool in TOOL_DEFS
            if self._tools_checkbox_enabled(tool, self._tool_status(tool, target))
        }
        self._refresh_tools_tree()
        self._update_tools_download_button()

    def _unselect_all_tool_images(self) -> None:
        self.tools_checked_tools.clear()
        self._refresh_tools_tree()
        self._update_tools_download_button()

    def _select_missing_tool_images(self) -> None:
        target = self.state.run_target.get()
        self.tools_checked_tools = {
            tool for tool in TOOL_DEFS
            if self._tools_checkbox_enabled(tool, self._tool_status(tool, target))
            and self._tool_status(tool, target) in ("Missing", "Unknown", "Error")
        }
        self._refresh_tools_tree()
        self._update_tools_download_button()

    def _ensure_missing_tool_images(self) -> None:
        target = self.state.run_target.get()
        missing = [tool for tool in TOOL_DEFS if self._tool_status(tool, target) in ("Missing", "Unknown") and is_tool_enabled(tool)]
        self._ensure_tool_images(missing)

    def _update_config_tool_status_labels(self) -> None:
        if not getattr(self, "tool_status_labels", None):
            return
        target = self.state.run_target.get()
        for stage, label in self.tool_status_labels.items():
            tool_key = tool_key_from_display(self.state.tool_vars.get(stage).get()) if stage in self.state.tool_vars else ""
            status = self._tool_status(tool_key, target)
            label.configure(text=self._status_label_text(status), foreground=self._status_color(status))

    def _ensure_local_images_with_dialog(self) -> bool:
        dialog, log, progress, state = build_image_dialog(self.root, "Docker image preflight")
        required_tools = [tool for tool in dict.fromkeys(self.state.get_selected_tools().values()) if tool and is_tool_enabled(tool)]

        def worker() -> None:
            ok = True
            try:
                for tool_key in required_tools:
                    tool = TOOL_DEFS.get(tool_key, {})
                    image = tool.get("image", tool_key)
                    self.root.after(0, lambda i=image: append_dialog_log(log, f"Checking {i}"))
                    result, err, _build_time = ensure_image(
                        tool_key,
                        on_progress=None,
                        on_build_log=lambda line: self.root.after(0, lambda l=line: append_dialog_log(log, l)),
                    )
                    if not result:
                        ok = False
                        self.root.after(0, lambda e=err: append_dialog_log(log, f"ERROR: {e}"))
                        break
                    if not image_exists(image):
                        ok = False
                        self.root.after(0, lambda i=image: append_dialog_log(log, f"ERROR: image still missing after ensure: {i}"))
                        break
                    self.root.after(0, lambda i=image: append_dialog_log(log, f"OK image: {i}"))
            finally:
                state["ok"] = ok
                state["done"] = True
                self.root.after(0, progress.stop)
                self.root.after(0, dialog.destroy if ok else lambda: None)

        threading.Thread(target=worker, daemon=True).start()
        self.root.wait_window(dialog)
        return state["ok"]

    def _ensure_remote_images_with_dialog(self, runner: RemoteRunner) -> bool:
        dialog, log, progress, state = build_image_dialog(self.root, "Remote Docker image preflight")

        def worker() -> None:
            ok = True
            try:
                def on_line(line: str) -> None:
                    self.root.after(0, lambda l=line: append_dialog_log(log, l))

                runner.on_log = on_line
                if not runner.remote_job_dir:
                    runner.upload_job()
                ok = runner.ensure_images()
            except Exception as exc:
                ok = False
                err_msg = f"REMOTE IMAGE ERROR: {type(exc).__name__}: {exc}"
                self.root.after(0, lambda m=err_msg: append_dialog_log(log, m))
            finally:
                runner.on_log = self._remote_log_event
                state["ok"] = ok
                state["done"] = True
                self.root.after(0, progress.stop)
                self.root.after(0, dialog.destroy if ok else lambda: None)

        threading.Thread(target=worker, daemon=True).start()
        self.root.wait_window(dialog)
        return state["ok"]
