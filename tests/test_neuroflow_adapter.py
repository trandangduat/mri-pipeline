from __future__ import annotations

import pytest

from pipeline.neuroflow_adapter import NEUROFLOW_STAGE_TO_LOCAL_STAGE, _preset_id_from_request


def test_preset_id_from_pipeline_mode() -> None:
    assert (
        _preset_id_from_request({"pipeline_mode": "FreeSurfer 8 + Volume + Cortical Thickness"})
        == "freesurfer8_all"
    )
    assert _preset_id_from_request({"pipeline_mode": "FastSurfer + Volume"}) == "fastsurfer_volumetrics"


def test_explicit_neuroflow_preset_wins() -> None:
    assert (
        _preset_id_from_request(
            {"pipeline_mode": "FreeSurfer 8 + Volume", "neuroflow_preset": "custom_preset"}
        )
        == "custom_preset"
    )


def test_unknown_pipeline_mode_requires_mapping() -> None:
    with pytest.raises(ValueError):
        _preset_id_from_request({"pipeline_mode": "Custom"})


def test_stage_mapping_covers_current_gui_stages() -> None:
    assert NEUROFLOW_STAGE_TO_LOCAL_STAGE["reorient_resize"] == "reorientation"
    assert NEUROFLOW_STAGE_TO_LOCAL_STAGE["subcortical_segmentation"] == "segmentation"
    assert NEUROFLOW_STAGE_TO_LOCAL_STAGE["statistics_atlas_mapping"] == "stats_extraction"
