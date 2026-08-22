from __future__ import annotations

from typing import TypeAlias

from app_backend import paths
from pipeline.config import ATLAS_DEFS, EXTERNAL_MNI_VOLUME_ATLASES, EXPORT_OUTPUT_ITEMS, PROJECT_ROOT, STAT_VECTOR_DEFS, ExportConfig
from pipeline.presets import PIPELINE_MODE_ALIASES, PIPELINE_MODES, PRESET_CONFIGS
from pipeline.registry import (
    FS7_RECON_STYLE_STAGE_ORDER,
    STAGE_LABELS,
    STAGE_ORDER,
    TOOL_DEFS,
    enabled_tools_for_stage,
    is_tool_enabled,
    is_tool_visible,
    tool_display_name,
)
from pipeline.stats import VECTOR_SPECS
from pipeline.tool_compat import tool_contracts_payload

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def _aliases_for_mode(mode: str) -> list[str]:
    return sorted(alias for alias, target in PIPELINE_MODE_ALIASES.items() if target == mode)


def _preset_metadata(mode: str) -> dict[str, JsonValue]:
    preset = PRESET_CONFIGS.get(mode, {})
    return {
        "tools": dict(preset.get("tools", {})),
        "stats": sorted(str(stat) for stat in preset.get("stats", set())),
        "default_atlases": {
            str(stat): [str(atlas) for atlas in atlases]
            for stat, atlases in preset.get("default_atlases", {}).items()
        },
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value]


def _tool_metadata(tool_key: str, tool: dict[str, object]) -> dict[str, JsonValue]:
    return {
        "key": tool_key,
        "display_name": tool_display_name(tool_key),
        "stage": str(tool.get("stage", "")),
        "image": str(tool.get("image", "")),
        "dockerfile": str(tool.get("dockerfile", "")) if tool.get("dockerfile") else "",
        "needs_license": bool(tool.get("needs_license", False)),
        "enabled": is_tool_enabled(tool_key),
        "visible": is_tool_visible(tool_key),
        "timeout_sec": int(tool.get("timeout", 7200) or 7200),
        "output_files": _string_list(tool.get("output_files", [])),
        "output_globs": _string_list(tool.get("output_globs", [])),
    }


def _mni_atlas_metadata() -> dict[str, JsonValue]:
    atlas_types = {
        atlas: stat
        for stat, stat_def in STAT_VECTOR_DEFS.items()
        for atlas in stat_def.get("atlases", ())
        if atlas in EXTERNAL_MNI_VOLUME_ATLASES
    }
    return {
        atlas: {
            "key": atlas,
            "label": ATLAS_DEFS.get(atlas, atlas),
            "type": atlas_types.get(atlas, ""),
            "source": "MNI",
            "atlas_nifti": str(VECTOR_SPECS.get(atlas, {}).get("atlas_nifti", "")),
            "atlas_lut": str(VECTOR_SPECS.get(atlas, {}).get("atlas_lut", "")),
            "stats_basename": str(VECTOR_SPECS.get(atlas, {}).get("stats_basename", f"{atlas}.stats")),
        }
        for atlas in EXTERNAL_MNI_VOLUME_ATLASES
    }


def get_app_metadata() -> dict[str, JsonValue]:
    """Return JSON-compatible metadata for non-Tk frontends."""

    return {
        "version": 1,
        "project_root": str(paths.portable_root() or PROJECT_ROOT),
        "pipeline_modes": [
            {
                "id": mode,
                "aliases": _aliases_for_mode(mode),
                **_preset_metadata(mode),
            }
            for mode in PIPELINE_MODES
        ],
        "presets": {mode: _preset_metadata(mode) for mode in PRESET_CONFIGS},
        "stages": [{"id": stage, "label": STAGE_LABELS.get(stage, stage)} for stage in STAGE_ORDER],
        "stage_order": list(STAGE_ORDER),
        "fs7_recon_style_stage_order": list(FS7_RECON_STYLE_STAGE_ORDER),
        "tools": {tool_key: _tool_metadata(tool_key, tool) for tool_key, tool in TOOL_DEFS.items()},
        "tools_by_stage": {stage: enabled_tools_for_stage(stage) for stage in STAGE_ORDER},
        "tool_contracts": tool_contracts_payload(),
        "export_items": {
            item_id: {
                "id": item_id,
                "stage": str(item.get("stage", "")),
                "label": str(item.get("label", item_id)),
                "default_name": str(item.get("default_name", item_id)),
            }
            for item_id, item in EXPORT_OUTPUT_ITEMS.items()
        },
        "export_defaults": ExportConfig().to_dict(),
        "stats_vectors": {
            stat: {
                "key": stat,
                "label": str(stat_def.get("label", stat)),
                "value_column": str(stat_def.get("value_column", "")),
                "atlases": [str(atlas) for atlas in stat_def.get("atlases", ())],
            }
            for stat, stat_def in STAT_VECTOR_DEFS.items()
        },
        "atlases": {atlas: {"key": atlas, "label": label} for atlas, label in ATLAS_DEFS.items()},
        "mni_atlases": _mni_atlas_metadata(),
        "vector_specs": {
            key: {spec_key: str(spec_value) for spec_key, spec_value in spec.items()}
            for key, spec in VECTOR_SPECS.items()
        },
    }
