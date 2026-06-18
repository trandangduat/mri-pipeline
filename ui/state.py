import tkinter as tk
from tkinter import ttk
from pathlib import Path
from pipeline_runner import PROJECT_ROOT, STAGE_ORDER, TOOL_DEFS

class AppState:
    def __init__(self):
        # Input & Output
        self.input_mode = tk.StringVar(value="file")
        self.input_path = tk.StringVar()
        self.selected_files: list[str] = []
        self.output_dir = tk.StringVar(value=str(PROJECT_ROOT / "outputs"))
        self.license_dir = tk.StringVar(value=str(PROJECT_ROOT / "license"))
        
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
        self.remote_visible = tk.BooleanVar(value=True)

        # Pipeline tools
        self.tool_vars: dict[str, tk.StringVar] = {}
        defaults = {
            "reorientation": "mri_convert",
            "brain_extraction": "synthstrip",
            "segmentation": "fastsurfervinn",
            "bias_correction": "ants_n4",
            "template_registration": "synthmorph",
            "white_matter_segmentation": "wm_seg",
            "stats_extraction": "freesurfer_stats",
        }
        for stage in STAGE_ORDER:
            tools = [name for name, meta in TOOL_DEFS.items() if meta["stage"] == stage]
            self.tool_vars[stage] = tk.StringVar(value=defaults.get(stage, tools[0] if tools else ""))

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
        return {stage: var.get() for stage, var in self.tool_vars.items()}

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
        if loaded_pipeline_mode not in ("FreeSurfer Fixed (7 steps)", "Custom Tools"):
            loaded_pipeline_mode = "Custom Tools"
        self.pipeline_mode.set(loaded_pipeline_mode)
        self.input_path.set(config.get("input_path", ""))
        self.selected_files = list(config.get("selected_files", []))
        self.output_dir.set(config.get("output_dir", str(PROJECT_ROOT / "outputs")))
        self.license_dir.set(config.get("license_dir", str(PROJECT_ROOT / "license")))
        self.device.set(config.get("device", "cpu"))
        self.threads.set(int(config.get("threads", 4)))
        self.non_recursive.set(bool(config.get("non_recursive", False)))

        tools = config.get("tools", {})
        for stage, value in tools.items():
            if stage in self.tool_vars:
                self.tool_vars[stage].set(value)

        remote = config.get("remote", {})
        self.remote_host.set(remote.get("host", ""))
        self.remote_port.set(int(remote.get("port", 22)))
        self.remote_username.set(remote.get("username", ""))
        self.remote_password.set("")
        self.remote_key_path.set(remote.get("key_path", ""))
        self.remote_workspace.set(remote.get("workspace", "~/mri-remote-jobs"))
        self.remote_python.set(remote.get("python", "python3"))
