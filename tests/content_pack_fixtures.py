"""Helpers to build tiny synthetic signed content-pack fixtures for tests."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Iterable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pipeline.content_packs import (
    SURFACE_ATLASES_PACK_ID,
    SURFACE_ATLASES_PACK_ONLY_ATLASES,
    canonical_index_bytes,
)

# Dedicated test keypair (NOT the release key). Safe to embed in tests only.
TEST_CONTENT_PACK_PRIVATE_KEY_B64 = "+ldveCXkfUWPgV0FQBIqdHfj5Kd5OScLR08Oxl8o3/c="
TEST_CONTENT_PACK_PUBLIC_KEY_B64 = "uDWRcilpqcG54C39AM5icp3r6e0qZGWMO0jtend5fqs="


def test_private_key() -> Ed25519PrivateKey:
    raw = base64.b64decode(TEST_CONTENT_PACK_PRIVATE_KEY_B64)
    return Ed25519PrivateKey.from_private_bytes(raw)


def build_surface_atlases_fixture_files(
    dest_dir: Path,
    *,
    version: str = "0.0.1-test",
    include_kong_pack_only: bool = True,
    tamper_archive: bool = False,
) -> dict[str, Path]:
    """Create index.json, index.json.sig, and archive.zip under dest_dir."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, bytes] = {
        "LICENCES.txt": b"Synthetic test fixture. Not for redistribution of real atlases.\n",
        "assets/atlases/surface/destrieux/lh.destrieux.simple.2009-07-29.gcs": b"destrieux-lh\n",
        "assets/atlases/surface/destrieux/rh.destrieux.simple.2009-07-29.gcs": b"destrieux-rh\n",
        "assets/atlases/surface/yale/YBA_696_LH_fsaverage_new.annot": b"yale-lh-new\n",
        "assets/atlases/surface/yale/YBA_696_RH_fsaverage_new.annot": b"yale-rh-new\n",
        "assets/atlases/surface/kong/lh.200Parcels_Kong2022_17Networks.annot": b"kong200-lh\n",
        "assets/atlases/surface/kong/rh.200Parcels_Kong2022_17Networks.annot": b"kong200-rh\n",
        "assets/atlases/surface/schaefer/lh.Schaefer2018_100Parcels_7Networks.gcs": b"schaefer-lh\n",
        "assets/atlases/surface/schaefer/rh.Schaefer2018_100Parcels_7Networks.gcs": b"schaefer-rh\n",
    }
    if include_kong_pack_only:
        for atlas_key, defn in SURFACE_ATLASES_PACK_ONLY_ATLASES.items():
            features = str(defn["features"])
            files[f"info/{features}"] = f"feat-{atlas_key}\n".encode()
            for rel in defn["files"].values():
                files[f"assets/atlases/surface/{rel}"] = f"bytes-{rel}\n".encode()

    manifest_files = []
    unpacked = 0
    for rel, payload in sorted(files.items()):
        digest = hashlib.sha256(payload).hexdigest()
        manifest_files.append({"path": rel, "size": len(payload), "sha256": digest})
        unpacked += len(payload)

    manifest = {
        "pack_id": SURFACE_ATLASES_PACK_ID,
        "version": version,
        "files": manifest_files,
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, sort_keys=True, separators=(",", ":")))
        for rel, payload in sorted(files.items()):
            zf.writestr(rel, payload)
    archive_bytes = buf.getvalue()
    archive_sha = hashlib.sha256(archive_bytes).hexdigest()
    if tamper_archive:
        # Keep the signed index digest pointing at the honest archive, then
        # corrupt the on-disk bytes so install must reject the mismatch.
        archive_bytes = archive_bytes[:-5] + b"TAMPR"
    index = {
        "pack_id": SURFACE_ATLASES_PACK_ID,
        "version": version,
        "product_version": ">=0.1.0",
        "os": ["windows", "linux", "darwin"],
        "arch": ["x86_64", "arm64"],
        "url": "https://example.invalid/packs/surface-atlases-test.zip",
        "archive_sha256": archive_sha,
        "licences": [
            "Synthetic test fixture only. Redistribution rights required before shipping real surface-atlases binaries."
        ],
        "unpacked_size": unpacked,
        "resource_root_mapping": {
            "atlas-assets": "assets/atlases/surface",
            "info": "info",
        },
    }

    index_path = dest_dir / "index.json"
    archive_path = dest_dir / "archive.zip"
    signature_path = dest_dir / "index.json.sig"
    index_path.write_text(json.dumps(index, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    archive_path.write_bytes(archive_bytes)
    signature = test_private_key().sign(canonical_index_bytes(index))
    signature_path.write_text(base64.b64encode(signature).decode("ascii"), encoding="utf-8")
    return {
        "index": index_path,
        "archive": archive_path,
        "signature": signature_path,
    }
