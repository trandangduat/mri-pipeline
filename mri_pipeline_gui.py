"""Modern CustomTkinter demo for configuring an MRI processing pipeline.

The prototype does not run real MRI tools yet. It lets users select input data,
configure each pipeline stage, simulate progress in a background thread, and
write placeholder TSV outputs.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk
import tkinter.font as tkfont
import tkinter.scrolledtext as scrolledtext

try:
    import customtkinter as ctk
except ImportError as exc:  # pragma: no cover - shown only when dependency is missing.
    raise SystemExit("customtkinter is required. Install it with: pip install -r requirements.txt") from exc


PADX = 10
PADY = 10
FONT_FAMILY = "Segoe UI"
BODY_FONT = (FONT_FAMILY, 11)
HEADER_FONT = (FONT_FAMILY, 13, "bold")
TITLE_FONT = (FONT_FAMILY, 24, "bold")
PREFERRED_SANS_FONTS = (
    "Segoe UI",
    "Roboto",
    "Arial",
    "Helvetica",
    "Liberation Sans",
    "DejaVu Sans",
    "Noto Sans",
    "Ubuntu",
    "Cantarell",
    "bitstream charter",
)

APP_BG = "#f5f9fc"
PANEL_BG = "#ffffff"
PANEL_ALT = "#edf6fb"
BORDER = "#d7e3ec"
TEXT = "#172033"
MUTED_TEXT = "#64748b"
ACCENT = "#0ea5c6"
ACCENT_HOVER = "#087f9a"
SUCCESS = "#22c55e"
WARNING = "#f59e0b"
DANGER = "#ef4444"
PENDING = "#94a3b8"

BIDS_SUBJECT_PATTERN = re.compile(r"^sub-[A-Za-z0-9]+$")


@dataclass(frozen=True)
class PipelineStep:
    name: str
    tools: tuple[str, ...]
    default: str


@dataclass(frozen=True)
class RunConfig:
    input_path: str
    output_dir: str
    subject_id: str
    device: str
    thread_count: int
    selected_tools: list[str]


@dataclass(frozen=True)
class StepStatusWidgets:
    indicator: ctk.CTkLabel
    label: ctk.CTkLabel


PIPELINE_STEPS = [
    PipelineStep(
        name="Reorientation & Resampling",
        tools=("mri_convert", "NiBabel"),
        default="mri_convert",
    ),
    PipelineStep(
        name="Brain Extraction",
        tools=("SynthStrip", "HD-BET", "FSL BET"),
        default="SynthStrip",
    ),
    PipelineStep(
        name="Subcortical Segmentation",
        tools=("SynthSeg", "FreeSurferVINN"),
        default="SynthSeg",
    ),
    PipelineStep(
        name="Template Registration",
        tools=("Talairach",),
        default="Talairach",
    ),
    PipelineStep(
        name="Bias Field & Intensity Standardization",
        tools=("N4BiasFieldCorrection", "N3BiasFieldCorrection"),
        default="N4BiasFieldCorrection",
    ),
    PipelineStep(
        name="White Matter Segmentation",
        tools=("FreeSurfer",),
        default="FreeSurfer",
    ),
    PipelineStep(
        name="Surface Reconstruction",
        tools=("FreeSurfer recon-all",),
        default="FreeSurfer recon-all",
    ),
    PipelineStep(
        name="Surface Registration",
        tools=("FreeSurfer spherical registration",),
        default="FreeSurfer spherical registration",
    ),
    PipelineStep(
        name="Statistics & Atlas Mapping",
        tools=("FreeSurfer asegstats2table/aparcstats2table",),
        default="FreeSurfer asegstats2table/aparcstats2table",
    ),
]

OUTPUT_FILES = [
    "subcortical_volume.tsv",
    "cortical_volume.tsv",
    "cortical_thickness.tsv",
]

STATUS_STYLES = {
    "ready": ("Ready", SUCCESS),
    "pending": ("Pending", PENDING),
    "running": ("Running", ACCENT),
    "success": ("Success", SUCCESS),
    "fail": ("Failed", DANGER),
}


class MRIPipelineDemo(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("MRI Processing Pipeline")
        self.geometry("1180x760")
        self.minsize(1040, 680)
        self.configure(fg_color=APP_BG)

        self._configure_fonts()

        self.input_path = tk.StringVar()
        self.output_dir = tk.StringVar(value=str(Path.cwd() / "demo_outputs"))
        self.device = tk.StringVar(value="CPU")
        self.thread_count = tk.StringVar(value="4")
        self.subject_id = tk.StringVar(value="sub-001")
        self.run_state = tk.StringVar(value="Idle")

        self.step_vars: list[tk.StringVar] = []
        self.step_status_widgets: list[StepStatusWidgets] = []
        self.is_running = False

        self._configure_ttk_style()
        self._build_layout()

    def _configure_fonts(self) -> None:
        global FONT_FAMILY, BODY_FONT, HEADER_FONT, TITLE_FONT

        available_fonts = {font_name.lower(): font_name for font_name in tkfont.families(self)}
        candidates = [available_fonts.get(font_name.lower(), font_name) for font_name in PREFERRED_SANS_FONTS]

        selected_family = next(
            (font_name for font_name in candidates if self._is_usable_proportional_font(font_name)),
            tkfont.nametofont("TkDefaultFont").actual("family"),
        )

        FONT_FAMILY = selected_family
        BODY_FONT = (FONT_FAMILY, 11)
        HEADER_FONT = (FONT_FAMILY, 13, "bold")
        TITLE_FONT = (FONT_FAMILY, 24, "bold")
        self.option_add("*Font", f"{{{FONT_FAMILY}}} 11")

        for named_font in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
            try:
                tkfont.nametofont(named_font).configure(family=FONT_FAMILY, size=11)
            except tk.TclError:
                continue

    def _is_usable_proportional_font(self, font_name: str) -> bool:
        if self._looks_like_monospace(font_name):
            return False

        try:
            candidate = tkfont.Font(root=self, family=font_name, size=10)
        except tk.TclError:
            return False

        actual_family = candidate.actual("family")
        if self._looks_like_monospace(actual_family):
            return False

        return abs(candidate.measure("W") - candidate.measure("i")) > 1

    def _looks_like_monospace(self, font_name: str) -> bool:
        normalized = font_name.lower()
        return any(
            token in normalized
            for token in ("mono", "courier", "console", "terminal", "code", "fixed", "cursor", "glyph")
        )

    def _configure_ttk_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "MRI.Horizontal.TProgressbar",
            troughcolor=PANEL_ALT,
            background=ACCENT,
            bordercolor=PANEL_ALT,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
        )

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=PADX, pady=PADY)
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(0, weight=1)

        left_panel = self._create_panel(main)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=PADX, pady=PADY)
        left_panel.grid_columnconfigure(0, weight=1)
        left_panel.grid_rowconfigure(1, weight=1)

        right_panel = self._create_panel(main)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=PADX, pady=PADY)
        right_panel.grid_columnconfigure(0, weight=1)
        right_panel.grid_rowconfigure(2, weight=1)

        self._build_input_section(left_panel)
        self._build_pipeline_section(left_panel)
        self._build_execution_section(right_panel)
        self._build_output_section(right_panel)
        self._build_log_section(right_panel)

    def _create_panel(self, parent: ctk.CTkBaseClass) -> ctk.CTkFrame:
        return ctk.CTkFrame(parent, fg_color=PANEL_BG, corner_radius=16, border_width=1, border_color=BORDER)

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=PADX, pady=PADY)
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="MRI Processing Pipeline",
            font=TITLE_FONT,
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=PADX, pady=PADY)
        ctk.CTkLabel(
            header,
            text="Configure a 9-stage MRI workflow, select CPU/GPU execution, and generate demo TSV outputs.",
            font=BODY_FONT,
            text_color=MUTED_TEXT,
        ).grid(row=1, column=0, sticky="w", padx=PADX, pady=PADY)

    def _build_input_section(self, parent: ctk.CTkFrame) -> None:
        section = ctk.CTkFrame(parent, fg_color="transparent")
        section.grid(row=0, column=0, sticky="ew", padx=PADX, pady=PADY)
        section.grid_columnconfigure(1, weight=1)

        self._section_title(section, "Input Data", row=0, columnspan=3)

        ctk.CTkLabel(section, text="MRI Scan (NIfTI/DICOM)", font=BODY_FONT, text_color=TEXT).grid(
            row=1, column=0, sticky="w", padx=PADX, pady=PADY
        )
        self.input_entry = ctk.CTkEntry(
            section,
            textvariable=self.input_path,
            font=BODY_FONT,
            fg_color=PANEL_ALT,
            border_color=BORDER,
            text_color=TEXT,
        )
        self.input_entry.grid(row=1, column=1, sticky="ew", padx=PADX, pady=PADY)
        self._make_readonly(self.input_entry)
        ctk.CTkButton(
            section,
            text="Browse...",
            font=BODY_FONT,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self._choose_input,
        ).grid(row=1, column=2, sticky="ew", padx=PADX, pady=PADY)

        ctk.CTkLabel(section, text="Output Directory", font=BODY_FONT, text_color=TEXT).grid(
            row=2, column=0, sticky="w", padx=PADX, pady=PADY
        )
        self.output_entry = ctk.CTkEntry(
            section,
            textvariable=self.output_dir,
            font=BODY_FONT,
            fg_color=PANEL_ALT,
            border_color=BORDER,
            text_color=TEXT,
        )
        self.output_entry.grid(row=2, column=1, sticky="ew", padx=PADX, pady=PADY)
        self._make_readonly(self.output_entry)
        ctk.CTkButton(
            section,
            text="Select Folder",
            font=BODY_FONT,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self._choose_output_dir,
        ).grid(row=2, column=2, sticky="ew", padx=PADX, pady=PADY)

        ctk.CTkLabel(section, text="Subject ID", font=BODY_FONT, text_color=TEXT).grid(
            row=3, column=0, sticky="w", padx=PADX, pady=PADY
        )
        ctk.CTkEntry(
            section,
            textvariable=self.subject_id,
            font=BODY_FONT,
            fg_color=PANEL_ALT,
            border_color=BORDER,
            text_color=TEXT,
        ).grid(row=3, column=1, sticky="ew", padx=PADX, pady=PADY)
        ctk.CTkLabel(
            section,
            text="BIDS format required, for example: sub-001",
            font=BODY_FONT,
            text_color=MUTED_TEXT,
        ).grid(row=4, column=1, columnspan=2, sticky="w", padx=PADX, pady=PADY)

    def _build_pipeline_section(self, parent: ctk.CTkFrame) -> None:
        section = ctk.CTkFrame(parent, fg_color="transparent")
        section.grid(row=1, column=0, sticky="nsew", padx=PADX, pady=PADY)
        section.grid_columnconfigure(0, weight=1)
        section.grid_rowconfigure(1, weight=1)

        self._section_title(section, "Pipeline Configuration", row=0)

        steps_frame = ctk.CTkScrollableFrame(section, fg_color=PANEL_ALT, corner_radius=12)
        steps_frame.grid(row=1, column=0, sticky="nsew", padx=PADX, pady=PADY)
        steps_frame.grid_columnconfigure(2, weight=1)

        for index, step in enumerate(PIPELINE_STEPS, start=1):
            var = tk.StringVar(value=step.default)
            self.step_vars.append(var)

            indicator = ctk.CTkLabel(steps_frame, text="", width=12, height=12, corner_radius=6, fg_color=SUCCESS)
            indicator.grid(row=index, column=0, sticky="w", padx=PADX, pady=PADY)
            status_label = ctk.CTkLabel(steps_frame, text="Ready", font=BODY_FONT, text_color=SUCCESS, width=70)
            status_label.grid(row=index, column=1, sticky="w", padx=PADX, pady=PADY)

            ctk.CTkLabel(
                steps_frame,
                text=f"{index}. {step.name}",
                font=BODY_FONT,
                text_color=TEXT,
                anchor="w",
            ).grid(row=index, column=2, sticky="ew", padx=PADX, pady=PADY)

            ctk.CTkComboBox(
                steps_frame,
                values=list(step.tools),
                variable=var,
                state="readonly",
                font=BODY_FONT,
                dropdown_font=BODY_FONT,
                fg_color=PANEL_BG,
                border_color=BORDER,
                button_color=ACCENT,
                button_hover_color=ACCENT_HOVER,
            ).grid(row=index, column=3, sticky="ew", padx=PADX, pady=PADY)
            steps_frame.grid_columnconfigure(3, weight=1)
            self.step_status_widgets.append(StepStatusWidgets(indicator=indicator, label=status_label))

    def _build_execution_section(self, parent: ctk.CTkFrame) -> None:
        section = ctk.CTkFrame(parent, fg_color="transparent")
        section.grid(row=0, column=0, sticky="ew", padx=PADX, pady=PADY)
        section.grid_columnconfigure(1, weight=1)

        self._section_title(section, "Execution Settings", row=0, columnspan=2)

        ctk.CTkLabel(section, text="Device (CPU/GPU)", font=BODY_FONT, text_color=TEXT).grid(
            row=1, column=0, sticky="w", padx=PADX, pady=PADY
        )
        device_frame = ctk.CTkFrame(section, fg_color="transparent")
        device_frame.grid(row=1, column=1, sticky="w", padx=PADX, pady=PADY)
        ctk.CTkRadioButton(
            device_frame,
            text="CPU",
            variable=self.device,
            value="CPU",
            font=BODY_FONT,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
        ).grid(row=0, column=0, sticky="w", padx=PADX, pady=PADY)
        ctk.CTkRadioButton(
            device_frame,
            text="GPU",
            variable=self.device,
            value="GPU",
            font=BODY_FONT,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
        ).grid(row=0, column=1, sticky="w", padx=PADX, pady=PADY)

        ctk.CTkLabel(section, text="Thread Count", font=BODY_FONT, text_color=TEXT).grid(
            row=2, column=0, sticky="w", padx=PADX, pady=PADY
        )
        ctk.CTkComboBox(
            section,
            values=[str(value) for value in range(1, 65)],
            variable=self.thread_count,
            state="readonly",
            width=120,
            font=BODY_FONT,
            dropdown_font=BODY_FONT,
            fg_color=PANEL_ALT,
            border_color=BORDER,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
        ).grid(row=2, column=1, sticky="w", padx=PADX, pady=PADY)

        ctk.CTkLabel(section, text="Status", font=BODY_FONT, text_color=TEXT).grid(
            row=3, column=0, sticky="w", padx=PADX, pady=PADY
        )
        ctk.CTkLabel(section, textvariable=self.run_state, font=BODY_FONT, text_color=SUCCESS).grid(
            row=3, column=1, sticky="w", padx=PADX, pady=PADY
        )

        self.run_button = ctk.CTkButton(
            section,
            text="Start Processing",
            font=HEADER_FONT,
            fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=self._start_processing,
        )
        self.run_button.grid(row=4, column=0, columnspan=2, sticky="ew", padx=PADX, pady=PADY)

        self.progress = ttk.Progressbar(
            section,
            maximum=100,
            mode="determinate",
            style="MRI.Horizontal.TProgressbar",
        )
        self.progress.grid(row=5, column=0, columnspan=2, sticky="ew", padx=PADX, pady=PADY)

        ctk.CTkButton(
            section,
            text="Clear Logs",
            font=BODY_FONT,
            fg_color=PANEL_ALT,
            hover_color=BORDER,
            command=self._clear_log,
        ).grid(row=6, column=0, columnspan=2, sticky="ew", padx=PADX, pady=PADY)

    def _build_output_section(self, parent: ctk.CTkFrame) -> None:
        section = ctk.CTkFrame(parent, fg_color="transparent")
        section.grid(row=1, column=0, sticky="ew", padx=PADX, pady=PADY)
        section.grid_columnconfigure(0, weight=1)

        self._section_title(section, "Target Output Files", row=0)
        for index, filename in enumerate(OUTPUT_FILES, start=1):
            ctk.CTkLabel(
                section,
                text=f"{index}. {filename}",
                font=BODY_FONT,
                text_color=MUTED_TEXT,
                anchor="w",
            ).grid(row=index, column=0, sticky="ew", padx=PADX, pady=PADY)

    def _build_log_section(self, parent: ctk.CTkFrame) -> None:
        section = ctk.CTkFrame(parent, fg_color="transparent")
        section.grid(row=2, column=0, sticky="nsew", padx=PADX, pady=PADY)
        section.grid_columnconfigure(0, weight=1)
        section.grid_rowconfigure(1, weight=1)

        self._section_title(section, "Execution Log", row=0)
        self.log_box = scrolledtext.ScrolledText(
            section,
            height=12,
            wrap="word",
            relief="flat",
            borderwidth=0,
            background="#ffffff",
            foreground=TEXT,
            insertbackground=TEXT,
            selectbackground=ACCENT,
            font=BODY_FONT,
        )
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=PADX, pady=PADY)
        self.log_box.configure(state="disabled")
        self._log("Pipeline configuration is ready.")

    def _section_title(self, parent: ctk.CTkFrame, text: str, row: int, columnspan: int = 1) -> None:
        ctk.CTkLabel(parent, text=text, font=HEADER_FONT, text_color=TEXT).grid(
            row=row,
            column=0,
            columnspan=columnspan,
            sticky="w",
            padx=PADX,
            pady=PADY,
        )

    def _make_readonly(self, entry: ctk.CTkEntry) -> None:
        for sequence in ("<Key>", "<<Paste>>", "<Control-v>", "<Button-2>"):
            entry.bind(sequence, lambda _event: "break")

    def _choose_input(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select MRI Scan",
            filetypes=[
                ("MRI scans", ("*.mgz", "*.nii", "*.nii.gz", "*.dcm", "*.dicom")),
                ("NIfTI", ("*.nii", "*.nii.gz")),
                ("MGZ", "*.mgz"),
                ("DICOM", ("*.dcm", "*.dicom")),
                ("All files", "*.*"),
            ],
        )
        if selected:
            self.input_path.set(selected)

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(title="Select Output Directory")
        if selected:
            self.output_dir.set(selected)

    def _start_processing(self) -> None:
        if self.is_running:
            return

        error = self._validate_form()
        if error:
            messagebox.showerror("Validation Error", error)
            return

        run_config = RunConfig(
            input_path=self.input_path.get().strip(),
            output_dir=self.output_dir.get().strip(),
            subject_id=self.subject_id.get().strip(),
            device=self.device.get(),
            thread_count=int(self.thread_count.get()),
            selected_tools=[var.get() for var in self.step_vars],
        )

        self.is_running = True
        self.run_button.configure(state="disabled")
        self.progress.configure(value=0)
        self.run_state.set("Processing")
        self._set_all_step_status("pending")
        self._clear_log()
        self._log("Starting MRI processing demo.")
        self._log(f"Input: {run_config.input_path}")
        self._log(f"Output directory: {run_config.output_dir}")
        self._log(f"Subject ID: {run_config.subject_id}")
        self._log(f"Device: {run_config.device}; thread count: {run_config.thread_count}")

        worker = threading.Thread(target=self._run_demo_worker, args=(run_config,), daemon=True)
        worker.start()

    def _validate_form(self) -> str | None:
        input_path = self.input_path.get().strip()
        output_dir = self.output_dir.get().strip()
        subject_id = self.subject_id.get().strip()

        if not input_path:
            return "Please select an input MRI scan before starting processing."
        if not self._is_supported_input(input_path):
            return "Input must be a supported MRI file: .mgz, .nii, .nii.gz, .dcm, or .dicom."
        if not Path(input_path).exists():
            return "The selected input file does not exist. Please choose another MRI scan."
        if not output_dir:
            return "Please select an output directory."
        if not subject_id:
            return "Please enter a BIDS-compliant Subject ID, for example: sub-001."
        if not BIDS_SUBJECT_PATTERN.fullmatch(subject_id):
            return "Subject ID must follow BIDS format, for example: sub-001. Use only letters and numbers after 'sub-'."
        if int(self.thread_count.get()) < 1:
            return "Thread Count must be at least 1."
        return None

    def _is_supported_input(self, input_path: str) -> bool:
        return input_path.lower().endswith((".mgz", ".nii", ".nii.gz", ".dcm", ".dicom"))

    def _run_demo_worker(self, run_config: RunConfig) -> None:
        total_steps = len(PIPELINE_STEPS)

        for index, step in enumerate(PIPELINE_STEPS, start=1):
            tool = run_config.selected_tools[index - 1]
            self._ui(lambda step_index=index: self._set_step_status(step_index, "running"))
            self._ui(lambda step_index=index, current_step=step, selected_tool=tool: self._log(
                f"[{step_index}/{total_steps}] {current_step.name} using {selected_tool}"
            ))
            time.sleep(0.6)
            progress_value = int(index / total_steps * 90)
            self._ui(lambda value=progress_value: self.progress.configure(value=value))
            self._ui(lambda step_index=index: self._set_step_status(step_index, "success"))

        self._ui(lambda: self._log("Writing target TSV output files..."))
        time.sleep(0.4)
        try:
            written_files = self._write_placeholder_outputs(run_config)
        except OSError as exc:
            self._ui(lambda error=exc: self._finish_with_error(error))
            return

        self._ui(lambda: self.progress.configure(value=100))
        self._ui(lambda files=written_files: self._finish_success(files))

    def _write_placeholder_outputs(self, run_config: RunConfig) -> list[Path]:
        output_dir = Path(run_config.output_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)

        outputs = {
            "subcortical_volume.tsv": "subject\tstructure\tvolume_mm3\n{subject}\tLeft-Hippocampus\t3821\n{subject}\tRight-Hippocampus\t3764\n",
            "cortical_volume.tsv": "subject\tregion\tvolume_mm3\n{subject}\tlh_superiorfrontal\t15432\n{subject}\trh_superiorfrontal\t14987\n",
            "cortical_thickness.tsv": "subject\tregion\tthickness_mm\n{subject}\tlh_superiorfrontal\t2.61\n{subject}\trh_superiorfrontal\t2.58\n",
        }

        written_files = []
        for filename, template in outputs.items():
            path = output_dir / filename
            path.write_text(template.format(subject=run_config.subject_id), encoding="utf-8")
            written_files.append(path)
        return written_files

    def _finish_success(self, files: list[Path]) -> None:
        self.run_state.set("Completed")
        for path in files:
            self._log(f"Created: {path}")
        self._log("Demo completed. Real MRI tools are not executed in this prototype.")
        self.is_running = False
        self.run_button.configure(state="normal")
        messagebox.showinfo("Processing Complete", "Demo processing completed and generated 3 placeholder TSV files.")

    def _finish_with_error(self, error: OSError) -> None:
        self.run_state.set("Failed")
        self._log(f"Failed to write output files: {error}")
        self.is_running = False
        self.run_button.configure(state="normal")
        messagebox.showerror("Processing Failed", f"Could not write output files:\n{error}")

    def _set_all_step_status(self, status: str) -> None:
        for index in range(1, len(self.step_status_widgets) + 1):
            self._set_step_status(index, status)

    def _set_step_status(self, step_index: int, status: str) -> None:
        label, color = STATUS_STYLES[status]
        widgets = self.step_status_widgets[step_index - 1]
        widgets.indicator.configure(fg_color=color)
        widgets.label.configure(text=label, text_color=color)

    def _clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", tk.END)
        self.log_box.configure(state="disabled")

    def _log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert(tk.END, f"{time.strftime('%H:%M:%S')} | {message}\n")
        self.log_box.see(tk.END)
        self.log_box.configure(state="disabled")

    def _ui(self, callback: Callable[[], None]) -> None:
        self.after(0, callback)


def main() -> None:
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    app = MRIPipelineDemo()
    app.mainloop()


if __name__ == "__main__":
    main()
