"""Application policy identities. No policy name silently selects another engine."""

from __future__ import annotations

import json

INTEGRATION_VERSION = "1.0.0"
POLICY_NAMES = {
    "B0": "Sequential FIFO",
    "B1": "Parallel FIFO First-Fit",
    "B2": "Shortest Processing Time First-Fit",
    "B3": "Static Critical-Path First-Fit",
    "B4": "Static Critical-Path Protected Backfill",
    "B5": "Adaptive FIFO Resource Scheduler",
    "B6": "Full NeuroFLOW",
    "B7": "HEFT Family",
}
STATIC_POLICIES = frozenset({"B0", "B1", "B2", "B3", "B4", "B7"})
FIXED_POLICIES = frozenset({"B0", "B1", "B2"})


def normalize_policy(value: object = None) -> str:
    name = str(value or "B6").strip() or "B6"
    if name in POLICY_NAMES:
        return name
    for policy_id, label in POLICY_NAMES.items():
        if name == label:
            return policy_id
    raise ValueError(f"Unknown NeuroFLOW policy: {name}")


def default_configurations(value: object) -> dict[str, str]:
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as error:
            raise ValueError(
                "Baseline defaults must be a JSON object of stage IDs and configuration IDs"
            ) from error
    if not isinstance(value, dict) or any(
        not isinstance(k, str)
        or not isinstance(v, str)
        or not k.strip()
        or not v.strip()
        for k, v in value.items()
    ):
        raise ValueError(
            "Baseline defaults must map stage IDs to nonempty configuration IDs"
        )
    return dict(value)


def resolve_defaults(pipeline, requested: object, limits) -> dict[str, str]:
    """Resolve explicit defaults before filtering configurations for machine limits."""
    mapping = default_configurations(
        dict(pipeline.metadata).get("baseline_default_configurations")
    )
    mapping.update(default_configurations(requested))
    stages = {str(s.stage_id): s for s in pipeline.stages if s.enabled}
    unknown = mapping.keys() - stages.keys()
    if unknown:
        raise ValueError(
            f"Baseline defaults reference unknown or disabled stages: {sorted(unknown)}"
        )
    for stage_id, stage in stages.items():
        configs = {str(c.configuration_id): c for c in stage.execution_configurations}
        if stage_id not in mapping:
            if len(configs) != 1:
                raise ValueError(
                    f"{stage_id}: choose an explicit baseline default from {sorted(configs)}"
                )
            mapping[stage_id] = next(iter(configs))
        config = configs.get(mapping[stage_id])
        if config is None:
            raise ValueError(
                f"{stage_id}: unknown baseline default {mapping[stage_id]}"
            )
        if config.cpu_threads > min(
            limits.max_total_cpu_threads, limits.max_threads_per_task
        ):
            raise ValueError(f"{stage_id}: baseline default exceeds the CPU limit")
        if str(config.execution_mode) == "gpu" and not any(
            g.enabled for g in limits.gpus
        ):
            raise ValueError(f"{stage_id}: baseline default needs an enabled GPU")
    return mapping


def classify_failure(step) -> str:
    """Require explicit memory evidence. Exit code 137 alone is insufficient."""
    text = (
        str(getattr(step, "error", "") or "")
        + " "
        + str(getattr(step, "log_text", "") or "")
    ).lower()
    if any(
        term in text
        for term in (
            "cuda out of memory",
            "cuda error: out of memory",
            "gpu out of memory",
        )
    ):
        return "GPU_OOM"
    if any(
        term in text
        for term in (
            "oomkilled",
            "oom-kill",
            "out of memory",
            "cannot allocate memory",
            "std::bad_alloc",
        )
    ):
        return "RAM_OOM"
    return "PROCESS_CRASH"
