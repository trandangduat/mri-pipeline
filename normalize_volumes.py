#!/usr/bin/env python3

import argparse
import csv
import math
import os
import re
import struct
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import xml.etree.ElementTree as ET


SUBCORTICAL_STRUCTURES = [
    "total intracranial", "left cerebral white matter", "left lateral ventricle",
    "left inferior lateral ventricle", "left cerebellum white matter", "left cerebellum cortex",
    "left thalamus", "left caudate", "left putamen", "left pallidum",
    "3rd ventricle", "4th ventricle", "brain-stem", "left hippocampus",
    "left amygdala", "csf", "left accumbens area", "left ventral DC",
    "right cerebral white matter", "right lateral ventricle",
    "right inferior lateral ventricle", "right cerebellum white matter", "right cerebellum cortex",
    "right thalamus", "right caudate", "right putamen", "right pallidum",
    "right hippocampus", "right amygdala", "right accumbens area",
    "right ventral DC"
]


def _norm_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


SUBCORTICAL_KEYS = {_norm_name(name) for name in SUBCORTICAL_STRUCTURES}

CAT12_TISSUE_NAMES = {
    "vol_abs_cgw": ["cerebrospinal fluid", "gray matter", "white matter"],
    "vol_rel_cgw": ["relative cerebrospinal fluid", "relative gray matter", "relative white matter"],
}

# Native CAT12 ROI tables store tissue arrays under these element names.
CAT12_TISSUE_TAGS = {"vgm": "gm", "vwm": "wm", "vcsf": "csf"}

# Native CAT12 ROI tissue flags, generated from the atlas dictionaries that
# ship with CAT12 (templates_MNI152NLin2009cAsym/*.csv).
CAT12_TISSUE_FLAG_FILES = ("info/cat12_tissue_flags.txt", "cat12_tissue_flags.txt")


def _load_cat12_tissue_flags(*, required: bool = False) -> Dict[str, Dict[str, Tuple[int, int, int]]]:
    """Load native flags. CAT12 execution requires a valid resource."""
    roots: List[Path] = []
    resource_root = os.environ.get("NEUROFLOW_RESOURCE_ROOT")
    if resource_root:
        roots.append(Path(resource_root))
    roots.append(Path(__file__).resolve().parent)
    try:
        for root in roots:
            for rel in CAT12_TISSUE_FLAG_FILES:
                path = root / rel
                if not path.is_file():
                    continue
                table: Dict[str, Dict[str, Tuple[int, int, int]]] = {}
                with open(path, "r", encoding="utf-8") as handle:
                    for raw in handle:
                        if not raw.strip() or raw.startswith("#") or raw.startswith("atlas\t"):
                            continue
                        parts = raw.rstrip("\r\n").split("\t")
                        if len(parts) != 5 or not parts[0].strip() or not _norm_name(parts[1]):
                            raise ValueError(f"Invalid tissue row in {path}")
                        flags = tuple(int(value) for value in parts[2:])
                        if any(flag not in (0, 1) for flag in flags):
                            raise ValueError(f"Invalid tissue flags in {path}")
                        entries = table.setdefault(parts[0].strip().lower(), {})
                        name = _norm_name(parts[1])
                        if name in entries and entries[name] != flags:
                            raise ValueError(f"Conflicting tissue flags in {path}: {parts[1]}")
                        entries[name] = flags
                if not table:
                    raise ValueError(f"Empty tissue dictionary: {path}")
                return table
        raise FileNotFoundError("cat12_tissue_flags.txt is missing")
    except (OSError, UnicodeError, ValueError) as exc:
        if required:
            raise RuntimeError(f"Required CAT12 tissue dictionary is unavailable: {exc}") from exc
        return {}


CAT12_TISSUE_FLAGS = _load_cat12_tissue_flags()


