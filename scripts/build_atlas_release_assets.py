#!/usr/bin/env python3
"""Build compressed Atlas Release Assets for GitHub Releases.

Creates:
  - atlas-schaefer2018-400-17.zip (Schaefer 2018 400 parcels 17 networks - default)
  - atlas-destrieux.zip           (Destrieux simple 2009)
  - atlas-kong2022.zip            (Kong 2022 200 parcels 17 networks)
  - atlas-yale.zip                (Yale Brain Atlas)
  - atlas-schaefer2018-all.zip    (All Schaefer 2018 100-1000 parcels, 7 & 17 networks)
"""

import os
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SURFACE_DIR = PROJECT_ROOT / "assets" / "atlases" / "surface"
OUTPUT_DIR = PROJECT_ROOT / "dist" / "atlas-assets"

PACKS = {
    "atlas-schaefer2018-400-17.zip": [
        "schaefer/lh.Schaefer2018_400Parcels_17Networks.gcs",
        "schaefer/rh.Schaefer2018_400Parcels_17Networks.gcs",
    ],
    "atlas-destrieux.zip": [
        "destrieux/lh.destrieux.simple.2009-07-29.gcs",
        "destrieux/rh.destrieux.simple.2009-07-29.gcs",
    ],
    "atlas-kong2022.zip": [
        "kong/lh.200Parcels_Kong2022_17Networks.annot",
        "kong/rh.200Parcels_Kong2022_17Networks.annot",
    ],
    "atlas-yale.zip": [
        "yale/Yale_Brain_Atlas_LH_fsaverage.annot",
        "yale/Yale_Brain_Atlas_RH_fsaverage.annot",
        "yale/YBA_696_LH_fsaverage_new.annot",
        "yale/YBA_696_RH_fsaverage_new.annot",
    ],
}

def build_all_schaefer_list():
    schaefer_dir = SURFACE_DIR / "schaefer"
    if not schaefer_dir.is_dir():
        return []
    return [f"schaefer/{f.name}" for f in schaefer_dir.glob("*.gcs")]

def create_pack(zip_name: str, rel_files: list[str]):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / zip_name
    print(f"Creating {zip_name} with {len(rel_files)} files...")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for rel in rel_files:
            file_path = SURFACE_DIR / rel
            if not file_path.is_file():
                print(f"  Warning: missing file {file_path}")
                continue
            # Store in zip preserving category prefix e.g. schaefer/lh.gcs
            zf.write(file_path, arcname=rel)
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"  -> {out_path.name}: {size_mb:.2f} MB")

def main():
    if not SURFACE_DIR.is_dir():
        print(f"Error: surface atlas dir not found: {SURFACE_DIR}")
        return

    for zip_name, files in PACKS.items():
        create_pack(zip_name, files)

    all_schaefer = build_all_schaefer_list()
    if all_schaefer:
        create_pack("atlas-schaefer2018-all.zip", all_schaefer)

    print(f"\nDone! Assets created in {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
