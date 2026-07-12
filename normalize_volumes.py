#!/usr/bin/env python3
import argparse
import csv
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


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
    parser.add_argument("--output-subcortical", required=True)
    parser.add_argument("--output-cortical", required=True)
    parser.add_argument("--tool", default="FastSurferVINN")
    args = parser.parse_args()

    if args.stats_dir:
        _write_from_stats_dir(args.stats_dir, args.output_subcortical, args.output_cortical, args.subject_id, args.tool)
    elif args.input_csv:
        _write_synthseg_csv(args.input_csv, args.output_subcortical, args.output_cortical, args.subject_id, args.tool)
    else:
        parser.error("expected --stats-dir or --input-csv")


if __name__ == "__main__":
    main()
