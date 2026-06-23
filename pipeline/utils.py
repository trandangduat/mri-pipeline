from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .config import PipelineConfig, StepResult


def _file_stem(filename: str) -> str:
    name = filename
    for ext in (".nii.gz", ".nii", ".mgz", ".mgh", ".dcm"):
        if name.lower().endswith(ext):
            return name[: -len(ext)]
    return Path(filename).stem


def _default_subject_id(input_file: str) -> str:
    return _file_stem(Path(input_file).name)


_GENERIC_BASENAMES = frozenset({
    "001", "002", "003", "image", "images", "scan", "brain", "t1", "t1w", "t2", "flair", "data",
})


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

    if use_path and path.parent.name:
        if dataset_root:
            try:
                rel = path.relative_to(Path(dataset_root).expanduser().resolve())
                if len(rel.parts) >= 2:
                    return _sanitize_subject_id("__".join(rel.with_suffix("").parts))
            except ValueError:
                pass
        return _sanitize_subject_id(path.parent.name)

    if dataset_root:
        try:
            rel = path.relative_to(Path(dataset_root).expanduser().resolve())
            if len(rel.parts) > 1:
                return _sanitize_subject_id("__".join(rel.with_suffix("").parts))
        except ValueError:
            pass

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


def _is_supported_mri_file(path: Path) -> bool:
    return path.name.lower().endswith((".nii.gz", ".nii", ".mgz", ".mgh", ".dcm"))


def _discover_mri_files(input_dir: str, recursive: bool = True) -> list[str]:
    root = Path(input_dir).expanduser()
    if not root.exists() or not root.is_dir():
        return []
    iterator = root.rglob("*") if recursive else root.glob("*")
    return [str(p) for p in sorted(iterator) if p.is_file() and _is_supported_mri_file(p)]


def _safe_container_name(*parts: str) -> str:
    raw = "-".join(part for part in parts if part)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-_.")
    if not safe:
        safe = "mri-pipeline"
    if not safe[0].isalnum():
        safe = f"mri-{safe}"
    return f"{safe[:80]}-{uuid4().hex[:8]}"


def _parse_docker_memory(value: str) -> int | None:
    first = value.split("/", 1)[0].strip()
    match = re.match(r"^([0-9.]+)\s*([A-Za-z]+)$", first)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2).lower()
    multipliers = {
        "b": 1, "kb": 1000, "mb": 1000 ** 2, "gb": 1000 ** 3, "tb": 1000 ** 4,
        "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "tib": 1024 ** 4,
    }
    multiplier = multipliers.get(unit)
    return int(number * multiplier) if multiplier is not None else None


def _parse_docker_stats_line(line: str) -> tuple[float | None, int | None]:
    parts = line.split("|", 1)
    cpu: float | None = None
    if parts:
        raw_cpu = parts[0].strip().rstrip("%").strip()
        try:
            cpu = float(raw_cpu)
        except ValueError:
            cpu = None
    ram = _parse_docker_memory(parts[1]) if len(parts) > 1 else None
    return cpu, ram


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "n/a"
    if value < 1024:
        return f"{value} B"
    mib = value / (1024 ** 2)
    if mib < 1024:
        return f"{mib:.1f} MiB"
    return f"{mib / 1024:.2f} GiB"


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


def _append_step_log(logs_dir: str, tool_key: str, lines: list[str]) -> None:
    step_log = Path(logs_dir) / f"{tool_key}.log"
    try:
        with open(step_log, "a", encoding="utf-8") as f:
            f.write("\n".join(lines))
            f.write("\n")
    except PermissionError:
        fallback = Path(logs_dir) / f"{tool_key}_pipeline.log"
        try:
            with open(fallback, "a", encoding="utf-8") as f:
                f.write(f"Could not append to {step_log}; file is not writable by the host user.\n")
                f.write("\n".join(lines))
                f.write("\n")
        except OSError as exc:
            print(f"WARNING: could not write step log for {tool_key}: {exc}", flush=True)
    except OSError as exc:
        print(f"WARNING: could not write step log for {tool_key}: {exc}", flush=True)


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


