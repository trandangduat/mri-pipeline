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
