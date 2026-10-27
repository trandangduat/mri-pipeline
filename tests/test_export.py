from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import sys

import nibabel as nib
import numpy as np
import pytest

from pipeline import export
from pipeline.config import ExportConfig, PipelineConfig
from pipeline.runner import run_pipeline, run_pipeline_stage
from pipeline.state import PipelineTracker


@pytest.mark.parametrize("name, expected", [
    ("scan.v2", "scan.v2"), ("scan.v2.nii.gz", "scan.v2"),
    ("scan.v2.mgz", "scan.v2"), ("scan.v2.nii", "scan.v2"),
])
def test_strip_only_image_extensions(name, expected):
    assert export._strip_volume_extension(name) == expected


def test_export_names_reject_normalized_cross_stage_collisions():
    tools = {"reorientation": "fs7_recon_style_reorientation",
             "template_registration": "fs7_recon_style_template_registration"}
    config = ExportConfig(names={"reorientation.primary": "scan v2", "template_registration.primary": "scan_v2"})
    assert "shared" in export.export_name_errors(config, tools)[0]
    config.enabled = False
    assert export.export_name_errors(config, tools) == []


def test_parallel_exports_do_not_overwrite_other_stages(tmp_path):
    first, second = tmp_path / "first.mgz", tmp_path / "second.mgz"
    first.write_bytes(b"first-image")
    second.write_bytes(b"second-image")
    config = ExportConfig(default_format="same", names={"reorientation.primary": "scan", "segmentation.primary": "scan"})
    def write(stage, source):
        return export._export_stage_outputs(str(tmp_path), stage, [str(source)], config)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(write, "reorientation", first), pool.submit(write, "segmentation", second)]
        results = [f.result() for f in futures]
    assert sum(bool(paths) for paths, _ in results) == 1
    assert sum(bool(error) for _, error in results) == 1
    assert (tmp_path / "exports/scan.mgz").read_bytes() in (b"first-image", b"second-image")


def test_unknown_existing_export_is_preserved(tmp_path):
    source = tmp_path / "source.mgz"
    source.write_bytes(b"new")
    existing = tmp_path / "exports/01_reoriented.mgz"
    existing.parent.mkdir()
    existing.write_bytes(b"user-file")
    paths, error = export._export_stage_outputs(str(tmp_path), "reorientation", [str(source)], ExportConfig(default_format="same"))
    assert not paths and error
    assert existing.read_bytes() == b"user-file"


def test_owned_export_can_be_recreated_and_dotted_name_is_preserved(tmp_path):
    source = tmp_path / "source.mgz"
    source.write_bytes(b"old")
    config = ExportConfig(default_format="same", names={"reorientation.primary": "scan.v2"})
    paths, error = export._export_stage_outputs(str(tmp_path), "reorientation", [str(source)], config)
    assert not error and Path(paths[0]).name == "scan.v2.mgz"
    source.write_bytes(b"new")
    paths, error = export._export_stage_outputs(str(tmp_path), "reorientation", [str(source)], config)
    assert not error and Path(paths[0]).read_bytes() == b"new"
    with patch.object(export, "_copy_or_convert_export") as convert:
        export._export_stage_outputs(str(tmp_path), "reorientation", [str(source)], config, only_missing=True)
        convert.assert_not_called()
    Path(paths[0]).unlink()
    paths, error = export._export_stage_outputs(str(tmp_path), "reorientation", [str(source)], config, only_missing=True)
    assert not error and Path(paths[0]).read_bytes() == b"new"


def test_nibabel_fallback_preserves_mri_data_and_geometry(tmp_path):
    source, destination = tmp_path / "source.mgz", tmp_path / "converted.nii.gz"
    data = np.arange(60, dtype=np.float32).reshape(3, 4, 5)
    affine = np.diag([1.2, 1.3, 1.4, 1.0])
    nib.save(nib.MGHImage(data, affine), source)
    with patch.object(export, "require_image", return_value=(False, "missing converter")):
        ok, error = export._copy_or_convert_export(source, destination, str(tmp_path))
    assert ok and not error
    original, converted = nib.load(source), nib.load(destination)
    np.testing.assert_allclose(converted.get_fdata(), original.get_fdata())
    np.testing.assert_allclose(converted.affine, original.affine)


