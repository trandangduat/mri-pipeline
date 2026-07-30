from __future__ import annotations

from ui.gui_progress import progress_status_for_stage


def test_success_without_tool_is_rendered_as_skipped_for_pipeline_stage() -> None:
    assert progress_status_for_stage("success", "brain_extraction", "") == "skipped"


def test_success_with_tool_stays_success_for_pipeline_stage() -> None:
    assert progress_status_for_stage("success", "brain_extraction", "synthstrip_fs7") == "success"