def _load_cat12_roi_mapping(*, required: bool = False) -> Dict[str, Dict[str, dict]]:
    roots = [Path(__file__).resolve().parent]
    if os.environ.get("NEUROFLOW_RESOURCE_ROOT"):
        roots.insert(0, Path(os.environ["NEUROFLOW_RESOURCE_ROOT"]))
    try:
        for root in roots:
            path = root / "info" / "cat12_roi_mapping.txt"
            if not path.is_file():
                continue
            table: Dict[str, Dict[str, dict]] = {}
            with path.open(encoding="utf-8") as stream:
                for row in csv.DictReader((line for line in stream if not line.startswith("#")), delimiter="\t"):
                    atlas, roi_id = row["atlas"], row["roi_id"]
                    if (not roi_id.isdigit() or row["hemisphere"] not in {"lh", "rh", "both"}
                            or row["category"] not in {"cortical", "subcortical", "unavailable"}
                            or any(field not in {"Vgm", "Vwm", "Vcsf"} for field in row["fields"].split("+") if field)):
                        raise ValueError(f"Invalid CAT12 mapping row: {atlas}/{roi_id}")
                    entries = table.setdefault(atlas, {})
                    if roi_id in entries:
                        raise ValueError(f"Duplicate CAT12 ROI ID: {atlas}/{roi_id}")
                    entries[roi_id] = row
            if not table:
                raise ValueError("Empty CAT12 ROI mapping")
            return table
        raise FileNotFoundError("cat12_roi_mapping.txt is missing")
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        if required:
            raise RuntimeError(f"Required CAT12 ROI mapping is unavailable: {exc}") from exc
        return {}


CAT12_ROI_MAPPING = _load_cat12_roi_mapping()


def _cat12_roi_metadata(atlas: str, region: str, roi_id: str = "") -> Optional[dict]:
    entries = CAT12_ROI_MAPPING.get(atlas.lower(), {})
    name = _norm_name(region)
    if roi_id:
        entry = entries.get(str(roi_id))
        if entry and name in {_norm_name(entry["native_name"]), _norm_name(entry["native_abbr"])}:
            return entry
        if entries:
            raise ValueError(f"CAT12 ROI ID/name mismatch: {atlas}/{roi_id}/{region}")
        return None
    matches = [entry for entry in entries.values()
               if name in {_norm_name(entry["native_name"]), _norm_name(entry["native_abbr"])}]
    return matches[0] if len(matches) == 1 else None


def _cat12_roi_ids(parent: ET.Element, count: int) -> List[str]:
    text = _child_text(parent, "ids")
    ids = _numeric_tokens(text)
    if ids and (len(ids) != count or len(set(ids)) != len(ids)):
        raise ValueError(f"CAT12 ROI IDs do not match names in {_xml_tag(parent)}")
    return ids or [""] * count


def _xml_tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _numeric_tokens(value: Optional[str]) -> List[str]:
    return re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", value or "")


def _is_volume_tag(tag: str) -> bool:
    norm = _norm_name(tag)
    return norm in {"volume", "vol"} or norm.startswith("vol_")


def _tissue_of_tag(tag: str) -> Optional[str]:
    return CAT12_TISSUE_TAGS.get(_norm_name(tag))


def _is_cat12_volume_value_tag(tag: str) -> bool:
    return _is_volume_tag(tag) or _tissue_of_tag(tag) is not None


def _ml_to_mm3(value: Optional[str]) -> str:
    """Convert a native CAT12 volume in mL to mm3. Non-numeric input is kept as-is."""
    text = (value or "").strip()
    if not text:
        return value or ""
    try:
        scaled = Decimal(text) * 1000
    except (InvalidOperation, ValueError):
        return text
    if not scaled.is_finite():
        return text
    out = format(scaled, "f")
    if "." in out:
        out = out.rstrip("0").rstrip(".")
    return out or "0"


def _sum_ml(values: List[str]) -> str:
    total = Decimal(0)
    for value in values:
        try:
            total += Decimal(value)
        except (InvalidOperation, ValueError):
            return values[0]
    return format(total, "f")


def _cat12_region_tissues(region: str, atlas: str = "", roi_id: str = "") -> Tuple[str, ...]:
    """Use native flags or the explicit atlas measurement contract."""
    entry = _cat12_roi_metadata(atlas, region, roi_id)
    if entry is not None:
        fields = tuple(field[1:] for field in entry["fields"].split("+") if field)
        if atlas.lower() in {"cobra", "hammers", "ibsr", "lpba40", "mori", "neuromorphometrics"}:
            flags = CAT12_TISSUE_FLAGS.get(atlas.lower(), {}).get(_norm_name(entry["native_name"]))
            selected = tuple(kind for kind, flag in zip(("gm", "wm", "csf"), flags or ()) if flag)
            if flags is None or selected != fields:
                raise RuntimeError(f"CAT12 tissue dictionary disagrees with native ROI: {atlas}/{entry['roi_id']}")
            return selected
        return fields
    flags = CAT12_TISSUE_FLAGS.get(atlas.lower())
    if flags is not None:
        entry_flags = flags.get(_norm_name(region), ())
        return tuple(kind for kind, flag in zip(("gm", "wm", "csf"), entry_flags) if flag)
    # Legacy generic XML has no atlas dictionary. Only an explicit GM/volume field is usable.
    return ("gm",) if atlas.lower() in {"", "atlas", "roi"} else ()


