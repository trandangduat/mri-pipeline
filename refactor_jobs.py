import os
import re

# 1. Update gui_jobs.py
with open("ui/gui_jobs.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace class definition
content = content.replace("class JobsMixin:", """class JobsController:
    def __init__(self, gui):
        self.gui = gui
        
        # Jobs state
        self.active_job = None
        self.job_poll_after_id = None
        self.job_log_offset = 0
        self.job_monitors = {}
        self.remote_poll_in_flight = False
        
        # UI Elements
        self._attach_loading_active = False
        self._attach_loading_dialog = None
        self._attach_loading_spinner_label = None
        self._attach_busy_button_states = {}""")

# Rename self attributes within gui_jobs.py
replacements = {
    # Delegations to God Object
    "self.config_tab": "self.gui.config_tab",
    "self.current_image_key": "self.gui.current_image_key",
    "self.image_runs": "self.gui.image_runs",
    "self.notebook": "self.gui.notebook",
    "self.pipeline_ctrl": "self.gui.pipeline_ctrl",
    "self.progress": "self.gui.progress",
    "self.progress_context_by_job": "self.gui.progress_context_by_job",
    "self.progress_contexts": "self.gui.progress_contexts",
    "self.root": "self.gui.root",
    "self.state": "self.gui.state",
    
    # Delegations to GUI methods
    "self._activate_progress_context": "self.gui._activate_progress_context",
    "self._append_log": "self.gui._append_log",
    "self._build_run_request": "self.gui.pipeline_ctrl._build_run_request",
    "self._build_ssh_config": "self.gui.pipeline_ctrl._build_ssh_config",
    "self._input_files_for_progress": "self.gui._input_files_for_progress",
    "self._log": "self.gui._log",
    "self._make_icon": "self.gui._make_icon",
    "self._on_run_target_changed": "self.gui._on_run_target_changed",
    "self._prepare_progress_tab": "self.gui._prepare_progress_tab",
    "self._progress_job_identity": "self.gui._progress_job_identity",
    "self._progress_title_for_job": "self.gui._progress_title_for_job",
    "self._remote_download_outputs": "self.gui.pipeline_ctrl._remote_download_outputs",
    "self._remote_log_event": "self.gui.tools_ctrl._remote_log_event",
    "self._render_selected_detail": "self.gui._render_selected_detail",
    "self._require_remote_connection": "self.gui._require_remote_connection",
    "self._run_remote_task": "self.gui.pipeline_ctrl._run_remote_task",
    "self._server_connected": "self.gui._server_connected",
    "self._set_active_image_key": "self.gui._set_active_image_key",
    "self._set_idle_state": "self.gui._set_idle_state",
    "self._set_progress_count": "self.gui._set_progress_count",
    "self._show_progress_tab": "self.gui._show_progress_tab",
    "self._spinner_frame": "self.gui._spinner_frame",
    "self._start_pipeline": "self.gui.pipeline_ctrl._start_pipeline",
    "self._update_batch_summary": "self.gui._update_batch_summary",
    "self._update_image_run": "self.gui._update_image_run",
    "self._update_run_step": "self.gui._update_run_step",
    "self._validate_configuration": "self.gui._validate_configuration",
}

for old, new in replacements.items():
    content = content.replace(old, new)

with open("ui/gui_jobs.py", "w", encoding="utf-8") as f:
    f.write(content)

# 2. Update ui/main.py
with open("ui/main.py", "r", encoding="utf-8") as f:
    main_content = f.read()

main_content = main_content.replace("class PipelineGUI(JobsMixin, ProgressMixin):", "class PipelineGUI(ProgressMixin):")
main_content = main_content.replace("from ui.gui_jobs import JobsMixin", "from ui.gui_jobs import JobsController")

# Remove attributes initialized in __init__
to_remove_regex = re.compile(r'^\s*self\.(active_job|job_poll_after_id|job_log_offset|job_monitors|remote_poll_in_flight)\b')

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
main_content = main_content.replace("self.pipeline_ctrl = PipelineController(self)", "self.pipeline_ctrl = PipelineController(self)\n        self.jobs_ctrl = JobsController(self)")

# Route JobsController method calls inside main.py
methods_to_route = [
    "_attach_job_dialog", "_job_identity", "_remote_key_file_exists", "_ensure_remote_auth_for_job_action",
    "_remove_job_registry_entry", "_delete_path_if_exists", "_local_job_config_for_delete",
    "_input_files_from_job_config", "_delete_local_output_folders_for_job", "_delete_local_job_folders",
    "_delete_registry_job", "_merge_job_lists", "_is_background_monitor_active", "_can_start_new_pipeline",
    "_stop_current_job_monitor", "_register_job_monitor_for_active_context", "_load_job_monitor",
    "_save_job_monitor", "_attach_manual_job_dialog", "_set_attach_buttons_busy", "_sync_attach_toolbar_state",
    "_finish_attach_loading", "_show_attach_loading", "_attach_registry_job", "_attach_registry_job_loaded",
    "_remote_runner_from_job_entry", "_load_local_progress_state", "_download_registry_job", "_download_registry_jobs",
    "_enter_background_monitor_state", "_schedule_job_poll", "_poll_local_background_job", "_poll_active_job",
    "_start_remote_poll_worker", "_finish_remote_poll", "_handle_background_log_chunk", "_update_registry_for_active_job",
    "_known_jobs", "_running_local_jobs", "_remote_jobs_for_current_server", "_same_remote_server", "_running_remote_jobs",
    "_resumable_jobs_for_current_target", "_running_jobs_for_current_target", "_resume_job_dialog",
    "_resume_local_registry_job", "_resume_remote_registry_job", "_resume_registry_job", "_refresh_registry_entry_status",
    "_pid_is_running", "_choose_start_with_existing_jobs", "_pause_background_job",
]

for method in methods_to_route:
    main_content = re.sub(r'\bself\.' + method + r'\b', f"self.jobs_ctrl.{method}", main_content)

# Map self variables to self.jobs_ctrl in main.py
attrs_to_map = [
    "active_job", "job_poll_after_id", "job_log_offset", "job_monitors", "remote_poll_in_flight"
]

for attr in attrs_to_map:
    main_content = re.sub(r'\bself\.' + attr + r'\b', f"self.jobs_ctrl.{attr}", main_content)

with open("ui/main.py", "w", encoding="utf-8") as f:
    f.write(main_content)

# 3. Update ui/gui_pipeline.py and ui/tabs/config_tab.py
files_to_update = ["ui/gui_pipeline.py", "ui/tabs/config_tab.py"]
for file_path in files_to_update:
    if not os.path.exists(file_path): continue
    with open(file_path, "r", encoding="utf-8") as f:
        c = f.read()
    
    for attr in attrs_to_map:
        c = re.sub(r'\bself\.gui\.' + attr + r'\b', f"self.gui.jobs_ctrl.{attr}", c)
        c = re.sub(r'\bgui\.' + attr + r'\b', f"gui.jobs_ctrl.{attr}", c)

    for method in methods_to_route:
        c = re.sub(r'\bself\.gui\.' + method + r'\b', f"self.gui.jobs_ctrl.{method}", c)
        c = re.sub(r'\bgui\.' + method + r'\b', f"gui.jobs_ctrl.{method}", c)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(c)

print("Refactoring jobs complete.")
