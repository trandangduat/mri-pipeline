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


@dataclass
class ExportConfig:
    enabled: bool = True
    folder: str = "exports"
    default_format: str = ".nii.gz"
    names: dict[str, str] = field(default_factory=dict)
    formats: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict | None) -> "ExportConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", True)),
            folder=str(data.get("folder", "exports") or "exports"),
            default_format=str(data.get("default_format", ".nii.gz") or ".nii.gz"),
            names={str(k): str(v) for k, v in dict(data.get("names", {})).items()},
            formats={str(k): str(v) for k, v in dict(data.get("formats", {})).items()},
        )

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "folder": self.folder,
            "default_format": self.default_format,
            "names": self.names,
            "formats": self.formats,
        }


EXPORT_OUTPUT_ITEMS: dict[str, dict[str, str]] = {
    "reorientation.primary": {"stage": "reorientation", "label": "Reoriented MRI", "default_name": "01_reoriented"},
    "brain_extraction.primary": {"stage": "brain_extraction", "label": "Brain extracted MRI", "default_name": "02_brain"},
    "brain_extraction.mask": {"stage": "brain_extraction", "label": "Brain mask", "default_name": "02_brain_mask"},
    "segmentation.primary": {"stage": "segmentation", "label": "Segmentation", "default_name": "03_segmentation"},
    "template_registration.primary": {"stage": "template_registration", "label": "Registered MRI", "default_name": "04_registered"},
    "template_registration.deformation": {"stage": "template_registration", "label": "Deformation field", "default_name": "04_deformation_field"},
    "bias_correction.primary": {"stage": "bias_correction", "label": "Standardized MRI", "default_name": "05_standardized"},
    "white_matter_segmentation.primary": {"stage": "white_matter_segmentation", "label": "White matter mask", "default_name": "06_white_matter_mask"},
}


STAT_VECTOR_DEFS: dict[str, dict[str, object]] = {
    "cortical_thickness": {
        "label": "Cortical thickness",
        "value_column": "thickness_mm",
        "atlases": ("yale", "kong", "schaefer2018"),
    },
    "cortical_volume": {
        "label": "Cortical volume",
        "value_column": "volume_mm3",
        "atlases": (),
    },
    "subcortical_volume": {
        "label": "Subcortical volume",
        "value_column": "volume_mm3",
        "atlases": (),
    },
}


ATLAS_DEFS: dict[str, str] = {
    "yale": "Yale",
    "kong": "Kong",
    "schaefer2018": "Schaefer 2018",
}


@dataclass
class StatsVectorConfig:
    enabled_stats: dict[str, bool] = field(default_factory=lambda: {
        "cortical_thickness": False,
        "cortical_volume": False,
        "subcortical_volume": False,
    })
    atlases: dict[str, list[str]] = field(default_factory=lambda: {
        "cortical_thickness": [],
    })

    @classmethod
    def from_dict(cls, data: dict | None) -> "StatsVectorConfig":
        data = data or {}
        enabled = {key: bool(data.get("enabled_stats", {}).get(key, False)) for key in STAT_VECTOR_DEFS}
        atlases: dict[str, list[str]] = {}
        raw_atlases = data.get("atlases", {})
        for stat, stat_def in STAT_VECTOR_DEFS.items():
            allowed = set(stat_def.get("atlases", ()))
            atlases[stat] = [atlas for atlas in raw_atlases.get(stat, []) if atlas in allowed]
        return cls(enabled_stats=enabled, atlases=atlases)

    def to_dict(self) -> dict:
        return {
            "enabled_stats": self.enabled_stats,
            "atlases": self.atlases,
        }

