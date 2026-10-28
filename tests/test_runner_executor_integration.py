from __future__ import annotations

from pathlib import Path
import re

import pytest

from pipeline.config import PipelineConfig
from pipeline.executor import DockerResourceMetrics, ExecutionRequest, ExecutionResult, LocalDockerExecutor
from pipeline.registry import FREESURFER_RECON_STYLE_TIMEOUT, TOOL_DEFS
from pipeline.runner import _build_execution_request, run_pipeline, run_pipeline_stage


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


def test_run_pipeline_includes_container_name_suffix_when_configured(tmp_path, mocker) -> None:
    input_file = tmp_path / "input.nii.gz"
    input_file.write_text("input", encoding="utf-8")
    output_dir = tmp_path / "outputs"
    executor = RecordingExecutor()
    mocker.patch("pipeline.runner.require_image", return_value=(True, ""))

    config = PipelineConfig(
        input_file=str(input_file),
        output_dir=str(output_dir),
        subject_id="sub-01",
        container_name_suffix="reorientation_attempt-a",
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
    assert executor.requests[0].container_name.startswith(
        "mri-sub-01-mri_convert_fs7-reorientation_attempt-a-"
    )
    assert results[0].success is True


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


@pytest.mark.parametrize("threads", [1, 2, 4, 8])
@pytest.mark.parametrize("tool_key,gpu_device_id", [
    ("ordinary_args", None), ("fs8_reduced54_segmentation", None),
    ("fastsurfer_segmentation", None), ("fastsurfer_segmentation", "0"),
    ("fastsurfer_segmentation", "1"), ("fastsurfer_segmentation", "GPU-one"),
])
def test_selected_cpu_threads_reach_tool_and_docker(tmp_path, mocker, threads, tool_key, gpu_device_id):
    tool = {"image": "mock/tool"} if tool_key == "ordinary_args" else TOOL_DEFS[tool_key]
    config = PipelineConfig(
        input_file=str(tmp_path / "input.nii.gz"),
        output_dir=str(tmp_path / "out"),
        subject_id="sub-01",
        device="gpu" if gpu_device_id is not None else "cpu",
        gpu_device_id=gpu_device_id,
        threads=threads,
        cpu_thread_limit=threads,
    )
    req = _build_execution_request(
        tool_key=tool_key,
        tool=tool,
        config=config,
        subject_dir=str(tmp_path / "out/sub-01"),
        logs_dir=str(tmp_path / "logs"),
        input_for_next_step=None,
        license_mount=[],
        memory_limit_bytes=None,
    )
    process = mocker.Mock()
    process.communicate.return_value = ("completed", None)
    process.returncode = 0
    popen = mocker.patch("pipeline.executor.subprocess.Popen", return_value=process)
    mocker.patch("pipeline.executor.threading.Thread.start")
    mocker.patch("pipeline.executor.threading.Thread.join")

    result = LocalDockerExecutor().execute(req)

    assert result.success
    command = popen.call_args.args[0]
    assert command.count("--cpus") == 1
    assert command[command.index("--cpus") + 1] == str(threads)
    if gpu_device_id is None:
        assert "--gpus" not in command
    else:
        assert command[command.index("--gpus") + 1] == f"device={gpu_device_id}"
    if tool_key == "ordinary_args":
        assert command[command.index("--threads") + 1] == str(threads)
    else:
        assert req.args == []
        script = command[-1]
        if tool_key == "fastsurfer_segmentation":
            script = script.split("run_prediction.py", 1)[1].split(";", 1)[0]
        assert re.search(rf"--threads\s+{threads}(?=\s|;|$)", script)


@pytest.mark.parametrize("cpu_thread_limit", [None, 2])
def test_run_pipeline_stage_logs_selected_cpu_and_quota(tmp_path, mocker, cpu_thread_limit):
    input_file = tmp_path / "input.nii.gz"
    input_file.write_text("input")
    mocker.patch("pipeline.runner.require_image", return_value=(True, ""))
    executor = RecordingExecutor()
    config = PipelineConfig(
        input_file=str(input_file),
        output_dir=str(tmp_path / "out"),
        subject_id="sub-01",
        threads=4,
        cpu_thread_limit=cpu_thread_limit,
        selected_tools={"reorientation": "mri_convert_fs7"},
    )

    result, _ = run_pipeline_stage(config, "reorientation", executor=executor)

    assert result.success
    assert executor.requests[0].cpu_thread_limit == cpu_thread_limit
    stage_log = (tmp_path / "out/sub-01/logs/mri_convert_fs7.log").read_text()
    assert "Selected CPU threads: 4" in stage_log
    quota = cpu_thread_limit if cpu_thread_limit is not None else "unlimited"
    assert f"Docker CPU quota: {quota}" in stage_log
    assert "Peak CPU: n/a" in stage_log
    assert "Mean CPU: n/a" in stage_log
    assert "P95 CPU: n/a" in stage_log


@pytest.mark.parametrize("peak", [0, 321, None])
def test_run_pipeline_stage_preserves_gpu_metric_and_diagnostics(tmp_path, mocker, peak):
    from dataclasses import asdict
    input_file = tmp_path / "input.nii.gz"
    input_file.write_text("input")
    mocker.patch("pipeline.runner.require_image", return_value=(True, ""))
    class GPUExecutor(RecordingExecutor):
        def execute(self, req, on_metrics=None):
            result = super().execute(req, on_metrics)
            result.metrics = DockerResourceMetrics(
                peak_ram_bytes=1024**2, peak_gpu_memory_mib=peak,
                gpu_telemetry={"gpu_uuid": "GPU-one", "valid_samples": 1 if peak is not None else 0,
                               "reason": "" if peak is not None else "unsupported"})
            return result
    config = PipelineConfig(
        str(input_file), str(tmp_path / "out"), "sub-01", device="gpu", gpu_device_id="1",
        selected_tools={"reorientation": "mri_convert_fs7"})
    step, output = run_pipeline_stage(config, "reorientation", executor=GPUExecutor())
    assert step.success and Path(output).is_file()
    assert step.peak_gpu_memory_mib == peak
    # The remote result serializer uses dataclass fields.
    assert asdict(step)["peak_gpu_memory_mib"] == peak
    assert step.gpu_telemetry["gpu_uuid"] == "GPU-one"
    stage_log = (tmp_path / "out/sub-01/logs/mri_convert_fs7.log").read_text()
    assert f"Peak GPU memory (sampled MiB): {peak}" in stage_log
