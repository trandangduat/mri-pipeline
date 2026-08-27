from __future__ import annotations

from pathlib import Path
from app_backend.neuroflow_config_validator import validate_neuroflow_config


VALID_PRESET_YAML = """
schema_version: 1
pipeline_id: custom_preset_test
display_name: Custom Preset Test
stages:
  - id: stage_1
    display_name: Stage 1
    operation: recon
    implementation: test_tool
"""

VALID_PROFILE_YAML = """
schema_version: 1
profile_set_id: custom_profile_test
display_name: Custom Profile Test
profiles:
  - profile_id: prof_1
    pipeline_id: custom_preset_test
    configuration_id: cpu_1
"""


def test_validate_preset_valid_file(tmp_path: Path) -> None:
    file = tmp_path / "preset.yaml"
    file.write_text(VALID_PRESET_YAML, encoding="utf-8")

    result = validate_neuroflow_config(path=str(file), kind="preset")
    assert result["ok"] is True
    assert result["id"] == "custom_preset_test"
    assert result["display_name"] == "Custom Preset Test"
    assert result["stage_count"] == 1


def test_validate_profile_valid_file(tmp_path: Path) -> None:
    file = tmp_path / "profile.yaml"
    file.write_text(VALID_PROFILE_YAML, encoding="utf-8")

    result = validate_neuroflow_config(path=str(file), kind="profile")
    assert result["ok"] is True
    assert result["id"] == "custom_profile_test"
    assert result["display_name"] == "Custom Profile Test"
    assert result["profile_count"] == 1


def test_validate_preset_valid_content() -> None:
    result = validate_neuroflow_config(content=VALID_PRESET_YAML, kind="preset")
    assert result["ok"] is True
    assert result["id"] == "custom_preset_test"


def test_validate_rejects_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "non_existent.yaml"
    result = validate_neuroflow_config(path=str(missing), kind="preset")
    assert result["ok"] is False
    assert "does not exist" in str(result["error"])


def test_validate_rejects_workspace_file(tmp_path: Path) -> None:
    file = tmp_path / "workspace.json"
    file.write_text('{"type": "mri-pipeline-workspace", "pipeline_mode": "Custom"}', encoding="utf-8")

    result = validate_neuroflow_config(path=str(file), kind="preset")
    assert result["ok"] is False
    assert "Workspace file" in str(result["error"])


def test_validate_rejects_profile_as_preset(tmp_path: Path) -> None:
    file = tmp_path / "profile.yaml"
    file.write_text(VALID_PROFILE_YAML, encoding="utf-8")

    result = validate_neuroflow_config(path=str(file), kind="preset")
    assert result["ok"] is False
    assert "Profile configuration" in str(result["error"])


def test_validate_rejects_preset_as_profile(tmp_path: Path) -> None:
    file = tmp_path / "preset.yaml"
    file.write_text(VALID_PRESET_YAML, encoding="utf-8")

    result = validate_neuroflow_config(path=str(file), kind="profile")
    assert result["ok"] is False
    assert "Preset" in str(result["error"])


def test_validate_rejects_corrupted_content() -> None:
    result = validate_neuroflow_config(content="[invalid yaml: {", kind="preset")
    assert result["ok"] is False
    assert "valid YAML or JSON" in str(result["error"])
