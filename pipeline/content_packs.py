"""Signed optional content packs (surface-atlases and future packs).

Pack layout after activation under ``{data_root}/content-packs/<pack_id>/``::

    active.json                 # {"version": "...", "activated_at": "..."}
    versions/<version>/         # verified, read-only-intended tree
      pack-index.json           # canonical index copy used for activation
      manifest.json             # per-file path/size/sha256
      assets/atlases/surface/   # atlas-assets mount
      info/                     # optional feature lists for pack-only atlases
      LICENCES.txt

Installation accepts HTTPS URLs or local file import. Real proprietary atlas
binaries are never fetched by tests; fixtures use synthetic bytes and test keys.
Redistribution rights are still required before shipping real surface-atlases.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Release verification key (Ed25519 raw public key, base64). Matching private key
# is held offline for signing published packs and is intentionally not in-tree.
CONTENT_PACK_ED25519_PUBLIC_KEY_B64 = "qH13nwrU6bkBx7vp09cw9a59CviDG4mnGBlGSwWzNcs="

SURFACE_ATLASES_PACK_ID = "surface-atlases"
KNOWN_PACK_IDS: frozenset[str] = frozenset({SURFACE_ATLASES_PACK_ID})

# Default size caps. Surface atlases are ~577 MiB packed; keep headroom.
DEFAULT_MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_UNPACKED_BYTES = 3 * 1024 * 1024 * 1024
_DOWNLOAD_CHUNK = 1024 * 1024

_SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SAFE_REL_PATH = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")


class ContentPackError(ValueError):
    """Raised when a pack index, archive, or install step is rejected."""


@dataclass(frozen=True)
class PackIndex:
    pack_id: str
    version: str
    product_version: str
    os_list: tuple[str, ...]
    arch_list: tuple[str, ...]
    url: str
    archive_sha256: str
    licences: tuple[str, ...]
    unpacked_size: int
    resource_root_mapping: dict[str, str]
    raw: dict[str, Any]

    @property
    def atlas_assets_rel(self) -> str:
        return self.resource_root_mapping.get("atlas-assets", "assets/atlases/surface")

    @property
    def info_rel(self) -> str:
        return self.resource_root_mapping.get("info", "info")


# Kong 100/300/400 stay out of core VECTOR_SPECS so packaging does not require
# their feature lists. When a surface-atlases pack provides them, availability
# flips via these defs.
SURFACE_ATLASES_PACK_ONLY_ATLASES: dict[str, dict[str, Any]] = {
    "kong2022_100parcels_17networks": {
        "kind": "asset_annot",
        "label": "Kong2022 100 parcels (17 networks)",
        "stat": "cortical_thickness",
        "features": "100Parcels_Kong2022_17Networks_feats.txt",
        "files": {
            "lh": "kong/lh.100Parcels_Kong2022_17Networks.annot",
            "rh": "kong/rh.100Parcels_Kong2022_17Networks.annot",
        },
    },
    "kong2022_300parcels_17networks": {
        "kind": "asset_annot",
        "label": "Kong2022 300 parcels (17 networks)",
        "stat": "cortical_thickness",
        "features": "300Parcels_Kong2022_17Networks_feats.txt",
        "files": {
            "lh": "kong/lh.300Parcels_Kong2022_17Networks.annot",
            "rh": "kong/rh.300Parcels_Kong2022_17Networks.annot",
        },
    },
    "kong2022_400parcels_17networks": {
        "kind": "asset_annot",
        "label": "Kong2022 400 parcels (17 networks)",
        "stat": "cortical_thickness",
        "features": "400Parcels_Kong2022_17Networks_feats.txt",
        "files": {
            "lh": "kong/lh.400Parcels_Kong2022_17Networks.annot",
            "rh": "kong/rh.400Parcels_Kong2022_17Networks.annot",
        },
    },
}

# Files a complete surface-atlases pack is expected to provide (never the two
# orphan Yale annotations without the _new suffix).
SURFACE_ATLASES_EXPECTED_RELATIVE_FILES: tuple[str, ...] = (
    "assets/atlases/surface/destrieux/lh.destrieux.simple.2009-07-29.gcs",
    "assets/atlases/surface/destrieux/rh.destrieux.simple.2009-07-29.gcs",
    "assets/atlases/surface/yale/YBA_696_LH_fsaverage_new.annot",
    "assets/atlases/surface/yale/YBA_696_RH_fsaverage_new.annot",
    "assets/atlases/surface/kong/lh.200Parcels_Kong2022_17Networks.annot",
    "assets/atlases/surface/kong/rh.200Parcels_Kong2022_17Networks.annot",
    # Schaefer variants used by the app (representative set; full pack may add more)
    "assets/atlases/surface/schaefer/lh.Schaefer2018_100Parcels_7Networks.gcs",
    "assets/atlases/surface/schaefer/rh.Schaefer2018_100Parcels_7Networks.gcs",
)


def content_packs_root(data_root: Path | None = None) -> Path:
    if data_root is None:
        from app_backend import paths

        data_root = paths.data_root()
    return Path(data_root) / "content-packs"


def pack_home(pack_id: str, *, data_root: Path | None = None) -> Path:
    _require_known_pack_id(pack_id)
    return content_packs_root(data_root) / pack_id


def active_pack_root(pack_id: str, *, data_root: Path | None = None) -> Path | None:
    """Return the activated version directory, or None if not installed."""
    home = pack_home(pack_id, data_root=data_root)
    active_path = home / "active.json"
    if not active_path.is_file():
        return None
    try:
        payload = json.loads(active_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    version = str(payload.get("version", "") or "")
    if not version or not _SAFE_VERSION.match(version):
        return None
    root = home / "versions" / version
    if not root.is_dir():
        return None
    return root


def active_pack_index(pack_id: str, *, data_root: Path | None = None) -> PackIndex | None:
    root = active_pack_root(pack_id, data_root=data_root)
    if root is None:
        return None
    index_path = root / "pack-index.json"
    if not index_path.is_file():
        return None
    try:
        return parse_pack_index(json.loads(index_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ContentPackError):
        return None


def surface_atlas_assets_root(*, data_root: Path | None = None) -> Path | None:
    """Verified read-only atlas-assets root from the active surface-atlases pack."""
    root = active_pack_root(SURFACE_ATLASES_PACK_ID, data_root=data_root)
    if root is None:
        return None
    index = active_pack_index(SURFACE_ATLASES_PACK_ID, data_root=data_root)
    rel = index.atlas_assets_rel if index is not None else "assets/atlases/surface"
    mapped = root / rel
    return mapped if mapped.is_dir() else root / "assets" / "atlases" / "surface"


def surface_atlas_info_root(*, data_root: Path | None = None) -> Path | None:
    root = active_pack_root(SURFACE_ATLASES_PACK_ID, data_root=data_root)
    if root is None:
        return None
    index = active_pack_index(SURFACE_ATLASES_PACK_ID, data_root=data_root)
    rel = index.info_rel if index is not None else "info"
    mapped = root / rel
    return mapped if mapped.is_dir() else None


def canonical_index_bytes(index: Mapping[str, Any]) -> bytes:
    """Deterministic JSON bytes covered by the detached Ed25519 signature."""
    return json.dumps(index, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def parse_pack_index(raw: Mapping[str, Any]) -> PackIndex:
    pack_id = str(raw.get("pack_id", "") or "")
    _require_known_pack_id(pack_id)
    version = str(raw.get("version", "") or "")
    if not _SAFE_VERSION.match(version):
        raise ContentPackError(f"Invalid pack version: {version!r}")
    product_version = str(raw.get("product_version", "") or "")
    if not product_version.strip():
        raise ContentPackError("product_version is required")
    os_list = _string_tuple(raw.get("os"), field="os")
    arch_list = _string_tuple(raw.get("arch"), field="arch")
    url = str(raw.get("url", "") or "")
    archive_sha256 = str(raw.get("archive_sha256", "") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", archive_sha256):
        raise ContentPackError("archive_sha256 must be a 64-char hex SHA-256")
    licences = _string_tuple(raw.get("licences"), field="licences")
    if not licences:
        raise ContentPackError("licences must list at least one notice")
    try:
        unpacked_size = int(raw.get("unpacked_size", -1))
    except (TypeError, ValueError) as exc:
        raise ContentPackError("unpacked_size must be an integer") from exc
    if unpacked_size < 0:
        raise ContentPackError("unpacked_size must be >= 0")
    mapping_raw = raw.get("resource_root_mapping")
    if not isinstance(mapping_raw, dict) or not mapping_raw:
        raise ContentPackError("resource_root_mapping is required")
    mapping: dict[str, str] = {}
    for key, value in mapping_raw.items():
        key_s = str(key)
        value_s = str(value).replace("\\", "/").strip().lstrip("/")
        if not key_s or not _SAFE_REL_PATH.match(value_s):
            raise ContentPackError(f"Invalid resource_root_mapping entry: {key_s} -> {value_s}")
        mapping[key_s] = value_s
    if "atlas-assets" not in mapping:
        raise ContentPackError("resource_root_mapping must include atlas-assets")
    return PackIndex(
        pack_id=pack_id,
        version=version,
        product_version=product_version,
        os_list=os_list,
        arch_list=arch_list,
        url=url,
        archive_sha256=archive_sha256,
        licences=licences,
        unpacked_size=unpacked_size,
        resource_root_mapping=mapping,
        raw=dict(raw),
    )


def verify_detached_signature(
    payload: bytes,
    signature: bytes,
    *,
    public_key_b64: str | None = None,
) -> None:
    key_b64 = public_key_b64 or os.environ.get("NEUROFLOW_CONTENT_PACK_VERIFY_KEY") or CONTENT_PACK_ED25519_PUBLIC_KEY_B64
    try:
        public_raw = base64.b64decode(key_b64, validate=True)
    except Exception as exc:  # noqa: BLE001 - normalize key errors
        raise ContentPackError("Invalid content-pack public key encoding") from exc
    if len(public_raw) != 32:
        raise ContentPackError("Content-pack public key must be 32 raw Ed25519 bytes")
    if len(signature) != 64:
        raise ContentPackError("Ed25519 signature must be 64 bytes")
    public_key = Ed25519PublicKey.from_public_bytes(public_raw)
    try:
        public_key.verify(signature, payload)
    except InvalidSignature as exc:
        raise ContentPackError("Content-pack signature verification failed") from exc


def decode_signature_blob(raw: str | bytes) -> bytes:
    if isinstance(raw, bytes):
        text = raw.decode("utf-8").strip()
    else:
        text = raw.strip()
    if re.fullmatch(r"[0-9a-fA-F]{128}", text):
        return bytes.fromhex(text)
    try:
        decoded = base64.b64decode(text, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ContentPackError("Signature must be hex or base64") from exc
    if len(decoded) != 64:
        raise ContentPackError("Decoded signature must be 64 bytes")
    return decoded


def sha256_file(path: Path, *, max_bytes: int | None = None) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_DOWNLOAD_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise ContentPackError("File exceeds size limit while hashing")
            digest.update(chunk)
    return digest.hexdigest()


def list_pack_status(*, data_root: Path | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pack_id in sorted(KNOWN_PACK_IDS):
        index = active_pack_index(pack_id, data_root=data_root)
        root = active_pack_root(pack_id, data_root=data_root)
        rows.append(
            {
                "pack_id": pack_id,
                "known": True,
                "installed": root is not None,
                "version": index.version if index else None,
                "product_version": index.product_version if index else None,
                "licences": list(index.licences) if index else [],
                "unpacked_size": index.unpacked_size if index else None,
                "root": str(root) if root else None,
                "resource_root_mapping": dict(index.resource_root_mapping) if index else {},
                "redistribution_note": (
                    "Redistribution rights are still required before shipping real "
                    "surface-atlases proprietary binaries."
                    if pack_id == SURFACE_ATLASES_PACK_ID
                    else None
                ),
            }
        )
    return rows


def install_pack_from_local(
    *,
    pack_id: str,
    archive_path: Path,
    index_path: Path,
    signature_path: Path,
    data_root: Path | None = None,
    public_key_b64: str | None = None,
    max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
    max_unpacked_bytes: int = DEFAULT_MAX_UNPACKED_BYTES,
) -> dict[str, Any]:
    """Install a pack from local archive + index + detached signature files."""
    _require_known_pack_id(pack_id)
    archive_path = Path(archive_path)
    index_path = Path(index_path)
    signature_path = Path(signature_path)
    if not archive_path.is_file():
        raise ContentPackError(f"Archive not found: {archive_path}")
    if not index_path.is_file():
        raise ContentPackError(f"Index not found: {index_path}")
    if not signature_path.is_file():
        raise ContentPackError(f"Signature not found: {signature_path}")

    index_raw = json.loads(index_path.read_text(encoding="utf-8"))
    index = parse_pack_index(index_raw)
    if index.pack_id != pack_id:
        raise ContentPackError(f"Pack id mismatch: expected {pack_id}, got {index.pack_id}")
    verify_detached_signature(
        canonical_index_bytes(index_raw),
        decode_signature_blob(signature_path.read_bytes()),
        public_key_b64=public_key_b64,
    )

    archive_size = archive_path.stat().st_size
    if archive_size > max_archive_bytes:
        raise ContentPackError("Archive exceeds size limit")
    if index.unpacked_size > max_unpacked_bytes:
        raise ContentPackError("Declared unpacked_size exceeds limit")

    home = pack_home(pack_id, data_root=data_root)
    home.mkdir(parents=True, exist_ok=True)
    staging_parent = home / "staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    # Same-filesystem staging beside versions/ for atomic replace.
    staging = Path(tempfile.mkdtemp(prefix="pack-", dir=str(staging_parent)))
    part_path = staging / "archive.zip.part"
    try:
        _stream_copy(archive_path, part_path, max_bytes=max_archive_bytes)
        digest = sha256_file(part_path, max_bytes=max_archive_bytes)
        if digest != index.archive_sha256:
            raise ContentPackError("Archive SHA-256 does not match signed index")
        final_archive = staging / "archive.zip"
        part_path.replace(final_archive)
        extract_root = staging / "extract"
        extract_root.mkdir()
        _extract_verified_archive(
            final_archive,
            extract_root,
            expected_unpacked_size=index.unpacked_size,
            max_unpacked_bytes=max_unpacked_bytes,
        )
        # Persist index inside the version tree for later mounts.
        (extract_root / "pack-index.json").write_text(
            json.dumps(index_raw, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        version_dir = home / "versions" / index.version
        previous = active_pack_root(pack_id, data_root=data_root)
        previous_active = None
        active_file = home / "active.json"
        if active_file.is_file():
            previous_active = active_file.read_text(encoding="utf-8")

        if version_dir.exists():
            shutil.rmtree(version_dir)
        version_dir.parent.mkdir(parents=True, exist_ok=True)
        extract_root.replace(version_dir)

        active_payload = {
            "version": index.version,
            "activated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pack_id": pack_id,
        }
        tmp_active = home / "active.json.part"
        tmp_active.write_text(json.dumps(active_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        tmp_active.replace(active_file)
        return {
            "ok": True,
            "pack_id": pack_id,
            "version": index.version,
            "root": str(version_dir),
            "previous_version": Path(previous).name if previous else None,
            "previous_active_preserved_on_disk": previous_active is not None,
        }
    except Exception:
        # Keep previous activation intact; staging is discarded below.
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def install_pack_from_url(
    *,
    pack_id: str,
    index: Mapping[str, Any] | PackIndex,
    signature: bytes,
    data_root: Path | None = None,
    public_key_b64: str | None = None,
    url: str | None = None,
    max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
    max_unpacked_bytes: int = DEFAULT_MAX_UNPACKED_BYTES,
    opener: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Download a pack archive over HTTPS and install it after verification."""
    _require_known_pack_id(pack_id)
    index_obj = index if isinstance(index, PackIndex) else parse_pack_index(index)
    index_raw = index_obj.raw
    if index_obj.pack_id != pack_id:
        raise ContentPackError(f"Pack id mismatch: expected {pack_id}, got {index_obj.pack_id}")
    verify_detached_signature(
        canonical_index_bytes(index_raw),
        signature,
        public_key_b64=public_key_b64,
    )
    download_url = url or index_obj.url
    if not download_url.startswith("https://"):
        raise ContentPackError("Remote pack installs require an https:// URL")

    home = pack_home(pack_id, data_root=data_root)
    home.mkdir(parents=True, exist_ok=True)
    staging_parent = home / "staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="pack-", dir=str(staging_parent)))
    part_path = staging / "archive.zip.part"
    try:
        _download_https(download_url, part_path, max_bytes=max_archive_bytes, opener=opener)
        digest = sha256_file(part_path, max_bytes=max_archive_bytes)
        if digest != index_obj.archive_sha256:
            raise ContentPackError("Archive SHA-256 does not match signed index")
        # Reuse local installer path by writing index/sig beside the archive.
        index_path = staging / "index.json"
        sig_path = staging / "index.json.sig"
        index_path.write_text(json.dumps(index_raw, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        sig_path.write_bytes(base64.b64encode(signature))
        final_archive = staging / "download.zip"
        part_path.replace(final_archive)
        return install_pack_from_local(
            pack_id=pack_id,
            archive_path=final_archive,
            index_path=index_path,
            signature_path=sig_path,
            data_root=data_root,
            public_key_b64=public_key_b64,
            max_archive_bytes=max_archive_bytes,
            max_unpacked_bytes=max_unpacked_bytes,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def remove_pack(pack_id: str, *, data_root: Path | None = None) -> dict[str, Any]:
    """Remove an installed pack without touching user outputs or secrets."""
    _require_known_pack_id(pack_id)
    home = pack_home(pack_id, data_root=data_root)
    if not home.exists():
        return {"ok": True, "pack_id": pack_id, "removed": False, "reason": "not_installed"}
    active = home / "active.json"
    if active.exists():
        active.unlink()
    versions = home / "versions"
    if versions.exists():
        shutil.rmtree(versions)
    staging = home / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    # Leave empty home directory removable if vacant.
    try:
        home.rmdir()
    except OSError:
        pass
    return {"ok": True, "pack_id": pack_id, "removed": True}


def _extract_verified_archive(
    archive_path: Path,
    destination: Path,
    *,
    expected_unpacked_size: int,
    max_unpacked_bytes: int,
) -> None:
    try:
        with zipfile.ZipFile(archive_path) as zf:
            names = zf.namelist()
            if not names:
                raise ContentPackError("Archive is empty")
            if len(names) != len(set(names)):
                raise ContentPackError("Archive contains duplicate member names")

            manifest_info = None
            try:
                manifest_info = zf.getinfo("manifest.json")
            except KeyError as exc:
                raise ContentPackError("Archive missing manifest.json") from exc
            if _zipinfo_is_symlink(manifest_info):
                raise ContentPackError("manifest.json must not be a symlink")

            manifest_raw = json.loads(zf.read(manifest_info))
            files = manifest_raw.get("files")
            if not isinstance(files, list) or not files:
                raise ContentPackError("manifest.json files list is required")

            expected: dict[str, tuple[int, str]] = {}
            for entry in files:
                if not isinstance(entry, dict):
                    raise ContentPackError("manifest file entries must be objects")
                rel = str(entry.get("path", "") or "").replace("\\", "/").lstrip("/")
                if not _SAFE_REL_PATH.match(rel):
                    raise ContentPackError(f"Illegal manifest path: {rel}")
                if rel in expected:
                    raise ContentPackError(f"Duplicate manifest path: {rel}")
                if rel == "manifest.json":
                    raise ContentPackError("manifest.json must not list itself")
                try:
                    size = int(entry.get("size", -1))
                except (TypeError, ValueError) as exc:
                    raise ContentPackError(f"Invalid size for {rel}") from exc
                digest = str(entry.get("sha256", "") or "").lower()
                if size < 0 or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ContentPackError(f"Invalid size/sha256 for {rel}")
                expected[rel] = (size, digest)

            member_files = []
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                if name.endswith("/"):
                    continue
                if name == "manifest.json":
                    continue
                if _zipinfo_is_symlink(info):
                    raise ContentPackError(f"Symlinks are not allowed: {name}")
                if name != name.lstrip("/") or ".." in Path(name).parts:
                    raise ContentPackError(f"Illegal archive member path: {name}")
                if not _SAFE_REL_PATH.match(name):
                    raise ContentPackError(f"Illegal archive member path: {name}")
                member_files.append(info)

            member_names = {info.filename.replace("\\", "/") for info in member_files}
            if member_names != set(expected):
                raise ContentPackError(
                    "Archive members do not match manifest.json "
                    f"(extra={sorted(member_names - set(expected))}, "
                    f"missing={sorted(set(expected) - member_names)})"
                )

            total_unpacked = 0
            for info in member_files:
                name = info.filename.replace("\\", "/")
                size, digest = expected[name]
                if info.file_size != size:
                    raise ContentPackError(f"Size mismatch for {name}")
                total_unpacked += size
                if total_unpacked > max_unpacked_bytes:
                    raise ContentPackError("Unpacked size exceeds limit (compression bomb guard)")
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, target.open("wb") as dst:
                    hasher = hashlib.sha256()
                    remaining = size
                    while remaining > 0:
                        chunk = src.read(min(_DOWNLOAD_CHUNK, remaining))
                        if not chunk:
                            raise ContentPackError(f"Truncated archive member: {name}")
                        remaining -= len(chunk)
                        hasher.update(chunk)
                        dst.write(chunk)
                if hasher.hexdigest() != digest:
                    raise ContentPackError(f"SHA-256 mismatch for {name}")

            if total_unpacked != expected_unpacked_size:
                raise ContentPackError(
                    f"Unpacked size {total_unpacked} does not match index unpacked_size {expected_unpacked_size}"
                )

            # Write manifest into the tree for introspection.
            (destination / "manifest.json").write_text(
                json.dumps(manifest_raw, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
    except zipfile.BadZipFile as exc:
        raise ContentPackError("Archive is not a valid zip") from exc


def _zipinfo_is_symlink(info: zipfile.ZipInfo) -> bool:
    # Unix symlink: external attributes create mode << 16; symlink is 0o120000.
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def _stream_copy(source: Path, destination: Path, *, max_bytes: int) -> None:
    total = 0
    with source.open("rb") as src, destination.open("wb") as dst:
        while True:
            chunk = src.read(_DOWNLOAD_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ContentPackError("Archive exceeds size limit")
            dst.write(chunk)


def _download_https(
    url: str,
    destination: Path,
    *,
    max_bytes: int,
    opener: Callable[[str], Any] | None = None,
) -> None:
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(url) as response:
            total = 0
            with destination.open("wb") as dst:
                while True:
                    chunk = response.read(_DOWNLOAD_CHUNK)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise ContentPackError("Download exceeds size limit")
                    dst.write(chunk)
    except ContentPackError:
        raise
    except (urllib.error.URLError, OSError) as exc:
        raise ContentPackError(f"Failed to download pack: {exc}") from exc


def _require_known_pack_id(pack_id: str) -> None:
    if pack_id not in KNOWN_PACK_IDS:
        raise ContentPackError(f"Unknown content pack id: {pack_id}")


def _string_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ContentPackError(f"{field} must be a non-empty list")
    items = tuple(str(item) for item in value)
    if any(not item.strip() for item in items):
        raise ContentPackError(f"{field} entries must be non-empty strings")
    return items
