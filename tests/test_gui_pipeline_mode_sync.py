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
