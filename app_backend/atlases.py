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
from pipeline.config import MNI_ATLAS_DIR, PROJECT_ROOT, SCHAEFER2018_ATLAS_VARIANTS, SURFACE_ATLAS_DIR

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


def mni_atlases_data_dir() -> Path:
    """Writable location for downloaded/imported MNI volume atlases."""
    raw = os.environ.get("NEUROFLOW_MNI_ATLAS_DIR") or os.environ.get("MRI_PIPELINE_MNI_ATLAS_DIR")
    if raw:
        return Path(raw).expanduser()
    return data_root() / "atlases" / "mni"


def candidate_mni_atlas_dirs(res_root: Path | None = None) -> list[Path]:
    """Candidate directories to search for MNI volume atlas assets in order."""
    dirs: list[Path] = [mni_atlases_data_dir()]
    dirs.append(data_root() / "assets" / "atlases" / "mni")
    if res_root is not None:
        dirs.append(Path(res_root) / "assets" / "atlases" / "mni")
    from app_backend.paths import is_frozen
    if not is_frozen() and res_root is None:
        dirs.append(MNI_ATLAS_DIR)
    seen = set()
    result = []
    for d in dirs:
        rp = str(d.resolve()) if d.exists() else str(d)
        if rp not in seen:
            seen.add(rp)
            result.append(d)
    return result


def find_mni_atlas_file(filename: str, res_root: Path | None = None) -> Path:
    """Resolve an MNI volume atlas file path against candidate search paths."""
    clean_name = Path(filename).name
    for base in candidate_mni_atlas_dirs(res_root):
        candidate = base / clean_name
        if candidate.is_file():
            return candidate
    return mni_atlases_data_dir() / clean_name


def sync_mni_atlas_luts_to_data_dir(target_dir: Path | None = None) -> None:
    """Ensure LUT and label text files from source are mirrored into the MNI atlas directory."""
    dest = target_dir or mni_atlases_data_dir()
    dest.mkdir(parents=True, exist_ok=True)
    src_dir = MNI_ATLAS_DIR
    if src_dir.is_dir():
        for txt_file in src_dir.glob("*.txt"):
            target_file = dest / txt_file.name
            if not target_file.exists():
                try:
                    shutil.copy2(txt_file, target_file)
                except OSError:
                    pass


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
    pack_type: str = "surface"


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


MNI_VOLUME_PACK = AtlasPackDef(
    id="mni_volume_pack",
    label="MNI Volume Atlases (Standard Bundle)",
    description=(
        "Standard MNI152 volume atlases for subcortical and cortical volume projection: "
        "Harvard-Oxford (Subcortical & Cortical), Brainnetome 246, AAL3, Juelich, Pauli 2017, Schaefer 2018."
    ),
    category="mni",
    is_default=False,
    asset_filename="atlas-mni-volume-pack.zip",
    compressed_size_bytes=12500000,
    uncompressed_size_bytes=18500000,
    files=[
        "HarvardOxford-subl-maxprob-thr0-1mm.nii.gz",
        "HarvardOxford-cortl-maxprob-thr0-1mm.nii.gz",
        "BN_Atlas_246_1mm.nii.gz",
        "pauli_2017_labels.nii.gz",
        "juelich_maxprob-thr0-1mm.nii.gz",
        "aal.nii.gz",
        "schaefer2018_100_7.nii.gz",
    ],
    pack_type="volume",
)


