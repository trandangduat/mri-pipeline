import os
import re

# 1. Update gui_progress.py
with open("ui/gui_progress.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace class definition
content = content.replace("class ProgressMixin:", """class ProgressController:
    def __init__(self, gui):
        self.gui = gui
        
        # Progress state
        self.progress_tab = None
        self.progress_contexts = {}
        self.progress_context_by_job = {}
        self.active_progress_context_id = ""
        self.progress_log_body = None
        
        import tkinter as tk
        self.progress_log_toggle_text = tk.StringVar(value="Show Log")
        self.progress_log_visible = False
        self.progress_selected_tools = {}
        
        self.image_runs = {}
        self.image_rows = {}
        self.current_image_key = ""
        self.active_image_key = ""
        self.step_summary_rows = {}
        
        self.detail_chart = None
        self.gpu_chart = None
        self.log_text = None
        self.image_list_canvas = None
        self.image_list_frame = None
        self.progress_log_card = None""")

# The class definition replacement above overrides the imports.
# It doesn't override imports, it just replaces the class definition. But tkinter is imported locally.

# Rename self attributes within gui_progress.py
replacements = {
    # Delegations to God Object
    "self.config_tab": "self.gui.config_tab",
    "self.job_device_text": "self.gui.job_device_text",
    "self.job_preset_text": "self.gui.job_preset_text",
    "self.job_threads_text": "self.gui.job_threads_text",
    "self.log_queue": "self.gui.log_queue",
    "self.metrics_queue": "self.gui.metrics_queue",
    "self.notebook": "self.gui.notebook",
    "self.pipeline_ctrl": "self.gui.pipeline_ctrl",
    "self.progress": "self.gui.progress",
    "self.root": "self.gui.root",
    "self.run_button": "self.gui.run_button",
    "self.state": "self.gui.state",
    
    # Delegations to GUI methods
    "self._build_run_request": "self.gui.pipeline_ctrl._build_run_request",
    "self._get_status_icon": "self.gui._get_status_icon",
    "self._make_icon": "self.gui._make_icon",
    "self._on_notebook_click": "self.gui._on_notebook_click",
    "self._on_notebook_tab_changed": "self.gui._on_notebook_tab_changed",
    "self._poll_queues": "self.gui._poll_queues",
    "self._request_stop": "self.gui.pipeline_ctrl._stop_pipeline",
    "self._set_button_busy": "self.gui._set_button_busy",
    "self._spinner_frame": "self.gui._spinner_frame",
    "self._sync_attach_toolbar_state": "self.gui.jobs_ctrl._sync_attach_toolbar_state",
    "self._validate_configuration": "self.gui._validate_configuration",
    "self.active_job": "self.gui.jobs_ctrl.active_job",
    "self.job_log_offset": "self.gui.jobs_ctrl.job_log_offset",
    "self.job_monitors": "self.gui.jobs_ctrl.job_monitors",
    "self.job_poll_after_id": "self.gui.jobs_ctrl.job_poll_after_id",
    "self.remote_poll_in_flight": "self.gui.jobs_ctrl.remote_poll_in_flight",
}

for old, new in replacements.items():
    content = content.replace(old, new)

with open("ui/gui_progress.py", "w", encoding="utf-8") as f:
    f.write(content)

# 2. Update ui/main.py
with open("ui/main.py", "r", encoding="utf-8") as f:
    main_content = f.read()

main_content = main_content.replace("class PipelineGUI(ProgressMixin):", "class PipelineGUI:")
main_content = main_content.replace("from ui.gui_progress import ProgressMixin", "from ui.gui_progress import ProgressController")

# Remove attributes initialized in __init__
to_remove_regex = re.compile(r'^\s*self\.(progress_tab|progress_contexts|progress_context_by_job|active_progress_context_id|progress_log_body|progress_log_toggle_text|progress_log_visible|progress_selected_tools|image_runs|image_rows|current_image_key|active_image_key|step_summary_rows)\b')

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
main_content = main_content.replace("self.jobs_ctrl = JobsController(self)", "self.jobs_ctrl = JobsController(self)\n        self.progress_ctrl = ProgressController(self)")

# Route ProgressController method calls inside main.py
methods_to_route = [
    "_activate_progress_context", "_append_log", "_append_log_to_context", "_apply_step_row_widgets",
    "_clear_log", "_close_progress_tab", "_copy_progress_log", "_create_image_run", "_current_progress_context",
    "_ensure_progress_context", "_get_progress_count", "_handle_background_log_chunk", "_handle_remote_log_event",
    "_input_files_for_progress", "_log", "_make_progress_context", "_make_step_state", "_match_progress_input_key",
    "_on_image_done", "_on_image_start", "_on_metrics", "_on_progress", "_prepare_progress_tab",
    "_progress_job_identity", "_progress_title_for_job", "_remote_log_event", "_rename_active_progress_tab",
    "_render_selected_detail", "_render_step_summary", "_reset_step_summary", "_save_active_progress_context",
    "_select_image", "_set_active_image_key", "_set_current_image_key", "_set_detail_title", "_set_idle_state",
    "_set_progress_count", "_show_progress_tab", "_step_icon", "_step_status_color", "_sync_progress_context_to_state",
    "_toggle_progress_log", "_unique_progress_title", "_update_batch_summary", "_update_image_run", "_update_run_step",
]

for method in methods_to_route:
    main_content = re.sub(r'\bself\.' + method + r'\b', f"self.progress_ctrl.{method}", main_content)

# Map self variables to self.progress_ctrl in main.py
attrs_to_map = [
    "progress_tab", "progress_contexts", "progress_context_by_job", "active_progress_context_id",
    "progress_log_body", "progress_log_toggle_text", "progress_log_visible", "progress_selected_tools",
    "image_runs", "image_rows", "current_image_key", "active_image_key", "step_summary_rows",
    "detail_chart", "gpu_chart", "log_text", "image_list_canvas", "image_list_frame", "progress_log_card"
]

for attr in attrs_to_map:
    main_content = re.sub(r'\bself\.' + attr + r'\b', f"self.progress_ctrl.{attr}", main_content)

with open("ui/main.py", "w", encoding="utf-8") as f:
    f.write(main_content)

# 3. Update cross files
files_to_update = ["ui/gui_pipeline.py", "ui/gui_jobs.py", "ui/tabs/progress_tab.py", "ui/tabs/config_tab.py"]
for file_path in files_to_update:
    if not os.path.exists(file_path): continue
    with open(file_path, "r", encoding="utf-8") as f:
        c = f.read()
    
    if file_path == "ui/tabs/progress_tab.py":
        c = c.replace("_target(context, gui,", "_target(context, gui.progress_ctrl,")
        c = c.replace("gui.progress_tab", "gui.progress_ctrl.progress_tab")
        c = c.replace("gui.active_progress_context_id", "gui.progress_ctrl.active_progress_context_id")
        c = c.replace("gui._current_progress_context", "gui.progress_ctrl._current_progress_context")
        c = c.replace("gui._close_progress_tab", "gui.progress_ctrl._close_progress_tab")
        c = c.replace("gui._toggle_progress_log", "gui.progress_ctrl._toggle_progress_log")
        c = c.replace("gui._copy_progress_log", "gui.progress_ctrl._copy_progress_log")
    else:
        for attr in attrs_to_map:
            c = re.sub(r'\bself\.gui\.' + attr + r'\b', f"self.gui.progress_ctrl.{attr}", c)
            c = re.sub(r'\bgui\.' + attr + r'\b', f"gui.progress_ctrl.{attr}", c)

        for method in methods_to_route:
            c = re.sub(r'\bself\.gui\.' + method + r'\b', f"self.gui.progress_ctrl.{method}", c)
            c = re.sub(r'\bgui\.' + method + r'\b', f"gui.progress_ctrl.{method}", c)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(c)

print("Refactoring progress complete.")
