"""External baseline coordinator; the professor's source remains unchanged.

The original coordinator has no public policy hook. This subclass replaces only
admission. It inherits graph creation, result handling, retries, shutdown,
recovery, and transactional persistence. Internal helpers are guarded by a source
fingerprint, since they are not a stable public extension API.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from neuroflow import api
from neuroflow.coordinator import SchedulerCoordinator, _effective_snapshot
from neuroflow.exceptions import WorkspaceClosed
from neuroflow.lifecycle import mark_unschedulable, propagate_blocking
from neuroflow.models import AttemptId, ReservationId, SchedulerState, TaskState
from neuroflow.policy import SchedulingContext, schedule_plan_json

from .baseline_policies import schedule_baseline
from .policy_contract import (
    INTEGRATION_VERSION,
    STATIC_POLICIES,
    default_configurations,
)


def verify_library():
    import neuroflow

    expected = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "configs/baselines/neuroflow-source.json"
        ).read_text(encoding="utf-8")
    )
    root = Path(neuroflow.__file__).parent
    for relative, digest in expected.items():
        path = root / relative
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            != digest
        ):
            raise ValueError(
                f"Unsupported NeuroFLOW source version: {relative}. Baseline execution is blocked."
            )


def preflight_baseline(pipeline, profiles, config, req):
    from neuroflow.estimation import estimate_configuration, profile_state_from_config
    from neuroflow.models import ExecutionMode, ProfileKey

    verify_library()
    if (
        dict(config.metadata)["policy_choice"] == "B7"
        and req.get("neuroflow_heft_mode", "online") != "online"
    ):
        raise ValueError(
            "This integration supports online HEFT only. Batch HEFT is not enabled."
        )
    states = tuple(
        profile_state_from_config(p, profile_schema_version=profiles.schema_version)
        for p in profiles.profiles
    )
    for stage in pipeline.stages:
        if not stage.enabled:
            continue
        valid = False
        for c in stage.execution_configurations:
            key = ProfileKey(
                stage.implementation,
                stage.implementation_version,
                stage.stage_id,
                c.execution_mode,
                c.cpu_threads,
                str(req.get("neuroflow_machine_profile_id") or "application_default"),
                None,
                profiles.schema_version,
                pipeline_id=pipeline.pipeline_id,
                profile_id=c.profile_ref,
                configuration_id=c.configuration_id,
            )
            estimate = estimate_configuration(key, states, (), config.estimation)
            fits = (
                c.cpu_threads
                <= min(
                    config.limits.max_total_cpu_threads,
                    config.limits.max_threads_per_task,
                )
                and estimate.ram_reservation_mib <= config.limits.max_ram_mib
            )
            if c.execution_mode is ExecutionMode.GPU:
                classes = set(c.gpu.device_classes if c.gpu else ())
                required = max(
                    estimate.gpu_memory_reservation_mib or 0,
                    c.gpu.minimum_memory_mib or 0 if c.gpu else 0,
                )
                fits = fits and any(
                    g.enabled
                    and g.total_memory_mib >= required
                    and (not classes or g.device_class in classes)
                    for g in config.limits.gpus
                )
            valid = valid or fits
        if not valid:
            raise ValueError(
                f"{stage.stage_id}: no baseline configuration fits the initial CPU/RAM/GPU budget"
            )


def make_contract(policy_id, pipeline, profiles, config, requested_defaults, req):
    from neuroflow.configuration import canonical_json

    def digest(obj):
        return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()

    explicit_defaults = default_configurations(
        req.get("neuroflow_default_configurations")
    )
    preset_defaults = default_configurations(
        dict(pipeline.metadata).get("baseline_default_configurations")
    )
    return {
        "policy_id": policy_id,
        "engine": "AdaptiveScheduler" if policy_id == "B6" else "external_baseline",
        "integration_version": INTEGRATION_VERSION,
        "variant": "online_heft_single_host_zero_communication"
        if policy_id == "B7"
        else policy_id,
        "pipeline_sha256": digest(pipeline),
        "profiles_sha256": digest(profiles),
        "scheduler_sha256": digest(config),
        "default_configurations": requested_defaults,
        "default_configuration_sources": {
            stage_id: "request"
            if stage_id in explicit_defaults
            else (
                "preset_metadata"
                if stage_id in preset_defaults
                else "unique_configuration"
            )
            for stage_id in requested_defaults
        },
        "default_profile_references": {
            str(stage.stage_id): next(
                str(c.profile_ref)
                for c in stage.execution_configurations
                if str(c.configuration_id) == requested_defaults[str(stage.stage_id)]
            )
            for stage in pipeline.stages
            if str(stage.stage_id) in requested_defaults
        },
        "requested_concurrency": max(
            1, int(req.get("neuroflow_max_concurrent_tasks", 2) or 2)
        ),
        "effective_concurrency": config.limits.max_concurrent_tasks,
        "machine_profile_id": str(
            req.get("neuroflow_machine_profile_id") or "application_default"
        ),
        "cpu_budget": config.limits.max_total_cpu_threads,
        "ram_budget_mib": config.limits.max_ram_mib,
        "gpu_budget": json.loads(canonical_json(config.limits.gpus)),
        "io_heavy_budget": config.disk.max_io_heavy_tasks,
        "adaptive_profiles": policy_id in {"B5", "B6"},
        "adaptive_concurrency": policy_id in {"B5", "B6"} and config.warmup.enabled,
        "protected_backfill": policy_id in {"B4", "B6"},
    }


def check_resume(database, contract):
    """Inspect before recovery, output tracking, or workspace writes."""
    sidecar = Path(database).with_name("neuroflow_policy_contract.json")
    if not Path(database).exists():
        return
    if sidecar.exists():
        if json.loads(sidecar.read_text(encoding="utf-8")) != contract:
            raise ValueError(
                "Workspace policy, profiles, defaults, or limits differ. Use a new job directory."
            )
        connection = sqlite3.connect(
            Path(database).resolve().as_uri() + "?mode=ro", uri=True
        )
        try:
            from neuroflow.configuration import canonical_json
            from neuroflow.coordinator import _load_stored_scheduler_config

            stored_config = _load_stored_scheduler_config(
                connection.execute(
                    "SELECT scheduler_config_json FROM workspace"
                ).fetchone()[0]
            )
            actual = hashlib.sha256(
                canonical_json(stored_config).encode("utf-8")
            ).hexdigest()
            if actual != contract["scheduler_sha256"]:
                raise ValueError(
                    "Workspace configuration does not match its policy record. Use a new job directory."
                )
        finally:
            connection.close()
        return
    # Old B6 workspaces can retain their original engine. Old baseline/A4
    # workspaces must never be relabelled or recovered with the corrected engine.
    if contract["policy_id"] != "B6":
        raise ValueError(
            "Legacy baseline workspace: use a new job directory; results cannot be resumed with this engine."
        )
    connection = sqlite3.connect(
        Path(database).resolve().as_uri() + "?mode=ro", uri=True
    )
    try:
        config = json.loads(
            connection.execute(
                "SELECT scheduler_config_json FROM workspace"
            ).fetchone()[0]
        )
        metadata = config.get("metadata", {})
        if metadata.get("policy_choice", "B6") not in {"B6", "Full NeuroFLOW"}:
            raise ValueError(
                "Legacy workspace used a different policy. Use a new job directory."
            )
    finally:
        connection.close()


def write_contract(database, contract):
    path = Path(database).with_name("neuroflow_policy_contract.json")
    if not path.exists():
        path.write_text(
            json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def completed_execution_steps(database):
    """Read committed application results before recovery or output writes.

    Step evidence is stored atomically in TaskResult.metadata by the original
    persistence API. This read-only query fills a gap in its public read API.
    """
    from .config import StepResult

    connection = sqlite3.connect(
        Path(database).resolve().as_uri() + "?mode=ro", uri=True
    )
    try:
        rows = connection.execute(
            "SELECT t.image_id, r.metadata_json FROM tasks t JOIN results r ON t.task_id=r.task_id "
            "WHERE t.state='COMPLETED' AND r.status='SUCCEEDED' ORDER BY t.topological_sequence, t.task_id"
        ).fetchall()
        result = []
        for image_id, raw in rows:
            metadata = json.loads(raw)
            if "application_step" not in metadata:
                raise ValueError(
                    "Completed task has no saved execution evidence. Use a new job directory."
                )
            output = metadata.get("output_for_next")
            if output and not Path(output).is_file():
                raise ValueError(
                    f"Completed task output is missing: {output}. Restore it before resuming this job."
                )
            result.append(
                (image_id, StepResult(**metadata["application_step"]), output)
            )
        return result
    finally:
        connection.close()


class BaselineCoordinator(SchedulerCoordinator):
    """An explicit external engine. No runtime replacement of library methods."""

    @property
    def policy_id(self):
        return dict(self.scheduler_config.metadata)["policy_choice"]

    def _profile_effects(self, stored, task, configuration_id, result):
        if self.policy_id in STATIC_POLICIES:
            return (), (), False
        return super()._profile_effects(stored, task, configuration_id, result)

    def request_launches(self, request):
        stored = self._stored()
        now = self.clock.now()
        if request.maximum_number < 1:
            raise ValueError("maximum_number must be positive")
        age = (now - request.resource_snapshot.captured_at).total_seconds() * 1000
        if age < 0 or age > self.scheduler_config.resource_snapshot.maximum_age_ms:
            return self._empty_launch(
                api.LaunchResponseReason.STALE_RESOURCE_SNAPSHOT, ""
            )
        state = stored.workspace.state
        if state is SchedulerState.CLOSED:
            raise WorkspaceClosed("Workspace is closed")
        if state is SchedulerState.PAUSED:
            return self._empty_launch(api.LaunchResponseReason.SCHEDULER_PAUSED, "")
        if state is not SchedulerState.ACTIVE:
            return self._empty_launch(api.LaunchResponseReason.SHUTTING_DOWN, "")
        with self.store.unit_of_work():
            self.store.expire_stale_reservations()
            self._reconcile_tasks(now)
            stored = self.store.load_workspace()
            candidates = self._configuration_estimates(stored)
            supplied = replace(
                request.resource_snapshot,
                available_io_heavy_slots=min(
                    request.resource_snapshot.available_io_heavy_slots
                    if request.resource_snapshot.available_io_heavy_slots is not None
                    else self.scheduler_config.disk.max_io_heavy_tasks,
                    self.scheduler_config.disk.max_io_heavy_tasks,
                ),
            )
            effective = _effective_snapshot(supplied, stored.reservations)
            allocations = self._active_allocations(stored, candidates, now)
            active_count = len(allocations)
            ceiling = (
                stored.workspace.adaptive_concurrency
                if self.policy_id == "B5"
                else stored.workspace.scheduler_limits.max_concurrent_tasks
            )
            effective = replace(
                effective,
                available_concurrency_slots=min(
                    effective.available_concurrency_slots,
                    max(0, ceiling - active_count),
                ),
            )
            context = SchedulingContext(
                tasks=stored.tasks,
                images=stored.images,
                configuration_estimates=candidates,
                resources=effective,
                limits=stored.workspace.scheduler_limits,
                adaptive_concurrency=max(1, ceiling - active_count),
                maximum_launches=request.maximum_number,
                now=now,
                active_allocations=allocations,
                disk_enabled=self.scheduler_config.disk.enabled,
                disk_strict=self.scheduler_config.disk.strict,
                disk_reserve_mib=self.scheduler_config.disk.reserve_mib,
                policy_variant=self.policy_id,
            )
            # Permanently impossible ready tasks must terminate, not poll forever.
            from neuroflow import policy as core

            options, _ = core._prepared_options(context)
            impossible = {
                t.task_id: mark_unschedulable(t, occurred_at=now)
                for t in stored.tasks
                if t.state is TaskState.READY
                and not any(
                    core._total_feasible(context, o) for o in options[t.task_id]
                )
            }
            if impossible:
                staged = tuple(impossible.get(t.task_id, t) for t in stored.tasks)
                blocked = propagate_blocking(staged, occurred_at=now)
                self.store.update_lifecycle_tasks(
                    tuple(
                        t
                        for t, old in zip(blocked, stored.tasks, strict=True)
                        if t != old
                    ),
                    event_type="TASK_UNSCHEDULABLE",
                    occurred_at=now,
                )
                context = replace(context, tasks=blocked)
                stored = self.store.load_workspace()
            plan = schedule_baseline(context, self.policy_id)
            reason = self._launch_reason(plan, stored.tasks)
            trace = self.store.next_decision_trace_id()
            protection = plan.protected_task
            self.store.store_schedule_decision(
                snapshot=request.resource_snapshot,
                decision_trace_id=trace,
                plan_json=schedule_plan_json(plan),
                ready_task_ids=tuple(p.task_id for p in plan.priorities),
                protected_task_id=protection.task_id if protection else None,
                protected_start_ms=int(
                    (protection.predicted_start - now).total_seconds() * 1000
                )
                if protection
                else None,
                response_reason=reason.value if reason else None,
                created_at=now,
            )
            instructions = []
            for launch in plan.launches:
                number = self.store.next_attempt_number(launch.task_id)
                attempt_id = AttemptId(f"{launch.task_id}:attempt:{number}")
                reservation_id = ReservationId(f"{launch.task_id}:reservation:{number}")
                expires = self.clock.now() + timedelta(
                    milliseconds=max(
                        self.scheduler_config.reservation.timeout_ms, 600_000
                    )
                )
                attempt, _ = self.store.create_reservation(
                    task_id=launch.task_id,
                    attempt_id=attempt_id,
                    reservation_id=reservation_id,
                    configuration_id=launch.configuration_id,
                    execution_mode=launch.execution_mode,
                    cpu_threads=launch.cpu_threads,
                    ram_mib=launch.ram_mib,
                    expires_at=expires,
                    gpu_id=launch.gpu_id,
                    gpu_memory_mib=launch.gpu_memory_mib,
                    disk_mib=launch.disk_mib,
                    io_heavy_slots=launch.io_heavy_slots,
                    retry_ordinal=self.store.task(launch.task_id).retry.retry_count,
                    estimated_runtime_ms=launch.runtime_point_ms,
                )
                instructions.append(
                    api.LaunchInstruction(
                        str(reservation_id),
                        str(attempt_id),
                        str(launch.task_id),
                        launch.image_id,
                        launch.stage_id,
                        str(launch.configuration_id),
                        launch.execution_mode,
                        launch.cpu_threads,
                        str(launch.gpu_id) if launch.gpu_id is not None else None,
                        launch.runtime_point_ms,
                        launch.runtime_upper_ms,
                        launch.ram_mib,
                        launch.gpu_memory_mib,
                        launch.disk_mib,
                        attempt.attempt_number,
                        expires,
                        launch.explanation,
                        launch.execution_metadata,
                    )
                )
        status = self.get_status()
        return api.LaunchResponse(
            tuple(instructions),
            None if instructions else reason,
            status.terminal if not instructions else False,
            status,
            self._failed_tasks(),
            self._blocked_tasks(),
            self._unschedulable_tasks(),
            trace,
        )


def create_baseline_scheduler(**kwargs):
    verify_library()
    return api.AdaptiveScheduler(BaselineCoordinator.create(clock=None, **kwargs))


def load_baseline_scheduler(database_path, workspace_id):
    verify_library()
    coordinator, _ = BaselineCoordinator.load(
        database_path=database_path, expected_workspace_id=workspace_id, clock=None
    )
    return api.AdaptiveScheduler(coordinator)