ATLAS_PACKS: list[AtlasPackDef] = [
    MNI_VOLUME_PACK,
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
                if pack.pack_type == "volume":
                    resolved = find_mni_atlas_file(rel, res_root)
                else:
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
        from pipeline.config import EXTERNAL_MNI_VOLUME_ATLASES
        if norm in EXTERNAL_MNI_VOLUME_ATLASES or any(
            k in norm
            for k in (
                "harvard_oxford",
                "brainnetome",
                "pauli",
                "juelich",
                "aal",
                "schaefer2018_100_7",
            )
        ):
            return next((p for p in ATLAS_PACKS if p.id == "mni_volume_pack"), None)
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

        target_dir = mni_atlases_data_dir() if pack.pack_type == "volume" else surface_atlases_data_dir()
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

            import ssl
            ssl_ctx = None
            try:
                ssl_ctx = ssl.create_default_context()
            except Exception:
                ssl_ctx = ssl._create_unverified_context()

            def _open_req(request: urllib.request.Request):
                try:
                    return urllib.request.urlopen(request, timeout=30, context=ssl_ctx)
                except urllib.error.URLError as u_err:
                    if "CERTIFICATE_VERIFY_FAILED" in str(u_err):
                        unverified = ssl._create_unverified_context()
                        return urllib.request.urlopen(request, timeout=30, context=unverified)
                    raise

            with _open_req(req) as response, open(temp_file, "wb") as out_f:
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
                    if pack.pack_type == "volume":
                        # Volume files (.nii.gz, .txt) belong directly in target_dir
                        dest = target_dir / Path(normalized_member).name
                    else:
                        # Extract only intended atlas files
                        dest = target_dir / normalized_member
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            if pack.pack_type == "volume":
                sync_mni_atlas_luts_to_data_dir(target_dir)

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

        surface_dir = surface_atlases_data_dir()
        surface_dir.mkdir(parents=True, exist_ok=True)
        mni_dir = mni_atlases_data_dir()
        mni_dir.mkdir(parents=True, exist_ok=True)
        imported_count = 0
        volume_imported = False

        try:
            if src.is_file() and src.suffix.lower() == ".zip":
                with zipfile.ZipFile(src, "r") as zf:
                    for member in zf.namelist():
                        normalized = member.replace("\\", "/").strip("/")
                        if ".." in normalized or normalized.startswith("/"):
                            continue
                        name_lower = Path(normalized).name.lower()
                        if normalized.endswith((".gcs", ".annot")):
                            dest = surface_dir / normalized
                        elif normalized.endswith((".nii.gz", ".nii")) or "lut" in name_lower or "mni" in normalized.lower():
                            dest = mni_dir / Path(normalized).name
                            volume_imported = True
                        elif normalized.endswith(".txt"):
                            dest = mni_dir / Path(normalized).name
                            volume_imported = True
                        else:
                            continue
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(member) as s, open(dest, "wb") as d:
                            shutil.copyfileobj(s, d)
                        imported_count += 1
            elif src.is_dir():
                for root, _, files in os.walk(src):
                    for file in files:
                        name_lower = file.lower()
                        if file.endswith((".nii.gz", ".nii")) or "lut" in name_lower or Path(root).name.lower() == "mni":
                            dest = mni_dir / file
                            volume_imported = True
                        elif file.endswith((".gcs", ".annot", ".txt")):
                            file_p = Path(root) / file
                            rel_parent = file_p.parent.name.lower()
                            if rel_parent in ("schaefer", "destrieux", "kong", "yale"):
                                dest = surface_dir / rel_parent / file
                            elif "schaefer" in name_lower:
                                dest = surface_dir / "schaefer" / file
                            elif "destrieux" in name_lower:
                                dest = surface_dir / "destrieux" / file
                            elif "kong" in name_lower:
                                dest = surface_dir / "kong" / file
                            elif "yale" in name_lower or "yba" in name_lower:
                                dest = surface_dir / "yale" / file
                            else:
                                dest = surface_dir / file
                        else:
                            continue
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(Path(root) / file, dest)
                        imported_count += 1
            else:
                return {"ok": False, "error": f"Unsupported source format: {source_path}"}

            if volume_imported:
                sync_mni_atlas_luts_to_data_dir(mni_dir)

            return {
                "ok": True,
                "imported_count": imported_count,
                "target_dir": str(surface_dir),
                "packs": self.list_packs(),
            }
        except Exception as exc:
            return {"ok": False, "error": f"Import failed: {str(exc)}"}

    def remove_pack(self, pack_id: str, res_root: Path | None = None) -> dict[str, Any]:
        """Remove all installed files belonging to an atlas pack."""
        pack = next((p for p in ATLAS_PACKS if p.id == pack_id), None)
        if not pack:
            return {"ok": False, "error": f"Unknown atlas pack ID: {pack_id}"}

        deleted_files: list[str] = []
        errors: list[str] = []

        if pack.pack_type == "volume":
            candidate_dirs = candidate_mni_atlas_dirs(res_root)
            primary_dir = mni_atlases_data_dir()
        else:
            candidate_dirs = candidate_surface_atlas_dirs(res_root)
            primary_dir = surface_atlases_data_dir()

        if primary_dir not in candidate_dirs:
            candidate_dirs.insert(0, primary_dir)

        for rel in pack.files:
            file_name = Path(rel).name if pack.pack_type == "volume" else rel
            for base_dir in candidate_dirs:
                target_file = base_dir / file_name
                if target_file.is_file():
                    try:
                        target_file.unlink()
                        deleted_files.append(str(target_file))
                    except OSError as exc:
                        errors.append(f"Failed to delete {target_file}: {exc}")

                parent = target_file.parent
                if parent.exists() and parent.is_dir() and parent != base_dir:
                    try:
                        if not any(parent.iterdir()):
                            parent.rmdir()
                    except OSError:
                        pass

        if errors:
            return {"ok": False, "error": "; ".join(errors), "deleted_files": deleted_files}

        return {
            "ok": True,
            "pack_id": pack_id,
            "deleted_files": deleted_files,
            "packs": self.list_packs(res_root),
        }
