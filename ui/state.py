import tkinter as tk
from tkinter import ttk
from pathlib import Path
from pipeline_runner import ATLAS_DEFS, EXPORT_OUTPUT_ITEMS, PROJECT_ROOT, STAT_VECTOR_DEFS, STAGE_ORDER, TOOL_DEFS, enabled_tools_for_stage, is_tool_enabled, tool_display_name, tool_key_from_display

class AppState:
    def __init__(self):
        # Input & Output
        self.input_mode = tk.StringVar(value="file")
        self.input_path = tk.StringVar()
        self.selected_files: list[str] = []
        self.output_dir = tk.StringVar(value=str(PROJECT_ROOT / "outputs"))
        self.license_dir = tk.StringVar(value=str(PROJECT_ROOT / "license"))
        self.export_outputs_enabled = tk.BooleanVar(value=False)
        self.export_default_format = tk.StringVar(value=".nii.gz")
        self.export_name_vars: dict[str, tk.StringVar] = {}
        self.export_format_vars: dict[str, tk.StringVar] = {}
        for item_id, item in EXPORT_OUTPUT_ITEMS.items():
            self.export_name_vars[item_id] = tk.StringVar(value=item["default_name"])
            self.export_format_vars[item_id] = tk.StringVar(value=".nii.gz")
        
        # Runtime settings
        self.device = tk.StringVar(value="cpu")
        self.threads = tk.IntVar(value=4)
        self.non_recursive = tk.BooleanVar(value=False)
        self.run_target = tk.StringVar(value="Local")
        self.pipeline_mode = tk.StringVar(value="Custom Tools")
        self.allow_custom_tools = tk.BooleanVar(value=True)
        
        # Remote
        self.remote_host = tk.StringVar()
        self.remote_port = tk.IntVar(value=22)
        self.remote_username = tk.StringVar()
        self.remote_password = tk.StringVar()
        self.remote_key_path = tk.StringVar()
        self.remote_workspace = tk.StringVar(value="~/mri-remote-jobs")
        self.remote_python = tk.StringVar(value="python3")
        self.remote_status = tk.StringVar(value="Remote: idle")
        self.remote_visible = tk.BooleanVar(value=False)

        # Pipeline tools
        self.tool_vars: dict[str, tk.StringVar] = {}
        defaults = {
            "reorientation": "mri_convert_fs7",
            "brain_extraction": "synthstrip_fs7",
            "segmentation": "synthseg_freesurfer_fs7",
            "template_registration": "",
            "bias_correction": "ants_n4",
            "white_matter_segmentation": "",
            "surface_reconstruction": "",
            "surface_registration": "",
            "stats_extraction": "",
        }
        for stage in STAGE_ORDER:
            tools = enabled_tools_for_stage(stage)
            default_tool = defaults.get(stage, tools[0] if tools else "")
            self.tool_vars[stage] = tk.StringVar(value=tool_display_name(default_tool) if default_tool else "")

        # Downloadable stats vectors
        self.stat_vector_enabled_vars: dict[str, tk.BooleanVar] = {}
        self.stat_atlas_vars: dict[str, dict[str, tk.BooleanVar]] = {}
        for stat, stat_def in STAT_VECTOR_DEFS.items():
            self.stat_vector_enabled_vars[stat] = tk.BooleanVar(value=False)
            self.stat_atlas_vars[stat] = {}
            for atlas in stat_def.get("atlases", ()):
                if atlas in ATLAS_DEFS:
                    self.stat_atlas_vars[stat][atlas] = tk.BooleanVar(value=False)

        # UI state variables
        self.pipeline_note = tk.StringVar(value="Standard pipeline with editable tools.")
        self.status_text = tk.StringVar(value="Ready")
        self.server_text = tk.StringVar(value="Server: local")
        self.cpu_text = tk.StringVar(value="CPU 0%")
        self.ram_text = tk.StringVar(value="RAM n/a")
        self.overall_progress_var = tk.DoubleVar(value=0)
        self.overall_progress_text = tk.StringVar(value="0%")
        self.config_status = tk.StringVar(value="Complete the pipeline configuration to enable Run Pipeline.")
        
        # Batch progress state
        self.batch_total_text = tk.StringVar(value="Success: 0 / 0")
        self.batch_running_text = tk.StringVar(value="Running: 0")
        self.batch_failed_text = tk.StringVar(value="Failed: 0")
        self.detail_title = tk.StringVar(value="Select an input image")

    def get_selected_tools(self) -> dict[str, str]:
        return {stage: tool_key_from_display(var.get()) for stage, var in self.tool_vars.items()}

    def get_export_config(self) -> dict:
        return {
            "enabled": self.export_outputs_enabled.get(),
            "folder": "exports",
            "default_format": self.export_default_format.get() or ".nii.gz",
            "names": {item_id: var.get().strip() for item_id, var in self.export_name_vars.items()},
            "formats": {item_id: self.export_default_format.get() or ".nii.gz" for item_id in self.export_name_vars},
        }

    def get_stats_vector_config(self) -> dict:
        return {
            "enabled_stats": {stat: var.get() for stat, var in self.stat_vector_enabled_vars.items()},
            "atlases": {
                stat: [atlas for atlas, var in atlas_vars.items() if var.get()]
                for stat, atlas_vars in self.stat_atlas_vars.items()
            },
        }

    def apply_stats_vector_config(self, data: dict | None) -> None:
        data = data or {}
        enabled_stats = data.get("enabled_stats", {})
        atlases = data.get("atlases", {})
        for stat, var in self.stat_vector_enabled_vars.items():
            var.set(bool(enabled_stats.get(stat, False)))
        for stat, atlas_vars in self.stat_atlas_vars.items():
            selected = set(atlases.get(stat, []))
            for atlas, var in atlas_vars.items():
                var.set(atlas in selected)

    def collect_workspace(self) -> dict:
        workspace = {
            "version": 1,
            "type": "mri-pipeline-workspace",
            "input_mode": self.input_mode.get(),
            "input_path": self.input_path.get(),
            "selected_files": self.selected_files,
            "output_dir": self.output_dir.get(),
            "export_outputs": self.get_export_config(),
            "stats_vectors": self.get_stats_vector_config(),
            "device": self.device.get(),
            "threads": int(self.threads.get()),
            "non_recursive": self.non_recursive.get(),
            "run_target": self.run_target.get(),
        }
        if self.run_target.get() == "Server":
            workspace["remote"] = {
                "host": self.remote_host.get(),
                "port": int(self.remote_port.get()),
                "username": self.remote_username.get(),
                "key_path": self.remote_key_path.get(),
                "workspace": self.remote_workspace.get(),
                "python": self.remote_python.get(),
            }
        return workspace

    def apply_workspace(self, workspace: dict) -> None:
        self.input_mode.set(workspace.get("input_mode", "file"))
        self.input_path.set(workspace.get("input_path", ""))
        self.selected_files = list(workspace.get("selected_files", []))
        self.output_dir.set(workspace.get("output_dir", str(PROJECT_ROOT / "outputs")))

        export = workspace.get("export_outputs", {})
        self.export_outputs_enabled.set(bool(export.get("enabled", False)))
        old_formats = export.get("formats") if isinstance(export.get("formats"), dict) else {}
        default_format = export.get("default_format") or next(iter(old_formats.values()), ".nii.gz")
        self.export_default_format.set(default_format if default_format in (".nii.gz", ".mgz") else ".nii.gz")
        for item_id, value in export.get("names", {}).items():
            if item_id in self.export_name_vars:
                self.export_name_vars[item_id].set(value)
        for item_id, value in export.get("formats", {}).items():
            if item_id in self.export_format_vars:
                self.export_format_vars[item_id].set(value if value in (".nii.gz", ".mgz") else ".nii.gz")
        self.apply_stats_vector_config(workspace.get("stats_vectors", {}))

        self.device.set(workspace.get("device", "cpu"))
        self.threads.set(int(workspace.get("threads", 4)))
        self.non_recursive.set(bool(workspace.get("non_recursive", False)))
        self.run_target.set(workspace.get("run_target", "Local"))

        remote = workspace.get("remote", {})
        if self.run_target.get() == "Server":
            self.remote_host.set(remote.get("host", ""))
            self.remote_port.set(int(remote.get("port", 22)))
            self.remote_username.set(remote.get("username", ""))
            self.remote_password.set("")
            self.remote_key_path.set(remote.get("key_path", ""))
            self.remote_workspace.set(remote.get("workspace", "~/mri-remote-jobs"))
            self.remote_python.set(remote.get("python", "python3"))

    def collect_config(self) -> dict:
        return {
            "version": 1,
            "run_target": self.run_target.get(),
            "pipeline_mode": self.pipeline_mode.get(),
            "input_mode": self.input_mode.get(),
            "input_path": self.input_path.get(),
            "selected_files": self.selected_files,
            "output_dir": self.output_dir.get(),
            "license_dir": self.license_dir.get(),
            "export_outputs": self.get_export_config(),
            "stats_vectors": self.get_stats_vector_config(),
            "device": self.device.get(),
            "threads": int(self.threads.get()),
            "non_recursive": self.non_recursive.get(),
            "tools": self.get_selected_tools(),
            "remote": {
                "host": self.remote_host.get(),
                "port": int(self.remote_port.get()),
                "username": self.remote_username.get(),
                "key_path": self.remote_key_path.get(),
                "workspace": self.remote_workspace.get(),
                "python": self.remote_python.get(),
            },
        }

    def apply_config(self, config: dict) -> None:
        self.input_mode.set(config.get("input_mode", "file"))
        self.run_target.set(config.get("run_target", "Local"))
        loaded_pipeline_mode = config.get("pipeline_mode", "Custom Tools")
        if loaded_pipeline_mode == "FreeSurfer Fixed (7 steps)":
            loaded_pipeline_mode = "FreeSurfer Fixed"
        if loaded_pipeline_mode not in ("FreeSurfer Fixed", "Custom Tools"):
            loaded_pipeline_mode = "Custom Tools"
        self.pipeline_mode.set(loaded_pipeline_mode)
        self.input_path.set(config.get("input_path", ""))
        self.selected_files = list(config.get("selected_files", []))
        self.output_dir.set(config.get("output_dir", str(PROJECT_ROOT / "outputs")))
        self.license_dir.set(config.get("license_dir", str(PROJECT_ROOT / "license")))
        export = config.get("export_outputs", {})
        self.export_outputs_enabled.set(bool(export.get("enabled", False)))
        old_formats = export.get("formats") if isinstance(export.get("formats"), dict) else {}
        default_format = export.get("default_format") or next(iter(old_formats.values()), ".nii.gz")
        self.export_default_format.set(default_format if default_format in (".nii.gz", ".mgz") else ".nii.gz")
        for item_id, value in export.get("names", {}).items():
            if item_id in self.export_name_vars:
                self.export_name_vars[item_id].set(value)
        for item_id, value in export.get("formats", {}).items():
            if item_id in self.export_format_vars:
                self.export_format_vars[item_id].set(value if value in (".nii.gz", ".mgz") else ".nii.gz")
        self.apply_stats_vector_config(config.get("stats_vectors", {}))
        self.device.set(config.get("device", "cpu"))
        self.threads.set(int(config.get("threads", 4)))
        self.non_recursive.set(bool(config.get("non_recursive", False)))

        tools = config.get("tools", {})
        for stage, value in tools.items():
            if stage in self.tool_vars:
                tool_key = tool_key_from_display(value)
                self.tool_vars[stage].set(tool_display_name(tool_key) if is_tool_enabled(tool_key) else "")

        remote = config.get("remote", {})
        self.remote_host.set(remote.get("host", ""))
        self.remote_port.set(int(remote.get("port", 22)))
        self.remote_username.set(remote.get("username", ""))
        self.remote_password.set("")
        self.remote_key_path.set(remote.get("key_path", ""))
        self.remote_workspace.set(remote.get("workspace", "~/mri-remote-jobs"))
        self.remote_python.set(remote.get("python", "python3"))
