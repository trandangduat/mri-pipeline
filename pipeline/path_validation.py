"""Filesystem checks shared by local and remote preflight."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

from .discovery import _dicom_files_in_series, _discover_mri_files, _is_supported_mri_input


def validate_input_paths(mode: str, path: str, files: list[str], recursive: bool = True) -> None:
    def check_input(value: str) -> None:
        candidate = Path(value).expanduser()
        if not candidate.exists():
            raise ValueError(f"Input does not exist: {value}")
        if not _is_supported_mri_input(candidate):
            raise ValueError(f"Input must be an MRI file or DICOM folder: {value}")
        members = _dicom_files_in_series(candidate) if candidate.is_dir() else [candidate]
        for member in members:
            try:
                with member.open("rb") as stream:
                    stream.read(1)
            except OSError as exc:
                raise ValueError(f"Cannot read input: {member}: {exc}") from exc

    if mode == "file":
        check_input(path or (files[0] if files else ""))
    elif mode == "files" or (mode == "dir" and files):
        if not files:
            raise ValueError("Choose at least one input file.")
        for value in files:
            check_input(value)
    elif mode == "dir":
        folder = Path(path).expanduser()
        if not folder.is_dir():
            raise ValueError(f"Input folder does not exist: {path}")
        if not os.access(folder, os.R_OK | os.X_OK):
            raise ValueError(f"Cannot read input folder: {path}")
        candidates = _discover_mri_files(str(folder), recursive=recursive)
        if not candidates:
            raise ValueError(f"No MRI files or DICOM series found in input folder: {path}")
        for value in candidates:
            check_input(value)
    else:
        raise ValueError("Input mode must be file, files, or dir.")


def validate_writable_directory(value: str, label: str = "Output") -> None:
    if not value.strip():
        raise ValueError(f"{label} directory is required.")
    folder = Path(value).expanduser()
    # Do not create the user's output tree during preflight. Test its nearest
    # existing parent when the worker will need to create the directory.
    parent = folder
    while not parent.exists() and parent != parent.parent:
        if parent.is_symlink():
            raise ValueError(f"{label} directory has a broken symbolic link: {parent}")
        parent = parent.parent
    if not parent.is_dir():
        raise ValueError(f"{label} path is not a directory: {parent}")
    try:
        with tempfile.TemporaryFile(prefix=".neuroflow-preflight-", dir=parent) as stream:
            stream.write(b"ok")
            stream.flush()
    except OSError as exc:
        raise ValueError(f"Cannot write {label.lower()} directory: {folder}: {exc}") from exc


def main() -> None:
    # This entry point runs on the server after shared code synchronization.
    import signal

    def timed_out(*_args):
        raise RuntimeError("Path validation timed out.")

    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(30)
    try:
        request = json.load(sys.stdin)
        if request.get("input_source") != "Local":
            validate_input_paths(request["mode"], request["input_path"], request["input_files"], request["recursive"])
        else:
            validate_writable_directory(request["input_server_dir"], "Staging")
        validate_writable_directory(request["output_dir"])
        print(json.dumps({"ok": True}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
