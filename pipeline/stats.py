from __future__ import annotations

import csv
import re
import logging
from pathlib import Path
from dataclasses import dataclass

from .config import (
    ATLAS_SHORT_NAMES,
    BatchImageResult,
    EXTERNAL_MNI_VOLUME_ATLASES,
    KONG2022_ATLAS_VARIANTS,
    PROJECT_ROOT,
    SCHAEFER2018_ATLAS_VARIANTS,
    STAT_VECTOR_DEFS,
    StatsVectorConfig,
)
from .discovery import build_subject_id_map, _derive_subject_id

VECTOR_SPECS = {
    "subcortical_volume": {
        "column": "subcortical_volume",
        "features": "subcortical_volume_feats.txt",
        "value": "volume_mm3",
    },
    "cortical_volume": {
        "column": "cortical_volume",
        "features": "cortical_volume_feats.txt",
        "value": "volume_mm3",
    },
    "freesurfer_aseg": {
        "column": "freesurfer_aseg_subcortical_volume",
        "features": "freesurfer_aseg_subcortical_volume_feats.txt",
        "value": "volume_mm3",
    },
    "freesurfer_aparc": {
        "column": "freesurfer_aparc_cortical_volume",
        "features": "freesurfer_aparc_cortical_volume_feats.txt",
        "value": "volume_mm3",
    },
    "fastsurfer_dkt": {
        "column": "fastsurfer_dkt_volume",
        "features": "fastsurfer_dkt_volume_feats.txt",
        "value": "volume_mm3",
    },
    "cat12_neuromorphometrics": {
        "column": "cat12_neuromorphometrics_volume",
        "features": "cat12_neuromorphometrics_volume_feats.txt",
        "value": "volume",
    },
    "cat12_schaefer2018_100parcels_17networks": {
        "column": "cat12_schaefer2018_100parcels_17networks_cortical_volume",
        "features": "cat12_schaefer2018_100parcels_17networks_cortical_volume_feats.txt",
        "value": "volume",
    },
    "cat12_schaefer2018_200parcels_17networks": {
        "column": "cat12_schaefer2018_200parcels_17networks_cortical_volume",
        "features": "cat12_schaefer2018_200parcels_17networks_cortical_volume_feats.txt",
        "value": "volume",
    },
    "cat12_schaefer2018_400parcels_17networks": {
        "column": "cat12_schaefer2018_400parcels_17networks_cortical_volume",
        "features": "cat12_schaefer2018_400parcels_17networks_cortical_volume_feats.txt",
        "value": "volume",
    },
    "cat12_schaefer2018_600parcels_17networks": {
        "column": "cat12_schaefer2018_600parcels_17networks_cortical_volume",
        "features": "cat12_schaefer2018_600parcels_17networks_cortical_volume_feats.txt",
        "value": "volume",
    },
    "cat12_aal3": {
        "column": "cat12_aal3_cortical_volume",
        "features": "cat12_aal3_cortical_volume_feats.txt",
        "value": "volume",
    },
    "cat12_anatomy3": {
        "column": "cat12_anatomy3_cortical_volume",
        "features": "cat12_anatomy3_cortical_volume_feats.txt",
        "value": "volume",
    },
    "cat12_cobra": {
        "column": "cat12_cobra_volume",
        "features": "cat12_cobra_volume_feats.txt",
        "value": "volume",
    },
    "cat12_hammers": {
        "column": "cat12_hammers_volume",
        "features": "cat12_hammers_volume_feats.txt",
        "value": "volume",
    },
    "cat12_ibsr": {
        "column": "cat12_ibsr_volume",
        "features": "cat12_ibsr_volume_feats.txt",
        "value": "volume",
    },
    "cat12_julichbrain3": {
        "column": "cat12_julichbrain3_cortical_volume",
        "features": "cat12_julichbrain3_cortical_volume_feats.txt",
        "value": "volume",
    },
    "cat12_lpba40": {
        "column": "cat12_lpba40_cortical_volume",
        "features": "cat12_lpba40_cortical_volume_feats.txt",
        "value": "volume",
    },
    "cat12_mori": {
        "column": "cat12_mori_cortical_volume",
        "features": "cat12_mori_cortical_volume_feats.txt",
        "value": "volume",
    },
    "cat12_suit": {
        "column": "cat12_suit_volume",
        "features": "cat12_suit_volume_feats.txt",
        "value": "volume",
    },
    "cat12_thalamic_nuclei": {
        "column": "cat12_thalamic_nuclei_volume",
        "features": "cat12_thalamic_nuclei_volume_feats.txt",
        "value": "volume",
    },
    "cat12_thalamus": {
        "column": "cat12_thalamus_volume",
        "features": "cat12_thalamus_volume_feats.txt",
        "value": "volume",
    },
    "mni_sclimbic": {
        "column": "mni_sclimbic_subcortical_volume",
        "features": "mni_sclimbic_subcortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_projection": True,
        "template_space": "mni152",
        "atlas_volume": "$FREESURFER_HOME/average/sclimbic.t1.nii.gz",
        "stats_basename": "mni_sclimbic.stats",
    },
    "harvard_oxford_subcortical": {
        "column": "harvard_oxford_subcortical_volume",
        "features": "harvard_oxford_subcortical_subcortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_projection": True,
        "template_space": "mni152",
        "atlas_nifti": "HarvardOxford-subl-maxprob-thr0-1mm.nii.gz",
        "atlas_lut": "harvard_oxford_sub_LUT.txt",
        "stats_basename": "harvard_oxford_sub.stats",
    },
    "harvard_oxford_cortical": {
        "column": "harvard_oxford_cortical_volume",
        "features": "harvard_oxford_cortical_cortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_projection": True,
        "template_space": "mni152",
        "atlas_nifti": "HarvardOxford-cortl-maxprob-thr0-1mm.nii.gz",
        "atlas_lut": "harvard_oxford_cort_LUT.txt",
        "stats_basename": "harvard_oxford_cort.stats",
    },
    "cerebra": {
        "column": "cerebra_subcortical_volume",
        "features": "cerebra_subcortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_projection": True,
        "template_space": "mni152",
        "stats_basename": "cerebra.stats",
    },
    "brainnetome246": {
        "column": "brainnetome246_cortical_volume",
        "features": "brainnetome246_cortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_projection": True,
        "template_space": "mni152",
        "atlas_nifti": "BN_Atlas_246_1mm.nii.gz",
        "atlas_lut": "BN_Atlas_246_LUT.txt",
        "stats_basename": "brainnetome246.stats",
    },
    "pauli_2017": {
        "column": "pauli_2017_subcortical_volume",
        "features": "pauli_2017_subcortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_projection": True,
        "template_space": "mni152",
        "atlas_nifti": "pauli_2017_labels.nii.gz",
        "atlas_lut": "pauli_2017_LUT.txt",
        "stats_basename": "pauli_2017.stats",
    },
    "juelich": {
        "column": "juelich_cortical_volume",
        "features": "juelich_cortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_projection": True,
        "template_space": "mni152",
        "atlas_nifti": "juelich_maxprob-thr0-1mm.nii.gz",
        "atlas_lut": "juelich_LUT.txt",
        "stats_basename": "juelich.stats",
    },
    "aal": {
        "column": "aal_cortical_volume",
        "features": "aal_cortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_projection": True,
        "template_space": "mni152",
        "atlas_nifti": "aal.nii.gz",
        "atlas_lut": "aal_LUT.txt",
        "stats_basename": "aal.stats",
    },
    "schaefer2018_100_7": {
        "column": "schaefer2018_100_7_cortical_volume",
        "features": "schaefer2018_100_7_cortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_projection": True,
        "template_space": "mni152",
        "atlas_nifti": "schaefer2018_100_7.nii.gz",
        "atlas_lut": "schaefer2018_100_7_LUT.txt",
        "stats_basename": "schaefer2018_100_7.stats",
    },
    "tian_subcortex": {
        "column": "tian_subcortex_subcortical_volume",
        "features": "tian_subcortex_subcortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_projection": True,
        "template_space": "mni152",
        "stats_basename": "tian_subcortex.stats",
    },
    "jhu_icbm_dti81": {
        "column": "jhu_icbm_dti81_volume",
        "features": "jhu_icbm_dti81_cortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_projection": True,
        "template_space": "mni152",
        "stats_basename": "jhu_icbm_dti81.stats",
    },
    "suit_cerebellum": {
        "column": "suit_cerebellum_volume",
        "features": "suit_cerebellum_cortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_projection": True,
        "template_space": "mni152",
        "stats_basename": "suit_cerebellum.stats",
    },
    "fs_hippo_amygdala": {
        "column": "fs_hippo_amygdala_subcortical_volume",
        "features": "fs_hippo_amygdala_subcortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_native_segmentation": True,
    },
    "fs_brainstem": {
        "column": "fs_brainstem_subcortical_volume",
        "features": "fs_brainstem_subcortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_native_segmentation": True,
    },
    "fs_thalamic_nuclei": {
        "column": "fs_thalamic_nuclei_subcortical_volume",
        "features": "fs_thalamic_nuclei_subcortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_native_segmentation": True,
    },
    "fs_sclimbic": {
        "column": "fs_sclimbic_subcortical_volume",
        "features": "fs_sclimbic_subcortical_volume_feats.txt",
        "value": "volume_mm3",
        "requires_native_segmentation": True,
    },
    "aparc": {
        "column": "aparc_cortical_thickness",
        "features": "aparc_cortical_thickness_feats.txt",
        "value": "thickness_mm",
        "stats_stem": "aparc",
    },
    "aparc_a2009s": {
        "column": "aparc_a2009s_cortical_thickness",
        "features": "aparc_a2009s_cortical_thickness_feats.txt",
        "value": "thickness_mm",
        "stats_stem": "aparc.a2009s",
    },
    "yale": {
        "column": "YBA_696parcels",
        "features": "YBA_696parcels_feats.txt",
        "value": "thickness_mm",
        "stats_stem": "YBA_696parcels",
    },
    **{
        key: {
            "column": stem,
            "features": f"{stem}_feats.txt",
            "value": "thickness_mm",
            "stats_stem": stem,
        }
        for key, _parcels, _networks, stem in KONG2022_ATLAS_VARIANTS
    },
    **{
        key: {
            "column": stem,
            "features": f"{stem}_feats.txt",
            "value": "thickness_mm",
            "stats_stem": stem,
        }
        for key, _parcels, _networks, stem in SCHAEFER2018_ATLAS_VARIANTS
    },
}


