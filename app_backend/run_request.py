from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

from pipeline.config import PROJECT_ROOT, ExportConfig, StatsVectorConfig
from pipeline.discovery import _is_dicom_file, _is_dicom_series_dir, _is_supported_mri_input
from pipeline.presets import (
    PRESET_CONFIGS,
    infer_pipeline_mode_from_tools,
    normalize_pipeline_mode,
    normalize_stats_vector_config_for_pipeline_mode,
)

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True)
class RunRequestInput:
    input_source: str = "Local"
    input_mode: str = "file"
    input_path: str = ""
    selected_files: list[str] = field(default_factory=list)
    output_dir: str = ""
    server_output_dir: str = ""
    input_server_dir: str = ""
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
    neuroflow_max_concurrent_tasks: int = 2
    neuroflow_policy: str = "B6"
    neuroflow_max_retries: int = 3
    neuroflow_warmup_enabled: bool = True
    neuroflow_warmup_initial_concurrency: int = 2
    neuroflow_warmup_safe_successes: int = 3
    neuroflow_preserve_oom_bounds: bool = True
    neuroflow_estimation_mode: str = "balanced"
    neuroflow_max_io_heavy_tasks: int = 2
    neuroflow_machine_profile_id: str = "application_default"
    neuroflow_preset_file: str = ""
    neuroflow_profile_file: str = ""
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
            input_server_dir=str(data.get("input_server_dir", "") or ""),
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
            neuroflow_max_concurrent_tasks=max(1, _int_from_data(data.get("neuroflow_max_concurrent_tasks"), 2)),
            neuroflow_policy=str(data.get("neuroflow_policy", "B6") or "B6").strip(),
            neuroflow_max_retries=max(0, _int_from_data(data.get("neuroflow_max_retries"), 3)),
            neuroflow_warmup_enabled=_bool_from_data(data.get("neuroflow_warmup_enabled"), True),
            neuroflow_warmup_initial_concurrency=max(1, _int_from_data(data.get("neuroflow_warmup_initial_concurrency"), 2)),
            neuroflow_warmup_safe_successes=max(1, _int_from_data(data.get("neuroflow_warmup_safe_successes"), 3)),
            neuroflow_preserve_oom_bounds=_bool_from_data(data.get("neuroflow_preserve_oom_bounds"), True),
            neuroflow_estimation_mode=str(data.get("neuroflow_estimation_mode", "balanced") or "balanced"),
            neuroflow_max_io_heavy_tasks=max(1, _int_from_data(data.get("neuroflow_max_io_heavy_tasks"), 2)),
            neuroflow_machine_profile_id=str(data.get("neuroflow_machine_profile_id", "") or "application_default"),
            neuroflow_preset_file=_neuroflow_config_path(data.get("neuroflow_preset_file")),
            neuroflow_profile_file=_neuroflow_config_path(data.get("neuroflow_profile_file")),
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


def prepare_run_request(
    config: RunRequestInput | dict[str, object],
    *,
    validate_license: bool = True,
) -> dict[str, JsonValue]:
    return _prepare_run_request_result(config, validate_license=validate_license).to_dict()


