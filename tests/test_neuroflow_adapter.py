from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import threading
import time
from types import ModuleType, SimpleNamespace

import pytest
import yaml

import pipeline.neuroflow_adapter as neuroflow_adapter
from pipeline.config import BatchImageResult
from pipeline.neuroflow_adapter import (
    NEUROFLOW_STAGE_TO_LOCAL_STAGE,
    _filter_profiles_for_thread_limit,
    _neuroflow_config_root,
    _preset_id_from_request,
    _scheduler_config,
    is_neuroflow_supported,
    run_neuroflow_batch,
)


@dataclass(frozen=True)
class _ExecutionConfig:
    configuration_id: str
    cpu_threads: int
    profile_ref: str


@dataclass(frozen=True)
class _StageConfig:
    stage_id: str
    execution_configurations: tuple[_ExecutionConfig, ...]


@dataclass(frozen=True)
class _PipelineConfig:
    stages: tuple[_StageConfig, ...]


@dataclass(frozen=True)
class _ProfileConfig:
    profile_id: str
    stage_id: str
    cpu_threads: int


@dataclass(frozen=True)
class _ProfileSetConfig:
    profiles: tuple[_ProfileConfig, ...]


def test_is_neuroflow_supported() -> None:
    assert is_neuroflow_supported({"pipeline_mode": "FreeSurfer 8 + Volume"}) is True
    assert is_neuroflow_supported({"pipeline_mode": "FastSurfer + Volume"}) is True
    assert is_neuroflow_supported({"pipeline_mode": "Custom"}) is False
    assert is_neuroflow_supported({"pipeline_mode": "Custom", "neuroflow_preset": "custom_preset"}) is True


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


def test_neuroflow_profiles_are_filtered_to_scheduler_thread_limit() -> None:
    pipeline = _PipelineConfig(
        stages=(
            _StageConfig(
                stage_id="surface_reconstruction",
                execution_configurations=(
                    _ExecutionConfig("cpu_4", 4, "profile_cpu_4"),
                    _ExecutionConfig("cpu_8", 8, "profile_cpu_8"),
                ),
            ),
        )
    )
    profiles = _ProfileSetConfig(
        profiles=(
            _ProfileConfig("profile_cpu_4", "surface_reconstruction", 4),
            _ProfileConfig("profile_cpu_8", "surface_reconstruction", 8),
        )
    )

    filtered_pipeline, filtered_profiles = _filter_profiles_for_thread_limit(pipeline, profiles, 5)

    assert [config.configuration_id for config in filtered_pipeline.stages[0].execution_configurations] == ["cpu_4"]
    assert [profile.profile_id for profile in filtered_profiles.profiles] == ["profile_cpu_4"]


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


def test_neuroflow_presets_match_normal_active_stages() -> None:
    from pipeline.presets import PRESET_CONFIGS
    from pipeline.registry import stage_order_for_tools

    root = _neuroflow_config_root()
    local_to_neuroflow = {v: k for k, v in NEUROFLOW_STAGE_TO_LOCAL_STAGE.items()}
    for preset_path in sorted((root / "presets").glob("*.yaml")):
        preset = yaml.safe_load(preset_path.read_text())
        mode = str(preset["metadata"]["pipeline_mode"])
        assert mode in PRESET_CONFIGS, f"{preset_path.name}: unknown pipeline mode {mode!r}"

        tools = PRESET_CONFIGS[mode]["tools"]
        stage_order = stage_order_for_tools(tools)
        active_local = [stage for stage in stage_order if tools.get(stage)]
        expected_stage_ids = [local_to_neuroflow[stage] for stage in active_local]
        assert [stage["id"] for stage in preset["stages"]] == expected_stage_ids, preset_path.name

        skipped = set(stage_order) - set(active_local)
        assert set(preset["metadata"]["skipped_pipeline_stages"]) == skipped, preset_path.name


