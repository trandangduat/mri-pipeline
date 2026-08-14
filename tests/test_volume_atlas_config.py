from __future__ import annotations

import csv
from pathlib import Path

from pipeline.config import (
    CORTICAL_VOLUME_ATLASES,
    SUBCORTICAL_VOLUME_ATLASES,
    STAT_VECTOR_DEFS,
    StatsVectorConfig,
)


def test_volume_atlas_keys_in_stat_vector_defs() -> None:
    sub_atlases = set(STAT_VECTOR_DEFS["subcortical_volume"]["atlases"])
    cort_atlases = set(STAT_VECTOR_DEFS["cortical_volume"]["atlases"])

    assert "freesurfer_aseg" in sub_atlases
    assert "fastsurfer_dkt" in sub_atlases
    assert "cat12_neuromorphometrics" in sub_atlases
    assert "cat12_ibsr" in sub_atlases
    assert "cat12_cobra" in sub_atlases

    assert "freesurfer_aparc" in cort_atlases
    assert "fastsurfer_dkt" in cort_atlases
    assert "cat12_schaefer2018_200parcels_17networks" in cort_atlases
    assert "cat12_aal3" in cort_atlases


def test_stats_vector_config_accepts_new_volume_atlases() -> None:
    data = {
        "enabled_stats": {"subcortical_volume": True, "cortical_volume": True, "cortical_thickness": False},
        "atlases": {
            "subcortical_volume": ["cat12_neuromorphometrics", "freesurfer_aseg"],
            "cortical_volume": ["freesurfer_aparc", "cat12_schaefer2018_200parcels_17networks"],
            "cortical_thickness": [],
        },
    }
    config = StatsVectorConfig.from_dict(data)
    assert "cat12_neuromorphometrics" in config.atlases["subcortical_volume"]
    assert "freesurfer_aseg" in config.atlases["subcortical_volume"]
    assert "freesurfer_aparc" in config.atlases["cortical_volume"]
    assert "cat12_schaefer2018_200parcels_17networks" in config.atlases["cortical_volume"]


def test_stats_vector_config_rejects_unknown_volume_atlases() -> None:
    data = {
        "enabled_stats": {"subcortical_volume": True, "cortical_volume": False, "cortical_thickness": False},
        "atlases": {
            "subcortical_volume": ["freesurfer_aseg", "nonexistent_atlas", "another_bad_one"],
            "cortical_volume": [],
            "cortical_thickness": [],
        },
    }
    config = StatsVectorConfig.from_dict(data)
    assert "freesurfer_aseg" in config.atlases["subcortical_volume"]
    assert "nonexistent_atlas" not in config.atlases["subcortical_volume"]
    assert "another_bad_one" not in config.atlases["subcortical_volume"]


def test_stats_vector_config_from_dict_defaults_volume_atlas_lists() -> None:
    config = StatsVectorConfig.from_dict(None)
    assert config.atlases["cortical_volume"] == []
    assert config.atlases["subcortical_volume"] == []


def test_subcortical_volume_atlas_tuple_contains_expected_keys() -> None:
    expected = {
        "freesurfer_aseg",
        "fastsurfer_dkt",
        "cat12_neuromorphometrics",
        "cat12_ibsr",
        "cat12_cobra",
        "cat12_hammers",
        "cat12_suit",
        "cat12_thalamic_nuclei",
        "cat12_thalamus",
    }
    assert expected <= set(SUBCORTICAL_VOLUME_ATLASES)


def test_cortical_volume_atlas_tuple_contains_expected_keys() -> None:
    expected = {
        "freesurfer_aparc",
        "fastsurfer_dkt",
        "cat12_schaefer2018_100parcels_17networks",
        "cat12_schaefer2018_200parcels_17networks",
        "cat12_schaefer2018_400parcels_17networks",
        "cat12_schaefer2018_600parcels_17networks",
        "cat12_aal3",
        "cat12_anatomy3",
        "cat12_hammers",
        "cat12_julichbrain3",
        "cat12_lpba40",
        "cat12_mori",
    }
    assert expected <= set(CORTICAL_VOLUME_ATLASES)


def test_freesurfer_aseg_label_stable() -> None:
    from pipeline.config import ATLAS_DEFS

    assert ATLAS_DEFS["freesurfer_aseg"] == "FreeSurfer Aseg Atlas"