def _write_pipeline_metrics_log(logs_dir: str, config: PipelineConfig, subject_dir: str, results: list[StepResult], started_at: float, ended_at: float) -> str:
    metrics_log = Path(logs_dir) / "pipeline_metrics.log"
    total_run = sum(r.duration_sec for r in results)
    total_build = sum(r.build_duration_sec for r in results)
    status = "SUCCESS" if results and all(r.success for r in results) else "FAILED"
    with open(metrics_log, "w", encoding="utf-8") as f:
        f.write("MRI Pipeline Metrics\n")
        f.write(f"Input file: {os.path.abspath(config.input_file)}\n")
        f.write(f"Subject ID: {config.subject_id}\n")
        f.write(f"Subject output: {subject_dir}\n")
        f.write(f"Started: {datetime.fromtimestamp(started_at).isoformat(timespec='seconds')}\n")
        f.write(f"Finished: {datetime.fromtimestamp(ended_at).isoformat(timespec='seconds')}\n")
        f.write(f"Status: {status}\n")
        f.write(f"Total wall time: {ended_at - started_at:.1f}s\n")
        f.write(f"Total run time: {total_run:.1f}s\n")
        f.write(f"Total build/pull time: {total_build:.1f}s\n\n")
        f.write("Stage\tTool\tStatus\tRun(s)\tBuild/Pull(s)\tPeak RAM\tError\n")
        for r in results:
            f.write(f"{r.stage}\t{r.tool}\t{'OK' if r.success else 'FAILED'}\t{r.duration_sec:.1f}\t{r.build_duration_sec:.1f}\t{_format_bytes(r.peak_ram_bytes)}\t{r.error}\n")
    return str(metrics_log)


def _pipeline_state_path(logs_dir: str) -> Path:
    return Path(logs_dir) / "pipeline_state.json"


def _load_pipeline_state(logs_dir: str) -> dict:
    path = _pipeline_state_path(logs_dir)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_pipeline_state(logs_dir: str, state: dict) -> None:
    path = _pipeline_state_path(logs_dir)
    Path(logs_dir).mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _new_pipeline_state(config: PipelineConfig, subject_dir: str) -> dict:
    return {
        "version": 2,
        "input_file": os.path.abspath(config.input_file),
        "subject_id": config.subject_id,
        "subject_dir": subject_dir,
        "status": "running",
        "current_stage": "",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "selected_tools": config.selected_tools,
        "export_config": config.export_config.to_dict(),
        "stats_vector_config": config.stats_vector_config.to_dict(),
        "stages": {},
    }


def _set_stage_state(logs_dir: str, state: dict, stage: str, tool: str, status: str, output_file: str = "", output_files_found: list[str] | None = None, error: str = "", duration_sec: float = 0.0) -> None:
    state.setdefault("stages", {})[stage] = {
        "tool": tool,
        "status": status,
        "output_file": output_file,
        "output_files_found": output_files_found or ([output_file] if output_file else []),
        "error": error,
        "duration_sec": duration_sec,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    state["current_stage"] = stage
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    if status == "failed":
        state["status"] = "failed"
    elif status == "running":
        state["status"] = "running"
    _write_pipeline_state(logs_dir, state)


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


def _resume_output_for_stage(subject_dir: str, state: dict, stage: str, tool_key: str, output_files: list[str], output_globs: list[str] | None = None) -> tuple[str | None, list[str]]:
    stage_state = state.get("stages", {}).get(stage, {})
    recorded_outputs = [p for p in stage_state.get("output_files_found", []) if p]
    if stage_state.get("status") == "completed" and stage_state.get("tool") == tool_key and recorded_outputs and all(Path(p).exists() for p in recorded_outputs):
        saved_output = stage_state.get("output_file")
        if saved_output and Path(saved_output).exists():
            return saved_output, recorded_outputs
        return recorded_outputs[0], recorded_outputs

    # Resume after interruption: trust verified files on disk, not only JSON state.
    found_outputs = _find_existing_outputs(subject_dir, output_files, output_globs)
    return (found_outputs[0], found_outputs) if found_outputs else (None, [])