def _is_thickness_tag(tag: str) -> bool:
    norm = _norm_name(tag)
    return norm in {"th", "th1", "th2", "thick", "thickness", "thickness_mm", "mean_thickness"} or "thickness" in norm


def _child_text(parent: ET.Element, *names: str) -> str:
    wanted = {_norm_name(name) for name in names}
    for child in list(parent):
        if _norm_name(_xml_tag(child)) in wanted and child.text and child.text.strip():
            return child.text.strip()
    return ""


def _text_items(element: ET.Element) -> List[str]:
    child_items = [child.text.strip() for child in list(element) if child.text and child.text.strip()]
    if child_items:
        return child_items
    text = (element.text or "").strip()
    if not text:
        return []
    if ";" in text:
        return [item.strip() for item in text.split(";") if item.strip()]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines if len(lines) > 1 else [text]


CAT12_CORTICAL_ATLAS_MARKERS = ("schaefer", "aal", "anatomy", "hammers", "julich", "lpba", "mori")

CAT12_ATLAS_NODE_TO_KEY: Dict[str, str] = {
    "Schaefer2018_100Parcels_17Networks_order": "cat12_schaefer2018_100parcels_17networks",
    "Schaefer2018_200Parcels_17Networks_order": "cat12_schaefer2018_200parcels_17networks",
    "Schaefer2018_400Parcels_17Networks_order": "cat12_schaefer2018_400parcels_17networks",
    "Schaefer2018_600Parcels_17Networks_order": "cat12_schaefer2018_600parcels_17networks",
    "neuromorphometrics": "cat12_neuromorphometrics",
    "aal3": "cat12_aal3",
    "anatomy3": "cat12_anatomy3",
    "cobra": "cat12_cobra",
    "hammers": "cat12_hammers",
    "ibsr": "cat12_ibsr",
    "julichbrain3": "cat12_julichbrain3",
    "lpba40": "cat12_lpba40",
    "mori": "cat12_mori",
    "suit": "cat12_suit",
    "thalamic_nuclei": "cat12_thalamic_nuclei",
    "thalamus": "cat12_thalamus",
}


def _classify_cat12_region(name: str, atlas: str = "", roi_id: str = "") -> str:
    entry = _cat12_roi_metadata(atlas, name, roi_id)
    if entry is not None:
        return entry["category"]
    if any(marker in _norm_name(atlas) for marker in CAT12_CORTICAL_ATLAS_MARKERS):
        return "cortical"
    norm = _norm_name(name)
    cortical_markers = ("cortex", "cortical", "ctx", "frontal", "temporal", "parietal", "occipital", "cingulate", "insula")
    return "cortical" if any(marker in norm for marker in cortical_markers) else "subcortical"


def _append_unique(
    row: List[str],
    rows: List[List[str]],
    seen: Set[Tuple[str, ...]],
    key_indexes: Tuple[int, ...] = (1, 2),
) -> None:
    key = tuple(row[index] for index in key_indexes)
    if key in seen:
        return
    seen.add(key)
    rows.append(row)


def _append_cat12_roi_volume(
    subject_id: str,
    region: str,
    value: str,
    tool: str,
    sub_rows: List[List[str]],
    cort_rows: List[List[str]],
    seen_sub: Set[Tuple[str, ...]],
    seen_cort: Set[Tuple[str, ...]],
    atlas: str = "",
    roi_id: str = "",
) -> None:
    entry = _cat12_roi_metadata(atlas, region, roi_id)
    kind = _classify_cat12_region(region, atlas, roi_id)
    if kind == "cortical":
        hemi = entry["hemisphere"] if entry else "both"
        _append_unique([subject_id, region, hemi, value, tool], cort_rows, seen_cort)
    elif kind == "subcortical":
        _append_unique([subject_id, region, value, tool], sub_rows, seen_sub)