def test_converter_preflight_requires_a_working_conversion_path():
    request = {"selected_tools": {"reorientation": "fs7_recon_style_reorientation"},
               "export_config": ExportConfig().to_dict()}
    with patch.dict(sys.modules, {"nibabel": None}), patch.object(export, "require_image", return_value=(False, "missing converter")) as image:
        assert "missing converter" in export.export_conversion_error(request)
        request["export_config"]["default_format"] = "same"
        image.reset_mock()
        assert not export.export_conversion_error(request)
        image.assert_not_called()
        request["export_config"]["enabled"] = False
        assert not export.export_conversion_error(request)
    request["export_config"] = ExportConfig().to_dict()
    with patch.object(export, "require_image", side_effect=AssertionError("fallback should suffice")):
        assert not export.export_conversion_error(request)


@pytest.mark.parametrize("per_stage", [True, False])
def test_resume_creates_missing_export_without_running_mri(tmp_path, per_stage):
    source = tmp_path / "input.nii.gz"
    nib.save(nib.Nifti1Image(np.ones((2, 2, 2)), np.eye(4)), source)
    output = tmp_path / "results"
    subject = output / "subject"
    existing = subject / "mri/01_reoriented.nii.gz"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(source.read_bytes())
    config = PipelineConfig(str(source), str(output), "subject", resume=True,
                            selected_tools={"reorientation": "mri_convert_fs7"},
                            export_config=ExportConfig(names={"reorientation.primary": "resumed.v2"}))
    with patch("pipeline.runner.LocalDockerExecutor.execute", side_effect=AssertionError("MRI must not rerun")):
        result = run_pipeline_stage(config, "reorientation")[0] if per_stage else run_pipeline(config)[0]
    assert result.success
    assert (subject / "exports/resumed.v2.nii.gz").read_bytes() == source.read_bytes()


def test_successful_export_retry_clears_old_error(tmp_path):
    config = PipelineConfig("input.mgz", str(tmp_path), "subject")
    tracker = PipelineTracker(str(tmp_path / "logs"), config, str(tmp_path))
    tracker.add_exported_outputs("reorientation", [], "old export error")
    tracker.add_exported_outputs("reorientation", ["scan.nii.gz"])
    assert "export_error" not in tracker.state["stages"]["reorientation"]


def test_start_validation_rejects_duplicate_export_names(tmp_path):
    from app_backend.run_request import prepare_run_request
    source = tmp_path / "input.mgz"
    source.write_bytes(b"input")
    result = prepare_run_request({"input_path": str(source), "output_dir": str(tmp_path / "output"),
        "pipeline_mode": "FreeSurfer 7 + Volume", "export_config": ExportConfig(names={
            "reorientation.primary": "scan", "template_registration.primary": "scan"}).to_dict()},
        validate_license=False)
    assert not result["ok"]
    assert "shared" in result["errors"][0]


def test_local_preflight_detects_missing_export_converter():
    from app_backend import local_runtime
    from pipeline.docker_runtime import DockerRuntime
    request = {"threads": 1, "ram_percent": 100, "neuroflow_enabled": False,
               "selected_tools": {"reorientation": "fs8_reduced54_reorientation"},
               "export_config": ExportConfig().to_dict()}
    with patch.object(local_runtime, "inspect_docker_runtime", return_value=DockerRuntime(4, 64 * 1024 ** 3)), \
         patch.object(local_runtime, "image_exists", return_value=True), \
         patch.object(export, "require_image", return_value=(False, "missing converter")), \
         patch.dict(sys.modules, {"nibabel": None}):
        events = list(local_runtime.local_runtime_checks(request))
    assert events[-1]["data"]["ok"] is False
    assert "missing converter" in events[-1]["data"]["error"]
