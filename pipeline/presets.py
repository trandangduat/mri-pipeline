from __future__ import annotations

from .config import STAT_VECTOR_DEFS

PIPELINE_MODES = (
    "CAT12 + Volume",
    "CAT12 + Cortical Thickness",
    "CAT12 + Volume + Cortical Thickness",
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


def infer_pipeline_mode_from_tools(selected_tools: object) -> str:
    if not isinstance(selected_tools, dict) or not selected_tools:
        return "Custom"
    normalized_tools = {str(stage): str(tool) for stage, tool in selected_tools.items() if tool}
    if not normalized_tools:
        return "Custom"
    matches: list[tuple[int, str]] = []
    for mode, preset in PRESET_CONFIGS.items():
        preset_tools = {str(stage): str(tool) for stage, tool in dict(preset.get("tools", {})).items() if tool}
        if normalized_tools == preset_tools:
            matches.append((len(preset.get("stats", ())), mode))
    if not matches:
        return "Custom"
    return sorted(matches, key=lambda item: (-item[0], item[1]))[0][1]

VOLUME_SKIPPED_STAGES = {
    "brain_extraction",
    "template_registration",
    "bias_correction",
    "white_matter_segmentation",
    "surface_reconstruction",
    "surface_registration",
}

FS7_VOLUME_SKIPPED_STAGES = {
    "bias_correction",
    "white_matter_segmentation",
    "surface_reconstruction",
    "surface_registration",
}

CAT12_VOLUME_SKIPPED_STAGES = {
    "reorientation",
    "brain_extraction",
    "template_registration",
    "bias_correction",
    "white_matter_segmentation",
    "surface_reconstruction",
    "surface_registration",
}

_BASE_FS7_TOOLS = {
    "reorientation": "mri_convert_fs7",
    "brain_extraction": "synthstrip_fs7",
    "template_registration": "",
    "bias_correction": "ants_n4",
    "white_matter_segmentation": "mri_binarize",
    "surface_reconstruction": "",
    "surface_registration": "",
    "stats_extraction": "freesurfer_stats_fs7",
}

FREESURFER_7_TOOLS = {
    "reorientation": "fs7_recon_style_reorientation",
    "brain_extraction": "fs7_recon_style_brain_extraction",
    "segmentation": "fs7_recon_style_segmentation",
    "template_registration": "fs7_recon_style_template_registration",
    "bias_correction": "fs7_recon_style_bias_correction",
    "white_matter_segmentation": "fs7_recon_style_wm_segmentation",
    "surface_reconstruction": "fs7_recon_style_surface_reconstruction",
    "surface_registration": "fs7_recon_style_surface_registration",
    "stats_extraction": "fs7_recon_style_stats",
}

FREESURFER_7_VOLUME_TOOLS = {
    **FREESURFER_7_TOOLS,
    **{stage: "" for stage in FS7_VOLUME_SKIPPED_STAGES},
    "stats_extraction": "fs7_recon_style_subcortical_stats",
}

FREESURFER_7_SURFACE_TOOLS = FREESURFER_7_TOOLS

FREESURFER_8_SURFACE_TOOLS = {
    "reorientation": "fs8_reduced54_reorientation",
    "brain_extraction": "fs8_reduced54_brain_extraction",
    "segmentation": "synthseg_freesurfer_fs8",
    "template_registration": "fs8_reduced54_template_registration",
    "bias_correction": "fs8_reduced54_bias_correction",
    "white_matter_segmentation": "fs8_reduced54_wm_segmentation",
    "surface_reconstruction": "fs8_reduced54_surface_reconstruction",
    "surface_registration": "fs8_reduced54_surface_registration",
    "stats_extraction": "fs8_reduced54_stats",
}

FREESURFER_8_VOLUME_TOOLS = {
    **FREESURFER_8_SURFACE_TOOLS,
    **{stage: "" for stage in VOLUME_SKIPPED_STAGES},
}

FREESURFER_8_TOOLS = FREESURFER_8_VOLUME_TOOLS

FASTSURFER_TOOLS = {
    "reorientation": "fastsurfer_reorientation",
    "brain_extraction": "",
    "segmentation": "fastsurfer_segmentation",
    "template_registration": "fastsurfer_template_registration",
    "bias_correction": "fastsurfer_standardization",
    "white_matter_segmentation": "fastsurfer_wm_segmentation",
    "surface_reconstruction": "",
    "surface_registration": "",
    "stats_extraction": "fastsurfer_volume_stats_extraction",
}

FASTSURFER_SURFACE_TOOLS = {
    **FASTSURFER_TOOLS,
    "surface_reconstruction": "fastsurfer_surface_reconstruction",
    "surface_registration": "fastsurfer_surface_registration",
    "stats_extraction": "fastsurfer_stats_extraction",
}

CAT12_VOLUME_TOOLS = {
    "reorientation": "",
    "brain_extraction": "",
    "segmentation": "cat12_volume_segmentation",
    "template_registration": "",
    "bias_correction": "",
    "white_matter_segmentation": "",
    "surface_reconstruction": "",
    "surface_registration": "",
    "stats_extraction": "cat12_volume_stats_extraction",
}

CAT12_FULL_TOOLS = {
    **CAT12_VOLUME_TOOLS,
    "segmentation": "cat12_full_segmentation",
    "stats_extraction": "cat12_full_stats_extraction",
}

VOLUME_STATS = {"cortical_volume", "subcortical_volume"}

SUBCORTICAL_VOLUME_STATS = {"subcortical_volume"}

THICKNESS_STATS = {"cortical_thickness"}

PRESET_CONFIGS = {
    "CAT12 + Volume": {
        "tools": CAT12_VOLUME_TOOLS,
        "stats": VOLUME_STATS,
        "default_atlases": {
            "subcortical_volume": ["cat12_neuromorphometrics"],
            "cortical_volume": ["cat12_schaefer2018_200parcels_17networks"],
        },
    },
    "CAT12 + Cortical Thickness": {
        "tools": CAT12_FULL_TOOLS,
        "stats": THICKNESS_STATS,
        "default_atlases": {
            "cortical_thickness": ["aparc"],
        },
    },
    "CAT12 + Volume + Cortical Thickness": {
        "tools": CAT12_FULL_TOOLS,
        "stats": VOLUME_STATS | THICKNESS_STATS,
        "default_atlases": {
            "subcortical_volume": ["cat12_neuromorphometrics"],
            "cortical_volume": ["cat12_schaefer2018_200parcels_17networks"],
            "cortical_thickness": ["aparc"],
        },
    },
    "FreeSurfer 8 + Volume": {
        "tools": FREESURFER_8_TOOLS,
        "stats": VOLUME_STATS,
        "default_atlases": {
            "subcortical_volume": ["freesurfer_aseg"],
            "cortical_volume": ["freesurfer_aparc"],
        },
    },
    "FreeSurfer 8 + Cortical Thickness": {
        "tools": FREESURFER_8_SURFACE_TOOLS,
        "stats": THICKNESS_STATS,
        "default_atlases": {
            "cortical_thickness": ["aparc"],
        },
    },
    "FreeSurfer 8 + Volume + Cortical Thickness": {
        "tools": FREESURFER_8_SURFACE_TOOLS,
        "stats": VOLUME_STATS | THICKNESS_STATS,
        "default_atlases": {
            "subcortical_volume": ["freesurfer_aseg"],
            "cortical_volume": ["freesurfer_aparc"],
            "cortical_thickness": ["aparc"],
        },
    },
    "FreeSurfer 7 + Volume": {
        "tools": FREESURFER_7_VOLUME_TOOLS,
        "stats": SUBCORTICAL_VOLUME_STATS,
        "default_atlases": {
            "subcortical_volume": ["freesurfer_aseg"],
        },
    },
    "FreeSurfer 7 + Cortical Thickness": {
        "tools": FREESURFER_7_SURFACE_TOOLS,
        "stats": THICKNESS_STATS,
        "default_atlases": {
            "cortical_thickness": ["aparc"],
        },
    },
    "FreeSurfer 7 + Volume + Cortical Thickness": {
        "tools": FREESURFER_7_SURFACE_TOOLS,
        "stats": VOLUME_STATS | THICKNESS_STATS,
        "default_atlases": {
            "subcortical_volume": ["freesurfer_aseg"],
            "cortical_volume": ["freesurfer_aparc"],
            "cortical_thickness": ["aparc"],
        },
    },
    "FastSurfer + Volume": {
        "tools": FASTSURFER_TOOLS,
        "stats": VOLUME_STATS,
        "default_atlases": {
            "subcortical_volume": ["fastsurfer_dkt"],
            "cortical_volume": ["fastsurfer_dkt"],
        },
    },
    "FastSurfer + Cortical Thickness": {
        "tools": FASTSURFER_SURFACE_TOOLS,
        "stats": THICKNESS_STATS,
        "default_atlases": {
            "cortical_thickness": ["aparc"],
        },
    },
    "FastSurfer + Volume + Cortical Thickness": {
        "tools": FASTSURFER_SURFACE_TOOLS,
        "stats": VOLUME_STATS | THICKNESS_STATS,
        "default_atlases": {
            "subcortical_volume": ["fastsurfer_dkt"],
            "cortical_volume": ["fastsurfer_dkt"],
            "cortical_thickness": ["aparc"],
        },
    },
}


def _json_value(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


def normalize_stats_vector_config_for_pipeline_mode(
    pipeline_mode: str, stats_vector_config: object | None
) -> dict[str, object]:
    """Infer preset-enabled stat vectors for raw job configs that only carry atlases.

    Workers can receive raw ``job_config.json`` payloads built by older clients that
    omit ``stats_vector_config.enabled_stats``. This helper normalizes those payloads
    against the preset definition while preserving user-selected atlas lists, so a
    missing ``enabled_stats`` cannot silently produce an empty stats-vector CSV.
    """
    mode = normalize_pipeline_mode(str(pipeline_mode or "") or "Custom")
    if mode == "Custom" or mode not in PRESET_CONFIGS:
        if not isinstance(stats_vector_config, dict):
            return {}
        return {str(key): _json_value(item) for key, item in stats_vector_config.items()}

    preset = PRESET_CONFIGS[mode]
    enabled = {str(stat) for stat in preset["stats"]}
    default_atlases = preset.get("default_atlases", {})
    raw = stats_vector_config if isinstance(stats_vector_config, dict) else {}
    raw_atlases = raw.get("atlases", {})
    atlas_config = raw_atlases if isinstance(raw_atlases, dict) else {}
    atlases: dict[str, object] = {}
    for stat, stat_def in STAT_VECTOR_DEFS.items():
        existing = atlas_config.get(stat, [])
        allowed = set(str(atlas) for atlas in stat_def.get("atlases", ()))
        if isinstance(existing, list) and existing:
            atlases[stat] = [str(atlas) for atlas in existing if atlas in allowed]
            continue
        preset_defaults = default_atlases.get(stat, [])
        valid_defaults = [str(atlas) for atlas in preset_defaults if atlas in allowed]
        if stat in enabled and valid_defaults:
            atlases[stat] = valid_defaults
        elif stat in enabled and allowed:
            atlases[stat] = [str(atlas) for atlas in stat_def.get("atlases", ()) if atlas in allowed][:1]
        else:
            atlases[stat] = []

    return {
        "enabled_stats": {stat: stat in enabled for stat in STAT_VECTOR_DEFS},
        "atlases": atlases,
    }
