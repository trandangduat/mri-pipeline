from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

from pipeline.config import STAT_VECTOR_DEFS, ExportConfig, StatsVectorConfig
from pipeline.discovery import _is_dicom_file, _is_dicom_series_dir, _is_supported_mri_input
from pipeline.presets import PRESET_CONFIGS, normalize_pipeline_mode

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True)
class RunRequestInput:
    input_source: str = "Local"
    input_mode: str = "file"
    input_path: str = ""
    selected_files: list[str] = field(default_factory=list)
    output_dir: str = ""
    server_output_dir: str = ""
    license_dir: str = ""
    device: str = "cpu"
    threads: int = 4
    ram_percent: int = 100
    non_recursive: bool = True
    run_target: str = "Local"
    pipeline_mode: str = "Custom"
    selected_tools: dict[str, str] = field(default_factory=dict)
    export_config: dict[str, JsonValue] = field(default_factory=lambda: ExportConfig().to_dict())
    stats_vector_config: dict[str, JsonValue] = field(default_factory=lambda: StatsVectorConfig().to_dict())
    neuroflow_enabled: bool = False
    neuroflow_max_concurrent_tasks: int = 1
    neuroflow_machine_profile_id: str = "application_default"
    batch_timestamp: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "RunRequestInput":
        return cls(
            input_source=str(data.get("input_source", "Local") or "Local"),
            input_mode=str(data.get("input_mode", "file") or "file"),
            input_path=str(data.get("input_path", "") or ""),
            selected_files=[str(path) for path in data.get("selected_files", []) if str(path).strip()]
            if isinstance(data.get("selected_files", []), list)
            else [],
            output_dir=str(data.get("output_dir", "") or ""),
            server_output_dir=str(data.get("server_output_dir", "") or ""),
            license_dir=str(data.get("license_dir", "") or ""),
            device=str(data.get("device", "cpu") or "cpu"),
            threads=_int_from_data(data.get("threads"), 4),
            ram_percent=_int_from_data(data.get("ram_percent"), 100),
            non_recursive=_bool_from_data(data.get("non_recursive"), True),
            run_target=str(data.get("run_target", "Local") or "Local"),
            pipeline_mode=normalize_pipeline_mode(str(data.get("pipeline_mode", "Custom") or "Custom")),
            selected_tools=_string_dict(data.get("selected_tools", {})),
            export_config=_json_dict(data.get("export_config", ExportConfig().to_dict())),
            stats_vector_config=_json_dict(data.get("stats_vector_config", StatsVectorConfig().to_dict())),
            neuroflow_enabled=_bool_from_data(data.get("neuroflow_enabled"), False),
            neuroflow_max_concurrent_tasks=max(1, _int_from_data(data.get("neuroflow_max_concurrent_tasks"), 1)),
            neuroflow_machine_profile_id=str(data.get("neuroflow_machine_profile_id", "") or "application_default"),
            batch_timestamp=str(data.get("batch_timestamp", "") or ""),
        )


@dataclass(frozen=True)
class RunRequestResult:
    request: dict[str, JsonValue] | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.request is not None and not self.errors

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "ok": self.ok,
            "request": self.request,
            "errors": list(self.errors),
        }


def prepare_run_request(config: RunRequestInput | dict[str, object]) -> dict[str, JsonValue]:
    return _prepare_run_request_result(config).to_dict()