def test_freesurfer7_volume_neuroflow_runs_template_registration_before_brain_extraction() -> None:
    root = _neuroflow_config_root()
    preset = yaml.safe_load((root / "presets" / "freesurfer7_volumetrics.yaml").read_text())

    stage_ids = [stage["id"] for stage in preset["stages"]]
    assert "template_registration" in stage_ids

    brain_extraction = next(stage for stage in preset["stages"] if stage["id"] == "brain_extraction")
    template_registration = next(stage for stage in preset["stages"] if stage["id"] == "template_registration")
    assert "template_registration" in brain_extraction["depends_on"]
    assert "reorient_resize" in template_registration["depends_on"]
    assert stage_ids.index("reorient_resize") < stage_ids.index("template_registration") < stage_ids.index("brain_extraction")
    assert "template_registration" not in preset["metadata"]["skipped_pipeline_stages"]


def test_neuroflow_profiles_cover_every_preset_stage() -> None:
    root = _neuroflow_config_root()
    for preset_path in sorted((root / "presets").glob("*.yaml")):
        preset = yaml.safe_load(preset_path.read_text())
        profile_set = str(preset["metadata"]["default_profile_set"])
        profile_path = root / "profiles" / f"{profile_set}.yaml"
        assert profile_path.is_file(), f"{preset_path.name}: missing profile set {profile_set}"
        profiles = yaml.safe_load(profile_path.read_text())

        covered = {str(profile["stage"]) for profile in profiles["profiles"]}
        expected = {str(stage["id"]) for stage in preset["stages"]}
        assert expected - covered == set(), f"{preset_path.name}: stages without profile coverage: {expected - covered}"


class _Record:
    def __init__(self, *args: object, **kwargs: object) -> None:
        if args:
            self._args = args
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


def test_neuroflow_continuous_replenishment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeAdaptiveScheduler.instances = []
    _install_fake_neuroflow(monkeypatch)

    class DynamicScheduler(_FakeAdaptiveScheduler):
        def __init__(self) -> None:
            super().__init__()
            self.step = 0

        def request_launches(self, *, request: object) -> SimpleNamespace:
            self.launch_requests.append(request)
            self.step += 1
            if self.step == 1:
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
                return SimpleNamespace(terminal=False, launches=launches, reason="initial_ready")
            elif self.step == 2:
                assert getattr(request, "maximum_number", 0) == 1
                launches = (
                    _Record(
                        image_id="subject-c",
                        stage_id="reorient_resize",
                        attempt_id="attempt-c",
                        reservation_id="reservation-c",
                        task_id="task-c",
                        execution_mode=SimpleNamespace(value="cpu"),
                        cpu_threads=1,
                        gpu_id=None,
                        configuration_id="config-c",
                    ),
                )
                return SimpleNamespace(terminal=False, launches=launches, reason="replenish_ready")
            else:
                return SimpleNamespace(terminal=True, launches=(), reason="all_done")

    fake_neuroflow = sys.modules["neuroflow"]
    fake_neuroflow.AdaptiveScheduler = DynamicScheduler

    b_can_finish = threading.Event()
    c_started = threading.Event()

    def fake_run_pipeline_stage(config: object, _stage: str, **_kwargs: object) -> tuple[_FakeStep, str]:
        if config.subject_id == "subject-a":
            return _FakeStep(), str(tmp_path / config.subject_id / "out.mgz")
        elif config.subject_id == "subject-b":
            c_started.wait(timeout=2.0)
            b_can_finish.wait(timeout=2.0)
            return _FakeStep(), str(tmp_path / config.subject_id / "out.mgz")
        elif config.subject_id == "subject-c":
            c_started.set()
            b_can_finish.set()
            return _FakeStep(), str(tmp_path / config.subject_id / "out.mgz")
        return _FakeStep(), str(tmp_path / config.subject_id / "out.mgz")

    class FakeStatsGenerator:
        def __init__(self, _config: object) -> None:
            pass

        def generate(self, _subject_dir: object, _subject_id: object) -> SimpleNamespace:
            return SimpleNamespace(files=[], warnings=[])

    monkeypatch.setattr(neuroflow_adapter, "run_pipeline_stage", fake_run_pipeline_stage)
    monkeypatch.setattr(neuroflow_adapter, "StatsGenerator", FakeStatsGenerator)
    monkeypatch.setattr(neuroflow_adapter, "write_batch_reports", lambda _ctx: None)

    results = run_neuroflow_batch(
        job_dir=tmp_path / "job",
        req={
            "pipeline_mode": "FreeSurfer 8 + Volume",
            "effective_output_dir": str(tmp_path / "out"),
            "selected_tools": {"reorientation": "fake_tool"},
            "threads": 2,
            "neuroflow_max_concurrent_tasks": 2,
        },
        input_files=[str(tmp_path / "a.nii.gz"), str(tmp_path / "b.nii.gz"), str(tmp_path / "c.nii.gz")],
        subject_id_map={
            str(tmp_path / "a.nii.gz"): "subject-a",
            str(tmp_path / "b.nii.gz"): "subject-b",
            str(tmp_path / "c.nii.gz"): "subject-c",
        },
    )

    scheduler = DynamicScheduler.instances[0]
    assert len(scheduler.results) == 3
    assert len(results) == 3
    assert all(r.success for r in results)


