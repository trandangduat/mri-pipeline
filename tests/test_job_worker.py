from __future__ import annotations

import importlib

from pipeline.config import StepResult
from pipeline.presets import PRESET_CONFIGS


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


def test_job_worker_normalizes_stats_vector_config_before_from_dict(mocker, tmp_path) -> None:
    job_worker = importlib.import_module("pipeline.job_worker")
    captured: list[object] = []

    def fake_run_pipeline(config, **_kwargs):
        return [StepResult("segmentation", "cat12_volume_segmentation", True, 1.0, "")]

    mocker.patch.object(job_worker, "run_pipeline", side_effect=fake_run_pipeline)
    mocker.patch.object(job_worker, "write_batch_reports")

    original_from_dict = job_worker.StatsVectorConfig.from_dict.__func__

    def recording_from_dict(data):
        captured.append(data)
        return original_from_dict(job_worker.StatsVectorConfig, data)

    mocker.patch.object(job_worker.StatsVectorConfig, "from_dict", recording_from_dict)
    req = {
        "mode": "file",
        "input_file": "/input/sub-01.nii",
        "output_dir": str(tmp_path / "outputs"),
        "pipeline_mode": "FreeSurfer 7 + Volume",
        "selected_tools": {
            "reorientation": "fs7_recon_style_reorientation",
            "template_registration": "fs7_recon_style_template_registration",
            "brain_extraction": "fs7_recon_style_brain_extraction",
            "segmentation": "fs7_recon_style_segmentation",
            "stats_extraction": "fs7_recon_style_subcortical_stats",
        },
        "stats_vector_config": {
            "atlases": {"subcortical_volume": ["freesurfer_aseg"]},
        },
    }

    code = job_worker._run_job(tmp_path, req)

    assert code == 0
    assert captured
    normalized = captured[0]
    assert normalized["enabled_stats"] == {
        "cortical_thickness": False,
        "cortical_volume": False,
        "subcortical_volume": True,
    }
    assert normalized["atlases"]["subcortical_volume"] == ["freesurfer_aseg"]


def test_job_worker_infers_neuroflow_preset_from_custom_tool_set(mocker, tmp_path) -> None:
    job_worker = importlib.import_module("pipeline.job_worker")
    captured: dict[str, object] = {}

    def fake_run_neuroflow_batch(**kwargs):
        captured.update(kwargs["req"])
        return []

    mocker.patch("pipeline.neuroflow_adapter.run_neuroflow_batch", side_effect=fake_run_neuroflow_batch)
    req = {
        "mode": "file",
        "input_file": "/input/sub-01.nii",
        "output_dir": str(tmp_path / "outputs"),
        "pipeline_mode": "Custom",
        "selected_tools": dict(PRESET_CONFIGS["FreeSurfer 8 + Volume + Cortical Thickness"]["tools"]),
        "neuroflow_enabled": True,
    }

    code = job_worker._run_job(tmp_path, req)

    assert code == 0
    assert captured["pipeline_mode"] == "FreeSurfer 8 + Volume + Cortical Thickness"


def test_job_worker_main_sets_stopped_state_on_stop_requested(mocker, tmp_path) -> None:
    import json
    from pathlib import Path
    job_worker = importlib.import_module("pipeline.job_worker")

    config_file = tmp_path / "job_config.json"
    config_file.write_text(json.dumps({"mode": "file", "input_file": "001.mgz", "output_dir": str(tmp_path / "out")}))
    (tmp_path / "stop_requested").write_text("stop requested")

    mocker.patch.object(job_worker, "_run_job", return_value=0)
    code = job_worker.main(["--job-config", str(config_file)])

    assert code == 0
    status = json.loads((tmp_path / "job_status.json").read_text())
    assert status["state"] == "stopped"
    assert (tmp_path / "exit_code.txt").read_text().strip() == "0"

