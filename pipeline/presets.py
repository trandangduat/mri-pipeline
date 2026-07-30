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
    "template_registration",
    "bias_correction",
    "white_matter_segmentation",
    "surface_reconstruction",
    "surface_registration",
}

FS7_VOLUME_SKIPPED_STAGES = {
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

FREESURFER_8_TOOLS = FREESURFER_8_SURFACE_TOOLS

FASTSURFER_TOOLS = {
    "reorientation": "fastsurfer_reorientation",
    "brain_extraction": "",
    "segmentation": "fastsurfer_segmentation",
    "template_registration": "fastsurfer_template_registration",
    "bias_correction": "fastsurfer_standardization",
    "white_matter_segmentation": "fastsurfer_wm_segmentation",
    "surface_reconstruction": "",
    "surface_registration": "",
    "stats_extraction": "fastsurfer_stats_extraction",
}

FASTSURFER_SURFACE_TOOLS = {
    **FASTSURFER_TOOLS,
    "surface_reconstruction": "fastsurfer_surface_reconstruction",
    "surface_registration": "fastsurfer_surface_registration",
}

VOLUME_STATS = {"cortical_volume", "subcortical_volume"}

SUBCORTICAL_VOLUME_STATS = {"subcortical_volume"}

THICKNESS_STATS = {"cortical_thickness"}

PRESET_CONFIGS = {
    "FreeSurfer 8 + Volume": {"tools": FREESURFER_8_TOOLS, "stats": VOLUME_STATS},
    "FreeSurfer 8 + Cortical Thickness": {"tools": FREESURFER_8_SURFACE_TOOLS, "stats": THICKNESS_STATS},
    "FreeSurfer 8 + Volume + Cortical Thickness": {"tools": FREESURFER_8_SURFACE_TOOLS, "stats": VOLUME_STATS | THICKNESS_STATS},
    "FreeSurfer 7 + Volume": {"tools": FREESURFER_7_VOLUME_TOOLS, "stats": SUBCORTICAL_VOLUME_STATS},
    "FreeSurfer 7 + Cortical Thickness": {"tools": FREESURFER_7_SURFACE_TOOLS, "stats": THICKNESS_STATS},
    "FreeSurfer 7 + Volume + Cortical Thickness": {"tools": FREESURFER_7_SURFACE_TOOLS, "stats": VOLUME_STATS | THICKNESS_STATS},
    "FastSurfer + Volume": {"tools": FASTSURFER_TOOLS, "stats": VOLUME_STATS},
    "FastSurfer + Cortical Thickness": {"tools": FASTSURFER_SURFACE_TOOLS, "stats": THICKNESS_STATS},
    "FastSurfer + Volume + Cortical Thickness": {"tools": FASTSURFER_SURFACE_TOOLS, "stats": VOLUME_STATS | THICKNESS_STATS},
}
