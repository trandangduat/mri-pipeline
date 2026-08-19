from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MNI_ATLAS_DIR = PROJECT_ROOT / "assets" / "atlases" / "mni"
SURFACE_ATLAS_DIR = PROJECT_ROOT / "assets" / "atlases" / "surface"

@dataclass
class ToolContext:
    input_path: str
    subject_id: str
    threads: int
    device: str
    dicom_list_path: str = ""
    enabled_stats: dict[str, bool | list[str]] = field(default_factory=dict)

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


def _schaefer2018_key(parcels: int, networks: int) -> str:
    if parcels == 200 and networks == 7:
        return "schaefer2018"
    return f"schaefer2018_{parcels}parcels_{networks}networks"


SCHAEFER2018_ATLAS_VARIANTS: tuple[tuple[str, int, int, str], ...] = tuple(
    (
        _schaefer2018_key(parcels, networks),
        parcels,
        networks,
        f"schaefer{parcels}_{networks}network",
    )
    for parcels in range(100, 1001, 100)
    for networks in (7, 17)
)

KONG2022_ATLAS_VARIANTS: tuple[tuple[str, int, int, str], ...] = tuple(
    (
        "kong" if parcels == 200 else f"kong2022_{parcels}parcels_17networks",
        parcels,
        17,
        f"{parcels}Parcels_Kong2022_17Networks",
    )
    for parcels in (100, 200, 300, 400)
)

SURFACE_ATLAS_STEMS: tuple[str, ...] = (
    "YBA_696parcels",
    *(stem for _key, _parcels, _networks, stem in KONG2022_ATLAS_VARIANTS),
    *(stem for _key, _parcels, _networks, stem in SCHAEFER2018_ATLAS_VARIANTS),
)

ATLAS_SHORT_NAMES: dict[str, str] = {
    "freesurfer_aseg": "",
    "freesurfer_aparc": "",
    "fastsurfer_dkt": "",
    "aparc": "",
    "aparc_a2009s": "aparc_a2009s",
    "yale": "yale",
    "mni_sclimbic": "sclimbic",
    "harvard_oxford_subcortical": "harvard_oxford_sub",
    "harvard_oxford_cortical": "harvard_oxford_cort",
    "brainnetome246": "brainnetome246",
    "pauli_2017": "pauli_2017",
    "juelich": "juelich",
    "aal": "aal",
    "schaefer2018_100_7": "schaefer2018",
    "cerebra": "cerebra",
    "tian_subcortex": "tian_subcortex",
    "jhu_icbm_dti81": "jhu_icbm_dti81",
    "suit_cerebellum": "suit_cerebellum",
    "fs_hippo_amygdala": "fs_hippo_amygdala",
    "fs_brainstem": "fs_brainstem",
    "fs_thalamic_nuclei": "fs_thalamic_nuclei",
    "fs_sclimbic": "fs_sclimbic",
    **{key: stem for key, _parcels, _networks, stem in KONG2022_ATLAS_VARIANTS},
    **{key: stem for key, _parcels, _networks, stem in SCHAEFER2018_ATLAS_VARIANTS},
    "cat12_neuromorphometrics": "",
    "cat12_schaefer2018_100parcels_17networks": "cat12_schaefer2018_100parcels_17networks",
    "cat12_schaefer2018_200parcels_17networks": "",
    "cat12_schaefer2018_400parcels_17networks": "cat12_schaefer2018_400parcels_17networks",
    "cat12_schaefer2018_600parcels_17networks": "cat12_schaefer2018_600parcels_17networks",
    "cat12_aal3": "cat12_aal3",
    "cat12_anatomy3": "cat12_anatomy3",
    "cat12_cobra": "cat12_cobra",
    "cat12_hammers": "cat12_hammers",
    "cat12_ibsr": "cat12_ibsr",
    "cat12_julichbrain3": "cat12_julichbrain3",
    "cat12_lpba40": "cat12_lpba40",
    "cat12_mori": "cat12_mori",
    "cat12_suit": "cat12_suit",
    "cat12_thalamic_nuclei": "cat12_thalamic_nuclei",
    "cat12_thalamus": "cat12_thalamus",
}

CORTICAL_THICKNESS_ATLASES: tuple[str, ...] = (
    "aparc",
    "aparc_a2009s",
    "yale",
    "kong",
    *(key for key, _parcels, _networks, _stem in SCHAEFER2018_ATLAS_VARIANTS),
)

FREESURFER_VOLUME_ATLASES: tuple[str, ...] = (
    "freesurfer_aseg",
    "freesurfer_aparc",
)

