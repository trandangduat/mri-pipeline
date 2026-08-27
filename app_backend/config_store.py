from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypeAlias

from app_backend import paths
from pipeline.jobs import read_json, write_json

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


class ConfigStore:
    def __init__(self, config_root: str | Path | None = None) -> None:
        self.config_root = Path(config_root) if config_root is not None else paths.config_root()

    def save_workspace(self, name: str, data: dict[str, object]) -> dict[str, JsonValue]:
        return self._save("workspaces", "mri-pipeline-workspace", name, data)

    def load_workspace(self, name: str) -> dict[str, JsonValue]:
        return self._load("workspaces", name)

    def list_workspaces(self) -> dict[str, JsonValue]:
        return self._list("workspaces")

    def save_preset(self, name: str, data: dict[str, object]) -> dict[str, JsonValue]:
        return self._save("preset", "mri-pipeline-preset", name, data)

    def load_preset(self, name: str) -> dict[str, JsonValue]:
        return self._load("preset", name)

    def list_presets(self) -> dict[str, JsonValue]:
        return self._list("preset")

    def export_json(self, path: str, data: dict[str, object]) -> dict[str, JsonValue]:
        raw = str(path or "").strip()
        if not raw:
            return {"ok": False, "error": "Export path is required"}
        target = Path(raw).expanduser()
        if target.suffix.lower() != ".json":
            target = target.with_name(target.name + ".json")
        payload = redact_passwords(_json_dict(data))
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            write_json(target, payload)
        except OSError as exc:
            return {"ok": False, "error": f"Could not write file: {exc}"}
        return {"ok": True, "path": str(target)}

    def _save(self, subdir: str, config_type: str, name: str, data: dict[str, object]) -> dict[str, JsonValue]:
        config_name = _sanitize_name(name)
        if not config_name:
            return {"ok": False, "error": "Invalid config name"}
        path = self._path(subdir, config_name)
        if path is None:
            return {"ok": False, "error": "Invalid config name"}
        payload = redact_passwords(_json_dict(data))
        payload["type"] = config_type
        payload["name"] = config_name
        write_json(path, payload)
        return {"ok": True, "name": config_name, "path": str(path)}

    def _load(self, subdir: str, name: str) -> dict[str, JsonValue]:
        config_name = _sanitize_name(name)
        if not config_name:
            return {"ok": False, "error": "Invalid config name"}
        path = self._path(subdir, config_name)
        if path is None:
            return {"ok": False, "error": "Invalid config name"}
        if not path.exists():
            return {"ok": False, "error": "Config not found"}
        return {"ok": True, "name": config_name, "path": str(path), "data": _json_dict(read_json(path, {}))}

    def _list(self, subdir: str) -> dict[str, JsonValue]:
        folder = self.config_root / subdir
        if not folder.exists():
            return {"ok": True, "items": []}
        root = self.config_root.resolve()
        items: list[JsonValue] = []
        for path in sorted(folder.glob("*.json"), key=lambda item: item.name.lower()):
            resolved = path.resolve()
            if not _is_relative_to(resolved, root):
                continue
            items.append({"name": path.stem, "path": str(path)})
        return {"ok": True, "items": items}

    def _path(self, subdir: str, name: str) -> Path | None:
        path = self.config_root / subdir / f"{name}.json"
        root = self.config_root.resolve()
        resolved = path.resolve(strict=False)
        if not _is_relative_to(resolved, root):
            return None
        return path


def _sanitize_name(name: str) -> str:
    raw = str(name or "").strip()
    if not raw or "/" in raw or "\\" in raw or ".." in raw:
        return ""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    return safe[:120]


def redact_passwords(value: JsonValue) -> JsonValue:
    if isinstance(value, list):
        return [redact_passwords(item) for item in value]
    if isinstance(value, dict):
        redacted: dict[str, JsonValue] = {}
        for key, item in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized == "password" or normalized.endswith("password") or normalized.endswith("_password"):
                continue
            redacted[key] = redact_passwords(item)
        return redacted
    return value


def _json_dict(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _json_value(item) for key, item in value.items()}


def _json_value(value: object) -> JsonValue:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
