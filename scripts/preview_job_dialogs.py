from __future__ import annotations

import sys
import threading
import time
import tkinter as tk
import argparse
from pathlib import Path
from types import SimpleNamespace
from tkinter import messagebox, ttk

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def timestamp(label: str) -> float:
    return time.mktime(time.strptime(label, "%Y%m%d_%H%M%S"))


def sample_jobs() -> list[dict]:
    output_dir = "/home/trandangduat/mri-pipeline/outputs"
    rows = [
        ("completed", "20260730_164556"),
        ("running", "20260730_163431"),
        ("failed", "20260730_160941"),
        ("failed", "20260730_160858"),
        ("completed", "20260730_112308"),
        ("failed", "20260729_204804"),
        ("completed", "20260729_132744"),
        ("failed", "20260729_104559"),
        ("completed", "20260729_013342"),
        ("completed", "20260728_224012"),
        ("failed", "20260728_183100"),
        ("completed", "20260728_090411"),
        ("completed", "20260727_171909"),
        ("failed", "20260727_120010"),
        ("completed", "20260726_204418"),
        ("completed", "20260726_081255"),
    ]
    jobs = []
    for state, stamp in rows:
        job_id = f"job_{stamp}"
        remote_job_dir = f"/home/catcd1/duat-jobs2/{job_id}"
        jobs.append(
            {
                "target": "Server",
                "state": state,
                "job_id": job_id,
                "remote_job_dir": remote_job_dir,
                "remote_output_dir": f"{remote_job_dir}/outputs",
                "output_dir": output_dir,
                "effective_output_dir": output_dir,
                "started_at": timestamp(stamp),
                "remote": {
                    "host": "10.8.0.1",
                    "port": 19622,
                    "username": "catcd1",
                    "workspace": "~/duat-jobs2",
                    "python": "python3",
                },
            }
        )
    return jobs


class FakeRegistryController:
    def __init__(self, jobs: list[dict]) -> None:
        self.jobs = jobs

    def _known_jobs(self) -> list[dict]:
        return list(self.jobs)

    def _running_local_jobs(self) -> list[dict]:
        return []

    def _same_remote_server(self, _entry: dict, _ssh_config, _workspace: str) -> bool:
        return True

    def _job_identity(self, job: dict) -> str:
        return str(job.get("remote_job_dir") or job.get("job_dir") or job.get("job_id"))

    def _merge_job_lists(self, first: list[dict], second: list[dict]) -> list[dict]:
        merged: dict[str, dict] = {}
        for job in [*first, *second]:
            merged[self._job_identity(job)] = job
        return list(merged.values())

    def _delete_registry_job(self, job: dict) -> bool:
        identity = self._job_identity(job)
        self.jobs = [entry for entry in self.jobs if self._job_identity(entry) != identity]
        return True


class FakeProgressController:
    def _append_log(self, line: str) -> None:
        print(line)


class FakeToolsController:
    def _remote_log_event(self, line: str) -> None:
        print(line)


class FakeUploadRunner:
    def __init__(self) -> None:
        self.config = SimpleNamespace(
            ssh=SimpleNamespace(username="catcd1", host="10.8.0.1", port=19622),
            remote_workspace="~/duat-jobs2",
        )
        self.on_log = lambda line: print(line)

    def upload_job(self) -> None:
        lines = [
            "Connecting SSH catcd1@10.8.0.1:19622...",
            "SSH connected.",
            "Remote job: /home/catcd1/duat-jobs2/job_20260730_164556",
            "Preparing run configuration...",
            "Using shared remote pipeline code: /home/catcd1/duat-jobs2/.shared-code",
            "Uploading file: configs/run_config.json -> /home/catcd1/duat-jobs2/job_20260730_164556/job_config.json",
            "Uploading file: license/license.txt -> /home/catcd1/duat-jobs2/job_20260730_164556/license.txt",
            "Remote upload complete.",
        ]
        for line in lines:
            time.sleep(0.35)
            self.on_log(line)


class FakeDownloadConfig:
    def __init__(self) -> None:
        self.download_subdir = ""
        self.ssh = SimpleNamespace(username="catcd1", host="10.8.0.1", port=19622)
        self.remote_workspace = "~/duat-jobs2"


