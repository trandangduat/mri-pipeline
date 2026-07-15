import tkinter as tk
from tkinter import ttk
from pathlib import Path
from pipeline_runner import ATLAS_DEFS, EXPORT_OUTPUT_ITEMS, PROJECT_ROOT, STAT_VECTOR_DEFS, STAGE_ORDER, TOOL_DEFS, enabled_tools_for_stage, is_tool_enabled, tool_display_name, tool_key_from_display


PIPELINE_MODES = (
    "FreeSurfer 8 + Volume",
    "FreeSurfer 8 + Cortical Thickness",
    "FreeSurfer 8 + Volume + Cortical Thickness",
    "FreeSurfer 7 + Volume",
    "FreeSurfer 7 + Cortical Thickness",
    "FreeSurfer 7 + Volume + Cortical Thickness",
    "FastSurfer + Volume",
    "FastSurfer + Cortical Thickness",
    "FastSurfer + Volume + Cortical Thickness",
    "Custom",
)
PIPELINE_MODE_ALIASES = {
    "Custom Tools": "Custom",
    "FS7": "FreeSurfer 7 + Volume",
    "FS8": "FreeSurfer 8 + Volume",
    "FreeSurfer7": "FreeSurfer 7 + Volume",
    "FreeSurfer8": "FreeSurfer 8 + Volume",
    "FreeSurfer 7": "FreeSurfer 7 + Volume",
    "FreeSurfer 8": "FreeSurfer 8 + Volume",
    "FreeSurfer Fixed": "FreeSurfer 7 + Volume",
    "FreeSurfer Fixed (7 steps)": "FreeSurfer 7 + Volume",
    "Volume": "FreeSurfer 7 + Volume",
    "Volume & Cortical Thickness": "FreeSurfer 7 + Volume + Cortical Thickness",
}


def normalize_pipeline_mode(mode: str) -> str:
    normalized = PIPELINE_MODE_ALIASES.get(mode, mode)
    normalized = PIPELINE_MODE_ALIASES.get(normalized, normalized)
    return normalized if normalized in PIPELINE_MODES else "Custom"

