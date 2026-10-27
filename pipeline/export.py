from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import tempfile
import threading
from pathlib import Path
from .config import EXPORT_OUTPUT_ITEMS, ExportConfig
from .registry import TOOL_DEFS, is_tool_enabled
from .docker_ops import require_image
from .executor import LocalDockerExecutor, ExecutionRequest
from .utils import _safe_container_name
from .workspace import _repair_host_permissions

_EXPORT_LOCK = threading.RLock()

def _volume_extension(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".nii.gz"):
        return ".nii.gz"
    return path.suffix.lower()

def _strip_volume_extension(name: str) -> str:
    lower = name.lower()
    for extension in (".nii.gz", ".nii", ".mgz", ".mgh"):
        if lower.endswith(extension):
            return name[:-len(extension)]
    return name

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
            command=["bash", "-c", f"{cmd_prefix}mri_convert {shlex.quote('/subject/' + src_rel)} {shlex.quote('/subject/' + dst_rel)}"],
            container_name=_safe_container_name("mri", subject_path.name, "export", dst.stem)
        )
        res = LocalDockerExecutor().execute(req)
        if res.return_code == 0 and dst.is_file() and dst.stat().st_size:
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

def _export_targets(stage: str, paths: list[str], config: ExportConfig):
    used: set[str] = set()
    volumes = [Path(p) for p in paths if _volume_extension(Path(p)) in (".nii", ".nii.gz", ".mgz", ".mgh")]
    default_format = config.default_format if config.default_format in ("same", ".nii.gz", ".mgz") else ".nii.gz"
    for index, source in enumerate(volumes):
        item = _export_item_id(stage, source, index)
        default_name = _default_export_name(item, source)
        stem = _safe_export_stem(_strip_volume_extension(config.names.get(item, default_name)), default_name)
        format_ = config.formats.get(item, default_format)
        if format_ not in ("same", ".nii.gz", ".mgz"):
            format_ = default_format
        extension = _volume_extension(source) if format_ == "same" else format_
        filename = stem + extension
        if filename.casefold() in used:
            filename = f"{stem}_{index + 1}{extension}"
        used.add(filename.casefold())
        yield source, item, filename


def _configured_targets(config: ExportConfig, tools: dict):
    for stage, key in tools.items():
        if not key or not is_tool_enabled(key):
            continue
        tool = TOOL_DEFS.get(key, {})
        paths = list(tool.get("output_files", [])) + list(tool.get("output_globs", []))
        for source, item, filename in _export_targets(stage, paths, config):
            yield stage, source, item, filename


def export_name_errors(config: ExportConfig, tools: dict) -> list[str]:
    if not config.enabled:
        return []
    destinations = {}
    for stage, source, item, filename in _configured_targets(config, tools):
        previous = destinations.setdefault(filename.casefold(), (stage, item))
        if previous != (stage, item):
            return [f"Export filename '{filename}' is shared by {previous[1]} and {item}. Choose different output names."]
    return []


def export_conversion_error(request: dict) -> str:
    """Check the converter only when configured outputs need a format change."""
    config = ExportConfig.from_dict(request.get("export_config"))
    if not config.enabled or not any(
        _volume_extension(source) != _volume_extension(Path(filename))
        for _, source, _, filename in _configured_targets(config, request.get("selected_tools", {}))
    ):
        return ""
    try:
        import nibabel
        if callable(nibabel.load) and callable(nibabel.save):
            return ""
    except Exception:
        pass
    ok, error = require_image("mri_convert_fs7")
    if not ok:
        return f"Image export needs nibabel or the FreeSurfer converter. {error}"
    license_path = Path(request.get("license_dir") or os.environ.get("FS_LICENSE") or "").expanduser()
    if not license_path.is_file() and not (license_path / "license.txt").is_file():
        return "Image export needs a FreeSurfer license file or nibabel. Select a license or repair the installation."
    return ""


def _write_export(source: Path, destination: Path, subject_dir: str, license_dir: str,
                  stage: str, item: str, only_missing: bool) -> tuple[bool, str]:
    # Per-file ownership permits resume without allowing another stage to overwrite an image.
    owner = destination.with_name(".export-" + hashlib.sha256(destination.name.casefold().encode()).hexdigest()[:20] + ".json")
    identity = {"source": str(source.resolve()), "stage": stage, "item": item}
    temporary = None
    claimed = False
    with _EXPORT_LOCK:
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and not owner.exists():
                return False, f"Export destination already exists and is not owned by this stage: {destination.name}"
            try:
                with owner.open("x", encoding="utf-8") as stream:
                    json.dump(identity, stream)
                claimed = True
            except FileExistsError:
                if json.loads(owner.read_text(encoding="utf-8")) != identity:
                    return False, f"Export filename belongs to another output: {destination.name}"
            existed = destination.exists()
            if only_missing and existed and destination.stat().st_size:
                return True, ""
            with tempfile.NamedTemporaryFile(prefix=".export-", suffix=_volume_extension(destination),
                                             dir=destination.parent, delete=False) as stream:
                temporary = Path(stream.name)
            ok, error = _copy_or_convert_export(source, temporary, subject_dir, license_dir)
            if not ok:
                return False, error
            if existed:
                os.replace(temporary, destination)
            else:
                # Exclusive publication also protects against a different worker creating this path.
                os.link(temporary, destination)
            return True, ""
        except (OSError, ValueError) as exc:
            return False, str(exc)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if claimed and not destination.exists():
                owner.unlink(missing_ok=True)


def _export_stage_outputs(
    subject_dir: str,
    stage: str,
    outputs_found: list[str],
    export_config: ExportConfig,
    license_dir: str = "",
    *,
    only_missing: bool = False,
) -> tuple[list[str], str]:
    if not export_config.enabled:
        return [], ""
    export_dir = Path(subject_dir) / _safe_export_stem(export_config.folder, "exports")
    exported: list[str] = []
    errors: list[str] = []
    for source, item, filename in _export_targets(stage, outputs_found, export_config):
        if not source.is_file():
            continue
        destination = export_dir / filename
        ok, error = _write_export(source, destination, subject_dir, license_dir, stage, item, only_missing)
        if ok:
            exported.append(str(destination))
        else:
            errors.append(f"{source.name} -> {filename}: {error}")
    return exported, "; ".join(errors)
