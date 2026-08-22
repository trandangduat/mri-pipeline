from __future__ import annotations

import json
import sys
import ast
import subprocess
from pathlib import Path

from pipeline.config import ATLAS_DEFS, EXPORT_OUTPUT_ITEMS, STAT_VECTOR_DEFS
from pipeline.presets import PIPELINE_MODES, PRESET_CONFIGS
from pipeline.registry import STAGE_ORDER, TOOL_DEFS, enabled_tools_for_stage, tool_display_name


APP_BACKEND_PATHS = list(Path("app_backend").rglob("*.py"))


def _get_app_metadata() -> dict[str, object]:
    from app_backend.metadata import get_app_metadata

    return get_app_metadata()


def test_app_metadata_is_json_serializable_and_tkinter_free() -> None:
    metadata = _get_app_metadata()

    json.dumps(metadata)
    code = (
        "import json, sys; "
        "from app_backend.metadata import get_app_metadata; "
        "json.dumps(get_app_metadata()); "
        "raise SystemExit(1 if any(name == 'tkinter' or name.startswith('tkinter.') for name in sys.modules) else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr or result.stdout


def test_app_backend_does_not_import_legacy_ui_or_tkinter() -> None:
    forbidden: list[str] = []
    for path in APP_BACKEND_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "tkinter" or alias.name.startswith("tkinter.") or alias.name == "ui" or alias.name.startswith("ui."):
                        forbidden.append(f"{path}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "tkinter" or module.startswith("tkinter.") or module == "ui" or module.startswith("ui."):
                    forbidden.append(f"{path}:{node.lineno}: from {module} import ...")

    assert forbidden == []


def test_app_metadata_exposes_pipeline_sources_of_truth() -> None:
    metadata = _get_app_metadata()

    assert [stage["id"] for stage in metadata["stages"]] == STAGE_ORDER
    assert [mode["id"] for mode in metadata["pipeline_modes"]] == list(PIPELINE_MODES)
    assert set(metadata["presets"]) == set(PRESET_CONFIGS)
    assert set(metadata["export_items"]) == set(EXPORT_OUTPUT_ITEMS)
    assert set(metadata["stats_vectors"]) == set(STAT_VECTOR_DEFS)
    assert set(metadata["atlases"]) == set(ATLAS_DEFS)


def test_app_metadata_exposes_mni_atlas_metadata() -> None:
    metadata = _get_app_metadata()

    mni_atlases = metadata["mni_atlases"]
    assert "harvard_oxford_subcortical" in mni_atlases
    assert mni_atlases["harvard_oxford_subcortical"]["atlas_nifti"] == "HarvardOxford-subl-maxprob-thr0-1mm.nii.gz"
    assert mni_atlases["harvard_oxford_cortical"]["atlas_nifti"] == "HarvardOxford-cortl-maxprob-thr0-1mm.nii.gz"
    assert mni_atlases["harvard_oxford_cortical"]["atlas_lut"] == "harvard_oxford_cort_LUT.txt"


def test_app_metadata_exposes_visible_tools_without_non_serializable_fields() -> None:
    metadata = _get_app_metadata()

    assert set(metadata["tools"]) == set(TOOL_DEFS)
    for tool_key, tool in metadata["tools"].items():
        source_tool = TOOL_DEFS[tool_key]
        assert tool["key"] == tool_key
        assert tool["display_name"] == tool_display_name(tool_key)
        assert tool["stage"] == source_tool["stage"]
        assert "command_builder" not in tool
        assert "command" not in tool

    for stage in STAGE_ORDER:
        assert metadata["tools_by_stage"][stage] == enabled_tools_for_stage(stage)


def test_app_metadata_exposes_tool_contracts() -> None:
    from pipeline.tool_compat import TOOL_CONTRACTS, tool_contracts_payload

    metadata = _get_app_metadata()

    assert metadata["tool_contracts"] == tool_contracts_payload()
    assert set(metadata["tool_contracts"]) == set(TOOL_CONTRACTS)
    entry = metadata["tool_contracts"]["fastsurfer_reorientation"]
    assert entry == {"requires": [], "produces": ["orig_mgz"]}
