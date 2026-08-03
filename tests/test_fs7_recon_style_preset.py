from __future__ import annotations

from pipeline.config import ToolContext
from pipeline.presets import FREESURFER_7_SURFACE_TOOLS, FREESURFER_7_VOLUME_TOOLS, PRESET_CONFIGS, SUBCORTICAL_VOLUME_STATS
from pipeline.registry import STAGE_ORDER, TOOL_DEFS, stage_order_for_tools


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

EXPECTED_FS7_VOLUME_TOOLS = {
    **EXPECTED_FS7_TOOLS,
    "bias_correction": "",
    "white_matter_segmentation": "",
    "surface_reconstruction": "",
    "surface_registration": "",
    "stats_extraction": "fs7_recon_style_subcortical_stats",
}


def test_freesurfer7_presets_use_recon_style_9_stage_tools() -> None:
    assert FREESURFER_7_SURFACE_TOOLS == EXPECTED_FS7_TOOLS
    assert PRESET_CONFIGS["FreeSurfer 7 + Cortical Thickness"]["tools"] == EXPECTED_FS7_TOOLS
    assert PRESET_CONFIGS["FreeSurfer 7 + Volume + Cortical Thickness"]["tools"] == EXPECTED_FS7_TOOLS


def test_freesurfer7_volume_preset_is_subcortical_only() -> None:
    preset = PRESET_CONFIGS["FreeSurfer 7 + Volume"]

    assert FREESURFER_7_VOLUME_TOOLS == EXPECTED_FS7_VOLUME_TOOLS
    assert preset["tools"] == EXPECTED_FS7_VOLUME_TOOLS
    assert preset["stats"] == SUBCORTICAL_VOLUME_STATS


def test_freesurfer7_recon_style_tools_cover_all_pipeline_stages() -> None:
    for stage in STAGE_ORDER:
        tool_key = EXPECTED_FS7_TOOLS[stage]
        tool = TOOL_DEFS[tool_key]
        assert tool["stage"] == stage
        assert tool["image"] == "mkdayyyy/mri-fs7-all:latest"
        assert tool["needs_license"] is True
        assert callable(tool["command_builder"])
        assert tool["output_files"] or tool.get("output_globs")


def test_freesurfer7_template_registration_runs_before_skull_strip_and_segmentation() -> None:
    stage_order = stage_order_for_tools(EXPECTED_FS7_TOOLS)

    assert STAGE_ORDER.index("brain_extraction") < STAGE_ORDER.index("template_registration")
    assert stage_order.index("template_registration") < stage_order.index("brain_extraction")
    assert stage_order.index("template_registration") < stage_order.index("segmentation")


def test_freesurfer7_commands_match_successful_standalone_flow() -> None:
    ctx = ToolContext(input_path="/input/T1.nii.gz", subject_id="I776974", threads=4, device="cpu")

    commands = {stage: TOOL_DEFS[tool]["command_builder"](ctx) for stage, tool in EXPECTED_FS7_TOOLS.items()}

    assert "mri_convert /input/T1.nii.gz 001.mgz" in commands["reorientation"]
    assert "talairach_avi --i orig_nu.mgz" in commands["template_registration"]
    assert "lta_convert --src orig.mgz --trg \"$MNI305\"" in commands["template_registration"]
    assert "mri_em_register" not in commands["template_registration"]
    assert "mri_ca_register" not in commands["template_registration"]
    assert "talairach_avi --i orig_nu.mgz" not in commands["brain_extraction"]
    assert "mri_nu_correct.mni --i orig.mgz --o nu.mgz" in commands["brain_extraction"]
    assert "mri_normalize -g 1 -seed 1234 -mprage nu.mgz T1.mgz" in commands["brain_extraction"]
    assert "mri_em_register -skull nu.mgz" in commands["brain_extraction"]
    assert "mri_watershed -T1 -brain_atlas" in commands["brain_extraction"]
    assert "mri_em_register -uns 3 -mask brainmask.mgz" in commands["segmentation"]
    assert "mri_ca_normalize $CTRL_FLAG -mask brainmask.mgz" in commands["segmentation"]
    assert "mri_ca_register -threads 4" in commands["segmentation"]
    assert "-mask brainmask.mgz norm.mgz" in commands["segmentation"]
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


def test_freesurfer7_volume_stats_use_aseg_without_surface_dependencies() -> None:
    command = TOOL_DEFS["fs7_recon_style_subcortical_stats"]["command_builder"](
        ToolContext(input_path="/input/T1.nii.gz", subject_id="I776974", threads=4, device="cpu")
    )

    assert "mri_segstats --seg \"$SEG\"" in command
    assert "normalize_volumes.py" in command
    assert "subcortical_volume.tsv" in command
    assert "mris_place_surface" not in command
    assert "mri_surf2volseg" not in command
