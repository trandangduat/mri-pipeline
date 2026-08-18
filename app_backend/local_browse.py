"""Local filesystem batch scanning for the MRI Pipeline desktop app.

Provides the same response shape as ``remote.browse_path`` so the
frontend can reuse the same ``RemoteBrowseEntry`` / ``RemoteBrowseResponse``
schemas for both local and server sources.
"""

from __future__ import annotations

import os
import posixpath
from collections import Counter
from typing import TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

_IMAGE_EXTENSIONS = (".nii", ".nii.gz", ".mgz", ".mgh", ".dcm", ".dicom")
_BATCH_CANDIDATE_LIMIT = 1000
_BATCH_MAX_DEPTH = 6


def _is_image_file(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(ext) for ext in _IMAGE_EXTENSIONS)


def _file_stem(name: str) -> str:
    """Return filename without any known image extension."""
    lower = name.lower()
    for ext in sorted(_IMAGE_EXTENSIONS, key=len, reverse=True):
        if lower.endswith(ext):
            return name[: -len(ext)]
    dot = name.rfind(".")
    return name[:dot] if dot > 0 else name


def browse_local_path(data: dict[str, object]) -> dict[str, JsonValue]:
    """Scan a local directory for image-file candidates.

    Request fields:
      path      – local directory to scan (required)
      max_depth – int; 0 = direct files only, 1 = one level of subdirs, …
    """
    raw_path = str(data.get("path", "") or "").strip()
    if not raw_path:
        return {"ok": False, "error": "path is required"}
    if "\x00" in raw_path:
        return {"ok": False, "error": "Invalid path"}

    expanded = os.path.expanduser(raw_path)
    expanded = os.path.realpath(expanded)

    if not os.path.exists(expanded):
        return {"ok": False, "error": f"Path not found: {expanded}"}

    is_dir = os.path.isdir(expanded)
    scan_root = expanded if is_dir else os.path.dirname(expanded)

    raw_depth = data.get("max_depth")
    try:
        max_depth = max(0, min(int(raw_depth), _BATCH_CANDIDATE_LIMIT))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        max_depth = 1

    candidates: list[dict[str, JsonValue]] = []

    def _recurse(current_dir: str, depth: int, subject_hint: str | None) -> None:
        if len(candidates) >= _BATCH_CANDIDATE_LIMIT:
            return
        try:
            entries = os.scandir(current_dir)
        except OSError:
            return
        with entries:
            for entry in entries:
                if len(candidates) >= _BATCH_CANDIDATE_LIMIT:
                    return
                name = entry.name
                if not name or "\x00" in name:
                    continue
                entry_path = entry.path
                if entry.is_dir(follow_symlinks=False):
                    if depth < max_depth:
                        label = name if depth == 0 else subject_hint
                        _recurse(entry_path, depth + 1, label)
                else:
                    if _is_image_file(name):
                        rel = os.path.relpath(entry_path, scan_root).replace(os.sep, "/")
                        if depth == 0:
                            label = _file_stem(name)
                        else:
                            label = subject_hint or os.path.basename(current_dir)
                        try:
                            stat = entry.stat(follow_symlinks=False)
                            size = int(stat.st_size)
                            modified_at = int(stat.st_mtime)
                        except OSError:
                            size = 0
                            modified_at = None
                        candidates.append({
                            "name": name,
                            "path": entry_path,
                            "kind": "file",
                            "size": size,
                            "modified_at": modified_at,
                            "selectable": True,
                            "relative_path": rel,
                            "subject_label": label,
                            "depth": depth,
                            "parent": current_dir,
                        })

    _recurse(scan_root, 0, None)

    candidates.sort(key=lambda e: (str(e.get("subject_label", "")).lower(), str(e["name"]).lower()))

    label_counts: Counter[str] = Counter(str(e.get("subject_label", "")) for e in candidates)
    has_multi_subject_conflict = any(v > 1 for v in label_counts.values())

    return {
        "ok": True,
        "path": scan_root,
        "parent": os.path.dirname(scan_root),
        "entries": candidates,
        "image_count": len(candidates),
        "is_batch_scan": True,
        "has_multi_subject_conflict": has_multi_subject_conflict,
    }