def test_neuroflow_handles_empty_polls_while_tasks_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeAdaptiveScheduler.instances = []
    _install_fake_neuroflow(monkeypatch)

    class WaitingScheduler(_FakeAdaptiveScheduler):
        def __init__(self) -> None:
            super().__init__()
            self.step = 0

        def request_launches(self, *, request: object) -> SimpleNamespace:
            self.launch_requests.append(request)
            self.step += 1
            if self.step == 1:
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
                )
                return SimpleNamespace(terminal=False, launches=launches, reason="ready")
            elif self.step in (2, 3, 4):
                return SimpleNamespace(terminal=False, launches=(), reason="dependencies_pending")
            else:
                return SimpleNamespace(terminal=True, launches=(), reason="all_done")

    fake_neuroflow = sys.modules["neuroflow"]
    fake_neuroflow.AdaptiveScheduler = WaitingScheduler

    def fake_run_pipeline_stage(config: object, _stage: str, **_kwargs: object) -> tuple[_FakeStep, str]:
        time.sleep(0.15)
        return _FakeStep(), str(tmp_path / config.subject_id / "out.mgz")

    class FakeStatsGenerator:
        def __init__(self, _config: object) -> None:
            pass

        def generate(self, _subject_dir: object, _subject_id: object) -> SimpleNamespace:
            return SimpleNamespace(files=[], warnings=[])

    monkeypatch.setattr(neuroflow_adapter, "run_pipeline_stage", fake_run_pipeline_stage)
    monkeypatch.setattr(neuroflow_adapter, "StatsGenerator", FakeStatsGenerator)
    monkeypatch.setattr(neuroflow_adapter, "write_batch_reports", lambda _ctx: None)

    results = run_neuroflow_batch(
        job_dir=tmp_path / "job",
        req={
            "pipeline_mode": "FreeSurfer 8 + Volume",
            "effective_output_dir": str(tmp_path / "out"),
            "selected_tools": {"reorientation": "fake_tool"},
            "threads": 2,
            "neuroflow_max_concurrent_tasks": 2,
        },
        input_files=[str(tmp_path / "a.nii.gz")],
        subject_id_map={str(tmp_path / "a.nii.gz"): "subject-a"},
    )

    scheduler = WaitingScheduler.instances[0]
    assert len(scheduler.results) == 1
    assert len(results) == 1
    assert results[0].success is True


