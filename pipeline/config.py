from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ToolContext:
    input_path: str
    subject_id: str
    threads: int
    device: str

TOOL_DEFS: dict[str, dict] = {
    "mri_convert_fs8": {
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "reorientation",
        "needs_license": True,
        "command_builder": lambda ctx: f"mri_convert {ctx.input_path} /work/01_reoriented.nii.gz",
        "output_files": ["01_reoriented.nii.gz"],
    },
    "mri_convert_fs7": {
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "reorientation",
        "needs_license": True,
        "command_builder": lambda ctx: f"mri_convert {ctx.input_path} /work/01_reoriented.nii.gz",
        "output_files": ["01_reoriented.nii.gz"],
    },
    "nibabel": {
        "image": "duattran05/mri-nibabel-utils:latest",
        "dockerfile": "docker/nibabel-utils",
        "stage": "reorientation",
        "needs_license": False,
        "output_files": ["01_nibabel_reoriented.nii.gz"],
    },
    "synthstrip_fs8": {
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "brain_extraction",
        "needs_license": True,
        "command_builder": lambda ctx: (
            f"mri_synthstrip -i {ctx.input_path} "
            f"-o /work/02_synthstrip_brain.nii.gz "
            f"-m /work/02_synthstrip_brain_mask.nii.gz "
            f"{'-g' if ctx.device != 'cpu' else ''}"
        ),
        "output_files": ["02_synthstrip_brain.nii.gz", "02_synthstrip_brain_mask.nii.gz"],
    },
    "synthstrip_fs7": {
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "brain_extraction",
        "needs_license": True,
        "command_builder": lambda ctx: (
            f"mri_synthstrip -i {ctx.input_path} "
            f"-o /work/02_synthstrip_brain.nii.gz "
            f"-m /work/02_synthstrip_brain_mask.nii.gz "
            f"{'-g' if ctx.device != 'cpu' else ''}"
        ),
        "output_files": ["02_synthstrip_brain.nii.gz", "02_synthstrip_brain_mask.nii.gz"],
    },
    "hdbet": {
        "image": "duattran05/mri-hdbet:latest",
        "dockerfile": "docker/hdbet",
        "stage": "brain_extraction",
        "needs_license": False,
        "output_files": ["02_hdbet_brain.nii.gz", "02_hdbet_brain_bet.nii.gz"],
        "extra_mounts": {"hdbet_weights": "/root/.cache/torch/hub/checkpoints"},
    },
    "synthseg_freesurfer_fs8": {
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "segmentation",
        "needs_license": True,
        "command_builder": lambda ctx: (
            f"mri_synthseg --i {ctx.input_path} --o /work/03_freesurfer_synthseg_segmentation.nii.gz "
            f"--vol /work/03_freesurfer_synthseg_volumes.csv --threads {ctx.threads} --crop 160 "
            f"{'--cpu' if ctx.device == 'cpu' else ''} "
            f"&& python3 /app/normalize_volumes.py /work/03_freesurfer_synthseg_volumes.csv "
            f"/output/stats/subcortical_volume.tsv /output/stats/cortical_volume.tsv {ctx.subject_id} FreeSurferSynthSeg"
        ),
        "output_files": ["03_freesurfer_synthseg_segmentation.nii.gz"],
    },
    "synthseg_freesurfer_fs7": {
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "segmentation",
        "needs_license": True,
        "command_builder": lambda ctx: (
            f"mri_synthseg --i {ctx.input_path} --o /work/03_freesurfer_synthseg_segmentation.nii.gz "
            f"--vol /work/03_freesurfer_synthseg_volumes.csv --threads {ctx.threads} --crop 160 "
            f"{'--cpu' if ctx.device == 'cpu' else ''} "
            f"&& python3 /app/normalize_volumes.py /work/03_freesurfer_synthseg_volumes.csv "
            f"/output/stats/subcortical_volume.tsv /output/stats/cortical_volume.tsv {ctx.subject_id} FreeSurferSynthSeg"
        ),
        "output_files": ["03_freesurfer_synthseg_segmentation.nii.gz"],
    },
    "synthseg_standalone": {
        "image": "duattran05/mri-synthseg-standalone:latest",
        "dockerfile": "docker/synthseg-standalone",
        "stage": "segmentation",
        "needs_license": False,
        "output_files": ["03_synthseg_standalone_segmentation.nii.gz"],
    },
    "fastsurfervinn": {
        "image": "duattran05/mri-fastsurfervinn:latest",
        "dockerfile": "docker/fastsurfervinn",
        "stage": "segmentation",
        "needs_license": True,
        "output_files": ["03_fastsurfervinn_segmentation.nii.gz", "aparc.DKTatlas+aseg.deep.mgz"],
    },
    "ants_n4": {
        "image": "duattran05/mri-ants:latest",
        "dockerfile": "docker/ants",
        "stage": "bias_correction",
        "needs_license": False,
        "output_files": ["05_standardized.nii.gz"],
    },
    "synthmorph_fs8": {
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "template_registration",
        "needs_license": True,
        "command_builder": lambda ctx: (
            f"mri_synthmorph register -m deform -j {ctx.threads} "
            f"-o /work/04_synthmorph_registered.nii.gz {ctx.input_path} {ctx.input_path}"
        ),
        "output_files": [
            "04_warped.nii.gz",
            "04_deformation_field.nii.gz",
            "04_synthmorph_warped.nii.gz",
            "04_synthmorph_deformation_field.nii.gz",
        ],
        "output_globs": [
            "*warped*.nii*",
            "*moved*.nii*",
            "*registered*.nii*",
            "*warped*.mgz",
            "*moved*.mgz",
            "*registered*.mgz",
        ],
    },
    "mri_binarize": {
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "white_matter_segmentation",
        "needs_license": True,
        "command_builder": lambda ctx: f"mri_binarize --i {ctx.input_path} --wm --o /work/06_wm_mask.nii.gz",
        "output_files": ["06_wm_mask.nii.gz"],
    },
    "freesurfer_stats_fs8": {
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "stats_extraction",
        "needs_license": True,
        "output_files": [
            "subcortical_volume.tsv",
            "lh_aparc_volume.tsv",
            "rh_aparc_volume.tsv",
            "lh_aparc.DKTatlas_volume.tsv",
            "rh_aparc.DKTatlas_volume.tsv",
        ],
    },
}


