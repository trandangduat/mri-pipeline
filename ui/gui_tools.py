from __future__ import annotations
from ui.events import ui_events, EVENT_LOG_MESSAGE
"""Tool/image management mixin for the MRI Pipeline GUI."""


import json
import ssl
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import quote
from urllib.error import URLError
from urllib.request import Request, urlopen

from pipeline.config import (
    PROJECT_ROOT,
    STAGE_LABELS,
    TOOL_DEFS,
    is_tool_enabled,
    tool_display_name,
    tool_key_from_display,
)
from pipeline.docker_ops import (
    ensure_image,
    format_image_size,
    image_exists,
    image_size_bytes,
    remove_image,
)
from remote.remote_runner import RemoteRunConfig, RemoteRunner


class ToolsController:
    def __init__(self, gui):
        self.gui = gui
        
        # Tools state
        self.tab_frame = None
        self.table_frame = None
        self.log_text = None
        self.log_body = None
        self.log_toggle_text = None
        self.log_visible = False
        self.checked_tools = set()
        self.check_vars = {}
        self.status_icon_labels = {}
        self.python_env_check_button = None
        self.python_env_install_button = None
        self.refresh_button = None
        self.select_all_button = None
        self.unselect_all_button = None
        self.select_missing_button = None
        self.download_button = None
        self.delete_button = None
        self.row_widgets = {}
        self.python_env_status = tk.StringVar(value="Not checked")
        self.python_env_hint = tk.StringVar(value=sys.executable or "")
        self.python_env_status_icon_label = None
        self.python_env_status_label = None
        self.image_statuses = {"Local": {}, "Server": {}}
        self.image_sizes = {"Local": {}, "Server": {}}
        self.image_installed_sizes = {"Local": {}, "Server": {}}
        self.hub_size_loading = False
        self.status_labels = {}
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

    def _docker_hub_tag_url(self, image: str) -> str | None:
        image = image.split("@", 1)[0]
        if "/" not in image:
            namespace = "library"
            repo_tag = image
        else:
            first, rest = image.split("/", 1)
            if "." in first or ":" in first or first == "localhost":
                if first not in {"docker.io", "registry-1.docker.io", "index.docker.io"} or "/" not in rest:
                    return None
                namespace, repo_tag = rest.split("/", 1)
            else:
                namespace = first
                repo_tag = rest
        repo, tag = repo_tag.rsplit(":", 1) if ":" in repo_tag else (repo_tag, "latest")
        if not namespace or not repo or not tag:
            return None
        return f"https://hub.docker.com/v2/repositories/{quote(namespace)}/{quote(repo)}/tags/{quote(tag)}"

    def _fetch_docker_hub_image_size(self, image: str) -> str:
        url = self._docker_hub_tag_url(image)
        if not url:
            return "-"
        try:
            req = Request(url, headers={"User-Agent": "mri-pipeline-gui/1.0"})
            try:
                with urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except URLError as exc:
                if not isinstance(getattr(exc, "reason", None), ssl.SSLCertVerificationError):
                    raise
                context = ssl._create_unverified_context()
                with urlopen(req, timeout=10, context=context) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            size = data.get("full_size")
            return format_image_size(int(size)) if size is not None else "-"
        except Exception:
            return "-"

    def _set_hub_image_size(self, image: str, size: str) -> None:
        if not image:
            return
        for target in ("Local", "Server"):
            sizes = self.image_sizes.setdefault(target, {})
            if sizes.get(image, "-") in {"-", "Loading..."}:
                sizes[image] = size
        self._refresh_tree()

    def _preload_docker_hub_image_sizes(self) -> None:
        if getattr(self, "tools_hub_size_loading", False):
            return
        images = self._all_enabled_images()
        missing = [
            image for image in images
            if all(self.image_sizes.setdefault(target, {}).get(image, "-") == "-" for target in ("Local", "Server"))
        ]
        if not missing:
            return
        self.hub_size_loading = True
        for image in missing:
            for target in ("Local", "Server"):
                self.image_sizes.setdefault(target, {})[image] = "Loading..."
        self._refresh_tree()

        def worker() -> None:
            try:
                for image in missing:
                    size = self._fetch_docker_hub_image_size(image)
                    self.gui.root.after(0, lambda i=image, s=size: self._set_hub_image_size(i, s))
            finally:
                self.gui.root.after(0, lambda: setattr(self, "tools_hub_size_loading", False))

        threading.Thread(target=worker, daemon=True).start()

    def _tools_for_image(self, image: str) -> list[str]:
        return [
            tool_key for tool_key, tool in TOOL_DEFS.items()
            if is_tool_enabled(tool_key) and str(tool.get("image", "")) == image
        ]

    def _selected_images(self, statuses: set[str] | None = None) -> list[str]:
        target = self.gui.state.run_target.get()
        if target == "Server" and not self.gui._server_connected():
            return []
        images: list[str] = []
        for tool_key in self.checked_tools:
            image = self._tool_image(tool_key)
            if not image or image in images:
                continue
            if statuses is not None and self.image_statuses.setdefault(target, {}).get(image, "Unknown") not in statuses:
                continue
            images.append(image)
        return images

    def _representative_tools_for_images(self, images: list[str]) -> list[str]:
        tools: list[str] = []
        for image in dict.fromkeys(images):
            for tool_key, tool in TOOL_DEFS.items():
                if is_tool_enabled(tool_key) and str(tool.get("image", "")) == image:
                    tools.append(tool_key)
                    break
        return tools

    def _tool_status(self, tool_key: str, target: str | None = None) -> str:
        if not tool_key:
            return "Skipped"
        if not is_tool_enabled(tool_key):
            return "Disabled"
        image = self._tool_image(tool_key)
        if not image:
            return "Unknown"
        target = target or self.gui.state.run_target.get()
        return self.image_statuses.setdefault(target, {}).get(image, "Unknown")

    def _status_label_text(self, status: str) -> str:
        return "Not checked" if status == "Unknown" else status

    def _tool_status_icon(self, status: str) -> str:
        return {
            "Installed": "✓",
            "Missing": "✕",
            "Downloading": "↓",
            "Checking": "…",
            "Deleting": "…",
            "Disabled": "",
            "Skipped": "",
            "Error": "!",
            "Unknown": "?",
        }.get(status, "?")

    def _tool_status_icon_image(self, status: str, small: bool = False) -> tk.PhotoImage | None:
        if self.gui._is_busy_status(status):
            return None
        icon_name = {
            "Installed": "success",
            "Missing": "failed",
            "Error": "failed",
            "Disabled": None,
            "Skipped": None,
            "Unknown": "pending",
        }.get(status, "pending")
        if not icon_name:
            return None
        key = f"tool_status_{icon_name}_{'small' if small else 'normal'}"
        if key in self.gui.toolbar_icons:
            return self.gui.toolbar_icons[key]
        icon_path = Path(__file__).parent / "icons" / f"{icon_name}.png"
        if not icon_path.exists():
            return None
        try:
            if small:
                try:
                    from PIL import Image, ImageTk

                    img = Image.open(icon_path).convert("RGBA").resize((14, 14), resample=Image.BICUBIC)
                    photo = ImageTk.PhotoImage(img)
                    self.gui.toolbar_icons[key] = photo
                    return photo
                except Exception:
                    pass
            img = tk.PhotoImage(file=str(icon_path))
            if small:
                img = img.subsample(2, 2)
            self.gui.toolbar_icons[key] = img
            return img
        except Exception:
            return None

    def _checkbox_enabled(self, tool_key: str, status: str | None = None) -> bool:
        if not is_tool_enabled(tool_key):
            return False
        if self.gui.state.run_target.get() == "Server" and not self.gui._server_connected():
            return False
        status = status or self._tool_status(tool_key)
        return status not in {"Disabled", "Skipped", "Checking", "Downloading", "Deleting"}

    def _update_download_button(self) -> None:
        self._update_action_buttons()

    def _update_action_buttons(self) -> None:
        download_button = getattr(self, "tools_download_button", None)
        delete_button = getattr(self, "tools_delete_button", None)
        remote_ready = self.gui._remote_actions_enabled()
        download_enabled = remote_ready and bool(self._selected_images({"Missing", "Unknown", "Error"}))
        delete_enabled = remote_ready and bool(self._selected_images({"Installed"}))
        if download_button is not None:
            if not self.gui._is_button_busy(download_button):
                download_button.configure(state=tk.NORMAL if download_enabled else tk.DISABLED)
        if delete_button is not None:
            if not self.gui._is_button_busy(delete_button):
                delete_button.configure(state=tk.NORMAL if delete_enabled else tk.DISABLED)

    def _status_color(self, status: str) -> str:
        return {
            "Installed": "#16a34a",
            "Missing": "#dc2626",
            "Downloading": "#2563eb",
            "Checking": "#2563eb",
            "Deleting": "#f97316",
            "Disabled": "#64748b",
            "Skipped": "#64748b",
            "Error": "#dc2626",
        }.get(status, "#64748b")

    def _compressed_image_size_text(self, target: str, image: str) -> str:
        return self.image_sizes.setdefault(target, {}).get(image, "-")

    def _installed_image_size_text(self, target: str, image: str) -> str:
        return self.image_installed_sizes.setdefault(target, {}).get(image, "-")

    def _set_installed_image_size(self, target: str, image: str, size: str) -> None:
        if not image:
            return
        self.image_installed_sizes.setdefault(target, {})[image] = size
        self._refresh_tree()

    def _set_image_status(self, target: str, image: str, status: str) -> None:
        if not image:
            return
        self.image_statuses.setdefault(target, {})[image] = status
        self._refresh_tree()
        self._update_config_status_labels()
        self.gui._validate_configuration()

    def _refresh_tree(self) -> None:
        table = getattr(self, "tools_table_frame", None)
        if table is None:
            return
        target = self.gui.state.run_target.get()
        for idx, (tool_key, tool) in enumerate(TOOL_DEFS.items(), start=0):
            row = 2 + idx * 2
            stage = str(tool.get("stage", ""))
            image = str(tool.get("image", ""))
            status = self._tool_status(tool_key, target)
            enabled = self._checkbox_enabled(tool_key, status)
            if not enabled:
                self.checked_tools.discard(tool_key)
            var = self.check_vars.get(tool_key)
            if var is None:
                var = tk.BooleanVar(value=tool_key in self.checked_tools)
                self.check_vars[tool_key] = var
            var.set(tool_key in self.checked_tools)

            def on_check(key=tool_key, check_var=var) -> None:
                group = self._tools_for_image(self._tool_image(key))
                if check_var.get():
                    self.checked_tools.update(group)
                else:
                    self.checked_tools.difference_update(group)
                self._refresh_tree()
                self._update_download_button()

            widgets = self.row_widgets.get(tool_key)
            if widgets is None:
                cells = []
                for col in range(7):
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
                compressed_size_label = tk.Label(cells[4], anchor=tk.W, bg="#fafafa", fg="#475569")
                compressed_size_label.pack(fill=tk.BOTH, expand=True)
                installed_size_label = tk.Label(cells[5], anchor=tk.W, bg="#fafafa", fg="#475569")
                installed_size_label.pack(fill=tk.BOTH, expand=True)
                status_label = tk.Label(cells[6], text="", anchor=tk.CENTER, bg="#fafafa", fg="#111827")
                status_label.pack(anchor=tk.W)
                
                sep = ttk.Separator(table, orient=tk.HORIZONTAL)
                sep.grid(row=row+1, column=0, columnspan=7, sticky=tk.EW, pady=(2, 2))
                
                widgets = {
                    "cells": cells,
                    "check": check,
                    "stage": stage_label,
                    "tool": tool_label,
                    "image": image_label,
                    "compressed_size": compressed_size_label,
                    "installed_size": installed_size_label,
                    "status": status_label,
                    "sep": sep,
                }
                self.row_widgets[tool_key] = widgets

            row_selected = tool_key in self.checked_tools
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
            widgets["compressed_size"].configure(text=self._compressed_image_size_text(target, image), bg=bg)
            widgets["installed_size"].configure(text=self._installed_image_size_text(target, image), bg=bg)
            icon = self._tool_status_icon_image(status)
            if self.gui._is_busy_status(status):
                widgets["status"].configure(image=self.gui._spinner_frame() or "", text=f"  {status}", compound=tk.LEFT, bg=bg, fg=self._status_color(status), font=("Inter", 9))
            elif icon is not None:
                widgets["status"].configure(image=icon, text=f"  {status}", compound=tk.LEFT, bg=bg, fg=self._status_color(status), font=("Inter", 9))
            else:
                widgets["status"].configure(image="", text=self._tool_status_icon(status), compound=tk.CENTER, bg=bg, fg=self._status_color(status), font=("Inter", 10, "bold"))
            self.status_icon_labels[tool_key] = widgets["status"]
        self._update_download_button()

    def _toggle_log(self) -> None:
        body = getattr(self, "tools_log_body", None)
        label = getattr(self, "tools_log_toggle_text", None)
        if body is None:
            return
        self.log_visible = not self.log_visible
        if self.log_visible:
            body.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
            if label is not None:
                label.set("Hide Image Log")
        else:
            body.pack_forget()
            if label is not None:
                label.set("Show Image Log")

    def _append_log(self, line: str) -> None:
        log = getattr(self, "tools_log_text", None)
        if log is None:
            return
        log.configure(state=tk.NORMAL)
        log.insert(tk.END, line + "\n")
        log.see(tk.END)
        log.configure(state=tk.DISABLED)

    def _selected_rows(self) -> list[str]:
        return [tool for tool in self.checked_tools if tool in TOOL_DEFS]

    def _build_image_remote_runner(self) -> RemoteRunner | None:
        if self.gui.state.run_target.get() == "Server" and not self.gui._server_connected():
            return None
        ssh_config = self.gui._build_ssh_config()
        if ssh_config is None:
            return None
        return RemoteRunner(
            RemoteRunConfig(
                ssh=ssh_config,
                remote_workspace=self.gui.state.remote_workspace.get().strip() or "~/mri-remote-jobs",
                remote_python=self.gui.state.remote_python.get().strip() or "python3",
                output_dir=self.gui.state.output_dir.get().strip(),
                license_dir=self.gui.state.license_dir.get().strip(),
                ram_percent=int(self.gui.state.ram_percent.get()),
                export_config=self.gui.state.get_export_config(),
                stats_vector_config=self.gui.state.get_stats_vector_config(),
                selected_tools={},
            ),
            on_log=self._remote_log_event,
        )

    def _remote_log_event(self, line: str) -> None:
        keep = (
            "Connecting SSH", "SSH connected", "Base Python", "Remote venv:", "Venv Python", "Venv pip",
            "Creating remote venv", "Using remote venv", "Installing", "Installed:", "Missing:", "Downloading:", "Deleting:", "Deleted:", "Failed:",
            "Requirement", "Collecting", "Using cached", "Downloading ", "Successfully", "ERROR:", "WARNING:", "Docker:"
        )
        if line.startswith(keep):
            self.gui.root.after(0, lambda l=line: self._append_log(l))
        status_prefixes = {
            "Downloading: ": "Downloading",
            "Deleting: ": "Deleting",
            "Deleted: ": "Missing",
            "Installed: ": "Installed",
            "Missing: ": "Missing",
            "Failed: ": "Error",
        }
        for prefix, status in status_prefixes.items():
            if line.startswith(prefix):
                image = line[len(prefix):].strip().split()[0]
                self.gui.root.after(0, lambda i=image, s=status: self._set_image_status("Server", i, s))
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
            if icon_name == "running":
                icon_label.configure(image=self.gui._spinner_frame() or "", text="", foreground=color)
            else:
                icon = self.gui._make_icon(icon_name)
                icon_label.configure(image=icon if icon is not None else "", text="")

    def _check_python_environment(self) -> None:
        target = self.gui.state.run_target.get()
        if target == "Server" and not self.gui._require_remote_connection("checking the remote environment"):
            return
        self.gui._set_button_busy(getattr(self, "python_env_check_button", None), True, "Checking")
        self._set_python_env_status("Checking...")
        self._append_log(f"Checking Python: {target}")

        def worker() -> None:
            try:
                if target == "Local":
                    try:
                        version = subprocess.run([sys.executable, "--version"], capture_output=True, text=True, timeout=30)
                        pip = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, text=True, timeout=30)
                        py_text = (version.stdout or version.stderr).strip() or "Python not found"
                        pip_text = (pip.stdout or pip.stderr).strip() or "pip not found"
                        python_ok = version.returncode == 0
                        pip_ok = pip.returncode == 0
                        self.gui.root.after(0, lambda t=py_text, ok=python_ok: self._append_log(("Python OK: " if ok else "Python missing: ") + t))
                        self.gui.root.after(0, lambda t=pip_text, ok=pip_ok: self._append_log(("pip OK: " if ok else "pip missing: ") + t))
                        if python_ok and pip_ok:
                            status = "Local: Python OK, pip OK"
                        elif python_ok:
                            status = "Local: Python OK, pip missing"
                        else:
                            status = "Local: Python missing"
                        self.gui.root.after(0, lambda s=status: self._set_python_env_status(s))
                    except Exception as exc:
                        self.gui.root.after(0, lambda e=exc: self._append_log(f"Python check failed: {type(e).__name__}: {e}"))
                        self.gui.root.after(0, lambda: self._set_python_env_status("Local: Error"))
                    return

                runner = self._build_image_remote_runner()
                if runner is None:
                    self.gui.root.after(0, lambda: self._set_python_env_status("Not configured"))
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
                    self.gui.root.after(0, lambda p=venv_path: self.python_env_hint.set(p))
                    self.gui.root.after(0, lambda s=status: self._set_python_env_status(s))
                except Exception as exc:
                    self.gui.root.after(0, lambda e=exc: self._append_log(f"Python check failed: {type(e).__name__}: {e}"))
                    self.gui.root.after(0, lambda: self._set_python_env_status("Server: Error"))
            finally:
                self.gui.root.after(0, lambda: self.gui._set_button_busy(getattr(self, "python_env_check_button", None), False))

        threading.Thread(target=worker, daemon=True).start()

    def _install_python_requirements(self) -> None:
        target = self.gui.state.run_target.get()
        if target == "Server" and not self.gui._require_remote_connection("creating or updating remote packages"):
            return
        requirements = PROJECT_ROOT / "requirements.txt"
        if not requirements.exists():
            messagebox.showerror("Missing requirements", f"requirements.txt not found: {requirements}")
            return
        self.gui._set_button_busy(getattr(self, "python_env_install_button", None), True, "Installing")
        self._set_python_env_status("Installing...")
        action = "Installing Python packages from requirements.txt"
        if target == "Server":
            action = f"Creating/updating remote venv and packages: {self.gui._remote_venv_display_path()}"
        self._append_log(f"{action}: {target}")

        def worker() -> None:
            try:
                if target == "Local":
                    try:
                        pip_check = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, text=True, timeout=30)
                        if pip_check.returncode != 0:
                            self.gui.root.after(0, lambda: self._append_log("pip missing: trying ensurepip..."))
                            subprocess.run([sys.executable, "-m", "ensurepip", "--user", "--upgrade"], capture_output=True, text=True, timeout=120)
                        proc = subprocess.run(
                            [sys.executable, "-m", "pip", "install", "--user", "-r", str(requirements)],
                            capture_output=True,
                            text=True,
                            timeout=900,
                        )
                        ok = proc.returncode == 0
                        msg = "Python packages installed: Local" if ok else "Python packages failed: Local"
                        self.gui.root.after(0, lambda m=msg: self._append_log(m))
                        if not ok:
                            tail = " | ".join((proc.stderr or proc.stdout).strip().splitlines()[-3:])
                            self.gui.root.after(0, lambda t=tail: self._append_log(f"pip error: {t}"))
                        self.gui.root.after(0, lambda: self._set_python_env_status("Local: Python packages installed" if ok else "Local: Package install failed"))
                    except Exception as exc:
                        self.gui.root.after(0, lambda e=exc: self._append_log(f"Install failed: {type(e).__name__}: {e}"))
                        self.gui.root.after(0, lambda: self._set_python_env_status("Local: Package install failed"))
                    return

                runner = self._build_image_remote_runner()
                if runner is None:
                    self.gui.root.after(0, lambda: self._set_python_env_status("Not configured"))
                    return
                try:
                    ok = runner.install_python_requirements()
                    msg = "Remote venv packages installed: Server" if ok else "Remote venv package install failed: Server"
                    self.gui.root.after(0, lambda m=msg: self._append_log(m))
                    self.gui.root.after(0, lambda: self._set_python_env_status("Server: venv ready" if ok else "Server: venv package install failed"))
                except Exception as exc:
                    self.gui.root.after(0, lambda e=exc: self._append_log(f"Install failed: {type(e).__name__}: {e}"))
                    self.gui.root.after(0, lambda: self._set_python_env_status("Server: Package install failed"))
            finally:
                self.gui.root.after(0, lambda: self.gui._set_button_busy(getattr(self, "python_env_install_button", None), False))

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_image_statuses(self) -> None:
        target = self.gui.state.run_target.get()
        if target == "Server" and not self.gui._require_remote_connection("refreshing remote Docker images"):
            return
        images = self._all_enabled_images()
        if not images:
            self._append_log("No enabled tool images to check.")
            return
        self.gui._set_button_busy(getattr(self, "tools_refresh_button", None), True, "Refreshing")
        for image in images:
            self.image_statuses.setdefault(target, {})[image] = "Checking"
        self._refresh_tree()
        self._update_config_status_labels()

        def worker() -> None:
            try:
                if target == "Local":
                    for image in images:
                        self.gui.root.after(0, lambda i=image: self._append_log(f"Checking: {i}"))
                        installed = image_exists(image)
                        status = "Installed" if installed else "Missing"
                        size = format_image_size(image_size_bytes(image)) if installed else "-"
                        self.gui.root.after(0, lambda i=image, s=status: self._set_image_status("Local", i, s))
                        self.gui.root.after(0, lambda i=image, z=size: self._set_installed_image_size("Local", i, z))
                        self.gui.root.after(0, lambda i=image, s=status: self._append_log(f"{s}: {i}"))
                    return

                runner = self._build_image_remote_runner()
                if runner is None:
                    for image in images:
                        self.gui.root.after(0, lambda i=image: self._set_image_status("Server", i, "Unknown"))
                    return
                try:
                    details = runner.check_image_details(images)
                    for image, data in details.items():
                        installed = bool(data.get("installed"))
                        status = "Installed" if installed else "Missing"
                        size = format_image_size(data.get("size") if isinstance(data.get("size"), int) else None) if installed else "-"
                        self.gui.root.after(0, lambda i=image, s=status: self._set_image_status("Server", i, s))
                        self.gui.root.after(0, lambda i=image, z=size: self._set_installed_image_size("Server", i, z))
                except Exception as exc:
                    self.gui.root.after(0, lambda e=exc: self._append_log(f"Error: {type(e).__name__}: {e}"))
                    for image in images:
                        self.gui.root.after(0, lambda i=image: self._set_image_status("Server", i, "Error"))
            finally:
                self.gui.root.after(0, lambda: (self.gui._set_button_busy(getattr(self, "tools_refresh_button", None), False), self._update_action_buttons()))

        threading.Thread(target=worker, daemon=True).start()

    def _ensure_tool_images(self, tool_keys: list[str]) -> None:
        target = self.gui.state.run_target.get()
        if target == "Server" and not self.gui._require_remote_connection("downloading remote Docker images"):
            return
        requested = [tool for tool in dict.fromkeys(tool_keys) if tool in TOOL_DEFS and is_tool_enabled(tool)]
        images = [self._tool_image(tool) for tool in requested if self._tool_image(tool)]
        tool_keys = self._representative_tools_for_images(images)
        if not tool_keys:
            self._append_log("No enabled tools selected.")
            return
        self.gui._set_button_busy(getattr(self, "tools_download_button", None), True, "Downloading")
        for tool_key in tool_keys:
            self._set_image_status(target, self._tool_image(tool_key), "Downloading")

        def worker() -> None:
            try:
                if target == "Local":
                    for tool_key in tool_keys:
                        image = self._tool_image(tool_key)
                        self.gui.root.after(0, lambda i=image: self._append_log(f"Downloading: {i}"))
                        ok, err, _ = ensure_image(tool_key, on_build_log=None)
                        status = "Installed" if ok or image_exists(image) else "Error"
                        size = format_image_size(image_size_bytes(image)) if status == "Installed" else "-"
                        self.gui.root.after(0, lambda i=image, s=status: self._set_image_status("Local", i, s))
                        self.gui.root.after(0, lambda i=image, z=size: self._set_installed_image_size("Local", i, z))
                        msg = f"Installed: {image}" if status == "Installed" else f"Failed: {image} {err}"
                        self.gui.root.after(0, lambda m=msg: self._append_log(m))
                    return

                runner = self._build_image_remote_runner()
                if runner is None:
                    for tool_key in tool_keys:
                        self.gui.root.after(0, lambda i=self._tool_image(tool_key): self._set_image_status("Server", i, "Unknown"))
                    return
                try:
                    ok = runner.ensure_tool_images(tool_keys)
                    images = [self._tool_image(tool) for tool in tool_keys]
                    details = runner.check_image_details(images)
                    for image, data in details.items():
                        installed = bool(data.get("installed"))
                        status = "Installed" if installed else ("Missing" if ok else "Error")
                        size = format_image_size(data.get("size") if isinstance(data.get("size"), int) else None) if installed else "-"
                        self.gui.root.after(0, lambda i=image, s=status: self._set_image_status("Server", i, s))
                        self.gui.root.after(0, lambda i=image, z=size: self._set_installed_image_size("Server", i, z))
                except Exception as exc:
                    self.gui.root.after(0, lambda e=exc: self._append_log(f"Error: {type(e).__name__}: {e}"))
                    for tool_key in tool_keys:
                        self.gui.root.after(0, lambda i=self._tool_image(tool_key): self._set_image_status("Server", i, "Error"))
            finally:
                self.gui.root.after(0, lambda: (self.gui._set_button_busy(getattr(self, "tools_download_button", None), False), self._update_action_buttons()))

        threading.Thread(target=worker, daemon=True).start()

    def _ensure_checked_images(self) -> None:
        self._ensure_tool_images(self._representative_tools_for_images(self._selected_images({"Missing", "Unknown", "Error"})))

    def _delete_checked_images(self) -> None:
        target = self.gui.state.run_target.get()
        if target == "Server" and not self.gui._require_remote_connection("deleting remote Docker images"):
            return
        images = self._selected_images({"Installed"})
        if not images:
            self._append_log("No installed images selected for delete.")
            return
        if not messagebox.askyesno("Delete Docker images", "Delete these Docker images?\n\n" + "\n".join(images)):
            return
        self.gui._set_button_busy(getattr(self, "tools_delete_button", None), True, "Deleting")
        for image in images:
            self._set_image_status(target, image, "Deleting")

        def worker() -> None:
            try:
                if target == "Local":
                    for image in images:
                        self.gui.root.after(0, lambda i=image: self._append_log(f"Deleting: {i}"))
                        ok, err = remove_image(image)
                        status = "Missing" if ok else "Error"
                        self.gui.root.after(0, lambda i=image, s=status: self._set_image_status("Local", i, s))
                        if ok:
                            self.gui.root.after(0, lambda i=image: self._set_installed_image_size("Local", i, "-"))
                            self.gui.root.after(0, lambda i=image: self._append_log(f"Deleted: {i}"))
                        else:
                            self.gui.root.after(0, lambda i=image, e=err: self._append_log(f"Failed: {i} {e}"))
                    return

                runner = self._build_image_remote_runner()
                if runner is None:
                    for image in images:
                        self.gui.root.after(0, lambda i=image: self._set_image_status("Server", i, "Unknown"))
                    return
                try:
                    results = runner.remove_images(images)
                    for image, (ok, err) in results.items():
                        status = "Missing" if ok else "Error"
                        self.gui.root.after(0, lambda i=image, s=status: self._set_image_status("Server", i, s))
                        if ok:
                            self.gui.root.after(0, lambda i=image: self._set_installed_image_size("Server", i, "-"))
                        elif err:
                            self.gui.root.after(0, lambda i=image, e=err: self._append_log(f"Failed: {i} {e}"))
                except Exception as exc:
                    self.gui.root.after(0, lambda e=exc: self._append_log(f"Error: {type(e).__name__}: {e}"))
                    for image in images:
                        self.gui.root.after(0, lambda i=image: self._set_image_status("Server", i, "Error"))
            finally:
                self.gui.root.after(0, lambda: (self.gui._set_button_busy(getattr(self, "tools_delete_button", None), False), self._update_action_buttons()))

        threading.Thread(target=worker, daemon=True).start()

    def _select_all_images(self) -> None:
        target = self.gui.state.run_target.get()
        self.checked_tools = {
            tool for tool in TOOL_DEFS
            if self._checkbox_enabled(tool, self._tool_status(tool, target))
        }
        self._refresh_tree()
        self._update_download_button()

    def _unselect_all_images(self) -> None:
        self.checked_tools.clear()
        self._refresh_tree()
        self._update_download_button()

    def _select_missing_images(self) -> None:
        target = self.gui.state.run_target.get()
        self.checked_tools = {
            tool for tool in TOOL_DEFS
            if self._checkbox_enabled(tool, self._tool_status(tool, target))
            and self._tool_status(tool, target) in ("Missing", "Unknown", "Error")
        }
        self._refresh_tree()
        self._update_download_button()

    def _ensure_missing_images(self) -> None:
        target = self.gui.state.run_target.get()
        missing = [tool for tool in TOOL_DEFS if self._tool_status(tool, target) in ("Missing", "Unknown") and is_tool_enabled(tool)]
        images = [self._tool_image(tool) for tool in missing if self._tool_image(tool)]
        self._ensure_tool_images(self._representative_tools_for_images(images))

    def _update_config_status_labels(self) -> None:
        if not getattr(self, "status_labels", None):
            return
        target = self.gui.state.run_target.get()
        for stage, label in self.status_labels.items():
            tool_val = self.gui.state.tool_vars.get(stage).get() if stage in self.gui.state.tool_vars else ""
            tool_key = tool_key_from_display(tool_val)
            status = self._tool_status(tool_key, target)
            if status == "Skipped":
                if tool_val == "Not available":
                    label.configure(image="", text="-  Not used", compound=tk.LEFT, foreground="#94a3b8")
                    if hasattr(self, "tool_step_labels") and stage in self.tool_step_labels:
                        self.tool_step_labels[stage].configure(fg="#94a3b8")
                else:
                    optional = stage in getattr(self, "OPTIONAL_STAGES", set())
                    label.configure(image="", text="-  Optional" if optional else "", compound=tk.LEFT, foreground=self._status_color(status))
                    if hasattr(self, "tool_step_labels") and stage in self.tool_step_labels:
                        self.tool_step_labels[stage].configure(fg="#111827")
                continue
            
            if hasattr(self, "tool_step_labels") and stage in self.tool_step_labels:
                self.tool_step_labels[stage].configure(fg="#111827")
                
            icon = self._tool_status_icon_image(status, small=True)
            text = self._status_label_text(status)
            if self.gui._is_busy_status(status):
                label.configure(image=self.gui._spinner_frame() or "", text=f" {text}", compound=tk.LEFT, foreground=self._status_color(status))
            elif icon is not None:
                label.configure(image=icon, text=f" {text}", compound=tk.LEFT, foreground=self._status_color(status))
            else:
                label.configure(image="", text=text, compound=tk.LEFT, foreground=self._status_color(status))
