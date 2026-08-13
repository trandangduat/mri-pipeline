from __future__ import annotations

from pathlib import Path

from pipeline.config import PipelineConfig
from pipeline.executor import DockerResourceMetrics, ExecutionRequest, ExecutionResult
from pipeline.registry import FREESURFER_RECON_STYLE_TIMEOUT
from pipeline.runner import run_pipeline


class RecordingExecutor:
    def __init__(self) -> None:
        self.requests: list[ExecutionRequest] = []

    def execute(self, req: ExecutionRequest, on_metrics=None) -> ExecutionResult:
        self.requests.append(req)
        for host_path, container_path in req.mounts:
            if container_path == "/work":
                Path(host_path, "01_reoriented.nii.gz").write_text("ok", encoding="utf-8")
                break
        return ExecutionResult(
            success=True,
            error="",
            output="completed",
            duration_sec=0.1,
            metrics=DockerResourceMetrics(),
            container_name=req.container_name,
            return_code=0,
        )


class MultiStageExecutor:
    def __init__(self) -> None:
        self.requests: list[ExecutionRequest] = []

    def execute(self, req: ExecutionRequest, on_metrics=None) -> ExecutionResult:
        self.requests.append(req)
        output_names = ["01_reoriented.nii.gz"] if len(self.requests) == 1 else ["02_synthstrip_brain.nii.gz", "02_synthstrip_brain_mask.nii.gz"]
        for host_path, container_path in req.mounts:
            if container_path == "/work":
                for name in output_names:
                    Path(host_path, name).write_text("ok", encoding="utf-8")
                break
        return ExecutionResult(
            success=True,
            error="",
            output="completed",
            duration_sec=0.1,
            metrics=DockerResourceMetrics(),
            container_name=req.container_name,
            return_code=0,
        )


class SegmentationExecutor:
    def __init__(self) -> None:
        self.requests: list[ExecutionRequest] = []

    def execute(self, req: ExecutionRequest, on_metrics=None) -> ExecutionResult:
        self.requests.append(req)
        for host_path, container_path in req.mounts:
            if container_path == "/work":
                Path(host_path, "freesurfer", "sub-01", "mri").mkdir(parents=True, exist_ok=True)
                Path(host_path, "freesurfer", "sub-01", "mri", "aseg.presurf.mgz").write_text("ok", encoding="utf-8")
                break
        return ExecutionResult(
            success=True,
            error="",
            output="completed",
            duration_sec=0.1,
            metrics=DockerResourceMetrics(),
            container_name=req.container_name,
            return_code=0,
        )


class Fs8BiasExecutor:
    def __init__(self) -> None:
        self.requests: list[ExecutionRequest] = []

    def execute(self, req: ExecutionRequest, on_metrics=None) -> ExecutionResult:
        self.requests.append(req)
        for host_path, container_path in req.mounts:
            if container_path == "/work":
                mri_dir = Path(host_path, "freesurfer", "sub-01", "mri")
                mri_dir.mkdir(parents=True, exist_ok=True)
                Path(mri_dir, "brain.finalsurfs.mgz").write_text("ok", encoding="utf-8")
                break
        return ExecutionResult(
            success=True,
            error="",
            output="completed",
            duration_sec=0.1,
            metrics=DockerResourceMetrics(),
            container_name=req.container_name,
            return_code=0,
        )


def test_run_pipeline_executes_tool_with_execution_request(tmp_path, mocker) -> None:
    input_file = tmp_path / "input.nii.gz"
    input_file.write_text("input", encoding="utf-8")
    output_dir = tmp_path / "outputs"
    executor = RecordingExecutor()
    mocker.patch("pipeline.runner.require_image", return_value=(True, ""))

    config = PipelineConfig(
        input_file=str(input_file),
        output_dir=str(output_dir),
        subject_id="sub-01",
        selected_tools={
            "reorientation": "mri_convert_fs7",
            "brain_extraction": "",
            "segmentation": "",
            "template_registration": "",
            "bias_correction": "",
            "white_matter_segmentation": "",
            "surface_reconstruction": "",
            "surface_registration": "",
            "stats_extraction": "",
        },
    )

    results = run_pipeline(config, executor=executor)

    assert len(executor.requests) == 1
    req = executor.requests[0]
    assert isinstance(req, ExecutionRequest)
    assert req.image == "mkdayyyy/mri-fs7-all:latest"
    assert req.command == ["bash", "-c", "mri_convert /input/input.nii.gz /work/01_reoriented.nii.gz"]
    assert (str(input_file.parent), "/input") in req.mounts
    assert (str(output_dir / "sub-01"), "/work") in req.mounts
    assert results[0].success is True


