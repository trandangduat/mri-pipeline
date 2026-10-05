from __future__ import annotations

import os
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Generator

from app_backend.paths import data_root, resource_root
from pipeline.config import PROJECT_ROOT, SCHAEFER2018_ATLAS_VARIANTS, SURFACE_ATLAS_DIR

DEFAULT_RELEASE_BASE_URL = os.environ.get(
    "NEUROFLOW_ATLAS_RELEASE_URL",
    "https://github.com/trandangduat/mri-pipeline/releases/download/v0.1.0",
)


def surface_atlases_data_dir() -> Path:
    """Writable location for downloaded/imported surface atlases."""
    raw = os.environ.get("NEUROFLOW_SURFACE_ATLAS_DIR") or os.environ.get("MRI_PIPELINE_SURFACE_ATLAS_DIR")
    if raw:
        return Path(raw).expanduser()
    return data_root() / "atlases" / "surface"


def candidate_surface_atlas_dirs(res_root: Path | None = None) -> list[Path]:
    """Candidate directories to search for surface atlas assets in order."""
    dirs: list[Path] = [surface_atlases_data_dir()]
    # Secondary check in data_root/assets/atlases/surface
    dirs.append(data_root() / "assets" / "atlases" / "surface")
    # Packaged resources root
    if res_root is not None:
        dirs.append(Path(res_root) / "assets" / "atlases" / "surface")
    from app_backend.paths import is_frozen
    # Dev workspace project root (only in dev mode when res_root is not overridden)
    if not is_frozen() and res_root is None:
        dirs.append(PROJECT_ROOT / "assets" / "atlases" / "surface")
    # Keep unique paths
    seen = set()
    result = []
    for d in dirs:
        rp = str(d.resolve()) if d.exists() else str(d)
        if rp not in seen:
            seen.add(rp)
            result.append(d)
    return result


def find_surface_atlas_file(rel_path: str, res_root: Path | None = None) -> Path:
    """Resolve a relative atlas file path against candidate search paths."""
    for base in candidate_surface_atlas_dirs(res_root):
        candidate = base / rel_path
        if candidate.is_file():
            return candidate
    # Return default destination in data_dir if not found
    return surface_atlases_data_dir() / rel_path


@dataclass
class AtlasPackDef:
    id: str
    label: str
    description: str
    category: str
    is_default: bool
    asset_filename: str
    compressed_size_bytes: int
    uncompressed_size_bytes: int
    files: list[str]


def _schaefer_pack_files(parcels: int, networks: int) -> list[str]:
    return [
        f"schaefer/{hemi}.Schaefer2018_{parcels}Parcels_{networks}Networks.gcs"
        for hemi in ("lh", "rh")
    ]


def _schaefer_size_estimates(parcels: int) -> tuple[int, int]:
    """Rough download sizes from the shipped 400-parcel reference pack."""
    scale = (parcels / 400) ** 0.75
    compressed = max(500_000, int(8_150_000 * scale))
    uncompressed = max(1_000_000, int(27_232_092 * scale))
    return compressed, uncompressed


def _build_schaefer_packs() -> list[AtlasPackDef]:
    packs: list[AtlasPackDef] = []
    for atlas_key, parcels, networks, _stem in SCHAEFER2018_ATLAS_VARIANTS:
        is_default = atlas_key == "schaefer2018_400parcels_17networks"
        if is_default:
            compressed, uncompressed = 8_150_000, 27_232_092
        else:
            compressed, uncompressed = _schaefer_size_estimates(parcels)
        packs.append(
            AtlasPackDef(
                id=atlas_key,
                label=f"Schaefer 2018 ({parcels} Parcels, {networks} Networks)",
                description=(
                    "Default cortical thickness atlas for FreeSurfer pipelines."
                    if is_default
                    else f"Schaefer 2018 cortical parcellation ({parcels} parcels, {networks} Yeo networks)."
                ),
                category="schaefer",
                is_default=is_default,
                asset_filename=f"atlas-schaefer2018-{parcels}-{networks}.zip",
                compressed_size_bytes=compressed,
                uncompressed_size_bytes=uncompressed,
                files=_schaefer_pack_files(parcels, networks),
            )
        )
    packs.sort(
        key=lambda pack: (
            0 if pack.is_default else 1,
            next(p for key, p, _n, _s in SCHAEFER2018_ATLAS_VARIANTS if key == pack.id),
            next(n for key, _p, n, _s in SCHAEFER2018_ATLAS_VARIANTS if key == pack.id),
        )
    )
    return packs