class FakeDownloadRunner:
    def __init__(self, remote_job_dir: str) -> None:
        self.remote_job_dir = remote_job_dir
        self.config = FakeDownloadConfig()
        self.on_log = lambda line: print(line)

    def read_remote_metadata(self) -> dict:
        time.sleep(0.2)
        return {"download_subdir": Path(self.remote_job_dir).name}

    def count_download_files(self) -> int:
        time.sleep(0.3)
        self.on_log("Connecting SSH catcd1@10.8.0.1:19622...")
        self.on_log("SSH connected.")
        return 4

    def download_outputs(self, local_target_dir: str | Path | None = None) -> Path:
        target = Path(local_target_dir or PROJECT_ROOT / "outputs") / self.config.download_subdir
        lines = [
            "Connecting SSH catcd1@10.8.0.1:19622...",
            "SSH connected.",
            f"Downloading file: {self.remote_job_dir}/outputs/aparc.stats -> {target}/aparc.stats",
            f"Downloading file: {self.remote_job_dir}/outputs/aseg.stats -> {target}/aseg.stats",
            f"Downloading file: {self.remote_job_dir}/run.log -> {target}/run.log",
            f"Downloading file: {self.remote_job_dir}/job_metadata.json -> {target}/job_metadata.json",
        ]
        for line in lines:
            time.sleep(0.3)
            self.on_log(line)
        return target


class FakeRemoteListingRunner:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def list_background_jobs(self) -> list[dict]:
        return [job for job in sample_jobs() if job["state"] == "running"]


class FakeGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.toolbar_icons: dict[str, tk.PhotoImage] = {}
        self.state = SimpleNamespace(
            run_target=tk.StringVar(value="Server"),
            remote_workspace=tk.StringVar(value="~/duat-jobs2"),
            remote_python=tk.StringVar(value="python3"),
            output_dir=tk.StringVar(value="/home/trandangduat/mri-pipeline/outputs"),
            remote_host=tk.StringVar(value="10.8.0.1"),
            remote_port=tk.IntVar(value=19622),
            remote_username=tk.StringVar(value="catcd1"),
            remote_key_path=tk.StringVar(value=""),
            remote_status=tk.StringVar(value="Remote: idle"),
        )
        self.registry_ctrl = FakeRegistryController(sample_jobs())
        self.progress_ctrl = FakeProgressController()
        self.tools_ctrl = FakeToolsController()
        self.pipeline_ctrl = FakePipelineController(self)
        self.jobs_ctrl = FakeJobsController(self)

    def _validate_configuration(self) -> None:
        return

    def _spinner_frame(self) -> tk.PhotoImage | None:
        return self._make_icon("running", "#2563eb")

    def _make_icon(self, name: str, color: str | None = None) -> tk.PhotoImage | None:
        icon_key = f"{name}_{color}" if color else name
        if icon_key in self.toolbar_icons:
            return self.toolbar_icons[icon_key]
        icon_path = PROJECT_ROOT / "ui" / "icons" / f"{name}.png"
        if not icon_path.exists():
            return None
        try:
            if color:
                from PIL import Image, ImageTk

                hex_color = color.lstrip("#")
                rgb = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
                image = Image.open(icon_path).convert("RGBA")
                alpha = image.getchannel("A")
                tinted = Image.new("RGBA", image.size, (*rgb, 0))
                tinted.putalpha(alpha)
                icon = ImageTk.PhotoImage(tinted, master=self.root)
            else:
                icon = tk.PhotoImage(file=str(icon_path), master=self.root)
            self.toolbar_icons[icon_key] = icon
            return icon
        except Exception:
            return None


class FakePipelineController:
    def __init__(self, gui: FakeGUI) -> None:
        self.gui = gui
        self.running = False
        self.stop_requested = threading.Event()
        self.progress = None
        self.resume_button = None
        self.restart_button = None
        self.stop_button = None


class FakeJobsController:
    def __init__(self, gui: FakeGUI) -> None:
        self.gui = gui
        self._remote_upload_spinner_label = None

    def ensure_remote_auth_for_job_action(self, _action: str) -> bool:
        return True

    def _ensure_remote_auth_for_job_action(self, _action: str) -> bool:
        return True

    def build_ssh_config(self):
        return SimpleNamespace(host="10.8.0.1", port=19622, username="catcd1", key_path="")

    def _build_ssh_config(self):
        return self.build_ssh_config()

    def _attach_registry_job(self, job: dict | None) -> None:
        if not job:
            return
        messagebox.showinfo("Attach preview", f"Would attach:\n{job.get('remote_job_dir') or job.get('job_id')}")

    def _attach_manual_job_dialog(self) -> None:
        messagebox.showinfo("Manual Attach preview", "This would open the manual attach flow in the real app.")

    def _download_registry_jobs(self, jobs: list[dict]) -> None:
        from ui.dialogs.job_dialogs import show_download_outputs_dialog

        downloads = [
            (
                str(job.get("remote_job_dir") or job.get("job_id")),
                FakeDownloadRunner(str(job.get("remote_job_dir") or job.get("job_id"))),
                job.get("output_dir") or self.gui.state.output_dir.get(),
            )
            for job in jobs
        ]
        show_download_outputs_dialog(self.gui.pipeline_ctrl, downloads)


class FakeRemoteController:
    def _require_remote_connection(self, _action: str) -> bool:
        return True

    def _server_connected(self) -> bool:
        return True


