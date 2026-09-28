from __future__ import annotations

"""Availability of atlas feature lists and optional atlas asset files.

One source of truth for "is this atlas ready to run under the resource root?".
Built-in FreeSurfer classifiers (aparc) need no pack. Asset-backed surface and
MNI atlases require their feature list plus matching files on disk. Missing
content is a pre-Docker / pre-SSH validation error, not a mid-pipeline surprise.
"""

from pathlib import Path
from pathlib import Path

from pipeline.config import (
    EXTERNAL_MNI_VOLUME_ATLASES,
    KONG2022_CONTENT_PACK_PARCELS,
    MNI_ATLAS_DIR,
    PROJECT_ROOT,
    STAT_VECTOR_DEFS,
    SURFACE_ATLAS_DIR,
)


def kong2022_content_pack_atlas_key(parcels: int) -> str:
    return f"kong2022_{parcels}parcels_17networks"


def kong2022_content_pack_atlas_keys() -> tuple[str, ...]:
    return tuple(kong2022_content_pack_atlas_key(parcels) for parcels in KONG2022_CONTENT_PACK_PARCELS)


def _info_root(resource_root: Path | None = None) -> Path:
    root = Path(resource_root) if resource_root is not None else PROJECT_ROOT
    return root / "info"


def _surface_atlas_dir(resource_root: Path | None = None) -> Path:
    if resource_root is not None:
        return Path(resource_root) / "assets" / "atlases" / "surface"
    return SURFACE_ATLAS_DIR


def _mni_atlas_dir(resource_root: Path | None = None) -> Path:
    if resource_root is not None:
        return Path(resource_root) / "assets" / "atlases" / "mni"
    return MNI_ATLAS_DIR


def feature_list_path(atlas_key: str, *, resource_root: Path | None = None) -> Path | None:
    from pipeline.stats import VECTOR_SPECS

    spec = VECTOR_SPECS.get(atlas_key)
    if not spec:
        return None
    features = spec.get("features")
    if not isinstance(features, str) or not features.strip():
        return None
    return _info_root(resource_root) / features


def surface_atlas_asset_paths(atlas_key: str, *, resource_root: Path | None = None) -> list[Path]:
    from pipeline.registry import THICKNESS_ATLAS_DEFS

    defn = THICKNESS_ATLAS_DEFS.get(atlas_key)
    if not defn:
        return []
    kind = str(defn.get("kind", ""))
    if kind not in ("asset_gcs", "asset_annot"):
        return []
    files = defn.get("files")
    if not isinstance(files, dict):
        return []
    surface_root = _surface_atlas_dir(resource_root)
    return [surface_root / str(rel) for rel in files.values()]


def mni_atlas_asset_paths(atlas_key: str, *, resource_root: Path | None = None) -> list[Path]:
    from pipeline.stats import VECTOR_SPECS

    if atlas_key not in EXTERNAL_MNI_VOLUME_ATLASES:
        return []
    spec = VECTOR_SPECS.get(atlas_key, {})
    mni_root = _mni_atlas_dir(resource_root)
    paths: list[Path] = []
    nifti = spec.get("atlas_nifti")
    if isinstance(nifti, str) and nifti.strip():
        paths.append(mni_root / nifti)
    lut = spec.get("atlas_lut")
    if isinstance(lut, str) and lut.strip():
        paths.append(mni_root / lut)
    return paths


def missing_atlas_content_paths(atlas_key: str, *, resource_root: Path | None = None) -> list[Path]:
    missing: list[Path] = []
    feature_path = feature_list_path(atlas_key, resource_root=resource_root)
    if feature_path is not None and not feature_path.is_file():
        missing.append(feature_path)
    for path in surface_atlas_asset_paths(atlas_key, resource_root=resource_root):
        if not path.is_file():
            missing.append(path)
    for path in mni_atlas_asset_paths(atlas_key, resource_root=resource_root):
        if not path.is_file():
            missing.append(path)
    return missing


def is_atlas_content_available(atlas_key: str, *, resource_root: Path | None = None) -> bool:
    if atlas_key in kong2022_content_pack_atlas_keys():
        return False
    return not missing_atlas_content_paths(atlas_key, resource_root=resource_root)


def unavailable_atlas_message(atlas_key: str, *, resource_root: Path | None = None) -> str:
    if atlas_key in kong2022_content_pack_atlas_keys():
        return (
            f"Atlas '{atlas_key}' is unavailable in this install. "
            "Kong 100/300/400 parcel atlases are not redistributable in the core package; "
            "install a NeuroFlow surface-atlases content pack when available, or choose another atlas."
        )
    missing = missing_atlas_content_paths(atlas_key, resource_root=resource_root)
    if not missing:
        return ""
    names = ", ".join(path.name for path in missing)
    return (
        f"Atlas '{atlas_key}' content is not installed (missing: {names}). "
        "Install the required NeuroFlow content pack, then retry."
    )


def available_atlases_for_stat(stat_key: str, *, resource_root: Path | None = None) -> list[str]:
    allowed = [str(atlas) for atlas in STAT_VECTOR_DEFS.get(stat_key, {}).get("atlases", ())]
    return [atlas for atlas in allowed if is_atlas_content_available(atlas, resource_root=resource_root)]


def atlas_selection_errors(
    stats_vector_config: object | None,
    *,
    resource_root: Path | None = None,
) -> list[str]:
    """Return clear errors for requested atlases that are unknown or missing content."""
    if not isinstance(stats_vector_config, dict):
        return []
    raw_atlases = stats_vector_config.get("atlases", {})
    if not isinstance(raw_atlases, dict):
        return []

    errors: list[str] = []
    seen: set[str] = set()
    for stat_key, atlases in raw_atlases.items():
        if not isinstance(atlases, (list, tuple)):
            continue
        allowed = {str(atlas) for atlas in STAT_VECTOR_DEFS.get(str(stat_key), {}).get("atlases", ())}
        for atlas in atlases:
            atlas_key = str(atlas)
            if atlas_key in seen:
                continue
            seen.add(atlas_key)
            if atlas_key in kong2022_content_pack_atlas_keys():
                errors.append(unavailable_atlas_message(atlas_key, resource_root=resource_root))
                continue
            if atlas_key not in allowed:
                errors.append(
                    f"Atlas '{atlas_key}' is not available for '{stat_key}'. "
                    "Choose an atlas listed in Stats & Atlas Mapping."
                )
                continue
            message = unavailable_atlas_message(atlas_key, resource_root=resource_root)
            if message:
                errors.append(message)
    return errors
