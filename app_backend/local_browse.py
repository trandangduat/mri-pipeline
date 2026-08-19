"""Local filesystem batch scanning for the MRI Pipeline desktop app.

Provides the same response shape as ``remote.browse_path`` so the
frontend can reuse the same ``RemoteBrowseEntry`` / ``RemoteBrowseResponse``
schemas for both local and server sources.
"""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import TypeAlias

from pipeline.discovery import (
    DICOM_FILE_EXTENSIONS,
    VOLUME_FILE_EXTENSIONS,
    _dicom_files_in_series,
    _is_dicom_file,
    _is_dicom_series_dir,
)

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

_IMAGE_EXTENSIONS = (*VOLUME_FILE_EXTENSIONS, *DICOM_FILE_EXTENSIONS)
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
        max_depth = max(0, min(int(raw_depth), _BATCH_MAX_DEPTH))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        max_depth = 1

    candidates: list[dict[str, JsonValue]] = []

    # If scan_root itself is a DICOM series directory, emit it as a single candidate
    scan_root_path = Path(scan_root)
    if is_dir and _is_dicom_series_dir(scan_root_path):
        dicom_files = _dicom_files_in_series(scan_root_path)
        total_size = 0
        latest_mtime: int | None = None
        for f in dicom_files:
            try:
                st = f.stat()
                total_size += int(st.st_size)
                mtime = int(st.st_mtime)
                if latest_mtime is None or mtime > latest_mtime:
                    latest_mtime = mtime
            except OSError:
                pass
        name = os.path.basename(scan_root)
        candidates.append({
            "name": name,
            "path": scan_root,
            "kind": "file",
            "size": total_size,
            "modified_at": latest_mtime,
            "selectable": True,
            "relative_path": name,
            "subject_label": name,
            "depth": 0,
            "parent": os.path.dirname(scan_root),
            "is_dicom_series": True,
            "slice_count": len(dicom_files),
        })
        return {
            "ok": True,
            "path": scan_root,
            "parent": os.path.dirname(scan_root),
            "entries": candidates,
            "image_count": 1,
            "is_batch_scan": True,
            "has_multi_subject_conflict": False,
        }

    def _recurse(current_dir: str, depth: int, subject_hint: str | None) -> None:
        if len(candidates) >= _BATCH_CANDIDATE_LIMIT:
            return
        try:
            with os.scandir(current_dir) as it:
                entries = sorted(list(it), key=lambda e: e.name.lower())
        except OSError:
            return
        for entry in entries:
            if len(candidates) >= _BATCH_CANDIDATE_LIMIT:
                return
            name = entry.name
            if not name or "\x00" in name:
                continue
            entry_path = entry.path
            entry_path_obj = Path(entry_path)
            if entry.is_dir(follow_symlinks=False):
                if _is_dicom_series_dir(entry_path_obj):
                    dicom_files = _dicom_files_in_series(entry_path_obj)
                    total_size = 0
                    latest_mtime: int | None = None
                    for f in dicom_files:
                        try:
                            st = f.stat()
                            total_size += int(st.st_size)
                            mtime = int(st.st_mtime)
                            if latest_mtime is None or mtime > latest_mtime:
                                latest_mtime = mtime
                        except OSError:
                            pass
                    rel = os.path.relpath(entry_path, scan_root).replace(os.sep, "/")
                    label = name if depth == 0 else (subject_hint or os.path.basename(current_dir))
                    candidates.append({
                        "name": name,
                        "path": entry_path,
                        "kind": "file",
                        "size": total_size,
                        "modified_at": latest_mtime,
                        "selectable": True,
                        "relative_path": rel,
                        "subject_label": label,
                        "depth": depth,
                        "parent": current_dir,
                        "is_dicom_series": True,
                        "slice_count": len(dicom_files),
                    })
                elif depth < max_depth:
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
                        "is_dicom_series": False,
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