def preview_background_jobs(gui: FakeGUI) -> None:
    import ui.dialogs.job_dialogs as job_dialogs

    old_remote_runner = job_dialogs.RemoteRunner
    gui.remote_ctrl = FakeRemoteController()
    try:
        job_dialogs.RemoteRunner = FakeRemoteListingRunner
        job_dialogs.show_attach_job_dialog(gui.jobs_ctrl)
    finally:
        job_dialogs.RemoteRunner = old_remote_runner


def preview_existing_job_warning(gui: FakeGUI) -> None:
    from ui.gui_jobs import JobsController

    fake_self = SimpleNamespace(gui=gui)
    JobsController._choose_start_with_existing_jobs(fake_self, sample_jobs()[:2])


def preview_copy_files(gui: FakeGUI) -> None:
    from ui.dialogs.job_dialogs import show_upload_remote_job_dialog

    show_upload_remote_job_dialog(gui.jobs_ctrl, FakeUploadRunner())


def preview_download_outputs(gui: FakeGUI) -> None:
    from ui.dialogs.job_dialogs import show_download_outputs_dialog

    jobs = sample_jobs()[:2]
    downloads = [
        (
            str(job["remote_job_dir"]),
            FakeDownloadRunner(str(job["remote_job_dir"])),
            job["output_dir"],
        )
        for job in jobs
    ]
    show_download_outputs_dialog(gui.pipeline_ctrl, downloads)


def capture_window(root: tk.Tk, output_path: Path) -> None:
    root.update_idletasks()
    root.update()
    try:
        from PIL import ImageGrab
    except ImportError as exc:
        raise RuntimeError("Pillow is required for screenshots") from exc
    x = root.winfo_rootx()
    y = root.winfo_rooty()
    width = root.winfo_width()
    height = root.winfo_height()
    image = ImageGrab.grab()
    image = image.crop((x, y, x + width, y + height))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview MRI Pipeline job dialogs with mock data.")
    parser.add_argument("--dialog", choices=("launcher", "background-jobs", "background-running", "copy-files", "download-outputs"), default="launcher")
    parser.add_argument("--screenshot", type=Path, default=None)
    parser.add_argument("--screenshot-delay-ms", type=int, default=1200)
    args = parser.parse_args()

    root = tk.Tk()
    root.title("MRI Pipeline UI Dialog Preview")
    root.geometry("520x320")
    try:
        from ui.styles import setup_styles

        setup_styles(root)
    except Exception:
        root.configure(bg="#fafafa")
    gui = FakeGUI(root)

    if args.dialog != "launcher":
        root.withdraw()
        if args.screenshot is not None:
            root.deiconify()

        actions = {
            "background-jobs": lambda: preview_background_jobs(gui),
            "background-running": lambda: preview_existing_job_warning(gui),
            "copy-files": lambda: preview_copy_files(gui),
            "download-outputs": lambda: preview_download_outputs(gui),
        }

        def run_dialog() -> None:
            actions[args.dialog]()
            try:
                root.destroy()
            except tk.TclError:
                pass

        if args.screenshot is not None:
            def capture_dialog() -> None:
                for window in root.winfo_children():
                    if isinstance(window, tk.Toplevel):
                        window.update_idletasks()
                        if window.winfo_width() < 100 or window.winfo_height() < 100:
                            root.after(100, capture_dialog)
                            return
                        capture_window(window, args.screenshot)
                        window.destroy()
                        try:
                            root.destroy()
                        except tk.TclError:
                            pass
                        return
                root.after(100, capture_dialog)

            root.after(100, run_dialog)
            root.after(args.screenshot_delay_ms, capture_dialog)
        else:
            root.after(100, run_dialog)
        root.mainloop()
        return

    container = ttk.Frame(root, padding=20)
    container.pack(fill=tk.BOTH, expand=True)
    ttk.Label(container, text="Preview job dialogs", font=("Inter", 14, "bold")).pack(anchor=tk.W)
    ttk.Label(
        container,
        text="Open the dialogs with mock data. No SSH, Docker, or pipeline run is started.",
        wraplength=460,
        foreground="#475569",
    ).pack(anchor=tk.W, pady=(6, 18))

    buttons = ttk.Frame(container)
    buttons.pack(fill=tk.X)
    for text, command in (
        ("Background Jobs / Attach", lambda: preview_background_jobs(gui)),
        ("Background Job Running", lambda: preview_existing_job_warning(gui)),
        ("Copy files to remote server", lambda: preview_copy_files(gui)),
        ("Download Outputs", lambda: preview_download_outputs(gui)),
    ):
        ttk.Button(buttons, text=text, command=command).pack(fill=tk.X, pady=5)

    ttk.Label(container, textvariable=gui.state.remote_status, foreground="#64748b").pack(anchor=tk.W, pady=(18, 0))
    root.mainloop()


if __name__ == "__main__":
    main()
