from __future__ import annotations

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

VOLUME_SKIPPED_STAGES = {
    "brain_extraction",
    "bias_correction",
    "white_matter_segmentation",
    "surface_reconstruction",
    "surface_registration",
}

_BASE_FS7_TOOLS = {
    "reorientation": "mri_convert_fs7",
    "brain_extraction": "synthstrip_fs7",
    "template_registration": "synthmorph_fs8",
    "bias_correction": "ants_n4",
    "white_matter_segmentation": "mri_binarize",
    "surface_reconstruction": "",
    "surface_registration": "",
    "stats_extraction": "freesurfer_stats_fs7",
}

FREESURFER_7_TOOLS = {
    **_BASE_FS7_TOOLS,
    "segmentation": "synthseg_freesurfer_fs7",
}

FREESURFER_7_SURFACE_TOOLS = {
    **FREESURFER_7_TOOLS,
    "surface_reconstruction": "recon_all_fs7",
    "surface_registration": "surface_stats_fs7",
}

FREESURFER_8_TOOLS = {
    "reorientation": "mri_convert_fs8",
    "brain_extraction": "synthstrip_fs8",
    "segmentation": "synthseg_freesurfer_fs8",
    "template_registration": "synthmorph_fs8",
    "bias_correction": "ants_n4",
    "white_matter_segmentation": "mri_binarize",
    "surface_reconstruction": "",
    "surface_registration": "",
    "stats_extraction": "freesurfer_stats_fs8",
}

FREESURFER_8_SURFACE_TOOLS = {
    **FREESURFER_8_TOOLS,
    "surface_reconstruction": "recon_all_fs8",
    "surface_registration": "surface_stats_fs8",
}

FASTSURFER_TOOLS = {
    **_BASE_FS7_TOOLS,
    "segmentation": "fastsurfervinn",
}

FASTSURFER_SURFACE_TOOLS = {
    **FASTSURFER_TOOLS,
    "surface_reconstruction": "recon_all_fs7",
    "surface_registration": "surface_stats_fs7",
}

VOLUME_STATS = {"cortical_volume", "subcortical_volume"}

THICKNESS_STATS = {"cortical_thickness"}

PRESET_CONFIGS = {
    "FreeSurfer 8 + Volume": {"tools": FREESURFER_8_TOOLS, "stats": VOLUME_STATS},
    "FreeSurfer 8 + Cortical Thickness": {"tools": FREESURFER_8_SURFACE_TOOLS, "stats": THICKNESS_STATS},
    "FreeSurfer 8 + Volume + Cortical Thickness": {"tools": FREESURFER_8_SURFACE_TOOLS, "stats": VOLUME_STATS | THICKNESS_STATS},
    "FreeSurfer 7 + Volume": {"tools": FREESURFER_7_TOOLS, "stats": VOLUME_STATS},
    "FreeSurfer 7 + Cortical Thickness": {"tools": FREESURFER_7_SURFACE_TOOLS, "stats": THICKNESS_STATS},
    "FreeSurfer 7 + Volume + Cortical Thickness": {"tools": FREESURFER_7_SURFACE_TOOLS, "stats": VOLUME_STATS | THICKNESS_STATS},
    "FastSurfer + Volume": {"tools": FASTSURFER_TOOLS, "stats": VOLUME_STATS},
    "FastSurfer + Cortical Thickness": {"tools": FASTSURFER_SURFACE_TOOLS, "stats": THICKNESS_STATS},
    "FastSurfer + Volume + Cortical Thickness": {"tools": FASTSURFER_SURFACE_TOOLS, "stats": VOLUME_STATS | THICKNESS_STATS},
}

