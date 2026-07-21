from __future__ import annotations

import os
import re
from pathlib import Path

from .utils import _file_stem

VOLUME_FILE_EXTENSIONS = (".nii.gz", ".nii", ".mgz", ".mgh")
DICOM_FILE_EXTENSIONS = (".dcm", ".dicom", ".ima")
MRI_FILE_EXTENSIONS = (*VOLUME_FILE_EXTENSIONS, *DICOM_FILE_EXTENSIONS)

_GENERIC_BASENAMES = frozenset({
    "001", "002", "003", "image", "images", "scan", "brain", "t1", "t1w", "t2", "flair", "data",
})

def _default_subject_id(input_file: str) -> str:
    return _file_stem(Path(input_file).name)

def _is_generic_basename(filename: str) -> bool:
    stem = _file_stem(filename).lower()
    if stem in _GENERIC_BASENAMES:
        return True
    return bool(re.fullmatch(r"\d{1,6}", stem))

def _sanitize_subject_id(raw: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    if not safe:
        safe = "subject"
    if not safe[0].isalnum():
        safe = f"mri_{safe}"
    return safe[:200]

def _duplicate_basenames(files: list[str]) -> set[str]:
    counts: dict[str, int] = {}
    for f in files:
        name = Path(f).name
        counts[name] = counts.get(name, 0) + 1
    return {name for name, n in counts.items() if n > 1}

def _derive_subject_id(input_file: str, dataset_root: str = "", duplicate_basenames: set[str] | None = None) -> str:
    path = Path(input_file).expanduser().resolve()
    dup_names = duplicate_basenames or set()
    use_path = path.name in dup_names or _is_generic_basename(path.name)

    if dataset_root:
        try:
            rel = path.relative_to(Path(dataset_root).expanduser().resolve())
            if len(rel.parts) > 1:
                return _sanitize_subject_id("__".join(rel.with_suffix("").parts))
        except ValueError:
            pass

    if use_path and path.parent.name:
        return _sanitize_subject_id(path.parent.name)

    return _sanitize_subject_id(_default_subject_id(str(path)))

def build_subject_id_map(files: list[str], dataset_root: str) -> dict[str, str]:
    dup_names = _duplicate_basenames(files)
    used: set[str] = set()
    out: dict[str, str] = {}
    for f in sorted(files):
        base = _derive_subject_id(f, dataset_root, dup_names)
        sid = base
        counter = 2
        while sid in used:
            sid = f"{base}_{counter}"
            counter += 1
        used.add(sid)
        out[f] = sid
    return out

def _has_dicom_magic(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            header = f.read(132)
        return len(header) >= 132 and header[128:132] == b"DICM"
    except OSError:
        return False

def _is_dicom_file(path: Path) -> bool:
    lower = path.name.lower()
    if lower.endswith(DICOM_FILE_EXTENSIONS):
        return True
    return path.suffix == "" and _has_dicom_magic(path)

def _is_supported_mri_file(path: Path) -> bool:
    return path.name.lower().endswith(VOLUME_FILE_EXTENSIONS) or _is_dicom_file(path)

def _is_dicom_series_dir(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    try:
        return any(child.is_file() and _is_dicom_file(child) for child in path.iterdir())
    except OSError:
        return False

def _dicom_files_in_series(path: Path) -> list[Path]:
    if not path.exists() or not path.is_dir():
        return []
    try:
        return [child for child in sorted(path.iterdir(), key=lambda p: p.name.lower()) if child.is_file() and _is_dicom_file(child)]
    except OSError:
        return []

def _first_dicom_file_in_series(path: Path) -> Path | None:
    files = _dicom_files_in_series(path)
    return files[0] if files else None

def _is_supported_mri_input(path: str | Path) -> bool:
    p = Path(path).expanduser()
    if p.is_file():
        return _is_supported_mri_file(p)
    return _is_dicom_series_dir(p)

def _discover_mri_files(input_dir: str, recursive: bool = True) -> list[str]:
    root = Path(input_dir).expanduser()
    if not root.exists() or not root.is_dir():
        return []
    results: list[str] = []

    def scan_dir(directory: Path) -> None:
        if _is_dicom_series_dir(directory):
            results.append(str(directory))
            return
        try:
            children = sorted(directory.iterdir(), key=lambda p: p.as_posix().lower())
        except OSError:
            return
        for child in children:
            if child.is_file() and _is_supported_mri_file(child):
                results.append(str(child))
            elif recursive and child.is_dir():
                scan_dir(child)

    if recursive:
        scan_dir(root)
    else:
        if _is_dicom_series_dir(root):
            return [str(root)]
        try:
            children = sorted(root.iterdir(), key=lambda p: p.as_posix().lower())
        except OSError:
            return []
        for child in children:
            if child.is_file() and _is_supported_mri_file(child):
                results.append(str(child))
            elif child.is_dir() and _is_dicom_series_dir(child):
                results.append(str(child))
    return results

