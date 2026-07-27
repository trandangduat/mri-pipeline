from __future__ import annotations

from pipeline.config import ToolContext
from pipeline.presets import FREESURFER_7_SURFACE_TOOLS, PRESET_CONFIGS
from pipeline.registry import STAGE_ORDER, TOOL_DEFS


EXPECTED_FS7_TOOLS = {
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


def test_freesurfer7_presets_use_recon_style_9_stage_tools() -> None:
    assert FREESURFER_7_SURFACE_TOOLS == EXPECTED_FS7_TOOLS
    assert PRESET_CONFIGS["FreeSurfer 7 + Volume"]["tools"] == EXPECTED_FS7_TOOLS
    assert PRESET_CONFIGS["FreeSurfer 7 + Cortical Thickness"]["tools"] == EXPECTED_FS7_TOOLS
    assert PRESET_CONFIGS["FreeSurfer 7 + Volume + Cortical Thickness"]["tools"] == EXPECTED_FS7_TOOLS


def test_freesurfer7_recon_style_tools_cover_all_pipeline_stages() -> None:
    for stage in STAGE_ORDER:
        tool_key = EXPECTED_FS7_TOOLS[stage]
        tool = TOOL_DEFS[tool_key]
        assert tool["stage"] == stage
        assert tool["image"] == "mkdayyyy/mri-fs7-all:latest"
        assert tool["needs_license"] is True
        assert callable(tool["command_builder"])
        assert tool["output_files"] or tool.get("output_globs")


def test_freesurfer7_commands_match_successful_standalone_flow() -> None:
    ctx = ToolContext(input_path="/input/T1.nii.gz", subject_id="I776974", threads=4, device="cpu")

    commands = {stage: TOOL_DEFS[tool]["command_builder"](ctx) for stage, tool in EXPECTED_FS7_TOOLS.items()}

    assert "mri_convert /input/T1.nii.gz 001.mgz" in commands["reorientation"]
    assert "talairach_avi --i orig_nu.mgz" in commands["brain_extraction"]
    assert "mri_watershed -T1 -brain_atlas" in commands["brain_extraction"]
    assert "mri_ca_label -relabel_unlikely 9 .3" in commands["segmentation"]
    assert "mri_cc -aseg aseg.auto_noCCseg.mgz" in commands["segmentation"]
    assert "rm -f aseg.presurf.mgz; cp aseg.auto.mgz aseg.presurf.mgz" in commands["segmentation"]
    assert "test -s transforms/talairach.xfm" in commands["template_registration"]
    assert "mri_normalize -seed 1234 -mprage -aseg aseg.presurf.mgz" in commands["bias_correction"]
    assert "mri_edit_wm_with_aseg -keep-in" in commands["white_matter_segmentation"]
    assert "mris_fix_topology -mgz" in commands["surface_reconstruction"]
    assert "mri_label2label --label-cortex" in commands["surface_reconstruction"]
    assert "mris_register -curv lh.sphere" in commands["surface_registration"]
    assert "mris_ca_label -l label/lh.cortex.label" in commands["surface_registration"]
    assert "mri_surf2volseg --o aseg.mgz" in commands["stats_extraction"]
    assert "mri_segstats --seed 1234 --seg mri/aseg.mgz" in commands["stats_extraction"]