def test_neuroflow_survives_long_empty_poll_spell_before_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeAdaptiveScheduler.instances = []
    _install_fake_neuroflow(monkeypatch)
    monkeypatch.setattr(neuroflow_adapter.time, "sleep", lambda _seconds: None)

    class SlowReadyScheduler(_FakeAdaptiveScheduler):
        def __init__(self) -> None:
            super().__init__()
            self.step = 0

        def request_launches(self, *, request: object) -> SimpleNamespace:
            self.launch_requests.append(request)
            self.step += 1
            if self.step <= 65:
                return SimpleNamespace(terminal=False, launches=(), reason="dependencies_pending")
            if self.step == 66:
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
                )
                return SimpleNamespace(terminal=False, launches=launches, reason="ready")
            return SimpleNamespace(terminal=True, launches=(), reason="all_done")

    fake_neuroflow = sys.modules["neuroflow"]
    fake_neuroflow.AdaptiveScheduler = SlowReadyScheduler

    def fake_run_pipeline_stage(config: object, _stage: str, **_kwargs: object) -> tuple[_FakeStep, str]:
        return _FakeStep(), str(tmp_path / config.subject_id / "out.mgz")

    class FakeStatsGenerator:
        def __init__(self, _config: object) -> None:
            pass

        def generate(self, _subject_dir: object, _subject_id: object) -> SimpleNamespace:
            return SimpleNamespace(files=[], warnings=[])

    monkeypatch.setattr(neuroflow_adapter, "run_pipeline_stage", fake_run_pipeline_stage)
    monkeypatch.setattr(neuroflow_adapter, "StatsGenerator", FakeStatsGenerator)
    monkeypatch.setattr(neuroflow_adapter, "write_batch_reports", lambda _ctx: None)

    results = run_neuroflow_batch(
        job_dir=tmp_path / "job",
        req={
            "pipeline_mode": "FreeSurfer 8 + Volume",
            "effective_output_dir": str(tmp_path / "out"),
            "selected_tools": {"reorientation": "fake_tool"},
            "threads": 2,
            "neuroflow_max_concurrent_tasks": 2,
        },
        input_files=[str(tmp_path / "a.nii.gz")],
        subject_id_map={str(tmp_path / "a.nii.gz"): "subject-a"},
    )

    scheduler = SlowReadyScheduler.instances[0]
    assert len(scheduler.launch_requests) == 67
    assert len(scheduler.results) == 1
    assert results[0].success is True