ATLAS_PACKS: list[AtlasPackDef] = [
    *_build_schaefer_packs(),
    AtlasPackDef(
        id="destrieux",
        label="Destrieux (aparc.a2009s)",
        description="Destrieux 2009 cortical parcellation with 75 labels per hemisphere.",
        category="destrieux",
        is_default=False,
        asset_filename="atlas-destrieux.zip",
        compressed_size_bytes=7700000,
        uncompressed_size_bytes=41154446,
        files=[
            "destrieux/lh.destrieux.simple.2009-07-29.gcs",
            "destrieux/rh.destrieux.simple.2009-07-29.gcs",
        ],
    ),
    AtlasPackDef(
        id="kong2022",
        label="Kong 2022 (200 Parcels)",
        description="Kong 2022 individual-specific cortical parcellation.",
        category="kong",
        is_default=False,
        asset_filename="atlas-kong2022.zip",
        compressed_size_bytes=640000,
        uncompressed_size_bytes=2632073,
        files=[
            "kong/lh.200Parcels_Kong2022_17Networks.annot",
            "kong/rh.200Parcels_Kong2022_17Networks.annot",
        ],
    ),
    AtlasPackDef(
        id="yale",
        label="Yale Brain Atlas (YBA)",
        description="Yale Brodmann and anatomical surface parcellations.",
        category="yale",
        is_default=False,
        asset_filename="atlas-yale.zip",
        compressed_size_bytes=1400000,
        uncompressed_size_bytes=5307906,
        files=[
            "yale/Yale_Brain_Atlas_LH_fsaverage.annot",
            "yale/Yale_Brain_Atlas_RH_fsaverage.annot",
            "yale/YBA_696_LH_fsaverage_new.annot",
            "yale/YBA_696_RH_fsaverage_new.annot",
        ],
    ),
]


