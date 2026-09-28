from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app_backend import paths
from pipeline.content_packs import (
    KNOWN_PACK_IDS,
    ContentPackError,
    install_pack_from_local,
    install_pack_from_url,
    list_pack_status,
    parse_pack_index,
    remove_pack,
    decode_signature_blob,
)

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

# Local import of small signed test fixtures (not full proprietary atlases).
MAX_INLINE_ARCHIVE_BYTES = 16 * 1024 * 1024


class ContentPackService:
    """Backend wrapper around signed content-pack install/remove."""

    def __init__(self, data_root: Path | None = None) -> None:
        self.data_root = Path(data_root) if data_root is not None else paths.data_root()

    def list_packs(self) -> dict[str, JsonValue]:
        return {"ok": True, "packs": list_pack_status(data_root=self.data_root)}

    def install(self, payload: dict[str, object]) -> dict[str, JsonValue]:
        pack_id = str(payload.get("pack_id", "") or "").strip()
        if pack_id not in KNOWN_PACK_IDS:
            return {"ok": False, "error": f"Unknown content pack id: {pack_id}"}

        public_key_b64 = payload.get("public_key_b64")
        key = str(public_key_b64) if isinstance(public_key_b64, str) and public_key_b64.strip() else None

        local_archive = str(payload.get("local_archive", "") or "").strip()
        local_index = str(payload.get("local_index", "") or "").strip()
        local_signature = str(payload.get("local_signature", "") or "").strip()
        source_url = str(payload.get("source_url", "") or "").strip()

        try:
            if local_archive:
                if not local_index or not local_signature:
                    return {
                        "ok": False,
                        "error": "local_archive requires local_index and local_signature paths",
                    }
                result = install_pack_from_local(
                    pack_id=pack_id,
                    archive_path=Path(local_archive),
                    index_path=Path(local_index),
                    signature_path=Path(local_signature),
                    data_root=self.data_root,
                    public_key_b64=key,
                )
                return dict(result)

            archive_b64 = str(payload.get("archive_base64", "") or "")
            index_obj = payload.get("index")
            signature_b64 = str(payload.get("signature_base64", "") or "")
            if archive_b64 or index_obj is not None or signature_b64:
                return self._install_inline(
                    pack_id=pack_id,
                    archive_b64=archive_b64,
                    index_obj=index_obj,
                    signature_b64=signature_b64,
                    public_key_b64=key,
                )

            if source_url:
                parsed = urlparse(source_url)
                if parsed.scheme != "https":
                    return {"ok": False, "error": "source_url must be https://"}
                if not isinstance(index_obj, dict):
                    # Allow sibling index/signature fields for URL installs.
                    index_obj = payload.get("index")
                if not isinstance(index_obj, dict):
                    return {"ok": False, "error": "HTTPS install requires a signed index object"}
                if not signature_b64:
                    return {"ok": False, "error": "HTTPS install requires signature_base64"}
                index = parse_pack_index(index_obj)
                result = install_pack_from_url(
                    pack_id=pack_id,
                    index=index,
                    signature=decode_signature_blob(signature_b64),
                    data_root=self.data_root,
                    public_key_b64=key,
                    url=source_url,
                )
                return dict(result)

            return {
                "ok": False,
                "error": "Provide local_archive paths, inline archive_base64, or https source_url",
            }
        except ContentPackError as exc:
            return {"ok": False, "error": str(exc)}
        except (OSError, json.JSONDecodeError, binascii.Error, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    def remove(self, payload: dict[str, object]) -> dict[str, JsonValue]:
        pack_id = str(payload.get("pack_id", "") or "").strip()
        if pack_id not in KNOWN_PACK_IDS:
            return {"ok": False, "error": f"Unknown content pack id: {pack_id}"}
        try:
            return dict(remove_pack(pack_id, data_root=self.data_root))
        except ContentPackError as exc:
            return {"ok": False, "error": str(exc)}

    def _install_inline(
        self,
        *,
        pack_id: str,
        archive_b64: str,
        index_obj: object,
        signature_b64: str,
        public_key_b64: str | None,
    ) -> dict[str, JsonValue]:
        if not isinstance(index_obj, dict):
            return {"ok": False, "error": "index object is required for inline install"}
        if not archive_b64 or not signature_b64:
            return {"ok": False, "error": "archive_base64 and signature_base64 are required"}
        try:
            archive_bytes = base64.b64decode(archive_b64, validate=True)
        except (binascii.Error, ValueError):
            return {"ok": False, "error": "archive_base64 must be valid base64"}
        if len(archive_bytes) > MAX_INLINE_ARCHIVE_BYTES:
            return {"ok": False, "error": "Inline archive exceeds size limit"}

        staging = Path(paths.data_root()) / "content-packs" / pack_id / "staging-inline"
        # Prefer the service data_root for isolation in tests.
        staging = self.data_root / "content-packs" / pack_id / "staging-inline"
        staging.mkdir(parents=True, exist_ok=True)
        archive_path = staging / "archive.zip"
        index_path = staging / "index.json"
        signature_path = staging / "index.json.sig"
        try:
            archive_path.write_bytes(archive_bytes)
            index_path.write_text(json.dumps(index_obj, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            signature_path.write_text(signature_b64.strip(), encoding="utf-8")
            result = install_pack_from_local(
                pack_id=pack_id,
                archive_path=archive_path,
                index_path=index_path,
                signature_path=signature_path,
                data_root=self.data_root,
                public_key_b64=public_key_b64,
                max_archive_bytes=MAX_INLINE_ARCHIVE_BYTES,
                max_unpacked_bytes=MAX_INLINE_ARCHIVE_BYTES,
            )
            return dict(result)
        finally:
            # Best-effort cleanup of inline staging; installed version lives under versions/.
            for path in (archive_path, index_path, signature_path):
                try:
                    path.unlink()
                except OSError:
                    pass