def _cat12_vector_value_elements(parent: ET.Element, predicate) -> List[ET.Element]:
    elements = [child for child in list(parent) if predicate(_xml_tag(child))]
    for child in list(parent):
        if _norm_name(_xml_tag(child)) == "data":
            elements.extend(grandchild for grandchild in list(child) if predicate(_xml_tag(grandchild)))
    return elements


def _cat12_volume_arrays(parent: ET.Element) -> Tuple[Dict[str, List[str]], Optional[List[str]]]:
    """Collect native tissue arrays (Vgm/Vwm/Vcsf) and a generic volume array."""
    arrays: Dict[str, List[str]] = {}
    generic: Optional[List[str]] = None
    for child in _cat12_vector_value_elements(parent, _is_cat12_volume_value_tag):
        numbers = _numeric_tokens(child.text)
        if not numbers:
            continue
        kind = _tissue_of_tag(_xml_tag(child))
        if kind is None:
            if generic is None:
                generic = numbers
        else:
            arrays.setdefault(kind, numbers)
    return arrays, generic


def _match_cat12_array_length(
    arrays: Dict[str, List[str]],
    generic: Optional[List[str]],
    count: int,
) -> Tuple[Dict[str, List[str]], Optional[List[str]]]:
    matched = {kind: values for kind, values in arrays.items() if len(values) == count}
    if generic is not None and len(generic) != count:
        generic = None
    return matched, generic


def _cat12_pick_volume_mm3(
    region: str,
    atlas: str,
    arrays: Dict[str, List[str]],
    generic: Optional[List[str]],
    index: int,
    roi_id: str = "",
) -> str:
    """Pick the native tissue volume for a region and convert it to mm3.

    The native tissue flags decide the fields. A region without its designated
    fields stays unavailable instead of borrowing another tissue.
    """
    wanted = _cat12_region_tissues(region, atlas, roi_id)
    has_flags = atlas.lower() in CAT12_TISSUE_FLAGS or atlas.lower() in CAT12_ROI_MAPPING
    if wanted:
        values = [
            arrays[kind][index]
            for kind in wanted
            if kind in arrays and index < len(arrays[kind])
        ]
        if len(values) == len(wanted):
            return _ml_to_mm3(_sum_ml(values) if len(values) > 1 else values[0])
        if not has_flags and generic is not None and index < len(generic):
            return _ml_to_mm3(generic[index])
        print(
            f"normalize_volumes: no {'+'.join(wanted)} volume for region {region!r} "
            f"in atlas {atlas!r}; value stays unavailable.",
            file=sys.stderr,
        )
        return "NA"
    if not has_flags and generic is not None and index < len(generic):
        return _ml_to_mm3(generic[index])
    return "NA"


def _append_cat12_roi_thickness(
    subject_id: str,
    region: str,
    value: str,
    tool: str,
    rows: List[List[str]],
    seen: Set[Tuple[str, ...]],
) -> None:
    cortical = _split_cortical_name(region)
    if cortical:
        region_name, hemi = cortical
    else:
        region_name, hemi = region, "both"
    _append_unique([subject_id, region_name, hemi, value, tool], rows, seen)


def _cat12_report_rows(report_xml: Path, subject_id: str, tool: str) -> List[List[str]]:
    if not report_xml.exists():
        return []
    root = ET.parse(report_xml).getroot()
    rows: List[List[str]] = []
    seen: Set[Tuple[str, ...]] = set()
    for element in root.iter():
        tag = _norm_name(_xml_tag(element))
        numbers = _numeric_tokens(element.text)
        if not numbers:
            continue
        if tag == "vol_tiv":
            _append_unique(
                [subject_id, "total intracranial", _ml_to_mm3(numbers[0]), tool], rows, seen, (1,)
            )
            continue
        relative = tag.startswith("vol_rel_")
        tissue_names = CAT12_TISSUE_NAMES.get(tag)
        if tissue_names:
            for name, value in zip(tissue_names, numbers):
                _append_unique(
                    [subject_id, name, value if relative else _ml_to_mm3(value), tool],
                    rows, seen, (1,),
                )
            continue
        if tag.startswith("vol_") and len(numbers) == 1:
            name = tag.removeprefix("vol_").replace("_", " ")
            value = numbers[0] if relative else _ml_to_mm3(numbers[0])
            _append_unique([subject_id, name, value, tool], rows, seen, (1,))
    return rows


