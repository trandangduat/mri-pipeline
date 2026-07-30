from __future__ import annotations

from pipeline.config import ToolContext
from pipeline.presets import FASTSURFER_SURFACE_TOOLS, FASTSURFER_TOOLS, PRESET_CONFIGS
from pipeline.registry import TOOL_DEFS


def test_fastsurfer_volume_preset_uses_volume_stats_without_surface_stages() -> None:
    expected_tools = {
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

    assert FASTSURFER_TOOLS == expected_tools
    assert PRESET_CONFIGS["FastSurfer + Volume"]["tools"] == expected_tools


def test_fastsurfer_surface_presets_keep_full_stats_extraction() -> None:
    assert FASTSURFER_SURFACE_TOOLS["stats_extraction"] == "fastsurfer_stats_extraction"
    assert PRESET_CONFIGS["FastSurfer + Cortical Thickness"]["tools"]["stats_extraction"] == "fastsurfer_stats_extraction"
    assert PRESET_CONFIGS["FastSurfer + Volume + Cortical Thickness"]["tools"]["stats_extraction"] == "fastsurfer_stats_extraction"


def test_fastsurfer_volume_stats_do_not_require_surface_outputs() -> None:
    command = TOOL_DEFS["fastsurfer_volume_stats_extraction"]["command_builder"](
        ToolContext(input_path="/input/T1.mgz", subject_id="subj", threads=4, device="cpu")
    )

    assert "aparc.DKTatlas+aseg.deep" in command
    assert "normalize_volumes.py" in command
    assert "subcortical_volume.tsv" in command
    assert "cortical_volume.tsv" in command
    assert "sphere.reg" not in command
    assert "mris_anatomical_stats" not in command
    assert "mri_surf2volseg" not in command


def test_fastsurfer_full_stats_still_requires_surface_outputs() -> None:
    command = TOOL_DEFS["fastsurfer_stats_extraction"]["command_builder"](
        ToolContext(input_path="/input/T1.mgz", subject_id="subj", threads=4, device="cpu")
    )

    assert "sphere.reg" in command
    assert "mris_anatomical_stats" in command