def _prepare_run_request_result(
    config: RunRequestInput | dict[str, object],
    *,
    validate_license: bool = True,
) -> RunRequestResult:
    run_config = config if isinstance(config, RunRequestInput) else RunRequestInput.from_dict(config)
    errors = validate_run_request_input(run_config, validate_license=validate_license)
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
        elif input_path.is_dir() and _is_dicom_series_dir(input_path):
            request.update(
                {
                    "mode": "dir",
                    "is_batch": False,
                    "input_dir": str(input_path),
                    "input_file": str(input_path),
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


def validate_run_request_input(config: RunRequestInput, *, validate_license: bool = True) -> list[str]:
    is_remote = config.run_target == "Server"

    if is_remote and config.input_source == "Local" and not config.input_server_dir.strip():
        return [
            "Provide an input location on the server (staging directory) for uploaded local inputs."
        ]
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
    if validate_license:
        license_error = _license_error(config)
        if license_error:
            return [license_error]
    tool_combo_error = _tool_combo_error(config)
    if tool_combo_error:
        return [tool_combo_error]
    neuroflow_error = _neuroflow_error(config)
    if neuroflow_error:
        return [neuroflow_error]

    for label, raw_path in (
        ("preset", config.neuroflow_preset_file),
        ("profile", config.neuroflow_profile_file),
    ):
        if raw_path and not Path(raw_path).expanduser().is_file():
            return [f"NeuroFLOW {label} configuration file does not exist."]

    # Skip local file existence checks for remote jobs with server-side inputs
    # (files are on the server, not accessible locally). Lazy-upload jobs keep
    # their inputs local, so those still get validated here.
    if is_remote and config.input_source != "Local":
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
    from pipeline.neuroflow_adapter import is_neuroflow_supported

    is_batch = config.input_mode == "dir"
    batch_output_name = f"batch_{_batch_timestamp(config)}" if is_batch else ""
    output_dir = config.output_dir.strip()
    selected_tools = _selected_tools(config)
    pipeline_mode = config.pipeline_mode
    if pipeline_mode == "Custom" and config.neuroflow_enabled and not config.neuroflow_preset_file:
        inferred_mode = infer_pipeline_mode_from_tools(selected_tools)
        if inferred_mode != "Custom":
            pipeline_mode = inferred_mode
    return {
        "mode": config.input_mode,
        "pipeline_mode": pipeline_mode,
        "output_dir": output_dir,
        "server_output_dir": config.server_output_dir.strip(),
        "input_server_dir": config.input_server_dir.strip(),
        "effective_output_dir": str(Path(output_dir) / batch_output_name) if batch_output_name else output_dir,
        "is_batch": is_batch,
        "batch_output_name": batch_output_name,
        "license_dir": config.license_dir.strip(),
        "device": config.device,
        "threads": config.threads,
        "ram_percent": config.ram_percent,
        "selected_tools": selected_tools,
        "export_config": config.export_config,
        "stats_vector_config": normalize_stats_vector_config_for_pipeline_mode(pipeline_mode, config.stats_vector_config),
        "input_source": config.input_source,
        "run_target": config.run_target,
        "neuroflow_enabled": bool(config.neuroflow_enabled)
        and is_neuroflow_supported(
            {
                "pipeline_mode": pipeline_mode,
                "neuroflow_preset_file": config.neuroflow_preset_file,
                "neuroflow_profile_file": config.neuroflow_profile_file,
            }
        ),
        "neuroflow_max_concurrent_tasks": config.neuroflow_max_concurrent_tasks,
        "neuroflow_policy": config.neuroflow_policy,
        "neuroflow_max_retries": config.neuroflow_max_retries,
        "neuroflow_warmup_enabled": config.neuroflow_warmup_enabled,
        "neuroflow_warmup_initial_concurrency": config.neuroflow_warmup_initial_concurrency,
        "neuroflow_warmup_safe_successes": config.neuroflow_warmup_safe_successes,
        "neuroflow_preserve_oom_bounds": config.neuroflow_preserve_oom_bounds,
        "neuroflow_estimation_mode": config.neuroflow_estimation_mode,
        "neuroflow_max_io_heavy_tasks": config.neuroflow_max_io_heavy_tasks,
        "neuroflow_machine_profile_id": config.neuroflow_machine_profile_id.strip() or "application_default",
        "neuroflow_preset_file": config.neuroflow_preset_file,
        "neuroflow_profile_file": config.neuroflow_profile_file,
    }


def _neuroflow_config_path(value: object) -> str:
    raw_path = str(value or "").strip()
    if not raw_path:
        return ""
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        project_path = PROJECT_ROOT / path
        if project_path.is_file():
            return str(project_path)
    return str(path)


def _selected_tools(config: RunRequestInput) -> dict[str, str]:
    if config.pipeline_mode != "Custom" and config.pipeline_mode in PRESET_CONFIGS:
        return dict(PRESET_CONFIGS[config.pipeline_mode]["tools"])
    return dict(config.selected_tools)


def _stats_vector_config(config: RunRequestInput) -> dict[str, JsonValue]:
    return normalize_stats_vector_config_for_pipeline_mode(config.pipeline_mode, config.stats_vector_config)


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
    if not Path(license_path).expanduser().exists():
        return "FreeSurfer license file or directory does not exist."
    return ""


def _tool_combo_error(config: RunRequestInput) -> str:
    from pipeline.presets import infer_pipeline_mode_from_tools
    from pipeline.tool_compat import validate_tool_combo

    selected = _selected_tools(config)
    # A Custom map identical to a named preset executes as that preset.
    if config.pipeline_mode == "Custom" and infer_pipeline_mode_from_tools(selected) != "Custom":
        return ""
    violations = validate_tool_combo(selected)
    if not violations:
        return ""
    parts = [f"{v['stage']}: {v['reason']}" for v in violations[:3]]
    if len(violations) > 3:
        parts.append(f"(+{len(violations) - 3} more)")
    return "Invalid tool combination — " + "; ".join(parts)


def _neuroflow_error(config: RunRequestInput) -> str:
    if not config.neuroflow_enabled:
        return ""
    if config.neuroflow_max_concurrent_tasks < 1:
        return "NeuroFLOW max concurrent tasks must be at least 1."
    if config.neuroflow_max_retries < 0 or config.neuroflow_max_retries > 5:
        return "NeuroFLOW max retries must be between 0 and 5."
    if config.neuroflow_estimation_mode not in {"balanced", "conservative", "aggressive"}:
        return "NeuroFLOW estimation mode must be balanced, conservative, or aggressive."
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
