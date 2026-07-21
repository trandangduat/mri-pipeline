import os
import re

# 1. Update gui_tools.py
with open("ui/gui_tools.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace class definition
content = content.replace("class ToolsMixin:", """class ToolsController:
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
        self.python_env_status = None
        self.python_env_hint = None
        self.python_env_status_icon_label = None
        self.python_env_status_label = None
        self.image_statuses = {"Local": {}, "Server": {}}
        self.image_sizes = {"Local": {}, "Server": {}}
        self.image_installed_sizes = {"Local": {}, "Server": {}}
        self.hub_size_loading = False
        self.status_labels = {}""")

# Rename self attributes within gui_tools.py
replacements = {
    "self.tools_table_frame": "self.table_frame",
    "self.tools_tab": "self.tab_frame",
    "self.tools_log_toggle_text": "self.log_toggle_text",
    "self.tools_log_text": "self.log_text",
    "self.tools_log_body": "self.log_body",
    "self.tools_log_visible": "self.log_visible",
    "self.tools_checked_tools": "self.checked_tools",
    "self.tools_check_vars": "self.check_vars",
    "self.tools_status_icon_labels": "self.status_icon_labels",
    "self.tools_refresh_button": "self.refresh_button",
    "self.tools_select_all_button": "self.select_all_button",
    "self.tools_unselect_all_button": "self.unselect_all_button",
    "self.tools_select_missing_button": "self.select_missing_button",
    "self.tools_download_button": "self.download_button",
    "self.tools_delete_button": "self.delete_button",
    "self.tools_row_widgets": "self.row_widgets",
    "self.tool_image_installed_sizes": "self.image_installed_sizes",
    "self.tool_image_statuses": "self.image_statuses",
    "self.tool_image_sizes": "self.image_sizes",
    "self.tools_hub_size_loading": "self.hub_size_loading",
    "self.tool_status_labels": "self.status_labels",
    
    # Delegations to God Object
    "self.toolbar_icons": "self.gui.toolbar_icons",
    "self.state": "self.gui.state",
    "self.root": "self.gui.root",
    "self._server_connected": "self.gui._server_connected",
    "self._remote_actions_enabled": "self.gui._remote_actions_enabled",
    "self._is_busy_status": "self.gui._is_busy_status",
    "self._is_button_busy": "self.gui._is_button_busy",
    "self._set_button_busy": "self.gui._set_button_busy",
    "self._validate_configuration": "self.gui._validate_configuration",
    "self._sync_remote_connection_controls": "self.gui._sync_remote_connection_controls",
}

for old, new in replacements.items():
    content = content.replace(old, new)

method_renames = {
    "self._update_tools_action_buttons": "self._update_action_buttons",
    "self._update_tools_download_button": "self._update_download_button",
    "self._refresh_tools_tree": "self._refresh_tree",
    "self._toggle_tools_log": "self._toggle_log",
    "self._append_tools_log": "self._append_log",
    "self._selected_tool_rows": "self._selected_rows",
    "self._tools_remote_log_event": "self._remote_log_event",
    "self._refresh_tool_image_statuses": "self._refresh_image_statuses",
    "self._ensure_checked_tool_images": "self._ensure_checked_images",
    "self._delete_checked_tool_images": "self._delete_checked_images",
    "self._select_all_tool_images": "self._select_all_images",
    "self._unselect_all_tool_images": "self._unselect_all_images",
    "self._select_missing_tool_images": "self._select_missing_images",
    "self._ensure_missing_tool_images": "self._ensure_missing_images",
    "self._update_config_tool_status_labels": "self._update_config_status_labels",
    "self._tools_checkbox_enabled": "self._checkbox_enabled",
    "self.python_env_status": "self.python_env_status",
}

for old, new in method_renames.items():
    content = content.replace(old, new)

with open("ui/gui_tools.py", "w", encoding="utf-8") as f:
    f.write(content)

# 2. Update ui/main.py
with open("ui/main.py", "r", encoding="utf-8") as f:
    main_content = f.read()

main_content = main_content.replace("class PipelineGUI(ToolsMixin, JobsMixin, PipelineMixin, ProgressMixin):", "class PipelineGUI(JobsMixin, PipelineMixin, ProgressMixin):")
main_content = main_content.replace("from ui.gui_tools import ToolsMixin", "from ui.gui_tools import ToolsController")

# We will remove attributes matching self.tools_* or self.tool_image_* or self.python_env_* in __init__
to_remove_regex = re.compile(r'^\s*self\.(tools_(tab|table|log|check|status|refresh|select|unselect|download|delete|row|hub)|tool_image|python_env|tool_status_labels)\b')

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
    
    if in_init and to_remove_regex.match(line):
        continue
            
    new_lines.append(line)

main_content = "\n".join(new_lines)
main_content = main_content.replace("self._build_ui()", "self.tools_ctrl = ToolsController(self)\n        self._build_ui()")
main_content = main_content.replace("build_tools_tab(self.tools_tab, self)", "build_tools_tab(self.tools_ctrl.tab_frame, self.tools_ctrl)")
main_content = main_content.replace("self.notebook.add(self.tools_tab,", "self.notebook.add(self.tools_ctrl.tab_frame,")
main_content = main_content.replace("self.tools_tab = ttk.Frame(self.notebook)", "self.tools_ctrl.tab_frame = ttk.Frame(self.notebook)")

# Replace cross-calls inside main.py
# First replace the variables
for old, new in replacements.items():
    if old.startswith("self.") and "gui." not in new: # Only replace variables we renamed, not root/state
        attr = old.split(".")[1]
        new_attr = new.split(".")[1]
        # Regex to avoid prefix match (e.g. tools_tab replacing tools_table)
        main_content = re.sub(r'\bself\.' + attr + r'\b', f"self.tools_ctrl.{new_attr}", main_content)

for old, new in method_renames.items():
    if old.startswith("self."):
        attr = old.split(".")[1]
        new_attr = new.split(".")[1]
        main_content = re.sub(r'\bself\.' + attr + r'\b', f"self.tools_ctrl.{new_attr}", main_content)

with open("ui/main.py", "w", encoding="utf-8") as f:
    f.write(main_content)

# 3. Update ui/tabs/tools_tab.py
with open("ui/tabs/tools_tab.py", "r", encoding="utf-8") as f:
    tools_tab_content = f.read()

tools_tab_content = tools_tab_content.replace("def build_tools_tab(parent: ttk.Frame, gui) -> None:", "def build_tools_tab(parent: ttk.Frame, ctrl) -> None:")
tools_tab_content = tools_tab_content.replace("gui.", "ctrl.")
tools_tab_content = tools_tab_content.replace("ctrl.state.", "ctrl.gui.state.")
tools_tab_content = tools_tab_content.replace("ctrl._check_python_environment", "ctrl._check_python_environment")
tools_tab_content = tools_tab_content.replace("ctrl._install_python_requirements", "ctrl._install_python_requirements")
tools_tab_content = tools_tab_content.replace("ctrl._sync_remote_connection_controls", "ctrl.gui._sync_remote_connection_controls")

for old, new in replacements.items():
    if old.startswith("self.") and "gui." not in new:
        attr = old.split(".")[1]
        new_attr = new.split(".")[1]
        tools_tab_content = re.sub(r'\bctrl\.' + attr + r'\b', f"ctrl.{new_attr}", tools_tab_content)

for old, new in method_renames.items():
    if old.startswith("self."):
        attr = old.split(".")[1]
        new_attr = new.split(".")[1]
        tools_tab_content = re.sub(r'\bctrl\.' + attr + r'\b', f"ctrl.{new_attr}", tools_tab_content)

with open("ui/tabs/tools_tab.py", "w", encoding="utf-8") as f:
    f.write(tools_tab_content)

print("Refactoring complete v3.")