FASTSURFER_VOLUME_ATLASES: tuple[str, ...] = (
    "fastsurfer_dkt",
)

CAT12_SUBCORTICAL_VOLUME_ATLASES: tuple[str, ...] = (
    "cat12_neuromorphometrics",
    "cat12_ibsr",
    "cat12_cobra",
    "cat12_hammers",
    "cat12_suit",
    "cat12_thalamic_nuclei",
    "cat12_thalamus",
)

CAT12_CORTICAL_VOLUME_ATLASES: tuple[str, ...] = (
    "cat12_schaefer2018_100parcels_17networks",
    "cat12_schaefer2018_200parcels_17networks",
    "cat12_schaefer2018_400parcels_17networks",
    "cat12_schaefer2018_600parcels_17networks",
    "cat12_aal3",
    "cat12_anatomy3",
    "cat12_hammers",
    "cat12_julichbrain3",
    "cat12_lpba40",
    "cat12_mori",
)

EXTERNAL_MNI_SUBCORTICAL_VOLUME_ATLASES: tuple[str, ...] = (
    "mni_sclimbic",
    "harvard_oxford_subcortical",
    "brainnetome246",
    "pauli_2017",
    "aal",
    "cerebra",
    "tian_subcortex",
)

EXTERNAL_MNI_CORTICAL_VOLUME_ATLASES: tuple[str, ...] = (
    "harvard_oxford_cortical",
    "brainnetome246",
    "juelich",
    "aal",
    "schaefer2018_100_7",
)

EXTERNAL_MNI_HYBRID_VOLUME_ATLASES: tuple[str, ...] = (
    "jhu_icbm_dti81",
    "suit_cerebellum",
)

EXTERNAL_MNI_VOLUME_ATLASES: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            *EXTERNAL_MNI_SUBCORTICAL_VOLUME_ATLASES,
            *EXTERNAL_MNI_CORTICAL_VOLUME_ATLASES,
            *EXTERNAL_MNI_HYBRID_VOLUME_ATLASES,
        )
    )
)

FREESURFER_BUILTIN_SUBREGION_ATLASES: tuple[str, ...] = (
    "fs_hippo_amygdala",
    "fs_brainstem",
    "fs_thalamic_nuclei",
    "fs_sclimbic",
)

SUBCORTICAL_VOLUME_ATLASES: tuple[str, ...] = (
    *FREESURFER_VOLUME_ATLASES[:1],
    *FASTSURFER_VOLUME_ATLASES,
    *CAT12_SUBCORTICAL_VOLUME_ATLASES,
    *EXTERNAL_MNI_SUBCORTICAL_VOLUME_ATLASES,
    *FREESURFER_BUILTIN_SUBREGION_ATLASES,
)

CORTICAL_VOLUME_ATLASES: tuple[str, ...] = (
    *FREESURFER_VOLUME_ATLASES[1:],
    *FASTSURFER_VOLUME_ATLASES,
    *CAT12_CORTICAL_VOLUME_ATLASES,
    *EXTERNAL_MNI_CORTICAL_VOLUME_ATLASES,
    *EXTERNAL_MNI_HYBRID_VOLUME_ATLASES,
)

STAT_VECTOR_DEFS: dict[str, dict[str, object]] = {
    "cortical_thickness": {
        "label": "Cortical thickness",
        "value_column": "thickness_mm",
        "atlases": CORTICAL_THICKNESS_ATLASES,
    },
    "cortical_volume": {
        "label": "Cortical volume",
        "value_column": "volume_mm3",
        "atlases": CORTICAL_VOLUME_ATLASES,
    },
    "subcortical_volume": {
        "label": "Subcortical volume",
        "value_column": "volume_mm3",
        "atlases": SUBCORTICAL_VOLUME_ATLASES,
    },
}