log = logging.getLogger(__name__)

@dataclass
class StatsResult:
    files: list[str]
    warnings: list[str]

def _read_tsv_dict_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, 'r', encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f, delimiter='\t'))


def _sanitize_vector_feature(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe.strip("_") or "feature"

def _stats_source_candidates(stats_dir: Path, stat: str, atlas: str = "") -> list[Path]:
    if stat == "subcortical_volume" and not atlas:
        return [stats_dir / "subcortical_volume.tsv"]
    if stat == "cortical_volume" and not atlas:
        return [stats_dir / "cortical_volume.tsv"]
    if not atlas:
        return []
    if stat == "cortical_volume":
        return [
            stats_dir / f"{atlas}_cortical_volume.tsv",
            stats_dir / f"cortical_volume_{atlas}.tsv",
            stats_dir / f"{atlas}_volume.tsv",
        ]
    if stat == "cortical_thickness":
        return [
            stats_dir / f"{atlas}_cortical_thickness.tsv",
            stats_dir / f"cortical_thickness_{atlas}.tsv",
            stats_dir / f"{atlas}_thickness.tsv",
        ]
    if stat == "subcortical_volume":
        return [
            stats_dir / f"{atlas}_subcortical_volume.tsv",
            stats_dir / f"subcortical_volume_{atlas}.tsv",
            stats_dir / f"{atlas}_volume.tsv",
        ]
    return []

def _norm_feature(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")

def _load_vector_features(filename: str) -> list[str]:
    path = PROJECT_ROOT / "info" / filename
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines() if line.strip()]


def _atlas_column_name(vector_type: str, atlas: str, is_default: bool) -> str:
    if is_default:
        return vector_type
    short_name = ATLAS_SHORT_NAMES.get(atlas) or atlas
    return f"{vector_type}_{short_name}"

def _as_number(value: str | float | int | None) -> float | str:
    if value is None:
        return "NA"
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().strip("'").strip('"')
    if not text or text.upper() in {"NA", "NAN", "NONE"}:
        return "NA"
    try:
        return float(text)
    except ValueError:
        return "NA"

def _vector_list_string(values: list[str | float | int | None]) -> str:
    return repr([_as_number(value) for value in values])

def _parse_freesurfer_stats_table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    headers: list[str] = []
    rows: list[dict[str, str]] = []
    if not path.exists():
        return headers, rows
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# ColHeaders"):
            headers = line.split()[2:]
            continue
        if line.startswith("#") or not headers:
            continue
        parts = line.split()
        if len(parts) >= len(headers):
            rows.append(dict(zip(headers, parts[: len(headers)])))
    return headers, rows

def _parse_freesurfer_measures(path: Path) -> dict[str, str]:
    measures: dict[str, str] = {}
    if not path.exists():
        return measures
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line.startswith("# Measure "):
            continue
        parts = [part.strip() for part in line[len("# Measure "):].split(",")]
        if len(parts) < 2:
            continue
        numeric = next((part for part in reversed(parts) if re.fullmatch(r"[-+]?\d+(\.\d+)?([eE][-+]?\d+)?", part)), "")
        if not numeric:
            continue
        for key in parts[:2]:
            if key:
                measures[key] = numeric
                measures[_norm_feature(key)] = numeric
    return measures

def _put_value(values: dict[str, str], key: str, value: str) -> None:
    if not key:
        return
    values[key] = value
    values[_norm_feature(key)] = value

def _copy_value_alias(values: dict[str, str], target: str, *sources: str) -> None:
    if values.get(target) or values.get(_norm_feature(target)):
        return
    for source in sources:
        value = values.get(source) or values.get(_norm_feature(source))
        if value:
            _put_value(values, target, value)
            return

def _sum_value_alias(values: dict[str, str], target: str, *sources: str) -> None:
    if values.get(target) or values.get(_norm_feature(target)):
        return
    total = 0.0
    for source in sources:
        value = values.get(source) or values.get(_norm_feature(source))
        number = _as_number(value)
        if number == "NA":
            return
        total += float(number)
    _put_value(values, target, str(round(total, 6)))

def _read_subcortical_values(stats_dir: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in [stats_dir / "aseg.stats", stats_dir / "aparc.DKTatlas+aseg.deep.stats", stats_dir / "aseg+DKT.stats"]:
        _headers, rows = _parse_freesurfer_stats_table(path)
        for row in rows:
            name = row.get("StructName", "")
            volume = row.get("Volume_mm3") or row.get("Volume") or row.get("NVoxels")
            if name and volume:
                _put_value(values, name, volume)
        for key, value in _parse_freesurfer_measures(path).items():
            _put_value(values, key, value)

    tsv = stats_dir / "subcortical_volume.tsv"
    if tsv.exists():
        with open(tsv, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                _put_value(values, row.get("structure", ""), row.get("volume_mm3", ""))

    for row in _read_tsv_dict_rows(stats_dir / "cortical_volume.tsv"):
                region = row.get("region", "")
                hemi = row.get("hemisphere", "")
                volume = row.get("volume_mm3", "")
                if region == "cerebellum cortex" and hemi == "lh":
                    _put_value(values, "Left-Cerebellum-Cortex", volume)
                elif region == "cerebellum cortex" and hemi == "rh":
                    _put_value(values, "Right-Cerebellum-Cortex", volume)
                elif region == "cerebral cortex" and hemi == "lh":
                    _put_value(values, "lhCortexVol", volume)
                elif region == "cerebral cortex" and hemi == "rh":
                    _put_value(values, "rhCortexVol", volume)

    _copy_value_alias(values, "Left-Inf-Lat-Vent", "left inferior lateral ventricle")
    _copy_value_alias(values, "Right-Inf-Lat-Vent", "right inferior lateral ventricle")
    _copy_value_alias(values, "Left-VentralDC", "left ventral DC")
    _copy_value_alias(values, "Right-VentralDC", "right ventral DC")
    _copy_value_alias(values, "lhCerebralWhiteMatterVol", "left cerebral white matter")
    _copy_value_alias(values, "rhCerebralWhiteMatterVol", "right cerebral white matter")
    _copy_value_alias(values, "EstimatedTotalIntraCranialVol", "total intracranial")
    _sum_value_alias(values, "CortexVol", "lhCortexVol", "rhCortexVol")
    _sum_value_alias(values, "CerebralWhiteMatterVol", "lhCerebralWhiteMatterVol", "rhCerebralWhiteMatterVol")
    return values

def _cortical_feature_key(region: str, hemi: str = "") -> str:
    raw = (region or "").strip()
    lower = raw.lower()
    for prefix, parsed_hemi in (("ctx-lh-", "lh"), ("ctx-rh-", "rh"), ("ctx_lh_", "lh"), ("ctx_rh_", "rh")):
        if lower.startswith(prefix):
            return f"{parsed_hemi}_{raw[len(prefix):]}"
    if hemi in {"lh", "rh"}:
        return f"{hemi}_{raw}"
    if lower.startswith("left "):
        return f"lh_{raw[5:]}"
    if lower.startswith("right "):
        return f"rh_{raw[6:]}"
    return ""

def _read_cortical_volume_values(stats_dir: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in [stats_dir / "aparc.DKTatlas+aseg.deep.stats", stats_dir / "aseg+DKT.stats", stats_dir / "aseg+DKT.VINN.stats"]:
        _headers, rows = _parse_freesurfer_stats_table(path)
        for row in rows:
            name = row.get("StructName", "")
            volume = row.get("GrayVol") or row.get("Volume_mm3") or row.get("Volume")
            key = _cortical_feature_key(name)
            if key and volume:
                _put_value(values, key, volume)

    for hemi in ("lh", "rh"):
        for path in [stats_dir / f"{hemi}.aparc.stats", stats_dir / f"{hemi}.aparc.DKTatlas.stats"]:
            _headers, rows = _parse_freesurfer_stats_table(path)
            for row in rows:
                name = row.get("StructName", "")
                volume = row.get("GrayVol") or row.get("Volume_mm3") or row.get("Volume")
                if name and volume:
                    _put_value(values, _cortical_feature_key(name, hemi), volume)

    for row in _read_tsv_dict_rows(stats_dir / "cortical_volume.tsv"):
        hemi = row.get("hemisphere", "")
        region = row.get("region", "")
        key = _cortical_feature_key(region, hemi)
        if key:
            _put_value(values, key, row.get("volume_mm3", ""))
    return values


def _read_freesurfer_aparc_cortical_values(stats_dir: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for hemi in ("lh", "rh"):
        for path in [stats_dir / f"{hemi}.aparc.stats", stats_dir / f"{hemi}.aparc.DKTatlas.stats",
                     stats_dir / f"{hemi}.aparc.DKTatlas.mapped.stats"]:
            _headers, rows = _parse_freesurfer_stats_table(path)
            for row in rows:
                name = row.get("StructName", "")
                volume = row.get("GrayVol") or row.get("Volume_mm3") or row.get("Volume")
                if name and volume:
                    _put_value(values, _cortical_feature_key(name, hemi), volume)

    for row in _read_tsv_dict_rows(stats_dir / "cortical_volume.tsv"):
        hemi = row.get("hemisphere", "")
        region = row.get("region", "")
        key = _cortical_feature_key(region, hemi)
        if key:
            _put_value(values, key, row.get("volume_mm3", ""))
    return values


def _read_fastsurfer_dkt_values(stats_dir: Path, stat: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in [stats_dir / "aparc.DKTatlas+aseg.deep.stats", stats_dir / "aseg+DKT.stats",
                 stats_dir / "aseg+DKT.VINN.stats"]:
        _headers, rows = _parse_freesurfer_stats_table(path)
        for row in rows:
            name = row.get("StructName", "")
            volume = row.get("GrayVol") or row.get("Volume_mm3") or row.get("Volume")
            if not name or not volume:
                continue
            cortical = _cortical_feature_key(name)
            if cortical:
                if stat == "cortical_volume":
                    _put_value(values, cortical, volume)
            else:
                if stat == "subcortical_volume":
                    _put_value(values, name, volume)
        for key, value in _parse_freesurfer_measures(path).items():
            if stat == "subcortical_volume":
                _put_value(values, key, value)

    if stat == "subcortical_volume":
        tsv = stats_dir / "subcortical_volume.tsv"
        if tsv.exists():
            with open(tsv, "r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f, delimiter="\t"):
                    _put_value(values, row.get("structure", ""), row.get("volume_mm3", ""))
    elif stat == "cortical_volume":
        for hemi in ("lh", "rh"):
            for path in [stats_dir / f"{hemi}.aparc.DKTatlas.mapped.stats",
                         stats_dir / f"{hemi}.aparc.DKTatlas.stats"]:
                _headers, rows = _parse_freesurfer_stats_table(path)
                for row in rows:
                    name = row.get("StructName", "")
                    volume = row.get("GrayVol") or row.get("Volume_mm3") or row.get("Volume")
                    if name and volume:
                        _put_value(values, _cortical_feature_key(name, hemi), volume)
        for row in _read_tsv_dict_rows(stats_dir / "cortical_volume.tsv"):
            hemi = row.get("hemisphere", "")
            region = row.get("region", "")
            key = _cortical_feature_key(region, hemi)
            if key:
                _put_value(values, key, row.get("volume_mm3", ""))
    return values


def _read_cat12_atlas_values(stats_dir: Path, atlas: str, stat: str) -> dict[str, str]:
    values: dict[str, str] = {}
    atlas_tsv = stats_dir / f"cat12_{stat}_by_atlas.tsv"
    if not atlas_tsv.exists():
        atlas_tsv = stats_dir / "cat12_subcortical_volume_by_atlas.tsv" if stat == "subcortical_volume" else stats_dir / "cat12_cortical_volume_by_atlas.tsv"
    if atlas_tsv.exists():
        for row in _read_tsv_dict_rows(atlas_tsv):
            row_atlas = row.get("atlas", "")
            if row_atlas != atlas:
                continue
            if stat == "subcortical_volume":
                structure = row.get("structure", "")
                volume = row.get("volume", "")
                if structure and volume:
                    _put_value(values, structure, volume)
            else:
                region = row.get("region", "")
                hemi = row.get("hemisphere", "both")
                volume = row.get("volume", "")
                if region and volume:
                    key = _cortical_feature_key(region, hemi)
                    if key:
                        _put_value(values, key, volume)
                    else:
                        _put_value(values, region, volume)

    if not values:
        for row in _read_tsv_dict_rows(stats_dir / "subcortical_volume.tsv"):
            structure = row.get("structure", "")
            volume = row.get("volume_mm3", "")
            if structure and volume:
                _put_value(values, structure, volume)
        for row in _read_tsv_dict_rows(stats_dir / "cortical_volume.tsv"):
            hemi = row.get("hemisphere", "")
            region = row.get("region", "")
            volume = row.get("volume_mm3", "")
            key = _cortical_feature_key(region, hemi)
            if key and volume:
                _put_value(values, key, volume)
    return values


def _read_projected_atlas_values(stats_dir: Path, atlas: str) -> dict[str, str]:
    return _read_mni_atlas_values(stats_dir, atlas)


def _read_mni_atlas_values(stats_dir: Path, atlas: str) -> dict[str, str]:
    values: dict[str, str] = {}
    spec = VECTOR_SPECS.get(atlas, {})
    mapping_dir = stats_dir / "atlas_mapping"
    stats_basename = str(spec.get("stats_basename") or f"{atlas}.stats")
    candidates = [
        mapping_dir / stats_basename,
        stats_dir / stats_basename,
        mapping_dir / f"{atlas}.stats",
        stats_dir / f"{atlas}.stats",
    ]
    stats_file = next((path for path in candidates if path.exists()), None)
    if not stats_file:
        return values
    _headers, rows = _parse_freesurfer_stats_table(stats_file)
    for row in rows:
        name = row.get("StructName", "")
        volume = row.get("Volume_mm3") or row.get("Volume") or row.get("NVoxels")
        if name and name != "Unknown" and volume:
            _put_value(values, name, volume)
    return values

def _atlas_stats_candidates(stats_dir: Path, atlas: str, hemi: str) -> list[Path]:
    stem = str(VECTOR_SPECS[atlas].get("stats_stem", atlas))
    candidates = [
        stats_dir / f"{hemi}.{stem}.stats",
        stats_dir / f"{hemi}_{stem}.stats",
        stats_dir / f"{hemi}.{stem.lower()}.stats",
        stats_dir / f"{hemi}_{stem.lower()}.stats",
    ]
    if atlas == "aparc":
        candidates.extend(
            [
                stats_dir / f"{hemi}.aparc.DKTatlas.mapped.stats",
                stats_dir / f"{hemi}.aparc.dktatlas.mapped.stats",
            ]
        )
    return candidates

def _read_atlas_thickness_values(stats_dir: Path, atlas: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for hemi in ("lh", "rh"):
        hemi_upper = hemi.upper()
        for path in _atlas_stats_candidates(stats_dir, atlas, hemi):
            _headers, rows = _parse_freesurfer_stats_table(path)
            for row in rows:
                name = row.get("StructName", "")
                thick = row.get("ThickAvg") or row.get("MeanThickness") or row.get("thickness_mm")
                if not name or not thick:
                    continue
                for key in (name, f"{hemi}_{name}", f"{hemi_upper}_{name}"):
                    _put_value(values, key, thick)
    return values

def _values_for_vector(stats_dir: Path, stat: str, atlas: str = "") -> dict[str, str]:
    spec = VECTOR_SPECS.get(atlas, {})
    if spec.get("requires_projection") or atlas in EXTERNAL_MNI_VOLUME_ATLASES:
        return _read_mni_atlas_values(stats_dir, atlas)
    if stat == "subcortical_volume":
        if atlas == "freesurfer_aseg" or not atlas:
            return _read_subcortical_values(stats_dir)
        if atlas == "fastsurfer_dkt":
            return _read_fastsurfer_dkt_values(stats_dir, stat)
        if atlas.startswith("cat12_"):
            return _read_cat12_atlas_values(stats_dir, atlas, stat)
        return _read_subcortical_values(stats_dir)
    if stat == "cortical_volume":
        if atlas == "freesurfer_aparc":
            return _read_freesurfer_aparc_cortical_values(stats_dir)
        if atlas == "fastsurfer_dkt":
            return _read_fastsurfer_dkt_values(stats_dir, stat)
        if atlas.startswith("cat12_"):
            return _read_cat12_atlas_values(stats_dir, atlas, stat)
        if not atlas:
            return _read_cortical_volume_values(stats_dir)
        return _read_cortical_volume_values(stats_dir)
    if stat == "cortical_thickness":
        return _read_atlas_thickness_values(stats_dir, atlas) if atlas else {}
    return {}

def _lookup_feature(values: dict[str, str], feature: str) -> str:
    if feature in values:
        return values[feature]
    norm = _norm_feature(feature)
    if norm in values:
        return values[norm]
    return "NA"

def _write_standard_vector(
    vectors_dir: Path,
    subject_id: str,
    column: str,
    features: list[str],
    values_by_feature: dict[str, str],
) -> tuple[list[str], str, int]:
    vector_values = [_lookup_feature(values_by_feature, feature) for feature in features]
    missing = sum(1 for value in vector_values if _as_number(value) == "NA")
    list_text = _vector_list_string(vector_values)
    vectors_dir.mkdir(parents=True, exist_ok=True)
    txt_path = vectors_dir / f"{column}.txt"
    txt_path.write_text(list_text + "\n", encoding="utf-8")
    feature_path = vectors_dir / f"{column}_features.tsv"
    with open(feature_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["index", "feature", "value"])
        for idx, (feature, value) in enumerate(zip(features, vector_values), start=1):
            writer.writerow([idx, feature, _as_number(value)])
    return [str(txt_path), str(feature_path)], list_text, missing

def _write_vector_from_long_tsv(src: Path, dst: Path, subject_id: str, value_column: str) -> tuple[bool, str]:
    delimiter = "\t" if src.suffix.lower() == ".tsv" else ","
    with open(src, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter=delimiter))
    if not rows:
        return False, f"empty stats file: {src.name}"

    columns = rows[0].keys()
    value_candidates = [value_column, "value", "mean", "thickness", "volume", "volume_mm3"]
    value_key = next((col for col in value_candidates if col in columns), "")
    if not value_key:
        return False, f"missing value column in {src.name}; expected one of {', '.join(value_candidates)}"

    feature_keys = [col for col in columns if col not in {"subject", "tool", value_key}]
    if not feature_keys:
        return False, f"missing feature columns in {src.name}"

    vector: dict[str, str] = {}
    for row in rows:
        parts = [row.get(key, "") for key in feature_keys if row.get(key, "")]
        feature = _sanitize_vector_feature("__".join(parts))
        if feature in vector:
            suffix = 2
            base = feature
            while f"{base}_{suffix}" in vector:
                suffix += 1
            feature = f"{base}_{suffix}"
        vector[feature] = row.get(value_key, "")

    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["subject", *vector.keys()])
        writer.writerow([subject_id, *vector.values()])
    return True, ""

class StatsGenerator:
    def __init__(self, config: StatsVectorConfig):
        self.config = config

    def generate(self, subject_dir: str, subject_id: str) -> StatsResult:
        config = self.config
        generated: list[str] = []
        warnings: list[str] = []
        stats_dir = Path(subject_dir) / "stats"
        vectors_dir = stats_dir / "vectors"
        vector_columns: dict[str, str] = {}

        requested: list[tuple[str, str, str, bool]] = []
        if config.enabled_stats.get("subcortical_volume"):
            requested.append(("subcortical_volume", "freesurfer_aseg", "freesurfer_aseg", True))
            for atlas in config.atlases.get("subcortical_volume", []):
                if atlas == "freesurfer_aseg":
                    continue
                requested.append(("subcortical_volume", atlas, atlas, False))
        if config.enabled_stats.get("cortical_volume"):
            requested.append(("cortical_volume", "freesurfer_aparc", "freesurfer_aparc", True))
            for atlas in config.atlases.get("cortical_volume", []):
                if atlas == "freesurfer_aparc":
                    continue
                requested.append(("cortical_volume", atlas, atlas, False))
        if config.enabled_stats.get("cortical_thickness"):
            atlases = list(config.atlases.get("cortical_thickness", []))
            if not atlases:
                warnings.append("cortical_thickness: no atlas selected")
            for index, atlas in enumerate(atlases):
                requested.append(("cortical_thickness", atlas, atlas, index == 0))

        for stat, atlas, spec_key, is_default in requested:
            spec = VECTOR_SPECS.get(spec_key)
            if not spec:
                warnings.append(f"{stat}:{atlas or 'default'}: no vector spec")
                continue
            column = _atlas_column_name(stat, atlas, is_default)
            features = _load_vector_features(str(spec["features"]))
            if not features:
                warnings.append(f"{column}: missing feature list info/{spec['features']}")
                continue
            values = _values_for_vector(stats_dir, stat, atlas)
            paths, list_text, missing = _write_standard_vector(vectors_dir, subject_id, column, features, values)
            generated.extend(paths)
            vector_columns[column] = list_text
            if missing:
                warnings.append(f"{column}: {missing}/{len(features)} features missing; filled with NA")

        if vector_columns:
            csv_path = vectors_dir / "stats_vectors.csv"
            columns = ["subject", *vector_columns.keys()]
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerow([subject_id, *[vector_columns[col] for col in vector_columns]])
            generated.append(str(csv_path))
            manifest_path = vectors_dir / "stats_vectors_manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                import json
                json.dump(
                    {
                        "subject": subject_id,
                        "columns": list(vector_columns.keys()),
                        "feature_files": {key: str(value["features"]) for key, value in VECTOR_SPECS.items()},
                        "format": "CSV cells contain Python-list-style vectors aligned 1:1 with the corresponding *_feats.txt file.",
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
            generated.append(str(manifest_path))
        return StatsResult(files=generated, warnings=warnings)

def _requested_vector_feature_map(config: StatsVectorConfig) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    defaults = {"subcortical_volume": "freesurfer_aseg", "cortical_volume": "freesurfer_aparc"}
    for stat in ["subcortical_volume", "cortical_volume", "cortical_thickness"]:
        if not config.enabled_stats.get(stat):
            continue
        if stat in defaults:
            spec = VECTOR_SPECS.get(defaults[stat])
            if spec:
                out[stat] = _load_vector_features(str(spec["features"]))
            for atlas in config.atlases.get(stat, []):
                if atlas == defaults[stat]:
                    continue
                spec = VECTOR_SPECS.get(atlas)
                if not spec:
                    continue
                out[_atlas_column_name(stat, atlas, False)] = _load_vector_features(str(spec["features"]))
            continue
        for index, atlas in enumerate(config.atlases.get(stat, [])):
            spec = VECTOR_SPECS.get(atlas)
            if not spec:
                continue
            out[_atlas_column_name(stat, atlas, index == 0)] = _load_vector_features(str(spec["features"]))
    return out

