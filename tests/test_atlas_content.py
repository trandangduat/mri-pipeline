from __future__ import annotations

from pathlib import Path

from pipeline.atlas_content import (
    atlas_selection_errors,
    available_atlases_for_stat,
    is_atlas_content_available,
    kong2022_content_pack_atlas_keys,
    unavailable_atlas_message,
)
from pipeline.config import ATLAS_DEFS, CORTICAL_THICKNESS_ATLASES, KONG2022_ATLAS_VARIANTS
from packaging_resources import collect_core_info_datas


def test_kong_variants_only_include_shipped_200_parcel_atlas() -> None:
    assert [parcels for _key, parcels, _networks, _stem in KONG2022_ATLAS_VARIANTS] == [200]
    assert "kong" in ATLAS_DEFS
    assert "kong" in CORTICAL_THICKNESS_ATLASES
    for key in kong2022_content_pack_atlas_keys():
        assert key not in ATLAS_DEFS
        assert key not in CORTICAL_THICKNESS_ATLASES
        assert is_atlas_content_available(key) is False


def test_present_surface_atlases_are_available() -> None:
    assert is_atlas_content_available("aparc") is True
    assert is_atlas_content_available("kong") is True
    assert is_atlas_content_available("aparc_a2009s") is True
    assert "kong" in available_atlases_for_stat("cortical_thickness")
    assert "aparc" in available_atlases_for_stat("cortical_thickness")


def test_content_pack_kong_options_fail_closed_with_actionable_error() -> None:
    key = kong2022_content_pack_atlas_keys()[0]
    message = unavailable_atlas_message(key)
    assert "unavailable" in message.lower()
    assert "content pack" in message.lower()

    errors = atlas_selection_errors(
        {"atlases": {"cortical_thickness": [key, "aparc"]}}
    )
    assert errors
    assert key in errors[0]
    assert "content pack" in errors[0].lower()


def test_unknown_atlas_selection_fails_closed() -> None:
    errors = atlas_selection_errors(
        {"atlases": {"cortical_thickness": ["not_a_real_atlas"]}}
    )
    assert errors
    assert "not_a_real_atlas" in errors[0]


def test_core_packaging_feature_lists_all_exist_on_disk() -> None:
    datas = collect_core_info_datas(Path("."))
    assert datas
    assert all(Path(source).is_file() for source, _destination in datas)
    names = {Path(source).name for source, _destination in datas}
    assert "200Parcels_Kong2022_17Networks_feats.txt" in names
    assert "100Parcels_Kong2022_17Networks_feats.txt" not in names
    assert "300Parcels_Kong2022_17Networks_feats.txt" not in names
    assert "400Parcels_Kong2022_17Networks_feats.txt" not in names
