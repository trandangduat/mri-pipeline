from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest
import yaml

import pipeline.neuroflow_adapter as neuroflow_adapter
from pipeline.config import BatchImageResult
from pipeline.neuroflow_adapter import (
    NEUROFLOW_STAGE_TO_LOCAL_STAGE,
    _neuroflow_config_root,
    _preset_id_from_request,
    run_neuroflow_batch,
)


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


def test_neuroflow_config_root_uses_tracked_pipeline_configs() -> None:
    root = _neuroflow_config_root()

    assert root.as_posix().endswith("configs/neuroflow")
    assert (root / "presets" / "freesurfer8_all.yaml").is_file()
    assert (root / "profiles" / "freesurfer8_all_default.yaml").is_file()


def test_freesurfer8_volume_neuroflow_preset_only_schedules_active_volume_stages() -> None:
    root = _neuroflow_config_root()
    preset = yaml.safe_load((root / "presets" / "freesurfer8_volumetrics.yaml").read_text())
    profiles = yaml.safe_load((root / "profiles" / "freesurfer8_volumetrics_default.yaml").read_text())

    assert [stage["id"] for stage in preset["stages"]] == [
        "reorient_resize",
        "subcortical_segmentation",
        "statistics_atlas_mapping",
    ]
    assert {profile["stage"] for profile in profiles["profiles"]} == {
        "reorient_resize",
        "subcortical_segmentation",
        "statistics_atlas_mapping",
    }


class _Record:
    def __init__(self, **kwargs: object) -> None:
        self.__dict__.update(kwargs)


@dataclass
class _FakeStep:
    success: bool = True
    duration_sec: float = 0.01
    peak_ram_bytes: int = 1024 * 1024
    error: str = ""
    return_code: int = 0
    tool: str = "fake_tool"
    peak_cpu_pct: float = 12.0


class _FakeAdaptiveScheduler:
    instances: list[_FakeAdaptiveScheduler] = []

    def __init__(self) -> None:
        self.launch_requests: list[object] = []
        self.results: list[object] = []
        self._requested = False
        self.thread_id = threading.get_ident()

    @classmethod
    def create(cls, **_kwargs: object) -> _FakeAdaptiveScheduler:
        scheduler = cls()
        cls.instances.append(scheduler)
        return scheduler

    @classmethod
    def load(cls, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(scheduler=cls.create())

    def add_images(self, **_kwargs: object) -> None:
        return None

    def request_launches(self, *, request: object) -> SimpleNamespace:
        self.launch_requests.append(request)
        if self._requested:
            return SimpleNamespace(terminal=True, launches=(), reason="done")
        self._requested = True
        launches = (
            _Record(
                image_id="subject-a",
                stage_id="reorient_resize",
                attempt_id="attempt-a",
                reservation_id="reservation-a",
                task_id="task-a",
                execution_mode=SimpleNamespace(value="cpu"),
                cpu_threads=1,
                gpu_id=None,
                configuration_id="config-a",
            ),
            _Record(
                image_id="subject-b",
                stage_id="reorient_resize",
                attempt_id="attempt-b",
                reservation_id="reservation-b",
                task_id="task-b",
                execution_mode=SimpleNamespace(value="cpu"),
                cpu_threads=1,
                gpu_id=None,
                configuration_id="config-b",
            ),
        )
        return SimpleNamespace(terminal=False, launches=launches, reason="ready")

    def confirm_started(self, **_kwargs: object) -> None:
        assert threading.get_ident() == self.thread_id
        return None

    def report_result(self, *, result: object) -> None:
        assert threading.get_ident() == self.thread_id
        self.results.append(result)

    def save(self) -> None:
        return None

    def close(self) -> None:
        return None


def _install_fake_neuroflow(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_neuroflow = ModuleType("neuroflow")
    fake_neuroflow.AdaptiveScheduler = _FakeAdaptiveScheduler
    fake_neuroflow.AddImagesRequest = _Record
    fake_neuroflow.ConfirmStart = _Record
    fake_neuroflow.ErrorCategory = SimpleNamespace(PROCESS_CRASH="process_crash")
    fake_neuroflow.GPUResource = _Record
    fake_neuroflow.ImageSpec = _Record
    fake_neuroflow.LaunchRequest = _Record
    fake_neuroflow.ResourceSnapshot = _Record
    fake_neuroflow.ResultStatus = SimpleNamespace(SUCCEEDED="succeeded", FAILED="failed")
    fake_neuroflow.TaskError = _Record
    fake_neuroflow.TaskMetrics = _Record
    fake_neuroflow.TaskResult = _Record

    fake_config = ModuleType("neuroflow.configuration")

    def load_pipeline_file(_path: object) -> SimpleNamespace:
        return SimpleNamespace(pipeline_id="fake_pipeline", pipeline_version="1")

    def load_profile_set_file(_path: object) -> object:
        return object()

    def load_scheduler_dict(value: object) -> object:
        return value

    def validate_cross_documents(*_args: object) -> None:
        return None

    fake_config.load_pipeline_file = load_pipeline_file
    fake_config.load_profile_set_file = load_profile_set_file
    fake_config.load_scheduler_dict = load_scheduler_dict
    fake_config.validate_cross_documents = validate_cross_documents

    monkeypatch.setitem(sys.modules, "neuroflow", fake_neuroflow)
    monkeypatch.setitem(sys.modules, "neuroflow.configuration", fake_config)


def test_neuroflow_batch_runs_ready_launches_concurrently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeAdaptiveScheduler.instances = []
    _install_fake_neuroflow(monkeypatch)
    barrier = threading.Barrier(2, timeout=1.0)
    stage_calls: list[str] = []

    def fake_run_pipeline_stage(config: object, _stage: str, **_kwargs: object) -> tuple[_FakeStep, str]:
        stage_calls.append(config.subject_id)
        barrier.wait()
        return _FakeStep(), str(tmp_path / config.subject_id / "out.mgz")

    class FakeStatsGenerator:
        def __init__(self, _config: object) -> None:
            pass

        def generate(self, _subject_dir: object, _subject_id: object) -> SimpleNamespace:
            return SimpleNamespace(files=[], warnings=[])

    monkeypatch.setattr(neuroflow_adapter, "run_pipeline_stage", fake_run_pipeline_stage)
    monkeypatch.setattr(neuroflow_adapter, "StatsGenerator", FakeStatsGenerator)

    def write_batch_reports(_context: object) -> None:
        return None

    monkeypatch.setattr(neuroflow_adapter, "write_batch_reports", write_batch_reports)

    results = run_neuroflow_batch(
        job_dir=tmp_path / "job",
        req={
            "pipeline_mode": "FreeSurfer 8 + Volume",
            "effective_output_dir": str(tmp_path / "out"),
            "selected_tools": {"reorientation": "fake_tool"},
            "threads": 2,
            "neuroflow_max_concurrent_tasks": 2,
        },
        input_files=[str(tmp_path / "a.nii.gz"), str(tmp_path / "b.nii.gz")],
        subject_id_map={
            str(tmp_path / "a.nii.gz"): "subject-a",
            str(tmp_path / "b.nii.gz"): "subject-b",
        },
    )

    scheduler = _FakeAdaptiveScheduler.instances[0]
    assert sorted(stage_calls) == ["subject-a", "subject-b"]
    assert scheduler.launch_requests[0].maximum_number == 2
    assert len(scheduler.results) == 2
    assert [result.subject_id for result in results] == ["subject-a", "subject-b"]
    assert all(isinstance(result, BatchImageResult) for result in results)
