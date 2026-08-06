#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
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


def _xml_tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _numeric_tokens(value: str | None) -> List[str]:
    return re.findall(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", value or "")


def _is_volume_tag(tag: str) -> bool:
    norm = _norm_name(tag)
    return norm in {"volume", "vol", "vgm", "vwm", "vcsf"} or norm.startswith("vol_")


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


def _classify_cat12_region(name: str) -> str:
    norm = _norm_name(name)
    cortical_markers = ("cortex", "cortical", "ctx", "frontal", "temporal", "parietal", "occipital", "cingulate", "insula")
    return "cortical" if any(marker in norm for marker in cortical_markers) else "subcortical"


def _append_unique(row: List[str], rows: List[List[str]], seen: Set[Tuple[str, str]]) -> None:
    key = (row[1], row[2])
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
    seen_sub: Set[Tuple[str, str]],
    seen_cort: Set[Tuple[str, str]],
) -> None:
    if _classify_cat12_region(region) == "cortical":
        _append_unique([subject_id, region, "both", value, tool], cort_rows, seen_cort)
    else:
        _append_unique([subject_id, region, value, tool], sub_rows, seen_sub)


def _append_cat12_roi_thickness(
    subject_id: str,
    region: str,
    value: str,
    tool: str,
    rows: List[List[str]],
    seen: Set[Tuple[str, str]],
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
    seen: Set[Tuple[str, str]] = set()
    for element in root.iter():
        tag = _norm_name(_xml_tag(element))
        numbers = _numeric_tokens(element.text)
        if not numbers:
            continue
        if tag == "vol_tiv":
            _append_unique([subject_id, "total intracranial", numbers[0], tool], rows, seen)
            continue
        tissue_names = CAT12_TISSUE_NAMES.get(tag)
        if tissue_names:
            for name, value in zip(tissue_names, numbers):
                _append_unique([subject_id, name, value, tool], rows, seen)
            continue
        if tag.startswith("vol_") and len(numbers) == 1:
            _append_unique([subject_id, tag.removeprefix("vol_").replace("_", " "), numbers[0], tool], rows, seen)
    return rows


def _cat12_roi_rows(roi_xml: Path, subject_id: str, tool: str) -> Tuple[List[List[str]], List[List[str]]]:
    if not roi_xml.exists():
        return [], []
    root = ET.parse(roi_xml).getroot()
    sub_rows: List[List[str]] = []
    cort_rows: List[List[str]] = []
    seen_sub: Set[Tuple[str, str]] = set()
    seen_cort: Set[Tuple[str, str]] = set()
    for parent in root.iter():
        region_names: List[str] = []
        for child in list(parent):
            if _norm_name(_xml_tag(child)) in {"names", "labels", "roi_names", "roinames", "regions"}:
                region_names.extend(_text_items(child))
        if region_names:
            for child in list(parent):
                if not _is_volume_tag(_xml_tag(child)):
                    continue
                numbers = _numeric_tokens(child.text)
                if len(numbers) != len(region_names):
                    continue
                for region, value in zip(region_names, numbers):
                    _append_cat12_roi_volume(subject_id, region, value, tool, sub_rows, cort_rows, seen_sub, seen_cort)

        region = _child_text(parent, "name", "label", "roi", "region")
        if not region:
            continue
        for child in list(parent):
            tag = _xml_tag(child)
            if not _is_volume_tag(tag):
                continue
            numbers = _numeric_tokens(child.text)
            if not numbers:
                continue
            value = numbers[0]
            _append_cat12_roi_volume(subject_id, region, value, tool, sub_rows, cort_rows, seen_sub, seen_cort)
    return sub_rows, cort_rows


def _cat12_roi_thickness_rows(roi_xml: Path, subject_id: str, tool: str) -> List[List[str]]:
    if not roi_xml.exists():
        return []
    root = ET.parse(roi_xml).getroot()
    rows: List[List[str]] = []
    seen: Set[Tuple[str, str]] = set()
    for parent in root.iter():
        region_names: List[str] = []
        for child in list(parent):
            if _norm_name(_xml_tag(child)) in {"names", "labels", "roi_names", "roinames", "regions"}:
                region_names.extend(_text_items(child))
        if region_names:
            for child in list(parent):
                if not _is_thickness_tag(_xml_tag(child)):
                    continue
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


def _write_cat12_xml(
    report_xml: str,
    roi_xml: str,
    out_sub: str,
    out_cort: str,
    subject_id: str,
    tool: str = "CAT12",
    out_thickness: str = "",
) -> None:
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
    if out_thickness:
        thickness_rows = _cat12_roi_thickness_rows(Path(roi_xml), subject_id, tool)
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
    seen_cort: Set[Tuple[str, str]] = set()

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
    parser.add_argument("--output-subcortical", required=True)
    parser.add_argument("--output-cortical", required=True)
    parser.add_argument("--output-thickness")
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
        )
    elif args.stats_dir:
        _write_from_stats_dir(args.stats_dir, args.output_subcortical, args.output_cortical, args.subject_id, args.tool)
    elif args.input_csv:
        _write_synthseg_csv(args.input_csv, args.output_subcortical, args.output_cortical, args.subject_id, args.tool)
    else:
        parser.error("expected --stats-dir, --input-csv, or --cat-report with --cat-roi")


if __name__ == "__main__":
    main()
