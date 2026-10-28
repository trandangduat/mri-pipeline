"""Durable GPU execution evidence. This is not scheduler state."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from .config import StepResult


def _stamp(path: str) -> dict:
    target = Path(path).resolve()
    stat = target.stat()
    if not target.is_file() or stat.st_size == 0:
        raise ValueError(f"Missing execution file: {target}")
    return {"path": str(target), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _input_stamp(path: str) -> dict:
    target = Path(path).resolve()
    if target.is_dir():
        # DICOM inputs can be directories. Keep file metadata, not MRI contents.
        return {"path": str(target), "files": [
            _stamp(str(child)) for child in sorted(target.rglob("*")) if child.is_file()
        ]}
    return _stamp(path)


def receipt_path(job_dir: Path, task_id: str) -> Path:
    key = hashlib.sha256(task_id.encode()).hexdigest()
    return job_dir / "gpu_execution_receipts" / f"{key}.json"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def execution_provenance(context, launch, local_stage: str, source_hashes: tuple[str, str]) -> dict:
    tool = context.config.selected_tools.get(local_stage, "")
    from .registry import TOOL_DEFS
    return {
        "task_id": str(launch.task_id),
        "input": _input_stamp(context.input_file),
        "stage_input": _stamp(context.input_for_stage(local_stage))
                       if context.input_for_stage(local_stage) else None,
        "subject_dir": str(Path(context.subject_dir).resolve()),
        "stage": local_stage,
        "tool": tool,
        "tool_image": TOOL_DEFS.get(tool, {}).get("image"),
        "configuration_id": str(launch.configuration_id),
        "gpu_id": str(launch.gpu_id),
        "cpu_threads": int(launch.cpu_threads),
        "mode": str(launch.execution_mode.value),
        "selected_tools": context.config.selected_tools,
        "license_dir": context.config.license_dir,
        "ram_percent": context.config.ram_percent,
        "runtime_ram_bytes": context.config.runtime_ram_bytes,
        "stats": asdict(context.config.stats_vector_config),
        "exports": asdict(context.config.export_config),
        "sources": list(source_hashes),
    }


def save_execution(path: Path, provenance: dict, launch, execution_id: str,
                   step: StepResult, output: str | None, outputs: list[str] | None = None) -> dict:
    if not output:
        raise ValueError("Successful GPU processing has no validated output")
    root = Path(provenance["subject_dir"])
    if not Path(output).resolve().is_relative_to(root):
        raise ValueError("GPU output is outside this subject workspace")
    evidence = {
        "schema_version": 1, "provenance": provenance,
        "attempt_id": str(launch.attempt_id), "execution_id": execution_id,
        "processing_success": True, "step": asdict(step),
        "output": _stamp(output), "reporting_state": "pending",
    }
    evidence["step"]["output_file"] = evidence["output"]["path"]
    evidence["outputs"] = [
        _stamp(item) for item in sorted(set((outputs or []) + [output]))
        if Path(item).is_file()
    ]
    write_json(path, evidence)
    return evidence


def load_execution(path: Path, provenance: dict) -> dict | None:
    if not path.exists():
        return None
    evidence = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(evidence, dict) or evidence.get("schema_version") != 1 or evidence.get("provenance") != provenance
            or evidence.get("processing_success") is not True
            or not evidence.get("attempt_id") or not evidence.get("execution_id")):
        raise ValueError("GPU receipt provenance does not match this task")
    output = evidence["output"]
    if not Path(output["path"]).resolve().is_relative_to(Path(provenance["subject_dir"])):
        raise ValueError("GPU receipt output is outside this subject workspace")
    if _stamp(output["path"]) != output:
        raise ValueError("GPU receipt output has changed or is missing")
    for item in evidence.get("outputs", [output]):
        if (not Path(item["path"]).resolve().is_relative_to(Path(provenance["subject_dir"]))
                or _stamp(item["path"]) != item):
            raise ValueError("GPU receipt output references have changed")
    step = StepResult(**evidence["step"])
    if not step.success or step.output_file != output["path"]:
        raise ValueError("GPU receipt does not describe validated processing")
    return evidence


def write_report(job_dir: Path, result, observation: dict) -> Path:
    key = hashlib.sha256(str(result.attempt_id).encode()).hexdigest()
    path = job_dir / "gpu_execution_receipts" / f"report-{key}.json"
    write_json(path, {"result": asdict(result), "observation": observation,
                      "reporting_state": "pending"})
    return path


def mark_reported(path: Path) -> None:
    evidence = json.loads(path.read_text(encoding="utf-8"))
    evidence["reporting_state"] = "reported"
    write_json(path, evidence)
