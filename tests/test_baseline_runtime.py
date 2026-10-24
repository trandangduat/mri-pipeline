"""Small behavioral cases using real library objects and local SQLite only."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "NeuroFLOW-private/src"))

from neuroflow import api
from neuroflow.clock import ManualClock
from neuroflow.configuration import (
    load_pipeline_dict,
    load_profile_set_dict,
    load_scheduler_dict,
)
from neuroflow.models import (
    ErrorCategory,
    ResourceSnapshot,
    ResultStatus,
    TaskError,
    TaskMetrics,
    TaskResult,
    TaskState,
)
from neuroflow.policy import ActiveAllocation, SchedulingContext

from pipeline.baseline_policies import schedule_baseline
from pipeline.policy_contract import (
    classify_failure,
    normalize_policy,
    resolve_defaults,
)
from pipeline.policy_runtime import (
    BaselineCoordinator,
    check_resume,
    make_contract,
    preflight_baseline,
    verify_library,
    write_contract,
)

NOW = datetime(2026, 10, 24, tzinfo=UTC)


def documents(specs, policy_id="B1", *, slots=4, cpu=4, warmup=False):
    """specs: stage ID, predecessors, [(threads, runtime, RAM)]."""
    stages, profiles = [], []
    for stage_id, parents, configurations in specs:
        configs = []
        for threads, duration, ram in configurations:
            ref = f"{stage_id}_cpu_{threads}"
            configs.append(
                {
                    "id": f"cpu_{threads}",
                    "mode": "cpu",
                    "cpu_threads": threads,
                    "profile_ref": ref,
                }
            )
            profiles.append(
                {
                    "profile_id": ref,
                    "implementation": f"impl_{stage_id}",
                    "implementation_version": "1",
                    "stage": stage_id,
                    "mode": "cpu",
                    "cpu_threads": threads,
                    "runtime": {"point_ms": duration, "upper_ms": duration},
                    "memory": {"peak_mib": ram, "reservation_mib": ram},
                    "sample_count": 1,
                    "source": "development_example",
                    "status": "example",
                }
            )
        stages.append(
            {
                "id": stage_id,
                "operation": stage_id,
                "implementation": f"impl_{stage_id}",
                "implementation_version": "1",
                "depends_on": parents,
                "execution_configurations": configs,
            }
        )
    pipeline = load_pipeline_dict(
        {
            "schema_version": 1,
            "pipeline_id": "tiny",
            "pipeline_version": "1",
            "display_name": "Tiny",
            "status": "example",
            "stages": stages,
        }
    )
    profile_set = load_profile_set_dict(
        {
            "schema_version": 1,
            "profile_set_id": "tiny_profiles",
            "profile_set_version": "1",
            "status": "example",
            "profiles": profiles,
        }
    )
    config = load_scheduler_dict(
        {
            "schema_version": 1,
            "scheduler_id": "tiny",
            "policy": {"name": "neuroflow", "algorithm_version": "1"},
            "metadata": {"policy_choice": policy_id, "policy_variant": policy_id},
            "limits": {
                "max_concurrent_tasks": 1 if policy_id == "B0" else slots,
                "max_total_cpu_threads": cpu,
                "max_threads_per_task": cpu,
                "max_ram_mib": 10000,
            },
            "warmup": {
                "enabled": warmup,
                "initial_concurrency": 1,
                "safe_successes_before_increase": 1,
            },
            "estimation": {"runtime": {"prior_guard": 1}, "ram": {"prior_guard": 1}},
            "retry": {"max_retries": 1, "transient_delays_ms": [1]},
        }
    )
    return pipeline, profile_set, config


def coordinator(tmp_path, policy_id, specs=None, **kwargs):
    docs = documents(
        specs or [("root", [], [(1, 100, 100)]), ("leaf", ["root"], [(1, 200, 100)])],
        policy_id,
        **kwargs,
    )
    clock = ManualClock(NOW)
    engine = BaselineCoordinator.create(
        database_path=tmp_path / "workspace.sqlite",
        workspace_id="test",
        pipeline_configs=(docs[0],),
        default_profiles=docs[1],
        scheduler_config=docs[2],
        machine_profile_id="machine",
        clock=clock,
    )
    engine.add_images(
        api.AddImagesRequest("add", (api.ImageSpec("image", "tiny", "1"),))
    )
    return engine, clock, docs


def snapshot(clock, *, cpu=4, slots=4, ram=10000):
    return ResourceSnapshot(
        f"snapshot-{clock.now().isoformat()}-{cpu}-{ram}-{slots}",
        clock.now(),
        cpu,
        ram,
        slots,
    )


def launch(engine, clock, **kwargs):
    return engine.request_launches(api.LaunchRequest(snapshot(clock, **kwargs), 4))


def finish(engine, clock, item, category=None):
    engine.confirm_started(
        api.ConfirmStart(
            f"confirm-{item.attempt_id}",
            item.reservation_id,
            item.attempt_id,
            item.task_id,
            item.attempt_id,
            clock.now(),
        )
    )
    clock.set(clock.now() + timedelta(milliseconds=100))
    result = TaskResult(
        f"result-{item.attempt_id}",
        item.task_id,
        item.attempt_id,
        item.attempt_id,
        ResultStatus.FAILED if category else ResultStatus.SUCCEEDED,
        1 if category else 0,
        not bool(category),
        TaskError(category, "test") if category else None,
        TaskMetrics(
            runtime_ms=100,
            peak_ram_mib=100,
            allocated_cpu_threads=item.cpu_threads,
            execution_mode=item.execution_mode,
        ),
        clock.now(),
    )
    return result, engine.report_result(result)


def context(engine, clock, *, allocations=(), cpu=4, slots=4):
    stored = engine.store.load_workspace()
    return SchedulingContext(
        stored.tasks,
        stored.images,
        engine._configuration_estimates(stored),
        snapshot(clock, cpu=cpu, slots=slots),
        stored.workspace.scheduler_limits,
        4,
        4,
        clock.now(),
        allocations,
    )


def test_policy_names_are_validated():
    assert normalize_policy("Sequential FIFO") == "B0"
    assert normalize_policy(" ") == "B6"
    with pytest.raises(ValueError, match="Unknown"):
        normalize_policy("typo")
    verify_library()


def test_defaults_are_explicit_and_not_changed_by_budget():
    pipeline, _, config = documents([("root", [], [(1, 100, 100), (4, 40, 100)])])
    with pytest.raises(ValueError, match="explicit"):
        resolve_defaults(pipeline, {}, config.limits)
    assert resolve_defaults(pipeline, {"root": "cpu_4"}, config.limits) == {
        "root": "cpu_4"
    }
    with pytest.raises(ValueError, match="CPU limit"):
        resolve_defaults(
            pipeline,
            {"root": "cpu_4"},
            replace(config.limits, max_total_cpu_threads=2, max_threads_per_task=2),
        )


def test_b0_reservation_blocks_second_launch_and_keeps_profiles_static(tmp_path):
    engine, clock, _ = coordinator(
        tmp_path, "B0", [("a", [], [(1, 100, 100)]), ("b", [], [(1, 200, 100)])]
    )
    before = engine.store.profile_states()
    first = launch(engine, clock).launches
    assert len(first) == 1 and first[0].stage_id == "a"
    assert not launch(engine, clock).launches
    result, _ = finish(engine, clock, first[0])
    assert engine.report_result(result).duplicate
    assert engine.store.profile_states() == before
    assert launch(engine, clock).launches[0].stage_id == "b"
    engine.store.close_connection()


def test_b0_waits_for_head_while_b1_first_fit_can_pass(tmp_path):
    engine, clock, _ = coordinator(
        tmp_path, "B0", [("a", [], [(4, 100, 100)]), ("b", [], [(1, 100, 100)])]
    )
    ctx = context(engine, clock, cpu=1)
    assert not schedule_baseline(ctx, "B0").launches
    assert [x.stage_id for x in schedule_baseline(ctx, "B1").launches] == ["b"]
    engine.store.close_connection()


@pytest.mark.parametrize("policy_id,expected", [("B1", ["a", "b"]), ("B2", ["b", "a"])])
def test_fifo_and_spt_have_different_order(tmp_path, policy_id, expected):
    engine, clock, _ = coordinator(
        tmp_path, policy_id, [("a", [], [(1, 500, 100)]), ("b", [], [(1, 100, 100)])]
    )
    assert [x.stage_id for x in launch(engine, clock).launches] == expected
    engine.store.close_connection()


def test_fifo_uses_ready_time_before_image_insertion_order(tmp_path):
    engine, clock, _ = coordinator(tmp_path, "B1")
    root = launch(engine, clock).launches[0]
    engine.add_images(
        api.AddImagesRequest("add-2", (api.ImageSpec("second", "tiny", "1"),))
    )
    finish(engine, clock, root)
    assert [l.task_id for l in launch(engine, clock).launches] == [
        "second:root",
        "image:leaf",
    ]
    engine.store.close_connection()


def test_critical_path_includes_descendant_cost(tmp_path):
    engine, clock, _ = coordinator(
        tmp_path,
        "B3",
        [
            ("a", [], [(1, 500, 100)]),
            ("b", [], [(1, 100, 100)]),
            ("c", ["b"], [(1, 1000, 100)]),
        ],
    )
    plan = schedule_baseline(context(engine, clock), "B3")
    assert [l.stage_id for l in plan.launches] == ["b", "a"]
    assert plan.priorities[0].upward_rank_ms == 1100
    engine.store.close_connection()


@pytest.mark.parametrize("duration,admitted", [(20, True), (200, False)])
def test_b4_backfill_preserves_protected_start(tmp_path, duration, admitted):
    engine, clock, _ = coordinator(
        tmp_path, "B4", [("a", [], [(4, 500, 100)]), ("b", [], [(1, duration, 100)])]
    )
    allocation = ActiveAllocation(
        "other", "other", NOW + timedelta(milliseconds=100), 3, 100
    )
    plan = schedule_baseline(
        context(engine, clock, allocations=(allocation,), cpu=1, slots=3), "B4"
    )
    assert plan.protected_task.task_id == "image:a"
    assert bool(plan.launches) == admitted
    if admitted:
        assert plan.launches[0].stage_id == "b"
    engine.store.close_connection()


def test_b5_learns_and_has_no_protected_backfill(tmp_path):
    engine, clock, _ = coordinator(tmp_path, "B5", warmup=True)
    before = engine.store.profile_states()
    item = launch(engine, clock).launches[0]
    finish(engine, clock, item)
    assert engine.store.profile_states() != before
    assert engine.get_status().adaptive_concurrency == 2
    assert schedule_baseline(context(engine, clock), "B5").protected_task is None
    engine.store.close_connection()


def test_heft_selects_earlier_finish_instead_of_fastest_runtime(tmp_path):
    engine, clock, _ = coordinator(
        tmp_path, "B7", [("a", [], [(4, 40, 100), (1, 60, 100)])]
    )
    allocation = ActiveAllocation(
        "other", "other", NOW + timedelta(milliseconds=100), 3, 100
    )
    plan = schedule_baseline(
        context(engine, clock, allocations=(allocation,), cpu=1, slots=3), "B7"
    )
    assert plan.launches[0].configuration_id == "cpu_1"
    engine.store.close_connection()


def test_heft_waits_for_unknown_external_resource_release(tmp_path):
    engine, clock, _ = coordinator(tmp_path, "B7")
    assert not schedule_baseline(context(engine, clock, cpu=0), "B7").launches
    engine.store.close_connection()


@pytest.mark.parametrize("policy_id", ["B4", "B5", "B7"])
def test_gpu_assignment_checks_class_memory_and_exclusivity(tmp_path, policy_id):
    from neuroflow.models import (
        ExecutionMode,
        GPUDefinition,
        GPURequirement,
        GPUResource,
    )

    engine, clock, _ = coordinator(
        tmp_path, policy_id, [("a", [], [(1, 100, 100)]), ("b", [], [(1, 100, 100)])]
    )
    ctx = context(engine, clock)
    tasks = tuple(
        replace(
            t,
            execution_configurations=tuple(
                replace(
                    c,
                    execution_mode=ExecutionMode.GPU,
                    gpu=GPURequirement(
                        minimum_memory_mib=512, device_classes=("cuda",)
                    ),
                )
                for c in t.execution_configurations
            ),
        )
        for t in ctx.tasks
    )
    task_map = {t.task_id: t for t in tasks}
    candidates = tuple(
        replace(
            c,
            configuration=task_map[c.task_id].execution_configurations[0],
            estimate=replace(
                c.estimate,
                gpu_memory_reservation_mib=1024,
                resolved_profile_key=replace(
                    c.estimate.resolved_profile_key, execution_mode=ExecutionMode.GPU
                ),
            ),
        )
        for c in ctx.configuration_estimates
    )
    definitions = (
        GPUDefinition("gpu_0", 2048, "other"),
        GPUDefinition("gpu_1", 2048, "cuda"),
    )
    gpus = (
        GPUResource("gpu_0", True, 2048, 2048, "other"),
        GPUResource("gpu_1", True, 2048, 2048, "cuda"),
    )
    ctx = replace(
        ctx,
        tasks=tasks,
        configuration_estimates=candidates,
        limits=replace(ctx.limits, gpus=definitions),
        resources=replace(ctx.resources, gpus=gpus),
    )
    plan = schedule_baseline(ctx, policy_id)
    assert len(plan.launches) == 1
    assert plan.launches[0].gpu_id == "gpu_1"
    assert plan.launches[0].gpu_memory_mib == 1024
    engine.store.close_connection()


@pytest.mark.parametrize("policy_id", ["B0", "B1", "B2", "B3", "B4", "B5", "B7"])
def test_baselines_use_common_lifecycle_and_finish_dag(tmp_path, policy_id):
    engine, clock, _ = coordinator(tmp_path, policy_id)
    for expected_stage in ("root", "leaf"):
        items = launch(engine, clock).launches
        assert len(items) == 1 and items[0].stage_id == expected_stage
        finish(engine, clock, items[0])
    assert engine.get_status().terminal
    assert not launch(engine, clock).launches
    engine.close()


def test_retry_and_recovery_use_original_persistence(tmp_path):
    engine, clock, _ = coordinator(tmp_path, "B0")
    item = launch(engine, clock).launches[0]
    _, response = finish(engine, clock, item, ErrorCategory.PROCESS_CRASH)
    assert response.task_state is TaskState.RETRY_WAIT
    clock.set(clock.now() + timedelta(seconds=1))
    retried = launch(engine, clock).launches[0]
    assert retried.attempt_number == 2
    engine.store.close_connection()
    restored, _ = BaselineCoordinator.load(
        database_path=tmp_path / "workspace.sqlite",
        expected_workspace_id="test",
        clock=clock,
    )
    assert restored.policy_id == "B0"
    restored.store.close_connection()


def test_resume_rejects_legacy_and_changed_contract_without_mutation(tmp_path):
    engine, _, docs = coordinator(tmp_path, "B0")
    engine.store.close_connection()
    database = tmp_path / "workspace.sqlite"
    before = database.read_bytes()
    contract = make_contract("B0", *docs, {}, {})
    with pytest.raises(ValueError, match="Legacy"):
        check_resume(database, contract)
    assert before == database.read_bytes()
    write_contract(database, contract)
    check_resume(database, json.loads(json.dumps(contract)))
    with pytest.raises(ValueError, match="differ"):
        check_resume(database, {**contract, "policy_id": "B1"})
    assert before == database.read_bytes()


def test_explicit_oom_evidence_is_required():
    assert (
        classify_failure(SimpleNamespace(error="exit 137", log_text="Killed"))
        == "PROCESS_CRASH"
    )
    assert (
        classify_failure(SimpleNamespace(error="", log_text="CUDA out of memory"))
        == "GPU_OOM"
    )
    assert (
        classify_failure(SimpleNamespace(error="OOMKilled", log_text="")) == "RAM_OOM"
    )


def test_preflight_uses_real_profiles_and_checks_ram():
    pipeline, profiles, config = documents([("root", [], [(1, 100, 20000)])], "B0")
    with pytest.raises(ValueError, match="budget"):
        preflight_baseline(pipeline, profiles, config, {})


def test_transaction_rolls_back_all_reservations_on_failure(tmp_path, monkeypatch):
    engine, clock, _ = coordinator(
        tmp_path, "B1", [("a", [], [(1, 100, 100)]), ("b", [], [(1, 100, 100)])]
    )
    original = engine.store.create_reservation
    count = 0

    def fail_second(**kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("injected storage failure")
        return original(**kwargs)

    monkeypatch.setattr(engine.store, "create_reservation", fail_second)
    with pytest.raises(RuntimeError, match="storage failure"):
        launch(engine, clock)
    stored = engine.store.load_workspace()
    assert not stored.attempts and not stored.reservations
    assert all(task.state is TaskState.READY for task in stored.tasks)
    engine.store.close_connection()


def test_expiry_and_shutdown_release_reservations_and_prevent_dispatch(tmp_path):
    engine, clock, _ = coordinator(tmp_path, "B0")
    first = launch(engine, clock).launches[0]
    clock.set(first.reservation_expires_at + timedelta(milliseconds=1))
    next_item = launch(engine, clock).launches[0]
    assert next_item.attempt_id != first.attempt_id
    engine.begin_shutdown(api.ShutdownRequest("stop", api.ShutdownMode.WAIT))
    assert not launch(engine, clock).launches
    engine.store.close_connection()


def test_b5_oom_updates_bound_and_reduces_concurrency(tmp_path):
    engine, clock, _ = coordinator(tmp_path, "B5", warmup=True)
    item = launch(engine, clock).launches[0]
    finish(engine, clock, item)
    assert engine.get_status().adaptive_concurrency == 2
    item = launch(engine, clock).launches[0]
    finish(engine, clock, item, ErrorCategory.RAM_OOM)
    assert engine.get_status().adaptive_concurrency == 1
    assert any(p.ram_oom_lower_bound_mib > 0 for p in engine.store.profile_states())
    engine.store.close_connection()