class AppState:
    def __init__(self):
        # Input & Output
        self.input_source = tk.StringVar(value="Local")
        self.input_mode = tk.StringVar(value="file")
        self.input_path = tk.StringVar()
        self.selected_files: list[str] = []
        self.output_dir = tk.StringVar(value=str(PROJECT_ROOT / "outputs"))
        self.server_output_dir = tk.StringVar()
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
        self.pipeline_mode = tk.StringVar(value="Custom")
        self.allow_custom_tools = tk.BooleanVar(value=True)
        self.workspace_name = ""

        # Remote
        self.remote_host = tk.StringVar()
        self.remote_port = tk.IntVar(value=22)
        self.remote_username = tk.StringVar()
        self.remote_password = tk.StringVar()
        self.remote_key_path = tk.StringVar()
        self.remote_workspace = tk.StringVar(value="~/mri-remote-jobs")
        self.remote_python = tk.StringVar(value="python3")
        self.remote_status = tk.StringVar(value="Remote: idle")

        # Pipeline tools
        self.tool_vars: dict[str, tk.StringVar] = {}
        defaults = {
            "reorientation": "mri_convert_fs7",
            "brain_extraction": "synthstrip_fs7",
            "segmentation": "synthseg_freesurfer_fs7",
            "template_registration": "synthmorph_fs8",
            "bias_correction": "ants_n4",
            "white_matter_segmentation": "mri_binarize",
            "surface_reconstruction": "",
            "surface_registration": "",
            "stats_extraction": "freesurfer_stats_fs7",
        }
        for stage in STAGE_ORDER:
            tools = enabled_tools_for_stage(stage)
            default_tool = defaults.get(stage, tools[0] if tools else "")
            self.tool_vars[stage] = tk.StringVar(value=tool_display_name(default_tool) if default_tool else "")

        # Downloadable stats vectors
        self.stat_vector_enabled_vars: dict[str, tk.BooleanVar] = {}
        self.stat_atlas_vars: dict[str, dict[str, tk.BooleanVar]] = {}
        self.stat_atlas_choice_vars: dict[str, tk.StringVar] = {}
        for stat, stat_def in STAT_VECTOR_DEFS.items():
            self.stat_vector_enabled_vars[stat] = tk.BooleanVar(value=False)
            self.stat_atlas_vars[stat] = {}
            default_atlas = next((atlas for atlas in stat_def.get("atlases", ()) if atlas in ATLAS_DEFS), "")
            for atlas in stat_def.get("atlases", ()):
                if atlas in ATLAS_DEFS:
                    self.stat_atlas_vars[stat][atlas] = tk.BooleanVar(value=atlas == default_atlas)
            if self.stat_atlas_vars[stat]:
                self.stat_atlas_choice_vars[stat] = tk.StringVar(value=self._atlas_label(default_atlas))

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

    def _atlas_key_from_choice(self, choice: str) -> str:
        choice = choice.strip()
        if choice in ATLAS_DEFS:
            return choice
        for atlas, label in ATLAS_DEFS.items():
            if label == choice:
                return atlas
        return ""

    def _atlas_label(self, atlas: str) -> str:
        return ATLAS_DEFS.get(atlas, atlas)

    def selected_atlases_for_stat(self, stat: str) -> list[str]:
        choice_var = self.stat_atlas_choice_vars.get(stat)
        if choice_var is not None:
            atlas = self._atlas_key_from_choice(choice_var.get())
            return [atlas] if atlas else []
        return [atlas for atlas, var in self.stat_atlas_vars.get(stat, {}).items() if var.get()]

    def set_stat_atlas_choice(self, stat: str, atlas: str) -> None:
        if stat in self.stat_atlas_choice_vars:
            self.stat_atlas_choice_vars[stat].set(self._atlas_label(atlas) if atlas else "")
        for atlas_key, var in self.stat_atlas_vars.get(stat, {}).items():
            var.set(atlas_key == atlas)

    def default_atlas_for_stat(self, stat: str) -> str:
        return next(iter(self.stat_atlas_vars.get(stat, {})), "")

    def get_stats_vector_config(self) -> dict:
        return {
            "enabled_stats": {stat: var.get() for stat, var in self.stat_vector_enabled_vars.items()},
            "atlases": {
                stat: self.selected_atlases_for_stat(stat)
                for stat in self.stat_atlas_vars
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
            selected_atlas = next((atlas for atlas in atlas_vars if atlas in selected), "")
            if not selected_atlas:
                selected_atlas = self.default_atlas_for_stat(stat)
            self.set_stat_atlas_choice(stat, selected_atlas)
            for atlas, var in atlas_vars.items():
                var.set(atlas == selected_atlas)

    def collect_workspace(self) -> dict:
        workspace = {
            "version": 1,
            "type": "mri-pipeline-workspace",
            "input_source": self.input_source.get(),
            "input_mode": self.input_mode.get(),
            "input_path": self.input_path.get(),
            "selected_files": self.selected_files,
            "output_dir": self.output_dir.get(),
            "server_output_dir": self.server_output_dir.get(),
            "export_outputs": self.get_export_config(),
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
        self.input_source.set(workspace.get("input_source", "Local"))
        self.input_path.set(workspace.get("input_path", ""))
        self.selected_files = list(workspace.get("selected_files", []))
        self.output_dir.set(workspace.get("output_dir", str(PROJECT_ROOT / "outputs")))
        self.server_output_dir.set(workspace.get("server_output_dir", ""))

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

        self.device.set(workspace.get("device", "cpu"))
        self.threads.set(int(workspace.get("threads", 4)))
        self.non_recursive.set(bool(workspace.get("non_recursive", False)))
        self.run_target.set(workspace.get("run_target", "Local"))

        self.input_source.set("Server" if self.run_target.get() == "Server" else "Local")

        remote = workspace.get("remote", {})
        if self.run_target.get() == "Server":
            self.remote_host.set(remote.get("host", ""))
            self.remote_port.set(int(remote.get("port", 22)))
            self.remote_username.set(remote.get("username", ""))
            self.remote_password.set("")
            self.remote_key_path.set(remote.get("key_path", ""))
            self.remote_workspace.set(remote.get("workspace", "~/mri-remote-jobs"))
            self.remote_python.set(remote.get("python", "python3"))
