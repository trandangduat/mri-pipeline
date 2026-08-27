from __future__ import annotations

import json
from pathlib import Path
from typing import TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def validate_neuroflow_config(
    *,
    path: str | Path | None = None,
    content: str | None = None,
    kind: str,
) -> dict[str, JsonValue]:
    """Validate a NeuroFLOW Preset (pipeline DAG) or Profile configuration file/content.

    Returns a dict with `{"ok": True, "id": "...", "display_name": "..."}` on success,
    or `{"ok": False, "error": "..."}` on failure.
    """
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind not in {"preset", "profile"}:
        return {"ok": False, "error": f"Invalid configuration kind: '{kind}'. Expected 'preset' or 'profile'."}

    raw_text = ""
    resolved_path: Path | None = None
    if path:
        raw_path = str(path).strip()
        if not raw_path:
            return {"ok": False, "error": "Configuration file path is empty."}
        resolved_path = Path(raw_path).expanduser()
        if not resolved_path.is_file():
            return {"ok": False, "error": f"File does not exist: {raw_path}"}
        try:
            raw_text = resolved_path.read_text(encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "error": f"Could not read file: {exc}"}
    elif content is not None:
        raw_text = str(content).strip()
        if not raw_text:
            return {"ok": False, "error": "Configuration content is empty."}
    else:
        return {"ok": False, "error": "Either path or content must be provided."}

    parsed = _parse_yaml_or_json(raw_text)
    if parsed is None or not isinstance(parsed, dict):
        return {
            "ok": False,
            "error": "The selected file is not a valid YAML or JSON object.",
        }

    # Disallow other configuration types
    file_type = str(parsed.get("type", "") or "")
    if file_type == "mri-pipeline-workspace":
        return {
            "ok": False,
            "error": "The selected file is a NeuroFlow Workspace file, not a NeuroFLOW scheduler configuration.",
        }
    if file_type == "mri-pipeline-preset":
        return {
            "ok": False,
            "error": "The selected file is an MRI Tool Preset file, not a NeuroFLOW DAG preset configuration.",
        }

    if normalized_kind == "preset":
        return _validate_preset(parsed, str(resolved_path) if resolved_path else None)
    else:
        return _validate_profile(parsed, str(resolved_path) if resolved_path else None)


def _validate_preset(data: dict, document_path: str | None) -> dict[str, JsonValue]:
    # Check if a profile file was accidentally supplied as a preset
    if "profile_set_id" in data or "profiles" in data:
        return {
            "ok": False,
            "error": "The selected file is a NeuroFLOW Profile configuration file, not a Preset (pipeline DAG) configuration.",
        }

    pipeline_id = str(data.get("pipeline_id", "") or "").strip()
    if not pipeline_id:
        return {
            "ok": False,
            "error": "Invalid preset configuration: missing required 'pipeline_id' identifier.",
        }

    stages = data.get("stages")
    if not isinstance(stages, list) or len(stages) == 0:
        return {
            "ok": False,
            "error": "Invalid preset configuration: 'stages' list is missing or empty.",
        }

    for idx, stage in enumerate(stages):
        if not isinstance(stage, dict):
            return {
                "ok": False,
                "error": f"Invalid stage at index {idx}: expected an object.",
            }
        stage_id = str(stage.get("id", "") or "").strip()
        if not stage_id:
            return {
                "ok": False,
                "error": f"Invalid stage at index {idx}: missing required 'id' attribute.",
            }

    display_name = str(data.get("display_name", "") or pipeline_id)
    return {
        "ok": True,
        "kind": "preset",
        "id": pipeline_id,
        "display_name": display_name,
        "stage_count": len(stages),
        "path": document_path,
    }


def _validate_profile(data: dict, document_path: str | None) -> dict[str, JsonValue]:
    # Check if a preset file was accidentally supplied as a profile
    if "pipeline_id" in data and "stages" in data:
        return {
            "ok": False,
            "error": "The selected file is a NeuroFLOW Preset (pipeline DAG) configuration file, not a Profile configuration.",
        }

    profile_set_id = str(data.get("profile_set_id", "") or "").strip()
    if not profile_set_id:
        return {
            "ok": False,
            "error": "Invalid profile configuration: missing required 'profile_set_id' identifier.",
        }

    profiles = data.get("profiles")
    if not isinstance(profiles, list) or len(profiles) == 0:
        return {
            "ok": False,
            "error": "Invalid profile configuration: 'profiles' list is missing or empty.",
        }

    for idx, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            return {
                "ok": False,
                "error": f"Invalid profile at index {idx}: expected an object.",
            }
        profile_id = str(profile.get("profile_id", "") or "").strip()
        if not profile_id:
            return {
                "ok": False,
                "error": f"Invalid profile at index {idx}: missing required 'profile_id' attribute.",
            }

    display_name = str(data.get("display_name", "") or profile_set_id)
    return {
        "ok": True,
        "kind": "profile",
        "id": profile_set_id,
        "display_name": display_name,
        "profile_count": len(profiles),
        "path": document_path,
    }


def _parse_yaml_or_json(content: str) -> object:
    try:
        import yaml
        return yaml.safe_load(content)
    except ImportError:
        pass
    except Exception:
        pass

    try:
        return json.loads(content)
    except Exception:
        return None