def test_neuroflow_stage_config_container_name_suffix_is_attempt_unique(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeAdaptiveScheduler.instances = []
    _install_fake_neuroflow(monkeypatch)
    stage_suffixes: list[str] = []

    def fake_run_pipeline_stage(config: object, _stage: str, **_kwargs: object) -> tuple[_FakeStep, str]:
        stage_suffixes.append(config.container_name_suffix)
        return _FakeStep(), str(tmp_path / config.subject_id / "out.mgz")

    class FakeStatsGenerator:
        def __init__(self, _config: object) -> None:
            pass

        def generate(self, _subject_dir: object, _subject_id: object) -> SimpleNamespace:
            return SimpleNamespace(files=[], warnings=[])

    monkeypatch.setattr(neuroflow_adapter, "run_pipeline_stage", fake_run_pipeline_stage)
    monkeypatch.setattr(neuroflow_adapter, "StatsGenerator", FakeStatsGenerator)
    monkeypatch.setattr(neuroflow_adapter, "write_batch_reports", lambda _ctx: None)

    run_neuroflow_batch(
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

    assert sorted(stage_suffixes) == ["reorientation_attempt-a", "reorientation_attempt-b"]


def test_neuroflow_batch_with_concurrency_4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeAdaptiveScheduler.instances = []
    _install_fake_neuroflow(monkeypatch)

    class Concurrency4Scheduler(_FakeAdaptiveScheduler):
        def request_launches(self, *, request: object) -> SimpleNamespace:
            self.launch_requests.append(request)
            if self._requested:
                return SimpleNamespace(terminal=True, launches=(), reason="done")
            self._requested = True
            launches = tuple(
                _Record(
                    image_id=f"subject-{i}",
                    stage_id="reorient_resize",
                    attempt_id=f"attempt-{i}",
                    reservation_id=f"reservation-{i}",
                    task_id=f"task-{i}",
                    execution_mode=SimpleNamespace(value="cpu"),
                    cpu_threads=1,
                    gpu_id=None,
                    configuration_id=f"config-{i}",
                )
                for i in range(4)
            )
            return SimpleNamespace(terminal=False, launches=launches, reason="ready")

    fake_neuroflow = sys.modules["neuroflow"]
    fake_neuroflow.AdaptiveScheduler = Concurrency4Scheduler

    barrier = threading.Barrier(4, timeout=1.0)
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
    monkeypatch.setattr(neuroflow_adapter, "write_batch_reports", lambda _ctx: None)

    input_files = [str(tmp_path / f"{i}.nii.gz") for i in range(4)]
    subject_id_map = {f: f"subject-{i}" for i, f in enumerate(input_files)}

    results = run_neuroflow_batch(
        job_dir=tmp_path / "job",
        req={
            "pipeline_mode": "FreeSurfer 8 + Volume",
            "effective_output_dir": str(tmp_path / "out"),
            "selected_tools": {"reorientation": "fake_tool"},
            "threads": 4,
            "neuroflow_max_concurrent_tasks": 4,
        },
        input_files=input_files,
        subject_id_map=subject_id_map,
    )

    scheduler = Concurrency4Scheduler.instances[0]
    assert sorted(stage_calls) == [f"subject-{i}" for i in range(4)]
    assert scheduler.launch_requests[0].maximum_number == 4
    assert len(scheduler.results) == 4
    assert len(results) == 4


def test_scheduler_config_parses_all_advanced_settings() -> None:
    neuroflow_src = str(Path(__file__).parents[1] / "NeuroFLOW-private" / "src")
    if neuroflow_src not in sys.path:
        sys.path.insert(0, neuroflow_src)

    req = {
        "threads": 5,
        "ram_percent": 80,
        "neuroflow_max_concurrent_tasks": 4,
        "neuroflow_max_retries": 2,
        "neuroflow_warmup_enabled": True,
        "neuroflow_warmup_initial_concurrency": 2,
        "neuroflow_warmup_safe_successes": 5,
        "neuroflow_preserve_oom_bounds": False,
        "neuroflow_estimation_mode": "conservative",
        "neuroflow_max_io_heavy_tasks": 3,
    }
    cfg = _scheduler_config(req)
    assert cfg.limits.max_concurrent_tasks == 4
    assert cfg.limits.max_total_cpu_threads == 5
    assert cfg.limits.max_threads_per_task == 5
    assert cfg.retry.max_retries == 2
    assert cfg.retry.preserve_oom_bounds_on_manual_retry is False
    assert cfg.warmup.enabled is True
    assert cfg.warmup.initial_concurrency == 2
    assert cfg.warmup.safe_successes_before_increase == 5
    assert cfg.disk.max_io_heavy_tasks == 3
    assert cfg.estimation.runtime.local_quantile == 0.95


def test_neuroflow_batch_normalizes_raw_stats_vector_config_for_preset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeAdaptiveScheduler.instances = []
    _install_fake_neuroflow(monkeypatch)
    captured_configs: list[object] = []

    def fake_run_pipeline_stage(config: object, _stage: str, **_kwargs: object) -> tuple[_FakeStep, str]:
        return _FakeStep(), str(tmp_path / config.subject_id / "out.mgz")

    class FakeStatsGenerator:
        def __init__(self, config: object) -> None:
            captured_configs.append(config)

        def generate(self, _subject_dir: object, _subject_id: object) -> SimpleNamespace:
            return SimpleNamespace(files=[], warnings=[])

    monkeypatch.setattr(neuroflow_adapter, "run_pipeline_stage", fake_run_pipeline_stage)
    monkeypatch.setattr(neuroflow_adapter, "StatsGenerator", FakeStatsGenerator)
    monkeypatch.setattr(neuroflow_adapter, "write_batch_reports", lambda _ctx: None)

    run_neuroflow_batch(
        job_dir=tmp_path / "job",
        req={
            "pipeline_mode": "FreeSurfer 7 + Volume",
            "effective_output_dir": str(tmp_path / "out"),
            "selected_tools": {"reorientation": "fake_tool"},
            "threads": 2,
            "neuroflow_max_concurrent_tasks": 2,
            "stats_vector_config": {
                "atlases": {"subcortical_volume": ["freesurfer_aseg"]},
            },
        },
        input_files=[str(tmp_path / "a.nii.gz")],
        subject_id_map={str(tmp_path / "a.nii.gz"): "subject-a"},
    )

    assert len(captured_configs) == 1
    stats_cfg = captured_configs[0]
    assert stats_cfg.enabled_stats["subcortical_volume"] is True
    assert stats_cfg.enabled_stats["cortical_volume"] is False
    assert stats_cfg.enabled_stats["cortical_thickness"] is False
    assert stats_cfg.atlases["subcortical_volume"] == ["freesurfer_aseg"]