ATLAS_DEFS: dict[str, str] = {
    "aparc": "Desikan-Killiany (aparc)",
    "aparc_a2009s": "Destrieux (aparc.a2009s)",
    "freesurfer_aseg": "FreeSurfer Aseg Atlas",
    "freesurfer_aparc": "FreeSurfer Aparc Cortical Volumes",
    "fastsurfer_dkt": "FastSurfer DKT Atlas",
    "yale": "Yale Brain Atlas - 696 parcels",
    **{
        key: f"Kong 2022 - {parcels} parcels / {networks} networks"
        for key, parcels, networks, _stem in KONG2022_ATLAS_VARIANTS
    },
    **{
        key: f"Schaefer 2018 - {parcels} parcels / {networks} networks"
        for key, parcels, networks, _stem in SCHAEFER2018_ATLAS_VARIANTS
    },
    "cat12_neuromorphometrics": "CAT12 Neuromorphometrics",
    "cat12_schaefer2018_100parcels_17networks": "CAT12 Schaefer 2018 - 100 parcels / 17 networks",
    "cat12_schaefer2018_200parcels_17networks": "CAT12 Schaefer 2018 - 200 parcels / 17 networks",
    "cat12_schaefer2018_400parcels_17networks": "CAT12 Schaefer 2018 - 400 parcels / 17 networks",
    "cat12_schaefer2018_600parcels_17networks": "CAT12 Schaefer 2018 - 600 parcels / 17 networks",
    "cat12_aal3": "CAT12 AAL3",
    "cat12_anatomy3": "CAT12 Anatomy3",
    "cat12_cobra": "CAT12 COBRA",
    "cat12_hammers": "CAT12 Hammers",
    "cat12_ibsr": "CAT12 IBSR",
    "cat12_julichbrain3": "CAT12 Julich Brain 3",
    "cat12_lpba40": "CAT12 LPBA40",
    "cat12_mori": "CAT12 Mori",
    "cat12_suit": "CAT12 SUIT",
    "cat12_thalamic_nuclei": "CAT12 Thalamic Nuclei",
    "cat12_thalamus": "CAT12 Thalamus",
    "mni_sclimbic": "FreeSurfer SCLimbic (MNI152 projection)",
    "harvard_oxford_subcortical": "Harvard-Oxford Subcortical (MNI152 projection)",
    "harvard_oxford_cortical": "Harvard-Oxford Cortical (MNI152 projection)",
    "cerebra": "CerebrA (MNI-ICBM152 projection)",
    "brainnetome246": "Brainnetome 246 (MNI projection)",
    "pauli_2017": "Pauli 2017 Subcortical Atlas (MNI projection)",
    "juelich": "Juelich Atlas (MNI projection)",
    "aal": "AAL Atlas (MNI projection)",
    "schaefer2018_100_7": "Schaefer 2018 - 100 parcels / 7 networks (MNI projection)",
    "tian_subcortex": "Tian Subcortical Atlas (MNI projection)",
    "jhu_icbm_dti81": "JHU ICBM-DTI-81 White Matter (MNI projection)",
    "suit_cerebellum": "SUIT Cerebellum (MNI projection)",
    "fs_hippo_amygdala": "FreeSurfer Hippocampal/Amygdala Subregions",
    "fs_brainstem": "FreeSurfer Brainstem Substructures",
    "fs_thalamic_nuclei": "FreeSurfer Thalamic Nuclei",
    "fs_sclimbic": "FreeSurfer SCLimbic Segmentation",
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
        "cortical_volume": [],
        "subcortical_volume": [],
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

@dataclass
class PipelineConfig:
    input_file: str
    output_dir: str
    subject_id: str
    license_dir: str = ""
    device: str = "cpu"
    threads: int = 4
    ram_percent: int = 100
    resume: bool = False
    selected_tools: dict[str, str] = field(default_factory=lambda: {
        "reorientation": "fs7_recon_style_reorientation",
        "brain_extraction": "fs7_recon_style_brain_extraction",
        "segmentation": "fs7_recon_style_segmentation",
        "template_registration": "fs7_recon_style_template_registration",
        "bias_correction": "fs7_recon_style_bias_correction",
        "white_matter_segmentation": "fs7_recon_style_wm_segmentation",
        "surface_reconstruction": "fs7_recon_style_surface_reconstruction",
        "surface_registration": "fs7_recon_style_surface_registration",
        "stats_extraction": "fs7_recon_style_stats",
    })
    export_config: ExportConfig = field(default_factory=ExportConfig)
    stats_vector_config: StatsVectorConfig = field(default_factory=StatsVectorConfig)

@dataclass
class StepResult:
    stage: str
    tool: str
    success: bool
    duration_sec: float
    output_file: str = ""
    build_duration_sec: float = 0.0
    peak_ram_bytes: int | None = None
    avg_ram_bytes: int | None = None
    p95_ram_bytes: int | None = None
    peak_cpu_pct: float | None = None
    avg_cpu_pct: float | None = None
    p95_cpu_pct: float | None = None
    log_text: str = ""
    output_files: list[str] = field(default_factory=list)
    error: str = ""
    return_code: int = 0

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
