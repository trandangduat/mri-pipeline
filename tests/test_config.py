from __future__ import annotations

from pipeline.config import ExportConfig, StatsVectorConfig

def test_export_config_from_dict_defaults():
    config = ExportConfig.from_dict(None)
    assert config.enabled is True
    assert config.folder == "exports"
    assert config.default_format == ".nii.gz"
    assert config.names == {}
    assert config.formats == {}

def test_export_config_from_dict_custom():
    data = {
        "enabled": False,
        "folder": "custom_exports",
        "default_format": ".nii",
        "names": {"stage1": "custom_name"},
        "formats": {"stage1": ".nii"}
    }
    config = ExportConfig.from_dict(data)
    assert config.enabled is False
    assert config.folder == "custom_exports"
    assert config.default_format == ".nii"
    assert config.names == {"stage1": "custom_name"}
    assert config.formats == {"stage1": ".nii"}

def test_export_config_to_dict():
    config = ExportConfig(enabled=False, folder="out")
    data = config.to_dict()
    assert data["enabled"] is False
    assert data["folder"] == "out"

def test_stats_vector_config_from_dict_defaults():
    config = StatsVectorConfig.from_dict(None)
    assert config.enabled_stats["cortical_thickness"] is False
    assert config.enabled_stats["cortical_volume"] is False
    assert config.enabled_stats["subcortical_volume"] is False
    assert config.atlases["cortical_thickness"] == []

def test_stats_vector_config_from_dict_filters_invalid_atlases():
    data = {
        "enabled_stats": {"cortical_thickness": True},
        "atlases": {
            "cortical_thickness": ["aparc", "invalid_atlas_name", "kong"]
        }
    }
    config = StatsVectorConfig.from_dict(data)
    assert config.enabled_stats["cortical_thickness"] is True
    assert "aparc" in config.atlases["cortical_thickness"]
    assert "kong" in config.atlases["cortical_thickness"]
    # Ensure 'invalid_atlas_name' is filtered out because it's not in STAT_VECTOR_DEFS
    assert "invalid_atlas_name" not in config.atlases["cortical_thickness"]
