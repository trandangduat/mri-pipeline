from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path
from .registry import STAGE_LABELS, tool_display_name
from .reports import _format_bytes

def _check_output_workspace(path: str, input_file: str = "") -> tuple[bool, str]:
    workspace = Path(path)
    try:
        workspace.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"cannot create output directory {workspace}: {exc}"

    probe = workspace / ".mri_pipeline_write_test"
    try:
        with open(probe, "wb") as f:
            f.write(b"ok")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        return False, f"output directory is not writable: {workspace}: {exc}"

    try:
        usage = shutil.disk_usage(workspace)
    except OSError as exc:
        return False, f"cannot check free disk for {workspace}: {exc}"

    input_size = 0
    if input_file:
        try:
            input_size = Path(input_file).stat().st_size
        except OSError:
            input_size = 0
    min_free = max(10 * 1024 ** 3, input_size * 20)
    if usage.free < min_free:
        return False, f"not enough free disk in {workspace}: free {_format_bytes(usage.free)}, recommended at least {_format_bytes(min_free)} for this pipeline run"
    return True, f"output workspace ok: free {_format_bytes(usage.free)}"

def _repair_host_permissions(path: str, image: str | None = None) -> None:
    target = Path(path)
    if not target.exists():
        return

    def chmod_tree() -> bool:
        ok = True
        for root, dirs, files in os.walk(target):
            for name in dirs:
                try:
                    os.chmod(Path(root) / name, 0o775)
                except OSError:
                    ok = False
            for name in files:
                try:
                    os.chmod(Path(root) / name, 0o664)
                except OSError:
                    ok = False
        try:
            os.chmod(target, 0o775)
        except OSError:
            ok = False
        return ok

    if chmod_tree() or not image:
        return
    uid = os.getuid() if hasattr(os, "getuid") else None
    gid = os.getgid() if hasattr(os, "getgid") else None
    if uid is None or gid is None:
        return
    helper_cmd = f"chown -R {uid}:{gid} /hostdir 2>/dev/null || chmod -R a+rwX /hostdir 2>/dev/null || true"
    try:
        import subprocess
        subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "sh", "-v", f"{target.resolve()}:/hostdir", image, "-c", helper_cmd],
            capture_output=True, text=True, timeout=120,
        )
    except Exception:
        return
    chmod_tree()

def _organize_output(subject_dir: str, preserve_dirs: set[str] | None = None) -> None:
    sd = Path(subject_dir)
    mri_dir = sd / "mri"
    stats_dir = sd / "stats"
    logs_dir = sd / "logs"
    preserved = {sd / name for name in (preserve_dirs or set()) if name}
    standard_dirs = {mri_dir, stats_dir, logs_dir, *preserved}
    mri_dir.mkdir(parents=True, exist_ok=True)
    stats_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    volume_exts = (".nii", ".nii.gz", ".mgz", ".mgh")
    for f in sd.rglob("*"):
        if f.is_file() and not any(f.parent == d or d in f.parents for d in standard_dirs) and f.name.lower().endswith(volume_exts):
            dest = mri_dir / f.name
            if not dest.exists():
                shutil.move(str(f), str(dest))

    for f in sd.rglob("*"):
        if f.is_file() and not any(f.parent == d or d in f.parents for d in standard_dirs) and f.suffix.lower() in (".tsv", ".csv", ".stats"):
            dest = stats_dir / f.name
            if not dest.exists():
                shutil.move(str(f), str(dest))

    for f in sd.rglob("*"):
        if f.is_file() and not any(f.parent == d or d in f.parents for d in standard_dirs) and f.suffix.lower() == ".log":
            dest = logs_dir / f.name
            if not dest.exists():
                shutil.move(str(f), str(dest))

    for d in sorted(sd.rglob("*"), reverse=True):
        if d.is_dir() and d not in standard_dirs and not any(parent in standard_dirs for parent in d.parents):
            try:
                d.rmdir()
            except OSError:
                pass


def _find_existing_outputs(subject_dir: str, possible_names: list[str], possible_globs: list[str] | None = None) -> list[str]:
    found: list[str] = []
    sd = Path(subject_dir)
    for name in possible_names:
        match = None
        for candidate in [sd / "mri" / name, sd / "stats" / name, sd / name]:
            if candidate.exists():
                match = str(candidate)
                break
        if match is None:
            matches = list(sd.rglob(name))
            if matches:
                match = str(matches[0])
        if match and match not in found:
            found.append(match)
    for pattern in possible_globs or []:
        for match in sorted(p for p in sd.rglob(pattern) if p.is_file()):
            path = str(match)
            if path not in found:
                found.append(path)
    return found

def _find_output_file(subject_dir: str, possible_names: list[str], possible_globs: list[str] | None = None) -> str | None:
    outputs = _find_existing_outputs(subject_dir, possible_names, possible_globs)
    return outputs[0] if outputs else None

def _describe_subject_files(subject_dir: str, limit: int = 80) -> str:
    sd = Path(subject_dir)
    if not sd.exists():
        return "subject output directory does not exist"
    files = sorted((p for p in sd.rglob("*") if p.is_file()), key=lambda p: str(p))
    if not files:
        return "no files found under subject output directory"
    rels = [str(p.relative_to(sd)) for p in files]
    if len(rels) > limit:
        rels = rels[:limit] + [f"... {len(files) - limit} more files"]
    return "; ".join(rels)