def _prepare_run_request_result(config: RunRequestInput | dict[str, object]) -> RunRequestResult:
    run_config = config if isinstance(config, RunRequestInput) else RunRequestInput.from_dict(config)
    errors = validate_run_request_input(run_config)
    if errors:
        return RunRequestResult(errors=errors)

    request = _base_request(run_config)
    mode = request["mode"]
    raw_input = run_config.input_path.strip()

    if mode == "file":
        path = run_config.selected_files[0] if run_config.selected_files else raw_input
        input_path = Path(path).expanduser()
        if input_path.is_file() and _is_dicom_file(input_path):
            parent = input_path.parent
            if _is_dicom_series_dir(parent):
                request.update(
                    {
                        "mode": "dir",
                        "is_batch": False,
                        "input_dir": str(parent),
                        "input_file": str(parent),
                        "recursive": False,
                    }
                )
                return RunRequestResult(request=request)
        request["input_file"] = path
    elif mode == "files":
        files = _normalized_input_files(_selected_or_split_files(run_config))
        request["input_files"] = files
        request["input_dir"] = _common_input_root(files)
    else:
        if run_config.selected_files:
            request["mode"] = "files"
            files = _normalized_input_files(run_config.selected_files)
            request["input_files"] = files
            request["input_dir"] = _common_input_root(files)
        else:
            request["input_dir"] = raw_input
            request["recursive"] = not run_config.non_recursive

    return RunRequestResult(request=request)


def validate_run_request_input(config: RunRequestInput) -> list[str]:
    is_remote = config.run_target == "Server"

    if is_remote and config.input_source != "Server":
        return ["Remote jobs require input source to be 'Server' (files must be on the remote server)."]
    if not is_remote and config.input_source == "Server":
        return ["Local runs can only use local input data."]

    raw_input = config.input_path.strip()
    has_selected_files = bool(config.selected_files)
    if not raw_input and not has_selected_files:
        return ["Choose an input MRI file or folder."]
    if not config.output_dir.strip():
        return ["Choose an output directory."]

    runtime_error = _runtime_error(config)
    if runtime_error:
        return [runtime_error]
    license_error = _license_error(config)
    if license_error:
        return [license_error]
    neuroflow_error = _neuroflow_error(config)
    if neuroflow_error:
        return [neuroflow_error]

    # Skip local file existence checks for remote jobs
    # (files are on the server, not accessible locally)
    if is_remote:
        return []

    mode = config.input_mode
    if mode == "file":
        path = config.selected_files[0] if config.selected_files else raw_input
        if not _is_supported_mri_input(path):
            return ["Input file or DICOM folder does not exist."]
    elif mode == "files":
        files = _selected_or_split_files(config)
        if not files:
            return ["Choose at least one input file."]
        if any(not _is_supported_mri_input(path) for path in files):
            return ["One or more selected input files or DICOM folders do not exist."]
    elif mode == "dir":
        if config.selected_files:
            if any(not _is_supported_mri_input(path) for path in config.selected_files):
                return ["One or more selected input files or DICOM folders do not exist."]
        elif not Path(raw_input).expanduser().is_dir():
            return ["Input folder does not exist."]
    else:
        return ["Input mode must be file, files, or dir."]

    return []


def _base_request(config: RunRequestInput) -> dict[str, JsonValue]:
    is_batch = config.input_mode == "dir"
    batch_output_name = f"batch_{_batch_timestamp(config)}" if is_batch else ""
    output_dir = config.output_dir.strip()
    return {
        "mode": config.input_mode,
        "output_dir": output_dir,
        "server_output_dir": config.server_output_dir.strip(),
        "effective_output_dir": str(Path(output_dir) / batch_output_name) if batch_output_name else output_dir,
        "is_batch": is_batch,
        "batch_output_name": batch_output_name,
        "license_dir": config.license_dir.strip(),
        "device": config.device,
        "threads": config.threads,
        "ram_percent": config.ram_percent,
        "selected_tools": _selected_tools(config),
        "export_config": config.export_config,
        "stats_vector_config": _stats_vector_config(config),
        "input_source": config.input_source,
        "run_target": config.run_target,
        "pipeline_mode": config.pipeline_mode,
        "neuroflow_enabled": config.neuroflow_enabled,
        "neuroflow_max_concurrent_tasks": config.neuroflow_max_concurrent_tasks,
        "neuroflow_machine_profile_id": config.neuroflow_machine_profile_id.strip() or "application_default",
    }


def _selected_tools(config: RunRequestInput) -> dict[str, str]:
    if config.pipeline_mode != "Custom" and config.pipeline_mode in PRESET_CONFIGS:
        return dict(PRESET_CONFIGS[config.pipeline_mode]["tools"])
    return dict(config.selected_tools)