def _cat12_roi_rows(roi_xml: Path, subject_id: str, tool: str) -> Tuple[List[List[str]], List[List[str]]]:
    if not roi_xml.exists():
        return [], []
    root = ET.parse(roi_xml).getroot()
    sub_rows: List[List[str]] = []
    cort_rows: List[List[str]] = []
    seen_sub: Set[Tuple[str, ...]] = set()
    seen_cort: Set[Tuple[str, ...]] = set()
    for parent in root.iter():
        region_names: List[str] = []
        for child in list(parent):
            if _norm_name(_xml_tag(child)) in {"names", "labels", "roi_names", "roinames", "regions"}:
                region_names.extend(_text_items(child))
        arrays, generic = _cat12_volume_arrays(parent)
        atlas = _xml_tag(parent)
        if region_names:
            arrays, generic = _match_cat12_array_length(arrays, generic, len(region_names))
            roi_ids = _cat12_roi_ids(parent, len(region_names))
            for index, region in enumerate(region_names):
                value = _cat12_pick_volume_mm3(region, atlas, arrays, generic, index, roi_ids[index])
                _append_cat12_roi_volume(subject_id, region, value, tool, sub_rows, cort_rows, seen_sub, seen_cort, atlas, roi_ids[index])

        region = _child_text(parent, "name", "label", "roi", "region")
        if not region:
            continue
        arrays, generic = _match_cat12_array_length(arrays, generic, 1)
        value = _cat12_pick_volume_mm3(region, atlas, arrays, generic, 0)
        _append_cat12_roi_volume(subject_id, region, value, tool, sub_rows, cort_rows, seen_sub, seen_cort)
    return sub_rows, cort_rows


def _append_cat12_atlas_row(
    subject_id: str,
    atlas_key: str,
    atlas_tag: str,
    region: str,
    value: str,
    tool: str,
    sub_rows: List[List[str]],
    cort_rows: List[List[str]],
    roi_id: str = "",
) -> None:
    entry = _cat12_roi_metadata(atlas_tag, region, roi_id)
    kind = _classify_cat12_region(region, atlas_tag, roi_id)
    identity = entry["roi_id"] if entry else roi_id
    if kind == "cortical":
        cortical = _split_cortical_name(region) if not entry else None
        label, hemi = cortical if cortical else (region, entry["hemisphere"] if entry else "both")
        cort_rows.append([subject_id, atlas_key, label, hemi, value, tool, identity])
    elif kind == "subcortical":
        sub_rows.append([subject_id, atlas_key, region, value, tool, identity])
    else:
        print(f"normalize_volumes: unclassified native ROI {atlas_tag}/{identity}/{region}; no cortical feature.", file=sys.stderr)


def _cat12_atlas_roi_rows(
    roi_xml: Path, subject_id: str, tool: str
) -> Tuple[List[List[str]], List[List[str]]]:
    if not roi_xml.exists():
        return [], []
    root = ET.parse(roi_xml).getroot()
    sub_rows: List[List[str]] = []
    cort_rows: List[List[str]] = []
    for parent in root.iter():
        region_names: List[str] = []
        for child in list(parent):
            if _norm_name(_xml_tag(child)) in {"names", "labels", "roi_names", "roinames", "regions"}:
                region_names.extend(_text_items(child))
        arrays, generic = _cat12_volume_arrays(parent)
        atlas_tag = _xml_tag(parent)
        if region_names:
            atlas_key = CAT12_ATLAS_NODE_TO_KEY.get(atlas_tag, "")
            if not atlas_key:
                atlas_key = CAT12_ATLAS_NODE_TO_KEY.get(atlas_tag.lower(), "")
            if not atlas_key:
                atlas_key = f"cat12_{_norm_name(atlas_tag)}"
            arrays, generic = _match_cat12_array_length(arrays, generic, len(region_names))
            roi_ids = _cat12_roi_ids(parent, len(region_names))
            for index, region in enumerate(region_names):
                value = _cat12_pick_volume_mm3(region, atlas_tag, arrays, generic, index, roi_ids[index])
                _append_cat12_atlas_row(
                    subject_id, atlas_key, atlas_tag, region, value, tool, sub_rows, cort_rows, roi_ids[index]
                )

        region = _child_text(parent, "name", "label", "roi", "region")
        if not region:
            continue
        parent_tag = atlas_tag
        parent_key = CAT12_ATLAS_NODE_TO_KEY.get(parent_tag, "")
        if not parent_key:
            parent_key = CAT12_ATLAS_NODE_TO_KEY.get(parent_tag.lower(), "")
        if not parent_key:
            parent_key = f"cat12_{_norm_name(parent_tag)}"
        arrays, generic = _match_cat12_array_length(arrays, generic, 1)
        value = _cat12_pick_volume_mm3(region, parent_tag, arrays, generic, 0)
        _append_cat12_atlas_row(
            subject_id, parent_key, parent_tag, region, value, tool, sub_rows, cort_rows
        )
    return sub_rows, cort_rows