TOOL_DEFS: dict[str, dict] = {
    "mri_convert_fs8": {
        "display_name": "MRI Convert FS8",
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "reorientation",
        "needs_license": True,
        "command_builder": lambda ctx: f"mri_convert {ctx.input_path} /work/01_reoriented.nii.gz",
        "output_files": ["01_reoriented.nii.gz"],
    },
    "mri_convert_fs7": {
        "display_name": "MRI Convert FS7",
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "reorientation",
        "needs_license": True,
        "command_builder": lambda ctx: f"mri_convert {ctx.input_path} /work/01_reoriented.nii.gz",
        "output_files": ["01_reoriented.nii.gz"],
    },
    "nibabel": {
        "display_name": "NiBabel",
        "image": "duattran05/mri-nibabel-utils:latest",
        "dockerfile": "docker/nibabel-utils",
        "stage": "reorientation",
        "needs_license": False,
        "output_files": ["01_nibabel_reoriented.nii.gz"],
    },
    "synthstrip_fs8": {
        "display_name": "SynthStrip FS8",
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
        "display_name": "SynthStrip FS7",
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
        "display_name": "HD-BET",
        "image": "duattran05/mri-hdbet:latest",
        "dockerfile": "docker/hdbet",
        "stage": "brain_extraction",
        "needs_license": False,
        "output_files": ["02_hdbet_brain.nii.gz", "02_hdbet_brain_bet.nii.gz"],
        "extra_mounts": {"hdbet_weights": "/root/.cache/torch/hub/checkpoints"},
    },
    "synthseg_freesurfer_fs8": {
        "display_name": "SynthSeg FS8",
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
        "display_name": "SynthSeg FS7",
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
        "display_name": "SynthSeg Standalone",
        "image": "duattran05/mri-synthseg-standalone:latest",
        "dockerfile": "docker/synthseg-standalone",
        "stage": "segmentation",
        "needs_license": False,
        "output_files": ["03_synthseg_standalone_segmentation.nii.gz"],
    },
    "fastsurfervinn": {
        "display_name": "FastSurferVINN",
        "image": "duattran05/mri-fastsurfervinn:latest",
        "dockerfile": "docker/fastsurfervinn",
        "stage": "segmentation",
        "needs_license": True,
        "output_files": ["03_fastsurfervinn_segmentation.nii.gz", "aparc.DKTatlas+aseg.deep.mgz"],
    },
    "ants_n4": {
        "display_name": "ANTs N4",
        "image": "duattran05/mri-ants:latest",
        "dockerfile": "docker/ants",
        "stage": "bias_correction",
        "needs_license": False,
        "output_files": ["05_standardized.nii.gz"],
    },
    "synthmorph_fs8": {
        "display_name": "SynthMorph FS8",
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
        "display_name": "MRI Binarize FS7",
        "image": "mkdayyyy/mri-fs7-all:latest",
        "stage": "white_matter_segmentation",
        "needs_license": True,
        "command_builder": lambda ctx: f"mri_binarize --i {ctx.input_path} --wm --o /work/06_wm_mask.nii.gz",
        "output_files": ["06_wm_mask.nii.gz"],
    },
    "freesurfer_stats_fs8": {
        "display_name": "FreeSurfer Stats FS8",
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


TOOL_DISPLAY_ALIASES = {
    "Mri Convert FS8": "mri_convert_fs8",
    "Mri Convert FS7": "mri_convert_fs7",
    "Mri Convert Fs8": "mri_convert_fs8",
    "Mri Convert Fs7": "mri_convert_fs7",
    "FreeSurfer SynthSeg FS8": "synthseg_freesurfer_fs8",
    "FreeSurfer SynthSeg FS7": "synthseg_freesurfer_fs7",
    "FreeSurfer SynthSeg Fs8": "synthseg_freesurfer_fs8",
    "FreeSurfer SynthSeg Fs7": "synthseg_freesurfer_fs7",
    "Mri Binarize": "mri_binarize",
    "MRI Binarize": "mri_binarize",
}


DISABLED_DOCKER_IMAGES = {
    "mkdayyyy/mri-fs8-all:latest",
}


STAGE_ORDER = [
    "reorientation",
    "brain_extraction",
    "segmentation",
    "template_registration",
    "bias_correction",
    "white_matter_segmentation",
    "surface_reconstruction",
    "surface_registration",
    "stats_extraction",
]


STAGE_LABELS = {
    "reorientation": "Reorientation, resize",
    "brain_extraction": "Brain Extraction",
    "segmentation": "Subcortical Segmentation",
    "template_registration": "Template Registration",
    "bias_correction": "Image standardization",
    "white_matter_segmentation": "WM Segmentation",
    "surface_reconstruction": "Surface Reconstruction",
    "surface_registration": "Surface Registration",
    "stats_extraction": "Statistics & Atlas Mapping",
}


def tool_display_name(tool_key: str) -> str:
    tool = TOOL_DEFS.get(tool_key)
    if not tool:
        return ""
    return str(tool.get("display_name") or tool_key.replace("_", " ").title())


def tool_key_from_display(value: str) -> str:
    if value in TOOL_DEFS:
        return value
    if value in TOOL_DISPLAY_ALIASES:
        return TOOL_DISPLAY_ALIASES[value]
    for tool_key in TOOL_DEFS:
        if tool_display_name(tool_key) == value:
            return tool_key
    return ""


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
        "template_registration": "",
        "bias_correction": "ants_n4",
        "white_matter_segmentation": "",
        "surface_reconstruction": "",
        "surface_registration": "",
        "stats_extraction": "",
    })
    export_config: ExportConfig = field(default_factory=ExportConfig)
    stats_vector_config: StatsVectorConfig = field(default_factory=StatsVectorConfig)


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
