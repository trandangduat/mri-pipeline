"""Check the corrected admission, Stop, and unit paths without MRI tools."""

import csv
from dataclasses import replace
from pathlib import Path
import sqlite3
import sys
import threading
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "NeuroFLOW-private/src"))

from neuroflow import AdaptiveScheduler, AddImagesRequest, ImageSpec, LaunchRequest
from neuroflow.clock import ManualClock
from neuroflow.models import IOClass
from normalize_volumes import _write_cat12_xml
from pipeline import neuroflow_adapter as adapter
from pipeline.config import StepResult
from pipeline.policy_runtime import BaselineCoordinator
from tests.test_baseline_runtime import NOW, documents


@pytest.mark.parametrize("policy", ["B6", "B1"])
def test_io_budget_limits_new_and_active_heavy_tasks(tmp_path, policy):
    pipeline, profiles, config = documents(
        [("root", [], [(1, 10000, 100)])], policy, slots=4, cpu=4,
    )
    pipeline = replace(pipeline, stages=tuple(
        replace(stage, execution_configurations=tuple(
            replace(item, io_class=IOClass.HEAVY) for item in stage.execution_configurations
        )) for stage in pipeline.stages
    ))
    config = replace(config, disk=replace(config.disk, max_io_heavy_tasks=2))
    scheduler_type = AdaptiveScheduler if policy == "B6" else BaselineCoordinator
    scheduler = scheduler_type.create(
        database_path=tmp_path / "workspace.sqlite", workspace_id="test",
        pipeline_configs=(pipeline,), default_profiles=profiles,
        scheduler_config=config, machine_profile_id="machine", clock=ManualClock(NOW),
    )
    store = scheduler._coordinator.store if policy == "B6" else scheduler.store
    try:
        scheduler.add_images(request=AddImagesRequest(
            "add", tuple(ImageSpec(f"image-{i}", "tiny", "1") for i in range(4)),
        ))
        snapshot = replace(adapter._resource_snapshot({
            "threads": 4, "ram_percent": 100, "runtime_ram_bytes": 1024**3,
            "neuroflow_policy": policy, "neuroflow_max_concurrent_tasks": 4,
            "neuroflow_max_io_heavy_tasks": 2, "device": "cpu",
        }), captured_at=NOW)
        assert snapshot.available_io_heavy_slots == 2
        zero_budget = adapter._resource_snapshot({
            "threads": 4, "ram_percent": 100, "runtime_ram_bytes": 1024**3,
            "neuroflow_policy": policy, "neuroflow_max_concurrent_tasks": 4,
            "neuroflow_max_io_heavy_tasks": 0, "device": "cpu",
        })
        assert zero_budget.available_io_heavy_slots == 0
        assert len(scheduler.request_launches(request=LaunchRequest(snapshot, 1)).launches) == 1
        assert len(scheduler.request_launches(request=LaunchRequest(snapshot, 4)).launches) == 1
        assert not scheduler.request_launches(request=LaunchRequest(snapshot, 4)).launches
    finally:
        store.close_connection()


@pytest.mark.parametrize("stage_success", [True, False])
def test_b6_stop_commits_results_and_releases_reservations(tmp_path, monkeypatch, stage_success):
    stopped = threading.Event()
    calls = []
    job_dir = tmp_path / "job"

    def database_counts():
        with sqlite3.connect(job_dir / "neuroflow_workspace.sqlite") as conn:
            count = conn.execute("SELECT count(*) FROM results").fetchone()[0]
            active = conn.execute(
                "SELECT count(*) FROM reservations WHERE state IN ('ACTIVE', 'STARTED')"
            ).fetchone()[0]
            return count, active

    def run_stage(config, stage, **kwargs):
        calls.append(stage)
        stopped.set()
        return StepResult(
            stage=stage, tool="mock", success=stage_success, duration_sec=0.01,
            peak_ram_bytes=1024**2, error="" if stage_success else "Stopped",
        ), None

    def on_image_done(*args):
        assert database_counts() == (1, 0)

    monkeypatch.setattr(adapter, "run_pipeline_stage", run_stage)
    monkeypatch.setattr(adapter, "StatsGenerator", lambda _: SimpleNamespace(
        generate=lambda *args: SimpleNamespace(files=[], warnings=[]),
    ))
    results = adapter.run_neuroflow_batch(
        job_dir=job_dir, req={
            "pipeline_mode": "FreeSurfer 8 + Volume", "neuroflow_policy": "B6",
            "device": "cpu", "effective_output_dir": str(tmp_path / "output"),
            "threads": 4, "runtime_ram_bytes": 512 * 1024**3,
            "neuroflow_max_concurrent_tasks": 1, "neuroflow_warmup_enabled": False,
            "neuroflow_max_retries": 3,
            "selected_tools": {"reorientation": "fs8_reduced54_reorientation"},
        }, input_files=["input.nii.gz"], subject_id_map={"input.nii.gz": "subject"},
        should_stop=stopped.is_set, on_image_done=on_image_done,
    )
    assert calls == ["reorientation"]
    assert not results[0].success
    assert database_counts() == (1, 0)
    with sqlite3.connect(job_dir / "neuroflow_workspace.sqlite") as conn:
        status, error = conn.execute("SELECT status,error_category FROM results").fetchone()
        assert status == ("SUCCEEDED" if stage_success else "INTERRUPTED")
        if not stage_success:
            assert error == "INTERRUPTED"


def test_cat12_fractions_have_their_own_table(tmp_path):
    report = tmp_path / "report.xml"
    report.write_text(
        "<cat><vol_TIV>1500</vol_TIV><vol_abs_CGW>300 600 600</vol_abs_CGW>"
        "<vol_rel_CGW>0.2 0.4 0.4</vol_rel_CGW><vol_rel_WMH>0.01</vol_rel_WMH></cat>",
        encoding="utf-8",
    )
    roi = tmp_path / "roi.xml"
    roi.write_text("<catROI/>", encoding="utf-8")
    volumes = tmp_path / "subcortical_volume.tsv"
    _write_cat12_xml(str(report), str(roi), str(volumes), str(tmp_path / "cortical.tsv"), "subject")
    with volumes.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    assert len(rows) == 4
    assert {row["structure"]: row["volume_mm3"] for row in rows}["gray matter"] == "600000"
    with (tmp_path / "cat12_tissue_fractions.tsv").open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        assert reader.fieldnames == ["subject", "structure", "fraction", "tool"]
        fractions = {row["structure"]: row["fraction"] for row in reader}
    assert fractions == {
        "relative cerebrospinal fluid": "0.2", "relative gray matter": "0.4",
        "relative white matter": "0.4", "rel wmh": "0.01",
    }