def _cat12_roi_thickness_rows(roi_xml: Path, subject_id: str, tool: str) -> List[List[str]]:
    if not roi_xml.exists():
        return []
    root = ET.parse(roi_xml).getroot()
    rows: List[List[str]] = []
    seen: Set[Tuple[str, ...]] = set()
    for parent in root.iter():
        region_names: List[str] = []
        for child in list(parent):
            if _norm_name(_xml_tag(child)) in {"names", "labels", "roi_names", "roinames", "regions"}:
                region_names.extend(_text_items(child))
        if region_names:
            for child in _cat12_vector_value_elements(parent, _is_thickness_tag):
                numbers = _numeric_tokens(child.text)
                if len(numbers) != len(region_names):
                    continue
                for region, value in zip(region_names, numbers):
                    _append_cat12_roi_thickness(subject_id, region, value, tool, rows, seen)

        region = _child_text(parent, "name", "label", "roi", "region")
        if not region:
            continue
        for child in list(parent):
            if not _is_thickness_tag(_xml_tag(child)):
                continue
            numbers = _numeric_tokens(child.text)
            if numbers:
                _append_cat12_roi_thickness(subject_id, region, numbers[0], tool, rows, seen)
    return rows


def _read_freesurfer_curv_values(path: Path) -> List[float]:
    if not path.exists():
        return []
    data = path.read_bytes()
    if len(data) < 15 or int.from_bytes(data[:3], "big", signed=False) != 16777215:
        return []
    vnum, _fnum, vals_per_vertex = struct.unpack(">iii", data[3:15])
    count = vnum * vals_per_vertex
    expected = 15 + count * 4
    if vals_per_vertex <= 0 or len(data) < expected:
        return []
    return [value for value in struct.unpack(f">{count}f", data[15:expected]) if math.isfinite(value)]


def _cat12_surface_thickness_rows(surf_dir: Path, subject_id: str, tool: str) -> List[List[str]]:
    rows: List[List[str]] = []
    all_values: List[float] = []
    for hemi in ("lh", "rh"):
        values = _read_freesurfer_curv_values(surf_dir / f"{hemi}.thickness.input")
        if not values:
            continue
        all_values.extend(values)
        rows.append([subject_id, "global cortical mean", hemi, f"{sum(values) / len(values):.6f}", tool])
    if all_values:
        rows.append([subject_id, "global cortical mean", "both", f"{sum(all_values) / len(all_values):.6f}", tool])
    return rows


