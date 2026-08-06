from __future__ import annotations

from pipeline.config import ToolContext
from pipeline.presets import CAT12_FULL_TOOLS, CAT12_VOLUME_TOOLS, PRESET_CONFIGS, THICKNESS_STATS, VOLUME_STATS
from pipeline.registry import TOOL_DEFS


def test_cat12_volume_preset_runs_cat_segmentation_and_stats_only() -> None:
    expected_tools = {
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

    assert CAT12_VOLUME_TOOLS == expected_tools
    assert PRESET_CONFIGS["CAT12 + Volume"] == {"tools": expected_tools, "stats": VOLUME_STATS}


def test_cat12_full_preset_runs_monolithic_surface_segmentation_and_stats() -> None:
    expected_tools = {
        "reorientation": "",
        "brain_extraction": "",
        "segmentation": "cat12_full_segmentation",
        "template_registration": "",
        "bias_correction": "",
        "white_matter_segmentation": "",
        "surface_reconstruction": "",
        "surface_registration": "",
        "stats_extraction": "cat12_full_stats_extraction",
    }

    assert CAT12_FULL_TOOLS == expected_tools
    assert PRESET_CONFIGS["CAT12 + Volume + Cortical Thickness"] == {
        "tools": expected_tools,
        "stats": VOLUME_STATS | THICKNESS_STATS,
    }


def test_cat12_volume_tools_use_standalone_image_without_surface_processing() -> None:
    segmentation = TOOL_DEFS["cat12_volume_segmentation"]
    stats = TOOL_DEFS["cat12_volume_stats_extraction"]

    assert segmentation["image"] == "duattran05/cat12_26_glibc:latest"
    assert stats["image"] == "duattran05/cat12_26_glibc:latest"
    assert segmentation["stage"] == "segmentation"
    assert segmentation["needs_license"] is False
    assert stats["stage"] == "stats_extraction"
    assert stats["needs_license"] is False
    assert "mri/mwp1*.nii.gz" in segmentation["output_globs"]
    assert "mri/p0*.nii.gz" in segmentation["output_globs"]

    ctx = ToolContext(input_path="/input/sub-01_T1w.nii", subject_id="sub-01", threads=4, device="cpu")
    command = segmentation["command_builder"](ctx)

    assert "cat_standalone_segment.m" in command
    assert "output.surface = 0" in command
    assert "CAT12 batch has unexpected output.surface setting" in command
    assert "CAT Preprocessing error" in command
    assert "catROI_*.xml" in command
    assert "case \"$INPUT_BASE\"" in command
    assert "*.mgz|*.mgh) WORK_INPUT=input.nii" in command
    assert "nibabel as nib" in command
    assert "CAT12 supports .nii, .nii.gz, .mgz, or .mgh input files" in command
    assert "cp \"$INPUT\" \"/work/$WORK_INPUT\"" in command


def test_cat12_full_tools_use_surface_candidate_image_and_thickness_output() -> None:
    segmentation = TOOL_DEFS["cat12_full_segmentation"]
    stats = TOOL_DEFS["cat12_full_stats_extraction"]

    assert segmentation["image"] == "duattran05/cat12_26_glibc:latest"
    assert stats["image"] == "duattran05/cat12_26_glibc:latest"
    assert "CAT12.9/surf/*thickness*" in segmentation["output_globs"]
    assert "stats/cat12_cortical_thickness.tsv" in stats["output_globs"]

    command = segmentation["command_builder"](
        ToolContext(input_path="/input/sub-01_T1w.nii", subject_id="sub-01", threads=4, device="cpu")
    )
    stats_command = stats["command_builder"](
        ToolContext(input_path="/work/CAT12.9/mri/mwp1input.nii", subject_id="sub-01", threads=4, device="cpu")
    )

    assert "cat_standalone_segment_enigma.m" in command
    assert "output.surface = 2" in command
    assert "*thickness*" in command
    assert "--output-thickness /output/stats/cat12_cortical_thickness.tsv" in stats_command


def test_cat12_volume_stats_command_normalizes_cat_xml_outputs() -> None:
    command = TOOL_DEFS["cat12_volume_stats_extraction"]["command_builder"](
        ToolContext(input_path="/work/mri/mwp1input.nii", subject_id="sub-01", threads=4, device="cpu")
    )

    assert "--cat-report" in command
    assert "--cat-roi" in command
    assert "subcortical_volume.tsv" in command
    assert "cortical_volume.tsv" in command