def test_run_pipeline_passes_prior_stage_output_to_next_stage(tmp_path, mocker) -> None:
    input_file = tmp_path / "input.nii.gz"
    input_file.write_text("input", encoding="utf-8")
    output_dir = tmp_path / "outputs"
    executor = MultiStageExecutor()
    mocker.patch("pipeline.runner.require_image", return_value=(True, ""))

    config = PipelineConfig(
        input_file=str(input_file),
        output_dir=str(output_dir),
        subject_id="sub-01",
        selected_tools={
            "reorientation": "mri_convert_fs7",
            "brain_extraction": "synthstrip_fs7",
            "segmentation": "",
            "template_registration": "",
            "bias_correction": "",
            "white_matter_segmentation": "",
            "surface_reconstruction": "",
            "surface_registration": "",
            "stats_extraction": "",
        },
    )

    results = run_pipeline(config, executor=executor)

    assert [result.stage for result in results] == ["reorientation", "brain_extraction"]
    assert len(executor.requests) == 2
    assert executor.requests[1].command == [
        "bash",
        "-c",
        "mri_synthstrip -i /work/mri/01_reoriented.nii.gz -o /work/02_synthstrip_brain.nii.gz -m /work/02_synthstrip_brain_mask.nii.gz ",
    ]


def test_run_pipeline_uses_tool_specific_timeout_for_fs7_segmentation(tmp_path, mocker) -> None:
    input_file = tmp_path / "input.nii.gz"
    input_file.write_text("input", encoding="utf-8")
    output_dir = tmp_path / "outputs"
    executor = SegmentationExecutor()
    mocker.patch("pipeline.runner.require_image", return_value=(True, ""))

    config = PipelineConfig(
        input_file=str(input_file),
        output_dir=str(output_dir),
        subject_id="sub-01",
        selected_tools={
            "reorientation": "",
            "brain_extraction": "",
            "segmentation": "fs7_recon_style_segmentation",
            "template_registration": "",
            "bias_correction": "",
            "white_matter_segmentation": "",
            "surface_reconstruction": "",
            "surface_registration": "",
            "stats_extraction": "",
        },
    )

    results = run_pipeline(config, executor=executor)

    assert results[0].success is True
    assert executor.requests[0].timeout > 7200


def test_run_pipeline_uses_recon_style_timeout_for_fs8_bias_correction(tmp_path, mocker) -> None:
    input_file = tmp_path / "input.mgz"
    input_file.write_text("input", encoding="utf-8")
    output_dir = tmp_path / "outputs"
    executor = Fs8BiasExecutor()
    mocker.patch("pipeline.runner.require_image", return_value=(True, ""))

    config = PipelineConfig(
        input_file=str(input_file),
        output_dir=str(output_dir),
        subject_id="sub-01",
        selected_tools={
            "reorientation": "",
            "brain_extraction": "",
            "segmentation": "",
            "template_registration": "",
            "bias_correction": "fs8_reduced54_bias_correction",
            "white_matter_segmentation": "",
            "surface_reconstruction": "",
            "surface_registration": "",
            "stats_extraction": "",
        },
    )

    results = run_pipeline(config, executor=executor)

    assert results[0].success is True
    assert executor.requests[0].timeout == FREESURFER_RECON_STYLE_TIMEOUT


def test_run_pipeline_fails_without_pull_when_image_missing(tmp_path, mocker) -> None:
    input_file = tmp_path / "input.nii.gz"
    input_file.write_text("input", encoding="utf-8")
    output_dir = tmp_path / "outputs"
    executor = RecordingExecutor()
    mocker.patch("pipeline.runner.require_image", return_value=(False, "Docker image missing: test/image:latest. Download it from Tools Configuration before starting the pipeline."))

    config = PipelineConfig(
        input_file=str(input_file),
        output_dir=str(output_dir),
        subject_id="sub-01",
        selected_tools={
            "reorientation": "mri_convert_fs7",
            "brain_extraction": "",
            "segmentation": "",
            "template_registration": "",
            "bias_correction": "",
            "white_matter_segmentation": "",
            "surface_reconstruction": "",
            "surface_registration": "",
            "stats_extraction": "",
        },
    )

    results = run_pipeline(config, executor=executor)

    assert len(executor.requests) == 0
    assert len(results) == 1
    assert results[0].success is False
    assert "Tools Configuration" in results[0].error