def _write_cat12_xml(
    report_xml: str,
    roi_xml: str,
    out_sub: str,
    out_cort: str,
    subject_id: str,
    tool: str = "CAT12",
    out_thickness: str = "",
    surf_dir: str = "",
    out_sub_by_atlas: str = "",
    out_cort_by_atlas: str = "",
) -> None:
    global CAT12_TISSUE_FLAGS, CAT12_ROI_MAPPING
    CAT12_TISSUE_FLAGS = _load_cat12_tissue_flags(required=True)
    CAT12_ROI_MAPPING = _load_cat12_roi_mapping(required=True)
    sub_rows = _cat12_report_rows(Path(report_xml), subject_id, tool)
    roi_sub_rows, cort_rows = _cat12_roi_rows(Path(roi_xml), subject_id, tool)
    sub_rows.extend(roi_sub_rows)

    Path(out_sub).parent.mkdir(parents=True, exist_ok=True)
    Path(out_cort).parent.mkdir(parents=True, exist_ok=True)
    with open(out_sub, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["subject", "structure", "volume_mm3", "tool"])
        writer.writerows(sub_rows)
    with open(out_cort, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["subject", "region", "hemisphere", "volume_mm3", "tool"])
        writer.writerows(cort_rows)

    if out_sub_by_atlas or out_cort_by_atlas:
        atlas_sub_rows, atlas_cort_rows = _cat12_atlas_roi_rows(Path(roi_xml), subject_id, tool)
        if out_sub_by_atlas:
            Path(out_sub_by_atlas).parent.mkdir(parents=True, exist_ok=True)
            with open(out_sub_by_atlas, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(["subject", "atlas", "structure", "volume_mm3", "tool", "roi_id"])
                writer.writerows(atlas_sub_rows)
        if out_cort_by_atlas:
            Path(out_cort_by_atlas).parent.mkdir(parents=True, exist_ok=True)
            with open(out_cort_by_atlas, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(["subject", "atlas", "region", "hemisphere", "volume_mm3", "tool", "roi_id"])
                writer.writerows(atlas_cort_rows)

    if out_thickness:
        thickness_rows = _cat12_roi_thickness_rows(Path(roi_xml), subject_id, tool)
        if not thickness_rows and surf_dir:
            thickness_rows = _cat12_surface_thickness_rows(Path(surf_dir), subject_id, tool)
        Path(out_thickness).parent.mkdir(parents=True, exist_ok=True)
        with open(out_thickness, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(["subject", "region", "hemisphere", "thickness_mm", "tool"])
            writer.writerows(thickness_rows)


def _parse_stats_table(path: Path) -> List[Dict[str, str]]:
    headers: List[str] = []
    rows: List[Dict[str, str]] = []
    if not path.exists():
        return rows
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
    return rows


def _parse_measures(path: Path) -> List[Tuple[str, str]]:
    measures: List[Tuple[str, str]] = []
    if not path.exists():
        return measures
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line.startswith("# Measure "):
            continue
        parts = [part.strip() for part in line[len("# Measure "):].split(",")]
        if len(parts) < 2:
            continue
        value = next((part for part in reversed(parts) if re.fullmatch(r"[-+]?\d+(\.\d+)?([eE][-+]?\d+)?", part)), "")
        name = parts[1] if len(parts) > 1 else parts[0]
        if name and value:
            measures.append((name, value))
    return measures


def _split_cortical_name(name: str, hemi_hint: str = "") -> Optional[Tuple[str, str]]:
    raw = name.strip()
    lower = raw.lower()
    for prefix, hemi in (("ctx-lh-", "lh"), ("ctx-rh-", "rh"), ("ctx_lh_", "lh"), ("ctx_rh_", "rh")):
        if lower.startswith(prefix):
            return raw[len(prefix):], hemi
    if hemi_hint in {"lh", "rh"}:
        return raw, hemi_hint
    if lower.startswith("left "):
        return raw[5:], "lh"
    if lower.startswith("right "):
        return raw[6:], "rh"
    return None


def _write_synthseg_csv(input_csv: str, out_sub: str, out_cort: str, subject_id: str, tool: str) -> None:
    if not os.path.exists(input_csv):
        sys.exit(2)

    with open(input_csv, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        sys.exit(2)

    header = rows[0]
    values = rows[1] if len(rows) > 1 else []

    # Skip first column (subject)
    structures = header[1:]
    volumes = values[1:] if len(values) > 1 else []

    Path(out_sub).parent.mkdir(parents=True, exist_ok=True)
    Path(out_cort).parent.mkdir(parents=True, exist_ok=True)

    with open(out_sub, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["subject", "structure", "volume_mm3", "tool"])
        for s, v in zip(structures, volumes):
            if _norm_name(s) in SUBCORTICAL_KEYS:
                writer.writerow([subject_id, s, v, tool])

    with open(out_cort, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["subject", "region", "hemisphere", "volume_mm3", "tool"])
        for s, v in zip(structures, volumes):
            if _norm_name(s) in SUBCORTICAL_KEYS:
                continue
            cortical = _split_cortical_name(s)
            if cortical:
                region, hemi = cortical
                writer.writerow([subject_id, region, hemi, v, tool])
            else:
                writer.writerow([subject_id, s, "both", v, tool])


def _write_from_stats_dir(stats_dir: str, out_sub: str, out_cort: str, subject_id: str, tool: str) -> None:
    stats_path = Path(stats_dir)
    table_candidates = [
        stats_path / "aseg.stats",
        stats_path / "aseg.VINN.stats",
        stats_path / "aparc.DKTatlas+aseg.deep.stats",
        stats_path / "aseg+DKT.stats",
        stats_path / "aseg+DKT.VINN.stats",
    ]
    surface_candidates = [
        ("lh", stats_path / "lh.aparc.stats"),
        ("rh", stats_path / "rh.aparc.stats"),
        ("lh", stats_path / "lh.aparc.DKTatlas.stats"),
        ("rh", stats_path / "rh.aparc.DKTatlas.stats"),
        ("lh", stats_path / "lh.aparc.DKTatlas.mapped.stats"),
        ("rh", stats_path / "rh.aparc.DKTatlas.mapped.stats"),
    ]

    sub_rows: List[List[str]] = []
    cort_rows: List[List[str]] = []
    seen_sub: Set[str] = set()
    seen_cort: Set[Tuple[str, ...]] = set()

    for path in table_candidates:
        for row in _parse_stats_table(path):
            name = row.get("StructName", "")
            volume = row.get("Volume_mm3") or row.get("GrayVol") or row.get("Volume") or row.get("NVoxels")
            if not name or not volume:
                continue
            cortical = _split_cortical_name(name)
            if cortical:
                region, hemi = cortical
                key = (hemi, _norm_name(region))
                if key not in seen_cort:
                    seen_cort.add(key)
                    cort_rows.append([subject_id, region, hemi, volume, tool])
                continue
            key = _norm_name(name)
            if key not in seen_sub:
                seen_sub.add(key)
                sub_rows.append([subject_id, name, volume, tool])
        for measure, volume in _parse_measures(path):
            key = _norm_name(measure)
            if key not in seen_sub:
                seen_sub.add(key)
                sub_rows.append([subject_id, measure, volume, tool])

    for hemi, path in surface_candidates:
        for row in _parse_stats_table(path):
            region = row.get("StructName", "")
            volume = row.get("GrayVol") or row.get("Volume_mm3") or row.get("Volume")
            if not region or not volume:
                continue
            key = (hemi, _norm_name(region))
            if key not in seen_cort:
                seen_cort.add(key)
                cort_rows.append([subject_id, region, hemi, volume, tool])

    Path(out_sub).parent.mkdir(parents=True, exist_ok=True)
    Path(out_cort).parent.mkdir(parents=True, exist_ok=True)
    with open(out_sub, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["subject", "structure", "volume_mm3", "tool"])
        writer.writerows(sub_rows)
    with open(out_cort, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["subject", "region", "hemisphere", "volume_mm3", "tool"])
        writer.writerows(cort_rows)


def main():
    if len(sys.argv) == 6 and not sys.argv[1].startswith("-"):
        _write_synthseg_csv(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
        return

    parser = argparse.ArgumentParser()
    parser.add_argument("--subject-id", required=True)
    parser.add_argument("--input-csv")
    parser.add_argument("--input-seg")
    parser.add_argument("--stats-dir")
    parser.add_argument("--cat-report")
    parser.add_argument("--cat-roi")
    parser.add_argument("--cat-surf-dir")
    parser.add_argument("--output-subcortical", required=True)
    parser.add_argument("--output-cortical", required=True)
    parser.add_argument("--output-thickness")
    parser.add_argument("--output-subcortical-by-atlas")
    parser.add_argument("--output-cortical-by-atlas")
    parser.add_argument("--tool", default="FastSurferVINN")
    args = parser.parse_args()

    if args.cat_report and args.cat_roi:
        _write_cat12_xml(
            args.cat_report,
            args.cat_roi,
            args.output_subcortical,
            args.output_cortical,
            args.subject_id,
            args.tool,
            args.output_thickness or "",
            args.cat_surf_dir or "",
            args.output_subcortical_by_atlas or "",
            args.output_cortical_by_atlas or "",
        )
    elif args.stats_dir:
        _write_from_stats_dir(args.stats_dir, args.output_subcortical, args.output_cortical, args.subject_id, args.tool)
    elif args.input_csv:
        _write_synthseg_csv(args.input_csv, args.output_subcortical, args.output_cortical, args.subject_id, args.tool)
    else:
        parser.error("expected --stats-dir, --input-csv, or --cat-report with --cat-roi")


if __name__ == "__main__":
    main()
