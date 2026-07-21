import os
import re

# 1. Update gui_pipeline.py
with open("ui/gui_pipeline.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace class definition
content = content.replace("class PipelineMixin:", """class PipelineController:
    def __init__(self, gui):
        self.gui = gui
        
        # Pipeline state
        self.running = False
        import threading
        self.stop_requested = threading.Event()
        self.remote_connecting = False
        self.remote_health_after_id = None
        self.remote_health_in_flight = False
        self.remote_runner = None
        
        # UI Elements
        self.remote_frame = None
        self.remote_body = None
        self.remote_pack_options = None
        self.remote_status_icon_label = None
        self.remote_host_entry = None
        self.remote_port_entry = None
        self.remote_username_entry = None
        self.remote_password_entry = None
        self.remote_key_entry = None
        self.remote_key_button = None
        self.remote_save_button = None
        self.remote_clear_button = None
        self.remote_test_button = None
        self.remote_connect_button = None
        self.remote_disconnect_button = None
        self.resume_button = None
        self.restart_button = None
        self.restart_tooltip = None
        self.stop_button = None
        self.stop_tooltip = None
        self._remote_upload_spinner_label = None
        self._remote_health_spinner_label = None""")

# Rename self attributes within gui_pipeline.py
replacements = {
    # Delegations to God Object
    "self.toolbar_icons": "self.gui.toolbar_icons",
    "self.state": "self.gui.state",
    "self.root": "self.gui.root",
    "self._set_button_busy": "self.gui._set_button_busy",
    "self._validate_configuration": "self.gui._validate_configuration",
    "self._spinner_frame": "self.gui._spinner_frame",
    "self._make_icon": "self.gui._make_icon",
    "self._append_log": "self.gui._append_log",
    "self._can_start_new_pipeline": "self.gui._can_start_new_pipeline",
    "self._clear_log": "self.gui._clear_log",
    "self._enter_background_monitor_state": "self.gui._enter_background_monitor_state",
    "self._input_files_for_progress": "self.gui._input_files_for_progress",
    "self._log": "self.gui._log",
    "self._prepare_progress_tab": "self.gui._prepare_progress_tab",
    "self._progress_job_identity": "self.gui._progress_job_identity",
    "self._progress_title_for_job": "self.gui._progress_title_for_job",
    "self._register_job_monitor_for_active_context": "self.gui._register_job_monitor_for_active_context",
    "self._registry_entry_for_local_job": "self.gui._registry_entry_for_local_job",
    "self._registry_entry_for_remote_job": "self.gui._registry_entry_for_remote_job",
    "self._rename_active_progress_tab": "self.gui._rename_active_progress_tab",
    "self._schedule_job_poll": "self.gui._schedule_job_poll",
    "self._selected_tools": "self.gui._selected_tools",
    "self._set_idle_state": "self.gui._set_idle_state",
    "self._set_remote_status_icon": "self.gui._set_remote_status_icon",
    "self._set_step_status": "self.gui._set_step_status",
    "self._set_thread_max": "self.gui._set_thread_max",
    "self._show_progress_tab": "self.gui._show_progress_tab",
    "self._sync_remote_connection_controls": "self.gui._sync_remote_connection_controls",
    "self.active_job": "self.gui.active_job",
    "self.detail_chart": "self.gui.detail_chart",
    "self.gpu_chart": "self.gui.gpu_chart",
    "self.job_log_offset": "self.gui.job_log_offset",
    "self.log_queue": "self.gui.log_queue",
    "self.progress": "self.gui.progress",
}

for old, new in replacements.items():
    content = content.replace(old, new)

with open("ui/gui_pipeline.py", "w", encoding="utf-8") as f:
    f.write(content)

# 2. Update ui/main.py
with open("ui/main.py", "r", encoding="utf-8") as f:
    main_content = f.read()

main_content = main_content.replace("class PipelineGUI(JobsMixin, PipelineMixin, ProgressMixin):", "class PipelineGUI(JobsMixin, ProgressMixin):")
main_content = main_content.replace("from ui.gui_pipeline import PipelineMixin", "from ui.gui_pipeline import PipelineController")

# Remove attributes initialized in __init__
to_remove_regex = re.compile(r'^\s*self\.(remote_connecting|remote_health_after_id|remote_health_in_flight|remote_runner|remote_frame|remote_body|remote_pack_options|remote_status_icon_label|remote_host_entry|remote_port_entry|remote_username_entry|remote_password_entry|remote_key_entry|remote_key_button|remote_save_button|remote_clear_button|remote_test_button|remote_connect_button|remote_disconnect_button|resume_button|restart_button|restart_tooltip|stop_button|stop_tooltip|_remote_upload_spinner_label|_remote_health_spinner_label|running|stop_requested)\b')

lines = main_content.splitlines()
in_init = False
new_lines = []
for line in lines:
    if line.startswith("    def __init__"):
        in_init = True
        new_lines.append(line)
        continue
    elif line.startswith("    def ") and in_init:
        in_init = False
    
    if in_init and to_remove_regex.search(line):
        continue
            
    new_lines.append(line)

main_content = "\n".join(new_lines)
main_content = main_content.replace("self.tools_ctrl = ToolsController(self)", "self.tools_ctrl = ToolsController(self)\n        self.pipeline_ctrl = PipelineController(self)")

# Route PipelineController method calls inside main.py
methods_to_route = [
    "_build_remote_runner",
    "_build_run_request",
    "_build_ssh_config",
    "_cancel_remote_health_check",
    "_common_input_root",
    "_common_remote_input_root",
    "_confirm_start_with_existing_jobs",
    "_connected_remote_signature",
    "_current_remote_connection_signature",
    "_read_remote_thread_max",
    "_remote_dir_contains_dicom",
    "_remote_is_dicom_name",
    "_remote_thread_max_signature",
    "_reset_remote_tool_image_state",
    "_run_remote_task",
    "_schedule_remote_health_check",
    "_start_lazy_upload_pipeline",
    "_start_local_background_pipeline",
    "_start_pipeline",
    "_resume_pipeline",
    "_stop_pipeline",
    "_start_remote_pipeline",
    "_upload_remote_job_with_dialog",
    "_validate_remote_input_request",
    "_remote_test_ssh",
    "_remote_connect",
    "_remote_disconnect",
    "_remote_download_outputs"
]

for method in methods_to_route:
    main_content = re.sub(r'\bself\.' + method + r'\b', f"self.pipeline_ctrl.{method}", main_content)

# Map self variables to self.pipeline_ctrl in main.py
attrs_to_map = [
    "running", "stop_requested", "remote_connecting", "remote_health_after_id", "remote_health_in_flight",
    "remote_runner", "remote_frame", "remote_body", "remote_pack_options", "remote_status_icon_label",
    "remote_host_entry", "remote_port_entry", "remote_username_entry", "remote_password_entry", "remote_key_entry",
    "remote_key_button", "remote_save_button", "remote_clear_button", "remote_test_button", "remote_connect_button",
    "remote_disconnect_button", "resume_button", "restart_button", "restart_tooltip", "stop_button", "stop_tooltip",
    "_remote_upload_spinner_label", "_remote_health_spinner_label"
]

for attr in attrs_to_map:
    main_content = re.sub(r'\bself\.' + attr + r'\b', f"self.pipeline_ctrl.{attr}", main_content)

with open("ui/main.py", "w", encoding="utf-8") as f:
    f.write(main_content)

# 3. Update ui/tabs/config_tab.py
with open("ui/tabs/config_tab.py", "r", encoding="utf-8") as f:
    config_tab_content = f.read()

# Route gui methods/variables in config_tab
for attr in attrs_to_map:
    config_tab_content = re.sub(r'\bgui\.' + attr + r'\b', f"gui.pipeline_ctrl.{attr}", config_tab_content)

for method in methods_to_route:
    config_tab_content = re.sub(r'\bgui\.' + method + r'\b', f"gui.pipeline_ctrl.{method}", config_tab_content)

with open("ui/tabs/config_tab.py", "w", encoding="utf-8") as f:
    f.write(config_tab_content)

# 4. Update ui/gui_tools.py
with open("ui/gui_tools.py", "r", encoding="utf-8") as f:
    tools_content = f.read()

for attr in attrs_to_map:
    tools_content = re.sub(r'\bself\.gui\.' + attr + r'\b', f"self.gui.pipeline_ctrl.{attr}", tools_content)

for method in methods_to_route:
    tools_content = re.sub(r'\bself\.gui\.' + method + r'\b', f"self.gui.pipeline_ctrl.{method}", tools_content)

with open("ui/gui_tools.py", "w", encoding="utf-8") as f:
    f.write(tools_content)

print("Refactoring pipeline complete.")