class AtlasService:
    def __init__(self, base_download_url: str | None = None) -> None:
        self.base_download_url = base_download_url or DEFAULT_RELEASE_BASE_URL

    def list_packs(self, res_root: Path | None = None) -> list[dict[str, Any]]:
        """Return list of atlas packs with installation status."""
        results: list[dict[str, Any]] = []
        for pack in ATLAS_PACKS:
            missing_files: list[str] = []
            for rel in pack.files:
                resolved = find_surface_atlas_file(rel, res_root)
                if not resolved.is_file():
                    missing_files.append(rel)
            installed = len(missing_files) == 0
            results.append({
                **asdict(pack),
                "installed": installed,
                "missing_files": missing_files,
                "installed_files_count": len(pack.files) - len(missing_files),
                "total_files_count": len(pack.files),
                "download_url": f"{self.base_download_url.rstrip('/')}/{pack.asset_filename}",
            })
        return results

    def get_pack_for_atlas_key(self, atlas_key: str) -> AtlasPackDef | None:
        """Find the matching pack for a specific atlas key e.g. schaefer2018_400parcels_17networks."""
        norm = atlas_key.lower().strip()
        for pack in ATLAS_PACKS:
            if pack.id == norm:
                return pack
        if "destrieux" in norm:
            return next((p for p in ATLAS_PACKS if p.id == "destrieux"), None)
        if "kong" in norm:
            return next((p for p in ATLAS_PACKS if p.id == "kong2022"), None)
        if "yale" in norm:
            return next((p for p in ATLAS_PACKS if p.id == "yale"), None)
        if "schaefer" in norm and "cat12" not in norm:
            return next((p for p in ATLAS_PACKS if p.id == norm), None)
        return None

    def download_pack_stream(self, pack_id: str) -> Generator[dict[str, Any], None, None]:
        """Download an atlas pack with streaming progress events."""
        pack = next((p for p in ATLAS_PACKS if p.id == pack_id), None)
        if not pack:
            yield {"step": "error", "error": f"Unknown atlas pack ID: {pack_id}"}
            return

        target_dir = surface_atlases_data_dir()
        target_dir.mkdir(parents=True, exist_ok=True)

        download_url = f"{self.base_download_url.rstrip('/')}/{pack.asset_filename}"
        yield {
            "step": "start",
            "pack_id": pack_id,
            "label": pack.label,
            "url": download_url,
            "total_bytes": pack.compressed_size_bytes,
        }

        # Download to a temporary file
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
                temp_file = Path(tf.name)

            headers = {"User-Agent": "NeuroFlow-Atlas-Downloader/1.0"}
            req = urllib.request.Request(download_url, headers=headers)

            yield {"step": "connecting", "message": f"Connecting to {download_url}..."}

            with urllib.request.urlopen(req, timeout=30) as response, open(temp_file, "wb") as out_f:
                content_length = response.headers.get("Content-Length")
                total = int(content_length) if content_length else pack.compressed_size_bytes
                downloaded = 0
                chunk_size = 64 * 1024
                last_report = 0

                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_f.write(chunk)
                    downloaded += len(chunk)
                    # Report progress every ~256KB or on completion
                    if downloaded - last_report >= 256 * 1024 or downloaded >= total:
                        pct = int(downloaded * 100 / total) if total > 0 else 0
                        yield {
                            "step": "downloading",
                            "downloaded_bytes": downloaded,
                            "total_bytes": total,
                            "percent": min(pct, 100),
                        }
                        last_report = downloaded

            yield {"step": "extracting", "message": "Extracting atlas files..."}

            # Extract files into target_dir
            with zipfile.ZipFile(temp_file, "r") as zf:
                for member in zf.namelist():
                    # Security check against zip traversal
                    normalized_member = member.replace("\\", "/").strip("/")
                    if ".." in normalized_member or normalized_member.startswith("/"):
                        continue
                    # Extract only intended atlas files
                    dest = target_dir / normalized_member
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            yield {
                "step": "complete",
                "pack_id": pack_id,
                "message": f"Successfully installed {pack.label}",
                "target_dir": str(target_dir),
            }

        except Exception as exc:
            yield {
                "step": "error",
                "error": f"Failed to download atlas pack {pack.label}: {str(exc)}",
            }
        finally:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass

    def import_local_folder(self, source_path: str) -> dict[str, Any]:
        """Import atlas files from a local directory or zip file."""
        src = Path(source_path).expanduser().resolve()
        if not src.exists():
            return {"ok": False, "error": f"Path does not exist: {source_path}"}

        target_dir = surface_atlases_data_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        imported_count = 0

        try:
            if src.is_file() and src.suffix.lower() == ".zip":
                with zipfile.ZipFile(src, "r") as zf:
                    for member in zf.namelist():
                        normalized = member.replace("\\", "/").strip("/")
                        if ".." in normalized or normalized.startswith("/"):
                            continue
                        if normalized.endswith((".gcs", ".annot", ".nii.gz", ".txt")):
                            dest = target_dir / normalized
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            with zf.open(member) as s, open(dest, "wb") as d:
                                shutil.copyfileobj(s, d)
                            imported_count += 1
            elif src.is_dir():
                for root, _, files in os.walk(src):
                    for file in files:
                        if file.endswith((".gcs", ".annot", ".nii.gz", ".txt")):
                            file_p = Path(root) / file
                            # Determine subfolder if known (e.g. schaefer, destrieux, kong, yale)
                            rel_parent = file_p.parent.name.lower()
                            if rel_parent in ("schaefer", "destrieux", "kong", "yale", "mni"):
                                dest = target_dir / rel_parent / file
                            else:
                                # Infer from filename
                                name_lower = file.lower()
                                if "schaefer" in name_lower:
                                    dest = target_dir / "schaefer" / file
                                elif "destrieux" in name_lower:
                                    dest = target_dir / "destrieux" / file
                                elif "kong" in name_lower:
                                    dest = target_dir / "kong" / file
                                elif "yale" in name_lower or "yba" in name_lower:
                                    dest = target_dir / "yale" / file
                                else:
                                    dest = target_dir / file
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(file_p, dest)
                            imported_count += 1
            else:
                return {"ok": False, "error": f"Unsupported source format: {source_path}"}

            return {
                "ok": True,
                "imported_count": imported_count,
                "target_dir": str(target_dir),
                "packs": self.list_packs(),
            }
        except Exception as exc:
            return {"ok": False, "error": f"Import failed: {str(exc)}"}