def _stats_vector_config(config: RunRequestInput) -> dict[str, JsonValue]:
    if config.pipeline_mode == "Custom" or config.pipeline_mode not in PRESET_CONFIGS:
        return dict(config.stats_vector_config)

    preset = PRESET_CONFIGS[config.pipeline_mode]
    enabled = {str(stat) for stat in preset["stats"]}
    default_atlases = preset.get("default_atlases", {})
    raw_atlases = config.stats_vector_config.get("atlases", {})
    atlas_config = raw_atlases if isinstance(raw_atlases, dict) else {}
    atlases: dict[str, JsonValue] = {}
    for stat, stat_def in STAT_VECTOR_DEFS.items():
        existing = atlas_config.get(stat, [])
        if isinstance(existing, list) and existing:
            atlases[stat] = [str(atlas) for atlas in existing]
            continue
        allowed = set(str(atlas) for atlas in stat_def.get("atlases", ()))
        preset_defaults = default_atlases.get(stat, [])
        valid_defaults = [str(atlas) for atlas in preset_defaults if atlas in allowed]
        if stat in enabled and valid_defaults:
            atlases[stat] = valid_defaults
        elif stat in enabled and allowed:
            atlases[stat] = [str(atlas) for atlas in stat_def.get("atlases", ()) if atlas in allowed][:1]
        else:
            atlases[stat] = []

    return {
        "enabled_stats": {stat: stat in enabled for stat in STAT_VECTOR_DEFS},
        "atlases": atlases,
    }


def _batch_timestamp(config: RunRequestInput) -> str:
    return config.batch_timestamp or time.strftime("%Y%m%d_%H%M%S")


def _selected_or_split_files(config: RunRequestInput) -> list[str]:
    return list(config.selected_files) or [path.strip() for path in config.input_path.split(";") if path.strip()]


def _normalized_input_files(files: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for path in files:
        normalized_path = _normalize_dicom_file_to_series_dir(path)
        if normalized_path not in seen:
            normalized.append(normalized_path)
            seen.add(normalized_path)
    return normalized


def _normalize_dicom_file_to_series_dir(path: str) -> str:
    input_path = Path(path).expanduser()
    if input_path.is_file() and _is_dicom_file(input_path) and _is_dicom_series_dir(input_path.parent):
        return str(input_path.parent)
    return path


def _common_input_root(files: list[str]) -> str:
    parents = [str(Path(path).expanduser().resolve().parent) for path in files]
    try:
        return os.path.commonpath(parents)
    except ValueError:
        return parents[0] if parents else ""


def _runtime_error(config: RunRequestInput) -> str:
    if config.threads < 1:
        return "Threads must be at least 1."
    if config.ram_percent < 1 or config.ram_percent > 100:
        return "RAM % must be between 1 and 100."
    return ""


def _license_error(config: RunRequestInput) -> str:
    from pipeline.registry import TOOL_DEFS

    if not any(TOOL_DEFS.get(tool_key, {}).get("needs_license") for tool_key in _selected_tools(config).values()):
        return ""
    license_path = config.license_dir.strip()
    if not license_path:
        return "FreeSurfer license file is required for the selected pipeline tools."
    if config.run_target != "Server" and not Path(license_path).expanduser().exists():
        return "FreeSurfer license file or directory does not exist."
    return ""


def _neuroflow_error(config: RunRequestInput) -> str:
    if not config.neuroflow_enabled:
        return ""
    from pipeline.neuroflow_adapter import PIPELINE_MODE_TO_PRESET

    if config.pipeline_mode not in PIPELINE_MODE_TO_PRESET:
        return "NeuroFLOW currently requires one of the FreeSurfer/FastSurfer preset pipeline modes."
    return ""


def _int_from_data(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool_from_data(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _json_dict(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _json_value(item) for key, item in value.items()}


def _json_value(value: object) -> JsonValue:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)
