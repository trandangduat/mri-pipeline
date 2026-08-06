from __future__ import annotations

import importlib

from pipeline.config import StepResult


def test_job_worker_module_imports_after_report_refactor() -> None:
    importlib.import_module("pipeline.job_worker")


def test_job_worker_uses_cat12_preset_tools_over_stale_config(mocker, tmp_path) -> None:
    job_worker = importlib.import_module("pipeline.job_worker")
    captured_tools = {}

    def fake_run_pipeline(config, **_kwargs):
        captured_tools.update(config.selected_tools)
        return [StepResult("segmentation", "cat12_volume_segmentation", True, 1.0, "")]

    mocker.patch.object(job_worker, "run_pipeline", side_effect=fake_run_pipeline)
    mocker.patch.object(job_worker, "write_batch_reports")
    req = {
        "mode": "file",
        "input_file": "/input/sub-01.nii",
        "output_dir": str(tmp_path / "outputs"),
        "pipeline_mode": "CAT12 + Volume",
        "selected_tools": {
            "reorientation": "fastsurfer_reorientation",
            "segmentation": "cat12_volume_segmentation",
            "stats_extraction": "cat12_volume_stats_extraction",
        },
    }

    code = job_worker._run_job(tmp_path, req)

    assert code == 0
    assert captured_tools["reorientation"] == ""
    assert captured_tools["segmentation"] == "cat12_volume_segmentation"
    assert captured_tools["stats_extraction"] == "cat12_volume_stats_extraction"
