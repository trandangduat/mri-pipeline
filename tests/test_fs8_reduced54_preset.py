from __future__ import annotations

from pipeline.config import ToolContext
from pipeline.presets import FREESURFER_8_SURFACE_TOOLS, FREESURFER_8_VOLUME_TOOLS, PRESET_CONFIGS
from pipeline.registry import (
    FREESURFER_RECON_STYLE_TIMEOUT,
    STAGE_ORDER,
    TOOL_DEFS,
    enabled_tools_for_stage,
    tool_display_name,
    tool_key_from_display,
)


def test_freesurfer8_surface_presets_use_surface_tools() -> None:
    expected_tools = {
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

    assert FREESURFER_8_SURFACE_TOOLS == expected_tools
    assert PRESET_CONFIGS["FreeSurfer 8 + Cortical Thickness"]["tools"] == expected_tools
    assert PRESET_CONFIGS["FreeSurfer 8 + Volume + Cortical Thickness"]["tools"] == expected_tools


def test_freesurfer8_volume_preset_blanks_surface_stages() -> None:
    assert PRESET_CONFIGS["FreeSurfer 8 + Volume"]["tools"] == FREESURFER_8_VOLUME_TOOLS
    assert FREESURFER_8_VOLUME_TOOLS["reorientation"] == "fs8_reduced54_reorientation"
    assert FREESURFER_8_VOLUME_TOOLS["segmentation"] == "synthseg_freesurfer_fs8"
    assert FREESURFER_8_VOLUME_TOOLS["stats_extraction"] == "fs8_reduced54_stats"
    for stage in ("brain_extraction", "template_registration", "bias_correction", "white_matter_segmentation", "surface_reconstruction", "surface_registration"):
        assert FREESURFER_8_VOLUME_TOOLS[stage] == "", f"{stage} should be blank for volume-only preset"


def test_freesurfer8_surface_tools_cover_all_pipeline_stages() -> None:
    for stage in STAGE_ORDER:
        tool_key = FREESURFER_8_SURFACE_TOOLS[stage]
        tool = TOOL_DEFS[tool_key]
        assert tool["stage"] == stage
        assert tool["image"] == "mkdayyyy/mri-fs8-all:latest"
        assert tool["needs_license"] is True
        assert callable(tool["command_builder"])
        assert tool["output_files"] or tool.get("output_globs")


def test_freesurfer8_surface_outputs_are_pipeline_markers() -> None:
    assert TOOL_DEFS["fs8_reduced54_surface_reconstruction"]["output_globs"] == [
        "freesurfer/*/surf/lh.thickness",
        "freesurfer/*/surf/rh.thickness",
    ]
    assert TOOL_DEFS["fs8_reduced54_surface_registration"]["output_globs"] == [
        "freesurfer/*/surf/lh.sphere.reg",
        "freesurfer/*/surf/rh.sphere.reg",
    ]
    assert TOOL_DEFS["fs8_reduced54_stats"]["output_files"] == [
        "lh.aparc.stats",
        "rh.aparc.stats",
        "aseg.stats",
        "subcortical_volume.tsv",
        "cortical_volume.tsv",
    ]


def test_freesurfer8_long_surface_stages_use_recon_style_timeout() -> None:
    for tool_key in (
        "fs8_reduced54_bias_correction",
        "fs8_reduced54_wm_segmentation",
        "fs8_reduced54_surface_reconstruction",
        "fs8_reduced54_surface_registration",
    ):
        assert TOOL_DEFS[tool_key]["timeout"] == FREESURFER_RECON_STYLE_TIMEOUT


def test_freesurfer8_surface_tool_names_do_not_expose_reduced54() -> None:
    selected_tool_names = [tool_display_name(tool) for tool in FREESURFER_8_SURFACE_TOOLS.values()]
    assert all("Reduced54" not in name for name in selected_tool_names)
    assert "FreeSurfer 8 SynthSeg" in selected_tool_names
    assert "fs8_reduced54_segmentation" not in enabled_tools_for_stage("segmentation")


def test_old_freesurfer8_tools_are_removed() -> None:
    removed_tool_keys = {
        "mri_convert_fs8",
        "synthstrip_fs8",
        "synthmorph_fs8",
        "mri_binarize_fs8",
        "recon_all_fs8",
        "surface_stats_fs8",
        "freesurfer_stats_fs8",
    }
    assert removed_tool_keys.isdisjoint(TOOL_DEFS)


def test_freesurfer8_volume_synthseg_uses_parc() -> None:
    command = TOOL_DEFS["synthseg_freesurfer_fs8"]["command_builder"](
        ToolContext(
            input_path="/input.nii",
            subject_id="subj",
            threads=4,
            device="cpu",
            enabled_stats={"cortical_volume": True, "subcortical_volume": True, "cortical_thickness": False},
        )
    )

    assert "--keepgeom --addctab --parc --cpu" in command


def test_freesurfer8_bias_correction_matches_reduced54_stage5() -> None:
    command = TOOL_DEFS["fs8_reduced54_bias_correction"]["command_builder"](
        ToolContext(
            input_path="/input.nii",
            subject_id="subj",
            threads=4,
            device="cpu",
            enabled_stats={"cortical_volume": True, "subcortical_volume": True, "cortical_thickness": True},
        )
    )

    assert "mri_ca_normalize" in command
    assert "mri_ca_register" not in command
    assert "mri_normalize -seed 1234 -mprage -aseg aseg.presurf.mgz" in command


def test_freesurfer8_template_registration_matches_recon_all_synthmorph() -> None:
    command = TOOL_DEFS["fs8_reduced54_template_registration"]["command_builder"](
        ToolContext(input_path="/input.nii", subject_id="subj", threads=4, device="cpu")
    )

    assert 'fs-synthmorph-reg --i synthstrip.mgz --t "$MNI305" --affine-only' in command
    assert 'lta_convert --ltavox2vox --inlta transforms/synthmorph.mni305/aff.lta' in command
    assert 'fs-synthmorph-reg --s "$SUBJ" --threads 4 --i "$SD/mri/orig.mgz" --test' in command
    assert "warp.to.mni152.1.0mm.1.0mm.inv.nii.gz" in command


def test_skipped_display_value_maps_to_no_tool() -> None:
    assert tool_key_from_display("Skipped") == ""
