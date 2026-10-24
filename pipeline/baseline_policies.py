"""Baseline admission rules over the original graph and resource primitives.

Internal NeuroFLOW primitives are version checked by policy_runtime. This module
does not change library functions, module globals, profiles, or execution metrics.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from neuroflow import policy as core
from neuroflow.models import ExecutionMode, TaskState


def _fifo_key(task, images):
    return (
        task.ready_at or task.created_at,
        images[task.image_id].insertion_sequence,
        task.topological_sequence,
        str(task.task_id),
    )


def _priorities(context, options, policy_id):
    images = {i.image_id: i for i in context.images}
    tasks = [t for t in context.tasks if t.state is TaskState.READY]
    if policy_id in {"B3", "B4"}:
        ranks = core.critical_path_ranks(context.tasks, options)
    elif policy_id == "B7":
        # HEFT uses the mean computation cost, not the fastest configuration.
        ranks = {}
        for task in sorted(
            context.tasks, key=lambda t: t.topological_sequence, reverse=True
        ):
            choices = options.get(task.task_id, ())
            cost = sum(o.estimate.runtime_point_ms for o in choices) / max(
                1, len(choices)
            )
            ranks[task.task_id] = cost + max(
                (ranks.get(s, 0) for s in task.successor_task_ids), default=0
            )
    else:
        ranks = {}

    def key(task):
        tie = _fifo_key(task, images)
        if policy_id == "B2":
            return (
                min(
                    (o.estimate.runtime_point_ms for o in options[task.task_id]),
                    default=float("inf"),
                ),
                *tie,
            )
        if policy_id in {"B3", "B4", "B7"}:
            return (-(ranks.get(task.task_id) or 0), *tie)
        return tie

    tasks.sort(key=key)
    return tuple(
        core.PriorityComponents(
            task.task_id,
            len(tasks) - index,
            int(ranks.get(task.task_id) or 0),
            0,
            0,
            max(
                0,
                int(
                    (context.now - (task.ready_at or task.created_at)).total_seconds()
                    * 1000
                ),
            ),
            images[task.image_id].insertion_sequence,
            task.topological_sequence,
        )
        for index, task in enumerate(tasks)
    )


def _static_choice(context, options, totals):
    choices = [
        core._choice(context, o, totals)
        for o in options
        if not core._resource_rejections(context, o, totals)
    ]
    return min(
        choices,
        key=lambda c: (
            c.option.estimate.runtime_point_ms,
            c.option.estimate.ram_reservation_mib,
            c.option.configuration.cpu_threads,
            str(c.option.configuration.configuration_id),
            str(c.gpu_id or ""),
        ),
        default=None,
    )


def _heft_choices(context, options):
    """Online HEFT with insertion into a cumulative CPU/RAM/GPU calendar.

    Only known tasks are used. Communication cost is zero on this single host.
    Observed results do not update static estimates. Replanning uses current
    reservations and unfinished tasks, so an overrun cannot release real capacity.
    """
    from neuroflow.models import GPUResource

    images = {i.image_id: i for i in context.images}
    active = {a.task_id: a for a in context.active_allocations}
    unfinished = {
        t.task_id: t
        for t in context.tasks
        if t.state
        in {
            TaskState.PENDING,
            TaskState.READY,
            TaskState.RETRY_WAIT,
            TaskState.INTERRUPTED,
        }
    }
    ranks = {}
    for task in sorted(
        unfinished.values(), key=lambda t: t.topological_sequence, reverse=True
    ):
        choices = options.get(task.task_id, ())
        mean = sum(o.estimate.runtime_point_ms for o in choices) / max(1, len(choices))
        ranks[task.task_id] = mean + max(
            (ranks.get(s, 0) for s in task.successor_task_ids), default=0
        )
    # Calendar rows: start, finish, CPU, RAM, disk, IO, GPU ID.
    calendar = [
        (
            context.now,
            max(context.now + timedelta(milliseconds=1), a.release_at),
            a.cpu_threads,
            a.ram_mib,
            a.disk_mib,
            a.io_heavy_slots,
            a.gpu_id,
        )
        for a in active.values()
    ]
    ends = {a.task_id: row[1] for a, row in zip(active.values(), calendar, strict=True)}
    cpu = min(
        context.limits.max_total_cpu_threads,
        context.resources.available_cpu_threads
        + sum(a.cpu_threads for a in active.values()),
    )
    ram = min(
        context.limits.max_ram_mib,
        context.resources.available_ram_mib + sum(a.ram_mib for a in active.values()),
    )
    slots = min(
        context.limits.max_concurrent_tasks,
        context.resources.available_concurrency_slots + len(active),
    )
    disk = context.resources.available_disk_mib
    if disk is not None:
        disk += sum(a.disk_mib for a in active.values())
    io = context.resources.available_io_heavy_slots
    if io is not None:
        io += sum(a.io_heavy_slots for a in active.values())
    original_gpus = {g.gpu_id: g for g in context.resources.gpus}
    gpus = tuple(
        GPUResource(
            g.gpu_id, True, g.total_memory_mib, g.total_memory_mib, g.device_class
        )
        if any(a.gpu_id == g.gpu_id for a in active.values())
        else original_gpus[g.gpu_id]
        for g in context.limits.gpus
        if g.enabled and g.gpu_id in original_gpus
    )
    full = replace(
        context,
        resources=replace(
            context.resources,
            available_cpu_threads=cpu,
            available_ram_mib=ram,
            available_concurrency_slots=slots,
            available_disk_mib=disk,
            available_io_heavy_slots=io,
            gpus=gpus,
        ),
        maximum_launches=max(1, slots),
        adaptive_concurrency=max(1, slots),
    )
    assignments = {}
    waiting = set()
    while unfinished:
        eligible = [
            t
            for t in unfinished.values()
            if not any(p in unfinished for p in t.predecessor_task_ids)
        ]
        if not eligible:
            raise ValueError("HEFT requires an acyclic task graph")
        task = min(eligible, key=lambda t: (-ranks[t.task_id], *_fifo_key(t, images)))
        if any(parent in waiting for parent in task.predecessor_task_ids):
            waiting.add(task.task_id)
            del unfinished[task.task_id]
            continue
        ready = max(
            [
                context.now,
                *(ends.get(p, context.now) for p in task.predecessor_task_ids),
            ]
        )
        if task.retry.retry_eligible_at is not None:
            ready = max(ready, task.retry.retry_eligible_at)
        candidates = []
        for option in options.get(task.task_id, ()):
            duration = timedelta(milliseconds=option.estimate.runtime_point_ms)
            gpu_ids = (
                (None,)
                if option.configuration.execution_mode is ExecutionMode.CPU
                else tuple(
                    g.gpu_id for g in core._gpu_candidates(full, option, gpus, ())
                )
            )
            for gpu_id in gpu_ids:
                for start in sorted(
                    {ready, *(row[1] for row in calendar if row[1] >= ready)}
                ):
                    finish = start + duration
                    points = {
                        start,
                        *(row[0] for row in calendar if start < row[0] < finish),
                    }
                    fits = True
                    for point in points:
                        occupied = [row for row in calendar if row[0] <= point < row[1]]
                        totals = core.ResourceTotals(
                            sum(r[2] for r in occupied),
                            sum(r[3] for r in occupied),
                            len(occupied),
                            sum(r[4] for r in occupied),
                            sum(r[5] for r in occupied),
                            tuple(r[6] for r in occupied if r[6] is not None),
                        )
                        if (
                            core._resource_rejections(full, option, totals)
                            or gpu_id in totals.gpu_ids
                        ):
                            fits = False
                            break
                    if fits:
                        candidates.append(
                            (
                                finish,
                                start,
                                str(option.configuration.configuration_id),
                                str(gpu_id or ""),
                                option,
                                gpu_id,
                            )
                        )
                        break
        if not candidates:
            # A transient shortage has no known release time. Wait for a new
            # snapshot. Never invent a finish time for an unplaced predecessor.
            waiting.add(task.task_id)
            del unfinished[task.task_id]
            continue
        finish, start, _, _, option, gpu_id = min(candidates, key=lambda c: c[:4])
        assignments[task.task_id] = (start, option, gpu_id)
        ends[task.task_id] = finish
        calendar.append(
            (
                start,
                finish,
                option.configuration.cpu_threads,
                option.estimate.ram_reservation_mib,
                core._disk(option),
                core._io(option),
                gpu_id,
            )
        )
        del unfinished[task.task_id]
    return assignments


def schedule_baseline(context, policy_id):
    core._validate_context(context)
    options, initial_rejections = core._prepared_options(context)
    if policy_id == "B7":
        # HEFT's mean cost includes slower declared configurations. Pareto
        # pruning is correct for resource optimization, but changes HEFT ranks.
        estimates = {
            (c.task_id, c.configuration.configuration_id): c
            for c in context.configuration_estimates
        }
        for rejection in initial_rejections:
            if rejection.code is core.ConfigurationRejectionCode.DOMINATED:
                candidate = estimates[(rejection.task_id, rejection.configuration_id)]
                options[rejection.task_id] += (
                    core._Option(
                        candidate.task_id, candidate.configuration, candidate.estimate
                    ),
                )
        initial_rejections = tuple(
            r
            for r in initial_rejections
            if r.code is not core.ConfigurationRejectionCode.DOMINATED
        )
    options = {
        task_id: tuple(o for o in choices if core._total_feasible(context, o))
        for task_id, choices in options.items()
    }
    priorities = _priorities(context, options, policy_id)
    protected = (
        core._protected_task(context, priorities, options)
        if policy_id == "B4"
        else None
    )
    heft = _heft_choices(context, options) if policy_id == "B7" else {}
    tasks = {t.task_id: t for t in context.tasks}
    totals = core.ResourceTotals()
    selected = ()
    rejected = list(initial_rejections)
    unselected = []
    unsafe = []
    slots = core._launch_limit(context)
    fair_share = max(
        1, core._cpu_capacity(context) // max(1, min(slots, len(priorities)))
    )
    for priority in priorities:
        task = tasks[priority.task_id]
        if len(selected) >= slots:
            unselected.append(
                core.UnselectedTask(task.task_id, core.TaskDecisionCode.LAUNCH_LIMIT)
            )
            continue
        choices = options[task.task_id]
        if policy_id == "B5":
            choice, extra_rejections = core._base_choice(
                context, choices, totals, fair_share
            )
            rejected.extend(extra_rejections)
        elif policy_id == "B7":
            choice = None
            assignment = heft.get(task.task_id)
            if assignment is not None:
                start, option, gpu_id = assignment
                if start <= context.now and not core._resource_rejections(
                    context, option, totals
                ):
                    choice = replace(
                        core._choice(context, option, totals), gpu_id=gpu_id
                    )
        else:
            choice = _static_choice(context, choices, totals)
        if choice is None:
            unselected.append(
                core.UnselectedTask(
                    task.task_id, core.TaskDecisionCode.RESOURCE_BLOCKED
                )
            )
            rejected.extend(
                core.ConfigurationRejection(
                    task.task_id, o.configuration.configuration_id, reason
                )
                for o in choices
                for reason in core._resource_rejections(context, o, totals)
            )
            if policy_id == "B0":
                # The head task must not be overtaken when resources are scarce.
                unselected.extend(
                    core.UnselectedTask(
                        p.task_id, core.TaskDecisionCode.RESOURCE_BLOCKED
                    )
                    for p in priorities[len(unselected) :]
                )
                break
            continue
        item = core._Provisional(
            task=task,
            priority=priority,
            choice=choice,
            totals_before=totals,
            protected_safe=None,
        )
        if protected is not None:
            if not core._backfill_safe(context, protected, item, selected):
                safe_options = tuple(
                    option
                    for option in choices
                    if not core._resource_rejections(context, option, totals)
                    and core._backfill_safe(
                        context,
                        protected,
                        replace(item, choice=core._choice(context, option, totals)),
                        selected,
                    )
                )
                choice = _static_choice(context, safe_options, totals)
                if choice is None:
                    unsafe.append(task.task_id)
                    unselected.append(
                        core.UnselectedTask(
                            task.task_id, core.TaskDecisionCode.BACKFILL_UNSAFE
                        )
                    )
                    continue
                item = replace(item, choice=choice)
            item = replace(item, protected_safe=True)
        selected += (item,)
        totals = core._add_totals(totals, choice)
    if policy_id == "B5":
        selected, totals = core._allocate_gpus(context, selected, options, totals, None)
        selected, totals = core._enrich_cpu(context, selected, options, totals, None)
    launches = []
    running_totals = core.ResourceTotals()
    for item in selected:
        item = replace(item, totals_before=running_totals)
        running_totals = core._add_totals(running_totals, item.choice)
        launch = core._selection(item, running_totals)
        launches.append(
            replace(
                launch,
                explanation=replace(
                    launch.explanation,
                    policy=policy_id,
                    reasons=(
                        f"external baseline {policy_id}",
                        "static estimates"
                        if policy_id != "B5"
                        else "adaptive estimates",
                    ),
                ),
            )
        )
    protection = None
    if protected is not None:
        task_id, option, start = protected
        protection = core.ProtectedTaskInfo(
            task_id,
            option.configuration.configuration_id,
            start,
            start + timedelta(milliseconds=option.estimate.runtime_point_ms),
            tuple(l.task_id for l in launches if l.task_id != task_id),
            tuple(unsafe),
        )
    plan = core.SchedulePlan(
        tuple(launches),
        priorities,
        tuple(rejected),
        tuple(unselected),
        protection,
        core.ResourceTotals(),
        totals,
    )
    core._validate_plan(context, plan)
    return plan
