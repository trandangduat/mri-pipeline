from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Tuple, List
from .config import EXPORT_OUTPUT_ITEMS, ExportConfig
from .registry import TOOL_DEFS
from .docker_ops import require_image
from .executor import LocalDockerExecutor, ExecutionRequest
from .utils import _safe_container_name
from .workspace import _repair_host_permissions

def _volume_extension(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".nii.gz"):
        return ".nii.gz"
    return path.suffix.lower()

def _strip_volume_extension(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".nii.gz"):
        return name[:-7]
    return Path(name).stem

def _safe_export_stem(value: str, fallback: str) -> str:
    raw = (value or fallback).strip()
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in raw).strip("._-")
    return safe or fallback

def _export_item_id(stage: str, path: Path, index: int) -> str:
    name = path.name.lower()
    if stage == "brain_extraction" and ("mask" in name or name.endswith("_bet.nii.gz") or name.endswith("_bet.mgz")):
        return "brain_extraction.mask"
    if stage == "template_registration" and ("deformation" in name or "field" in name):
        return "template_registration.deformation"
    primary = f"{stage}.primary"
    return primary if index == 0 else f"{stage}.extra{index + 1}"

def _default_export_name(item_id: str, path: Path) -> str:
    item = EXPORT_OUTPUT_ITEMS.get(item_id)
    if item:
        return item["default_name"]
    return _strip_volume_extension(path.name)

def _copy_or_convert_export(src: Path, dst: Path, subject_dir: str, license_dir: str = "") -> tuple[bool, str]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if _volume_extension(src) == _volume_extension(dst):
        shutil.copy2(src, dst)
        return True, ""

    subject_path = Path(subject_dir).resolve()
    src_rel = src.resolve().relative_to(subject_path).as_posix()
    dst_rel = dst.resolve().relative_to(subject_path).as_posix()

    # Mount FreeSurfer license if provided
    mounts: list[tuple[str, str]] = [(str(subject_path), "/subject")]
    cmd_prefix = ""

    lic_candidate: Path | None = None
    if license_dir:
        lp = Path(license_dir).resolve()
        if lp.is_file():
            lic_candidate = lp
        elif (lp / "license.txt").is_file():
            lic_candidate = lp / "license.txt"

    if not lic_candidate:
        env_lic = os.environ.get("FS_LICENSE", "").strip()
        if env_lic and Path(env_lic).is_file():
            lic_candidate = Path(env_lic).resolve()

    if lic_candidate and lic_candidate.is_file():
        mounts.append((str(lic_candidate), "/license/license.txt"))
        cmd_prefix = "export FS_LICENSE=/license/license.txt && "

    # 1. Primary: Use FreeSurfer mri_convert with license mount (official tool)
    docker_err = ""
    ok, err = require_image("mri_convert_fs7")
    if ok:
        req = ExecutionRequest(
            image=TOOL_DEFS["mri_convert_fs7"]["image"],
            args=[],
            mounts=mounts,
            command=["bash", "-c", f"{cmd_prefix}mri_convert /subject/{src_rel} /subject/{dst_rel}"],
            container_name=_safe_container_name("mri", subject_path.name, "export")
        )
        res = LocalDockerExecutor().execute(req)
        if res.return_code == 0 and dst.exists():
            _repair_host_permissions(str(subject_path), TOOL_DEFS["mri_convert_fs7"]["image"])
            return True, ""
        docker_err = res.output.strip()
    else:
        docker_err = err

    # 2. Resilient fallback: nibabel (ensures export succeeds without interrupting execution)
    try:
        import nibabel as nib
        img = nib.load(str(src))
        nib.save(img, str(dst))
        return True, ""
    except Exception as exc:
        tail = " | ".join(docker_err.splitlines()[-3:]) if docker_err else "mri_convert failed"
        return False, f"{tail} (fallback error: {exc})"

def _export_stage_outputs(
    subject_dir: str,
    stage: str,
    outputs_found: list[str],
    export_config: ExportConfig,
    license_dir: str = "",
) -> tuple[list[str], str]:
    if not export_config.enabled:
        return [], ""
    fmt_default = export_config.default_format if export_config.default_format in ("same", ".nii.gz", ".mgz") else ".nii.gz"
    export_folder = _safe_export_stem(export_config.folder, "exports")
    export_dir = Path(subject_dir) / export_folder
    exported: list[str] = []
    errors: list[str] = []
    used_names: set[str] = set()

    volume_exts = (".nii", ".nii.gz", ".mgz", ".mgh")
    volume_outputs = [Path(p) for p in outputs_found if Path(p).name.lower().endswith(volume_exts)]
    for idx, src in enumerate(volume_outputs):
        if not src.exists():
            continue
        item_id = _export_item_id(stage, src, idx)
        default_name = _default_export_name(item_id, src)
        configured_name = _strip_volume_extension(export_config.names.get(item_id, default_name))
        stem = _safe_export_stem(configured_name, default_name)
        target_format = export_config.formats.get(item_id, fmt_default)
        if target_format not in ("same", ".nii.gz", ".mgz"):
            target_format = fmt_default
        ext = _volume_extension(src) if target_format == "same" else target_format
        filename = f"{stem}{ext}"
        if filename in used_names:
            filename = f"{stem}_{idx + 1}{ext}"
        used_names.add(filename)
        dst = export_dir / filename
        ok, err = _copy_or_convert_export(src, dst, subject_dir, license_dir=license_dir)
        if ok:
            exported.append(str(dst))
        else:
            errors.append(f"{src.name} -> {filename}: {err}")
    return exported, "; ".join(errors)
