from __future__ import annotations

from pathlib import Path

from pipeline.config import PipelineConfig
from pipeline.executor import DockerResourceMetrics, ExecutionRequest, ExecutionResult
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


def test_run_pipeline_executes_tool_with_execution_request(tmp_path, mocker) -> None:
    input_file = tmp_path / "input.nii.gz"
    input_file.write_text("input", encoding="utf-8")
    output_dir = tmp_path / "outputs"
    executor = RecordingExecutor()
    mocker.patch("pipeline.runner.ensure_image", return_value=(True, "", 0.0))

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
