from __future__ import annotations
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import os
import threading
import json
from remote.ssh_client import SSHConfig, RemoteSSHClient

class RemoteController:
    def __init__(self, gui):
        self.gui = gui
        
    def _set_remote_status_icon(self, icon_name: str | None) -> None:

        label = getattr(self, "remote_status_icon_label", None)

        if label is None:

            return

        if icon_name == "running":

            label.configure(image=self.gui._spinner_frame() or "", text="", foreground="#2563eb")

            return

        icon = self.gui._make_icon(icon_name) if icon_name else None

        label.configure(image=icon if icon is not None else "", text="")

    def _current_remote_thread_signature(self) -> tuple[str, int, str, str, str] | None:

        return self._current_remote_connection_signature()

    def _current_remote_connection_signature(self) -> tuple[str, int, str, str, str] | None:

        host = self.gui.state.remote_host.get().strip()

        username = self.gui.state.remote_username.get().strip()

        workspace = self.gui.state.remote_workspace.get().strip() or "~/mri-remote-jobs"

        if not host or not username:

            return None

        try:

            port = int(self.gui.state.remote_port.get())

        except (tk.TclError, ValueError):

            return None

        return (host, port, username, self.gui.state.remote_key_path.get().strip(), workspace)

    def _server_connected(self) -> bool:

        return (

            self.gui.state.run_target.get() == "Server"

            and self.gui._connected_remote_signature is not None

            and self.gui._connected_remote_signature == self._current_remote_connection_signature()

        )

    def _remote_actions_enabled(self) -> bool:

        return self.gui.state.run_target.get() != "Server" or self._server_connected()

    def _server_thread_max_known(self) -> bool:

        if self.gui.max_threads is None:

            return False

        return self._server_connected() and self.gui._remote_thread_max_signature == self._current_remote_thread_signature()

    def _invalidate_remote_thread_max(self) -> None:

        if self.gui.state.run_target.get() != "Server":

            return

        current_signature = self._current_remote_connection_signature()

        if self.gui._connected_remote_signature is not None and current_signature == self.gui._connected_remote_signature:

            return

        self._cancel_remote_health_check()

        self.gui._thread_max_request_id += 1

        self.gui._set_thread_max(None)

        self._reset_remote_tool_image_state()

        self.gui.state.remote_status.set("Remote: disconnected")

        self._set_remote_status_icon("pending")

        self.gui.tools_ctrl._set_python_env_status("Not checked")

        self._sync_remote_connection_controls()

    def _reset_remote_tool_image_state(self) -> None:

        self.gui.tools_ctrl.image_statuses["Server"] = {}

        self.gui.tools_ctrl.image_installed_sizes["Server"] = {}

        self.gui.tools_ctrl.checked_tools.clear()

        self.gui.tools_ctrl._refresh_tree()

        self.gui.tools_ctrl._update_config_status_labels()

        self.gui.tools_ctrl._update_download_button()

        self.gui.validation_ctrl._validate_configuration()

    def _handle_remote_connection_lost(self, reason: str = "") -> None:

        if self.gui._connected_remote_signature is None and not self.gui.pipeline_ctrl.remote_connecting:

            return

        self._cancel_remote_health_check()

        self.gui._thread_max_request_id += 1

        self.gui._set_thread_max(None)

        self._reset_remote_tool_image_state()

        self.gui.state.remote_status.set("Remote: disconnected unexpectedly")

        self._set_remote_status_icon("failed")

        self.gui.tools_ctrl._set_python_env_status("Not checked")

        self._sync_remote_connection_controls()

        self.gui.validation_ctrl._validate_configuration()

        detail = f"\n\n{reason}" if reason else ""

        messagebox.showwarning("Server disconnected", "The server connection was lost. Remote actions are disabled until you connect again." + detail)

    def _cancel_remote_health_check(self) -> None:

        after_id = self.gui.pipeline_ctrl.remote_health_after_id

        if after_id:

            try:

                self.gui.root.after_cancel(after_id)

            except tk.TclError:

                pass

    def _schedule_remote_health_check(self, delay_ms: int = 15000) -> None:

        self._cancel_remote_health_check()

        if not self._server_connected():

            return

        self.gui.pipeline_ctrl.remote_health_after_id = self.gui.root.after(delay_ms, self._remote_health_check)

    def _ssh_config_from_current_remote(self) -> SSHConfig | None:

        host = self.gui.state.remote_host.get().strip()

        username = self.gui.state.remote_username.get().strip()

        if not host or not username:

            return None

        try:

            port = int(self.gui.state.remote_port.get())

        except (tk.TclError, ValueError):

            return None

        return SSHConfig(

            host=host,

            port=port,

            username=username,

            password=self.gui.state.remote_password.get(),

            key_path=self.gui.state.remote_key_path.get().strip(),

        )

    def _remote_health_check(self) -> None:

        if self.gui.pipeline_ctrl.remote_health_in_flight or not self._server_connected():

            return

        signature = self.gui._connected_remote_signature

        ssh_config = self._ssh_config_from_current_remote()

        if signature is None or ssh_config is None:

            self._handle_remote_connection_lost("Remote server configuration is incomplete.")

            return

        self.gui.pipeline_ctrl.remote_health_in_flight = True

    

        def worker() -> None:

            error = ""

            try:

                with RemoteSSHClient(ssh_config, lambda _line: None) as ssh:

                    code, _text = ssh.read_text("true")

                if code != 0:

                    error = f"Health check exited with code {code}."

            except Exception as exc:

                error = f"{type(exc).__name__}: {exc}"

    

            def finish() -> None:

                if signature != self.gui._connected_remote_signature:

                    return

                if error:

                    self._handle_remote_connection_lost(error)

                else:

                    self._schedule_remote_health_check()

    

            self.gui.root.after(0, finish)

    

        threading.Thread(target=worker, daemon=True).start()

    def _sync_remote_connection_controls(self) -> None:

        server_mode = self.gui.state.run_target.get() == "Server"

        editing_state = tk.NORMAL if server_mode and not self.gui.pipeline_ctrl.remote_connecting else tk.DISABLED

    

        if self.gui.run_target_combo is not None:

            self.gui.run_target_combo.configure(state=tk.DISABLED if self.gui.pipeline_ctrl.remote_connecting else "readonly")

        for widget in (

            self.gui.pipeline_ctrl.remote_host_entry,

            self.gui.pipeline_ctrl.remote_port_entry,

            self.gui.pipeline_ctrl.remote_username_entry,

            self.gui.pipeline_ctrl.remote_password_entry,

            self.gui.pipeline_ctrl.remote_key_entry,

            self.gui.remote_key_browse_button,

            self.gui.remote_workspace_entry,

        ):

            if widget is not None:

                widget.configure(state=editing_state)

        if self.gui.pipeline_ctrl.remote_connect_button is not None:

            if self.gui.pipeline_ctrl.remote_connecting:

                self.gui.pipeline_ctrl.remote_connect_button.configure(text="Connecting...", state=tk.DISABLED)

            else:

                self.gui.pipeline_ctrl.remote_connect_button.configure(text="Connect Server", state=tk.NORMAL if server_mode else tk.DISABLED)

    

        self.gui.tools_ctrl._refresh_tree()

        self.gui.tools_ctrl._update_config_status_labels()

        self._sync_remote_action_buttons()

        self.gui._sync_input_source_controls()

        self.gui._set_thread_max(self.gui.max_threads)

    def _sync_remote_action_buttons(self) -> None:

        enabled = self._remote_actions_enabled()

        state = tk.NORMAL if enabled else tk.DISABLED

        for button in (

            self.gui.tools_ctrl.python_env_check_button,

            self.gui.tools_ctrl.python_env_install_button,

            self.gui.tools_ctrl.refresh_button,

            self.gui.tools_ctrl.select_all_button,

            self.gui.tools_ctrl.unselect_all_button,

            self.gui.tools_ctrl.select_missing_button,

        ):

            if button is not None:

                button.configure(state=state)

        self.gui.tools_ctrl._update_action_buttons()

    def _require_remote_connection(self, action: str) -> bool:

        if self.gui.state.run_target.get() != "Server" or self._server_connected():

            return True

        messagebox.showwarning("Server not connected", f"Connect to the server before {action}.")

        return False

    def _read_remote_thread_max(self, ssh_config) -> int | None:

        command = "getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || python3 -c 'import os; print(os.cpu_count() or 1)'"

        with RemoteSSHClient(ssh_config, lambda _line: None) as ssh:

            code, text = ssh.read_text(command)

        if code != 0:

            return None

        for token in text.replace("\n", " ").split():

            try:

                value = int(token)

            except ValueError:

                continue

            if value > 0:

                return value

        return None

    def _remote_venv_display_path(self) -> str:

        workspace = (self.gui.state.remote_workspace.get().strip() or "~/mri-remote-jobs").rstrip("/")

        return f"{workspace}/.venv"

    def _upload_input_to_server_placeholder(self) -> None:

        from ui.dialogs.remote_browser import show_upload_dialog

        show_upload_dialog(self)

    def _browse_server_output(self) -> None:

        from ui.dialogs.remote_browser import show_remote_output_browser

        show_remote_output_browser(self)

    def _browse_remote_input(self) -> None:

        from ui.dialogs.remote_browser import show_remote_input_browser

        show_remote_input_browser(self.gui)

    def _browse_remote_key(self) -> None:

        path = filedialog.askopenfilename(

            title="Select SSH private key",

            filetypes=(("SSH key", "*"), ("All files", "*.*")),

        )

        if path:

            self.gui.state.remote_key_path.set(path)
