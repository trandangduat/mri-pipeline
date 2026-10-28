"""Exercise real admission and persistence, with the MRI tool call stubbed."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "NeuroFLOW-private/src"))

from pipeline import neuroflow_adapter as adapter
from pipeline.config import StepResult


@pytest.mark.parametrize("policy_id", ["B0", "B1", "B2", "B3", "B4", "B5", "B6", "B7"])
def test_real_adapter_routes_policies_to_the_shared_executor(
    tmp_path, monkeypatch, policy_id
):
    root = adapter._neuroflow_config_root()
    preset = yaml.safe_load((root / "presets/freesurfer8_volumetrics.yaml").read_text())
    defaults = {
        stage["id"]: "cpu_1" for stage in preset["stages"] if stage.get("enabled", True)
    }
    calls = []

    def run_stage(config, stage, **kwargs):
        calls.append(
            (config.subject_id, stage, config.threads, config.cpu_thread_limit)
        )
        return StepResult(
            stage=stage,
            tool="stub",
            success=True,
            duration_sec=0.01,
            peak_ram_bytes=1024 * 1024,
            peak_cpu_pct=20,
        ), None

    monkeypatch.setattr(adapter, "run_pipeline_stage", run_stage)
    monkeypatch.setattr(adapter, "_ram_limit_mib", lambda _: 1_000_000)
    monkeypatch.setattr(adapter, "write_batch_reports", lambda _: None)
    monkeypatch.setattr(
        adapter,
        "StatsGenerator",
        lambda _: SimpleNamespace(
            generate=lambda *args: SimpleNamespace(files=[], warnings=[])
        ),
    )
    req = {
        "pipeline_mode": "FreeSurfer 8 + Volume",
        "effective_output_dir": str(tmp_path / "out"),
        "threads": 4,
        "neuroflow_max_concurrent_tasks": 4,
        "neuroflow_warmup_enabled": False,
        "neuroflow_policy": policy_id,
        "neuroflow_default_configurations": defaults,
    }
    results = adapter.run_neuroflow_batch(
        job_dir=tmp_path / "job",
        req=req,
        input_files=["first.nii.gz", "second.nii.gz"],
        subject_id_map={"first.nii.gz": "first", "second.nii.gz": "second"},
    )
    assert len(calls) == len(defaults) * 2
    assert all(result.success for result in results)
    assert all(
        limit == threads
        for _, _, threads, limit in calls
    )
    if policy_id != "B6":
        contract = json.loads(
            (tmp_path / "job/neuroflow_policy_contract.json").read_text()
        )
        assert contract["policy_id"] == policy_id
        assert contract["engine"] == "external_baseline"
        previous_calls = len(calls)
        resumed = adapter.run_neuroflow_batch(
            job_dir=tmp_path / "job",
            req={**req, "resume": True},
            input_files=["first.nii.gz", "second.nii.gz"],
            subject_id_map={"first.nii.gz": "first", "second.nii.gz": "second"},
        )
        assert all(result.success for result in resumed)
        assert len(calls) == previous_calls


def test_missing_default_fails_before_output_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter, "_ram_limit_mib", lambda _: 1_000_000)
    with pytest.raises(ValueError, match="explicit"):
        adapter.run_neuroflow_batch(
            job_dir=tmp_path / "job",
            req={
                "pipeline_mode": "FreeSurfer 8 + Volume",
                "effective_output_dir": str(tmp_path / "out"),
                "threads": 4,
                "neuroflow_policy": "B0",
            },
            input_files=["first.nii.gz"],
            subject_id_map={},
        )
    assert not (tmp_path / "job").exists()
    assert not (tmp_path / "out").exists()


def test_stop_drains_results_and_missing_ram_is_not_fabricated(tmp_path, monkeypatch):
    from neuroflow.models import ReservationState
    from neuroflow.persistence import PersistenceStore

    stopped = threading.Event()
    defaults = {
        "reorient_resize": "cpu_1",
        "subcortical_segmentation": "cpu_1",
        "statistics_atlas_mapping": "cpu_1",
    }

    def stopped_stage(config, stage, **kwargs):
        stopped.set()
        return StepResult(
            stage=stage, tool="stub", success=False, error="stopped", duration_sec=0.01
        ), None

    monkeypatch.setattr(adapter, "run_pipeline_stage", stopped_stage)
    monkeypatch.setattr(adapter, "_ram_limit_mib", lambda _: 1_000_000)
    monkeypatch.setattr(adapter, "write_batch_reports", lambda _: None)
    monkeypatch.setattr(
        adapter,
        "StatsGenerator",
        lambda _: SimpleNamespace(
            generate=lambda *args: SimpleNamespace(files=[], warnings=[])
        ),
    )
    adapter.run_neuroflow_batch(
        job_dir=tmp_path / "job",
        req={
            "pipeline_mode": "FreeSurfer 8 + Volume",
            "effective_output_dir": str(tmp_path / "out"),
            "threads": 4,
            "neuroflow_policy": "B0",
            "neuroflow_default_configurations": defaults,
        },
        input_files=["first.nii.gz"],
        subject_id_map={"first.nii.gz": "first"},
        should_stop=stopped.is_set,
    )
    store = PersistenceStore.open(
        tmp_path / "job/neuroflow_workspace.sqlite", recover=False
    )
    assert all(
        r.state not in {ReservationState.ACTIVE, ReservationState.STARTED}
        for r in store.load_workspace().reservations
    )
    store.close_connection()
    observations = [
        json.loads(line)
        for line in (tmp_path / "job/neuroflow_observations.jsonl")
        .read_text()
        .splitlines()
    ]
    assert len(observations) == 1 and observations[0]["peak_ram_mib"] is None


@pytest.mark.parametrize("policy_id", ["B0", "B1", "B2", "B3", "B4", "B5", "B6", "B7"])
@pytest.mark.parametrize("missing", [False, True])
def test_scheduled_gpu_placement_and_failure(tmp_path, monkeypatch, policy_id, missing):
    from dataclasses import replace
    from tests.test_baseline_runtime import documents
    from neuroflow.configuration import MemoryProfileConfig
    from neuroflow.models import ExecutionMode, GPURequirement, GPUResource, ReservationState
    from neuroflow.persistence import PersistenceStore
    import neuroflow.configuration as configuration

    pipeline, profiles, _ = documents([("root", [], [(1, 100, 100)])], policy_id)
    stage = pipeline.stages[0]
    gpu_config = replace(stage.execution_configurations[0], execution_mode=ExecutionMode.GPU,
                         gpu=GPURequirement(minimum_memory_mib=128))
    pipeline = replace(pipeline, stages=(replace(stage, execution_configurations=(gpu_config,)),))
    profiles = replace(profiles, profiles=tuple(
        replace(p, mode=ExecutionMode.GPU,
                gpu_memory=MemoryProfileConfig(peak_mib=128, reservation_mib=128))
        for p in profiles.profiles
    ))
    gpu = GPUResource("gpu_1", True, 8192, 16384, "generic_cuda",
                      (("host_index", "1"), ("uuid", "GPU-one")))
    probes = []
    calls = []
    def gpu_resources(device):
        probes.append(device)
        return () if missing and len(probes) >= 3 else (gpu,)
    def run_stage(config, stage, **kwargs):
        calls.append(config)
        # Placement is tested independently of successful GPU telemetry (task 4).
        return StepResult(stage=stage, tool="stub", success=False, duration_sec=0.01,
                          peak_ram_bytes=1024**2, return_code=2, error="stub tool failed"), None

    monkeypatch.setattr(configuration, "load_pipeline_file", lambda path: pipeline)
    monkeypatch.setattr(configuration, "load_profile_set_file", lambda path: profiles)
    monkeypatch.setattr(adapter, "_gpu_resources", gpu_resources)
    monkeypatch.setattr(adapter.subprocess, "run",
                        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="unix:///var/run/docker.sock"))
    monkeypatch.setattr(adapter, "run_pipeline_stage", run_stage)
    monkeypatch.setattr(adapter, "write_batch_reports", lambda ctx: None)
    monkeypatch.setattr(adapter, "StatsGenerator",
                        lambda cfg: SimpleNamespace(generate=lambda *args: SimpleNamespace(files=[], warnings=[])))

    job = tmp_path / "job"
    results = adapter.run_neuroflow_batch(
        job_dir=job,
        req={"pipeline_mode": "FreeSurfer 8 + Volume",
             "effective_output_dir": str(tmp_path / "out"), "threads": 4,
             "runtime_ram_bytes": 16*1024**3, "device": "gpu",
             "neuroflow_policy": policy_id, "neuroflow_max_retries": 0,
             "neuroflow_max_concurrent_tasks": 1, "neuroflow_warmup_enabled": False,
             "selected_tools": {"root": "stub"}},
        input_files=["first.nii.gz"], subject_id_map={"first.nii.gz": "first"},
    )
    assert not results[0].success
    observation = json.loads((job / "neuroflow_observations.jsonl").read_text())
    if missing:
        assert calls == []
        assert "GPU" in observation["error"]
        assert observation["runtime_ms"] is None
        assert observation["peak_ram_mib"] is None
        store = PersistenceStore(job / "neuroflow_workspace.sqlite")
        try:
            stored = store.load_workspace()
            assert all(r.state not in {ReservationState.ACTIVE, ReservationState.STARTED}
                       for r in stored.reservations)
            assert stored.tasks[0].retry.last_failure_category.value == "CONTAINER_START_FAILURE"
        finally:
            store.close_connection()
    else:
        assert len(calls) == 1
        assert calls[0].gpu_device_id == "1"
        assert calls[0].cpu_thread_limit == calls[0].threads == 1


def _gpu_telemetry_case(tmp_path, monkeypatch, policy_id, peaks, *, ram=1024**2,
                        retries=0, failure="", receipt_failure=False):
    from dataclasses import replace
    from tests.test_baseline_runtime import documents
    from neuroflow.configuration import MemoryProfileConfig
    from neuroflow.models import ExecutionMode, GPURequirement, GPUResource
    import neuroflow.configuration as configuration

    pipeline, profiles, _ = documents([("root", [], [(1, 100, 100)])], policy_id)
    stage = pipeline.stages[0]
    gpu_config = replace(stage.execution_configurations[0], execution_mode=ExecutionMode.GPU,
                         gpu=GPURequirement(minimum_memory_mib=128))
    pipeline = replace(pipeline, stages=(replace(stage, execution_configurations=(gpu_config,)),))
    profiles = replace(profiles, profiles=tuple(
        replace(p, mode=ExecutionMode.GPU,
                gpu_memory=MemoryProfileConfig(peak_mib=128, reservation_mib=128))
        for p in profiles.profiles))
    gpu = GPUResource("gpu_1", True, 8192, 16384, "generic_cuda",
                      (("host_index", "1"), ("uuid", "GPU-one")))
    monkeypatch.setattr(configuration, "load_pipeline_file", lambda path: pipeline)
    monkeypatch.setattr(configuration, "load_profile_set_file", lambda path: profiles)
    monkeypatch.setattr(adapter, "_gpu_resources", lambda device: (gpu,))
    monkeypatch.setattr(adapter, "_require_local_gpu_docker_host", lambda: None)
    monkeypatch.setattr(adapter, "write_batch_reports", lambda ctx: None)
    monkeypatch.setattr(adapter, "StatsGenerator",
                        lambda cfg: SimpleNamespace(generate=lambda *args: SimpleNamespace(files=[], warnings=[])))
    original_config = adapter._scheduler_config
    def fast_retry(req):
        config = original_config(req)
        return replace(config, retry=replace(config.retry, transient_delays_ms=(1, 1, 1)))
    monkeypatch.setattr(adapter, "_scheduler_config", fast_retry)
    calls = []
    input_file = tmp_path / "input.nii.gz"
    input_file.write_text("input")
    output = tmp_path / "out/first/result.nii.gz"
    def run_stage(config, stage, **kwargs):
        calls.append(config)
        crashed = bool(failure and len(calls) == 1)
        if not crashed:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("valid MRI output")
        peak = peaks[min(len(calls) - 1, len(peaks) - 1)]
        return StepResult(
            stage=stage, tool="stub", success=not crashed, duration_sec=0.01,
            output_file=str(output) if not crashed else "",
            peak_ram_bytes=ram, peak_gpu_memory_mib=peak,
            gpu_telemetry={"gpu_uuid": "GPU-one", "container_id": "a"*64,
                           "valid_samples": 1 if peak is not None else 0,
                           "reason": "" if peak is not None else "unsupported"},
            return_code=1 if crashed else 0, error=failure if crashed else ""), str(output) if not crashed else None
    monkeypatch.setattr(adapter, "run_pipeline_stage", run_stage)
    if receipt_failure:
        from pipeline import gpu_execution_receipt
        def cannot_save(*args, **kwargs):
            raise OSError("receipt disk unavailable")
        monkeypatch.setattr(gpu_execution_receipt, "save_execution", cannot_save)
    job = tmp_path / "job"
    results = adapter.run_neuroflow_batch(
        job_dir=job,
        req={"pipeline_mode": "FreeSurfer 8 + Volume",
             "effective_output_dir": str(tmp_path / "out"), "threads": 4,
             "runtime_ram_bytes": 16*1024**3, "device": "gpu",
             "neuroflow_policy": policy_id, "neuroflow_max_retries": retries,
             "neuroflow_max_concurrent_tasks": 1, "neuroflow_warmup_enabled": False,
             "selected_tools": {"root": "stub"}},
        input_files=[str(input_file)], subject_id_map={str(input_file): "first"})
    return results, calls, job, output


@pytest.mark.parametrize("policy_id", ["B0", "B1", "B2", "B3", "B4", "B5", "B6", "B7"])
@pytest.mark.parametrize("peak", [0, 321, None])
def test_gpu_metric_reaches_real_scheduler_and_both_exports(tmp_path, monkeypatch, policy_id, peak):
    import csv
    import sqlite3
    results, calls, job, output = _gpu_telemetry_case(tmp_path, monkeypatch, policy_id, [peak])
    assert len(calls) == 1
    assert output.read_text() == "valid MRI output"
    accepted = peak is not None and not (peak == 0 and policy_id in {"B5", "B6"})
    assert results[0].success == accepted
    observation = json.loads((job / "neuroflow_observations.jsonl").read_text())
    assert observation["peak_gpu_memory_mib"] == peak
    assert observation["processing_success"] is True
    assert observation["preserved_output"] == str(output)
    assert observation["exit_code"] == 0
    with (job / "neuroflow_observations.tsv").open() as stream:
        row = next(csv.DictReader(stream, delimiter="\t"))
    assert row["peak_gpu_memory_mib"] == (str(peak) if peak is not None else "")
    copied = json.loads((tmp_path / "out/neuroflow_observations.jsonl").read_text())
    assert copied == observation
    reports = list((job / "gpu_execution_receipts").glob("report-*.json"))
    assert len(reports) == 1
    saved = json.loads(reports[0].read_text())
    assert saved["reporting_state"] == "reported"
    assert saved["result"]["metrics"]["peak_gpu_memory_mib"] == peak
    with sqlite3.connect(job / "neuroflow_workspace.sqlite") as connection:
        status, error = connection.execute("SELECT status,error_category FROM results").fetchone()
    assert status == ("SUCCEEDED" if accepted else "FAILED")
    assert error == (None if accepted else "VALIDATION_FAILURE")


@pytest.mark.parametrize("policy_id", ["B1", "B6"])
@pytest.mark.parametrize("receipt_failure", [False, True])
def test_gpu_telemetry_retry_does_not_rerun_mri(tmp_path, monkeypatch, policy_id, receipt_failure):
    results, calls, job, output = _gpu_telemetry_case(
        tmp_path, monkeypatch, policy_id, [None], retries=2, receipt_failure=receipt_failure)
    assert not results[0].success
    assert len(calls) == 1
    assert output.exists()
    observations = [json.loads(line) for line in (job / "neuroflow_observations.jsonl").read_text().splitlines()]
    assert len(observations) == 3
    assert all(item["processing_success"] and not item["success"] for item in observations)
    assert all(item["peak_gpu_memory_mib"] is None for item in observations)
    assert all(item["runtime_ms"] is None and item["peak_ram_mib"] is None for item in observations[1:])
    assert all("preserved" in item["error"] for item in observations[1:])


@pytest.mark.parametrize("policy_id", ["B1", "B6"])
def test_gpu_success_also_requires_genuine_ram(tmp_path, monkeypatch, policy_id):
    results, calls, job, output = _gpu_telemetry_case(
        tmp_path, monkeypatch, policy_id, [321], ram=None, retries=1)
    assert not results[0].success and len(calls) == 1 and output.exists()
    observations = [json.loads(line) for line in (job / "neuroflow_observations.jsonl").read_text().splitlines()]
    assert observations[0]["peak_ram_mib"] is None
    assert observations[0]["peak_gpu_memory_mib"] == 321
    assert "RAM" in observations[0]["error"]
    assert observations[1]["peak_gpu_memory_mib"] is None


@pytest.mark.parametrize("failure", ["tool crashed", "CUDA out of memory", "out of memory"])
def test_actual_gpu_processing_failures_still_retry(tmp_path, monkeypatch, failure):
    results, calls, job, output = _gpu_telemetry_case(
        tmp_path, monkeypatch, "B6", [None, 321], failure=failure, retries=1)
    assert results[0].success and len(calls) == 2
    observations = [json.loads(line) for line in (job / "neuroflow_observations.jsonl").read_text().splitlines()]
    assert not observations[0]["processing_success"]
    assert observations[1]["success"]



def test_gpu_duplicate_result_replays_without_duplicate_learning(tmp_path, monkeypatch):
    import sqlite3
    from neuroflow import AdaptiveScheduler
    original = AdaptiveScheduler.report_result
    replays = []
    def report_twice(self, *, result):
        first = original(self, result=result)
        second = original(self, result=result)
        replays.append(second)
        return first
    monkeypatch.setattr(AdaptiveScheduler, "report_result", report_twice)
    results, calls, job, output = _gpu_telemetry_case(tmp_path, monkeypatch, "B6", [321])
    assert results[0].success and len(calls) == 1
    assert len(replays) == 1 and replays[0].duplicate
    with sqlite3.connect(job / "neuroflow_workspace.sqlite") as connection:
        assert connection.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM profile_observations").fetchone()[0] == 1
    observation = json.loads((job / "neuroflow_observations.jsonl").read_text())
    adapter._write_observation(job, observation)
    assert len((job / "neuroflow_observations.jsonl").read_text().splitlines()) == 1
    assert len((job / "neuroflow_observations.tsv").read_text().splitlines()) == 2



def test_same_execution_recovers_a_metric_dropped_after_receipt_write(tmp_path, monkeypatch):
    from pipeline import gpu_execution_receipt as receipts
    save = receipts.save_execution
    def save_then_drop(path, provenance, launch, execution_id, step, output, outputs=None):
        evidence = save(path, provenance, launch, execution_id, step, output, outputs)
        assert step.peak_gpu_memory_mib == 321
        step.peak_gpu_memory_mib = None
        return evidence
    monkeypatch.setattr(receipts, "save_execution", save_then_drop)
    results, calls, job, output = _gpu_telemetry_case(tmp_path, monkeypatch, "B6", [321])
    assert results[0].success and len(calls) == 1
    observation = json.loads((job / "neuroflow_observations.jsonl").read_text())
    assert observation["peak_gpu_memory_mib"] == 321


def test_gpu_receipt_mismatch_on_retry_never_authorizes_success_or_rerun(tmp_path, monkeypatch):
    from pipeline import gpu_execution_receipt as receipts
    original = receipts.load_execution
    reads = []
    def mismatch_on_retry(path, provenance):
        reads.append(path)
        if len(reads) > 1:
            raise ValueError("GPU receipt provenance does not match this task")
        return original(path, provenance)
    monkeypatch.setattr(receipts, "load_execution", mismatch_on_retry)
    results, calls, job, output = _gpu_telemetry_case(
        tmp_path, monkeypatch, "B6", [None], retries=1)
    assert not results[0].success and len(calls) == 1 and output.exists()
    observations = [json.loads(line) for line in (job / "neuroflow_observations.jsonl").read_text().splitlines()]
    assert len(observations) == 2
    assert "cannot be reconciled" in observations[1]["error"]
    assert observations[1]["peak_gpu_memory_mib"] is None


def test_gpu_pending_report_and_outputs_survive_reporting_failure(tmp_path, monkeypatch):
    from neuroflow import AdaptiveScheduler
    def cannot_report(*args, **kwargs):
        raise RuntimeError("scheduler report interrupted")
    monkeypatch.setattr(AdaptiveScheduler, "report_result", cannot_report)
    with pytest.raises(RuntimeError, match="report interrupted"):
        _gpu_telemetry_case(tmp_path, monkeypatch, "B6", [321])
    reports = list((tmp_path / "job/gpu_execution_receipts").glob("report-*.json"))
    assert len(reports) == 1
    evidence = json.loads(reports[0].read_text())
    assert evidence["reporting_state"] == "pending"
    assert evidence["result"]["metrics"]["peak_gpu_memory_mib"] == 321
    assert evidence["result"]["attempt_id"] == evidence["result"]["execution_id"]
    assert (tmp_path / "out/first/result.nii.gz").exists()



@pytest.mark.parametrize("corruption", ["[]", "invalid json"])
def test_corrupt_gpu_receipt_remains_a_validation_failure(tmp_path, monkeypatch, corruption):
    from neuroflow import AdaptiveScheduler
    original = AdaptiveScheduler.report_result
    reports = []
    def corrupt_after_first_report(self, *, result):
        response = original(self, result=result)
        reports.append(result)
        if len(reports) == 1:
            folder = tmp_path / "job/gpu_execution_receipts"
            evidence = next(path for path in folder.glob("*.json") if not path.name.startswith("report-"))
            evidence.write_text(corruption)
        return response
    monkeypatch.setattr(AdaptiveScheduler, "report_result", corrupt_after_first_report)
    results, calls, job, output = _gpu_telemetry_case(
        tmp_path, monkeypatch, "B6", [None], retries=1)
    assert not results[0].success and len(calls) == 1 and output.exists()
    assert len(reports) == 2
    assert all(result.error.category.value == "VALIDATION_FAILURE" for result in reports)
    assert len((job / "neuroflow_observations.jsonl").read_text().splitlines()) == 2