DISABLED_DOCKER_IMAGES = {
    "mkdayyyy/mri-fs8-all:latest",
}


STAGE_ORDER = [
    "reorientation",
    "brain_extraction",
    "segmentation",
    "bias_correction",
    "template_registration",
    "white_matter_segmentation",
    "stats_extraction",
]


STAGE_LABELS = {
    "reorientation": "Reorientation & Resampling",
    "brain_extraction": "Brain Extraction",
    "segmentation": "Subcortical Segmentation",
    "bias_correction": "Bias Field Correction (N4)",
    "template_registration": "Template Registration (SynthMorph)",
    "white_matter_segmentation": "White Matter Segmentation",
    "stats_extraction": "FreeSurfer Stats Extraction",
}


def is_tool_enabled(tool_key: str) -> bool:
    tool = TOOL_DEFS.get(tool_key)
    if not tool:
        return False
    return tool.get("image") not in DISABLED_DOCKER_IMAGES and not tool.get("disabled", False)


def enabled_tools_for_stage(stage: str) -> list[str]:
    return [key for key, tool in TOOL_DEFS.items() if tool["stage"] == stage and is_tool_enabled(key)]


@dataclass
class PipelineConfig:
    input_file: str
    output_dir: str
    subject_id: str
    license_dir: str = ""
    device: str = "cpu"
    threads: int = 4
    resume: bool = False
    selected_tools: dict[str, str] = field(default_factory=lambda: {
        "reorientation": "mri_convert_fs7",
        "brain_extraction": "synthstrip_fs7",
        "segmentation": "synthseg_freesurfer_fs7",
        "bias_correction": "ants_n4",
        "template_registration": "",
        "white_matter_segmentation": "",
        "stats_extraction": "",
    })


@dataclass
class StepResult:
    stage: str
    tool: str
    success: bool
    duration_sec: float
    build_duration_sec: float = 0.0
    peak_ram_bytes: int | None = None
    peak_cpu_pct: float | None = None
    log_text: str = ""
    output_files: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class BatchImageResult:
    input_file: str
    subject_id: str
    subject_dir: str
    success: bool
    duration_sec: float
    steps: list[StepResult] = field(default_factory=list)
    error: str = ""


ProgressCallback = Callable[[str, str, float, str], None]
BuildLogCallback = Callable[[str], None]
MetricsCallback = Callable[[str, str, "float | None", "int | None", float, str], None]
