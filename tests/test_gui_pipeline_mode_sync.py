from __future__ import annotations

import sys
from types import SimpleNamespace

sys.modules.setdefault("sv_ttk", SimpleNamespace(set_theme=lambda _theme: None))

from ui.main import PipelineGUI


class Value:
    def __init__(self, value: str | bool) -> None:
        self.value = value

    def get(self) -> str | bool:
        return self.value

    def set(self, value: str | bool) -> None:
        self.value = value


def test_fastsurfer_full_keeps_brain_extraction_not_available_when_syncing_thickness() -> None:
    gui = PipelineGUI.__new__(PipelineGUI)
    gui.state = SimpleNamespace(
        pipeline_mode=Value("FastSurfer + Volume + Cortical Thickness"),
        stat_vector_enabled_vars={"cortical_thickness": Value(True)},
        tool_vars={
            "brain_extraction": Value("Not available"),
            "template_registration": Value("FastSurfer Template Registration"),
            "bias_correction": Value("FastSurfer Standardization"),
            "white_matter_segmentation": Value("FastSurfer WM Segmentation"),
            "surface_reconstruction": Value("Not available"),
            "surface_registration": Value("Not available"),
        },
    )

    PipelineGUI._sync_surface_stages_with_stats(gui)

    assert gui.state.tool_vars["brain_extraction"].get() == "Not available"
    assert gui.state.tool_vars["surface_reconstruction"].get() == "FastSurfer Surface Reconstruction"
    assert gui.state.tool_vars["surface_registration"].get() == "FastSurfer Surface Registration"


def test_cat12_volume_skips_reorientation_and_surface_stages() -> None:
    gui = PipelineGUI.__new__(PipelineGUI)
    gui.state = SimpleNamespace(pipeline_mode=Value("CAT12 + Volume"))

    skipped = PipelineGUI._volume_skipped_stages_for_mode(gui)

    assert "reorientation" in skipped
    assert "brain_extraction" in skipped
    assert "template_registration" in skipped
    assert "bias_correction" in skipped
    assert "white_matter_segmentation" in skipped
    assert "surface_reconstruction" in skipped
    assert "surface_registration" in skipped
    assert "segmentation" not in skipped
    assert "stats_extraction" not in skipped


def test_cat12_full_skips_reorientation_and_surface_stage_dropdowns() -> None:
    gui = PipelineGUI.__new__(PipelineGUI)
    gui.state = SimpleNamespace(pipeline_mode=Value("CAT12 + Volume + Cortical Thickness"))

    skipped = PipelineGUI._volume_skipped_stages_for_mode(gui)

    assert "reorientation" in skipped
    assert "surface_reconstruction" in skipped
    assert "surface_registration" in skipped
    assert "segmentation" not in skipped
    assert "stats_extraction" not in skipped
