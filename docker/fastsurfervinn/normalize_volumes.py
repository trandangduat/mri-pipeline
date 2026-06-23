#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import re
from pathlib import Path


def _parse_stats_table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
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


def _parse_measures(path: Path) -> list[tuple[str, str]]:
    measures: list[tuple[str, str]] = []
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


def _write_subcortical(stats_dir: Path, output_path: Path, subject_id: str) -> None:
    rows: list[list[str]] = []
    for name in ("aseg.stats", "aparc.DKTatlas+aseg.deep.stats", "aseg+DKT.stats"):
        path = stats_dir / name
        _headers, table_rows = _parse_stats_table(path)
        for row in table_rows:
            structure = row.get("StructName", "")
            volume = row.get("Volume_mm3") or row.get("Volume") or row.get("NVoxels")
            if structure and volume:
                rows.append([subject_id, structure, volume, "FastSurferVINN"])
        for measure, volume in _parse_measures(path):
            rows.append([subject_id, measure, volume, "FastSurferVINN"])
        if rows:
            break

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["subject", "structure", "volume_mm3", "tool"])
        writer.writerows(rows)


def _write_cortical(stats_dir: Path, output_path: Path, subject_id: str) -> None:
    rows: list[list[str]] = []
    for hemi in ("lh", "rh"):
        for stats_name in (f"{hemi}.aparc.stats", f"{hemi}.aparc.DKTatlas.stats"):
            path = stats_dir / stats_name
            _headers, table_rows = _parse_stats_table(path)
            for row in table_rows:
                region = row.get("StructName", "")
                volume = row.get("GrayVol") or row.get("Volume_mm3") or row.get("Volume")
                if region and volume:
                    rows.append([subject_id, region, hemi, volume, "FastSurferVINN"])
            if table_rows:
                break

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["subject", "region", "hemisphere", "volume_mm3", "tool"])
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject-id", required=True)
    parser.add_argument("--stats-dir", required=True)
    parser.add_argument("--output-subcortical", required=True)
    parser.add_argument("--output-cortical", required=True)
    args = parser.parse_args()

    stats_dir = Path(args.stats_dir)
    if not stats_dir.is_dir():
        print(f"Stats directory not found: {stats_dir}")
        return 0

    _write_subcortical(stats_dir, Path(args.output_subcortical), args.subject_id)
    _write_cortical(stats_dir, Path(args.output_cortical), args.subject_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
