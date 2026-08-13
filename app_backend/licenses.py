from __future__ import annotations

import base64
import binascii
import re
import time
from pathlib import Path

from app_backend.config_store import ConfigStore

JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

MAX_LICENSE_BYTES = 64 * 1024


class LicenseStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or ConfigStore().config_root / "licenses"

    def save_upload(self, payload: dict[str, object]) -> dict[str, JsonValue]:
        filename = _safe_license_filename(str(payload.get("filename", "license.txt") or "license.txt"))
        content_b64 = str(payload.get("content_base64", "") or "")
        if not content_b64:
            return {"ok": False, "error": "content_base64 is required"}
        try:
            content = base64.b64decode(content_b64, validate=True)
        except (binascii.Error, ValueError):
            return {"ok": False, "error": "content_base64 must be valid base64"}
        if not content:
            return {"ok": False, "error": "License file is empty"}
        if len(content) > MAX_LICENSE_BYTES:
            return {"ok": False, "error": "License file is too large"}

        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{int(time.time() * 1000)}-{filename}"
        path.write_bytes(content)
        return {"ok": True, "path": str(path)}


def _safe_license_filename(filename: str) -> str:
    name = Path(filename).name.strip() or "license.txt"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name or "license.txt"
