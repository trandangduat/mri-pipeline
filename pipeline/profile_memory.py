from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.config import PROJECT_ROOT

# Mapping of standard pipeline modes to their preset IDs
PIPELINE_MODE_TO_PRESET: dict[str, str] = {
    "FreeSurfer 8 + Volume": "freesurfer8_volumetrics",
    "FreeSurfer 8 + Cortical Thickness": "freesurfer8_cortical_thickness",
    "FreeSurfer 8 + Volume + Cortical Thickness": "freesurfer8_all",
    "FreeSurfer 7 + Volume": "freesurfer7_volumetrics",
    "FreeSurfer 7 + Cortical Thickness": "freesurfer7_cortical_thickness",
    "FreeSurfer 7 + Volume + Cortical Thickness": "freesurfer7_all",
    "FastSurfer + Volume": "fastsurfer_volumetrics",
    "FastSurfer + Cortical Thickness": "fastsurfer_cortical_thickness",
    "FastSurfer + Volume + Cortical Thickness": "fastsurfer_all",
}

# Standard peak RAM requirements (in MiB) measured from NeuroFLOW profiles
STANDARD_PROFILE_PEAKS: dict[str, int] = {
    "FreeSurfer 7 + Volume": 2083,
    "FastSurfer + Volume": 6830,
    "FreeSurfer 7 + Cortical Thickness": 11878,
    "FastSurfer + Cortical Thickness": 11878,
    "FreeSurfer 7 + Volume + Cortical Thickness": 13660,
    "FastSurfer + Volume + Cortical Thickness": 13660,
    "FreeSurfer 8 + Cortical Thickness": 14900,
    "FreeSurfer 8 + Volume + Cortical Thickness": 14900,
    "FreeSurfer 8 + Volume": 16507,
}


def load_profile_peak_mib(profile_path: Path | str) -> int:
    """Read a NeuroFLOW profile YAML file and return the maximum peak_mib."""
    path = Path(profile_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return 0
    try:
        import yaml

        with open(path, "r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp)
        if isinstance(data, dict):
            peaks = [
                int(p["memory"]["peak_mib"])
                for p in data.get("profiles", [])
                if isinstance(p, dict)
                and isinstance(p.get("memory"), dict)
                and "peak_mib" in p["memory"]
            ]
            if peaks:
                return max(peaks)
    except Exception:
        pass
    return 0


def get_profile_peak_ram_mib(
    run_request: dict[str, Any],
    profile_dir: Path | str | None = None,
) -> int:
    """Determine the peak RAM required (in MiB) for the given run request."""
    # 1. If explicit profile file is configured
    custom_profile = str(run_request.get("neuroflow_profile_file") or "").strip()
    if custom_profile:
        peak = load_profile_peak_mib(custom_profile)
        if peak > 0:
            return peak

    # 2. Check pipeline mode
    from pipeline.presets import normalize_pipeline_mode, infer_pipeline_mode_from_tools

    mode = normalize_pipeline_mode(str(run_request.get("pipeline_mode") or "").strip())
    if mode == "Custom":
        inferred = infer_pipeline_mode_from_tools(run_request.get("selected_tools"))
        if inferred != "Custom":
            mode = inferred

    if mode in PIPELINE_MODE_TO_PRESET:
        preset_id = PIPELINE_MODE_TO_PRESET[mode]
        base_dir = Path(profile_dir) if profile_dir else PROJECT_ROOT / "configs" / "neuroflow" / "profiles"
        yaml_file = base_dir / f"{preset_id}_default.yaml"
        peak = load_profile_peak_mib(yaml_file)
        if peak > 0:
            return peak
        return STANDARD_PROFILE_PEAKS.get(mode, 0)

    return STANDARD_PROFILE_PEAKS.get(mode, 0)


def get_all_standard_profile_peaks(
    profile_dir: Path | str | None = None,
) -> dict[str, int]:
    """Return dictionary of pipeline mode -> peak RAM in MiB for all standard presets."""
    result: dict[str, int] = {}
    base_dir = Path(profile_dir) if profile_dir else PROJECT_ROOT / "configs" / "neuroflow" / "profiles"

    for mode, preset_id in PIPELINE_MODE_TO_PRESET.items():
        yaml_file = base_dir / f"{preset_id}_default.yaml"
        peak = load_profile_peak_mib(yaml_file)
        result[mode] = peak if peak > 0 else STANDARD_PROFILE_PEAKS[mode]
    return result


def get_runnable_profiles(
    allocated_ram_mib: int,
    profile_dir: Path | str | None = None,
) -> list[tuple[str, int]]:
    """Return sorted list of (pipeline_mode, peak_mib) that can run within allocated RAM."""
    all_peaks = get_all_standard_profile_peaks(profile_dir=profile_dir)
    runnable = [
        (mode, peak)
        for mode, peak in all_peaks.items()
        if peak <= allocated_ram_mib
    ]
    # Sort ascending by peak RAM
    runnable.sort(key=lambda item: (item[1], item[0]))
    return runnable


def format_gib(mib: int) -> str:
    """Format MiB to human-readable GiB string."""
    return f"{mib / 1024:.1f} GiB"


def format_resource_check_failure(
    allocated_ram_mib: int,
    required_peak_mib: int,
    mode_name: str,
    total_ram_mib: int,
    ram_percent: int,
    profile_dir: Path | str | None = None,
) -> str:
    """Build a detailed failure message listing compatible FreeSurfer 7, 8, and FastSurfer profiles."""
    alloc_str = format_gib(allocated_ram_mib)
    req_str = format_gib(required_peak_mib)
    total_str = format_gib(total_ram_mib)

    lines = [
        f"Insufficient RAM allocated: {alloc_str} allocated ({ram_percent}% of {total_str} server RAM), "
        f"but \"{mode_name}\" requires {req_str} peak RAM."
    ]

    runnable = get_runnable_profiles(allocated_ram_mib, profile_dir=profile_dir)
    if runnable:
        lines.append(f"\nCompatible pipelines runnable with {alloc_str} RAM:")
        for mode, peak in runnable:
            lines.append(f"  • {mode} (Peak: {format_gib(peak)})")
        lines.append("\nTip: Increase RAM % in Runtime Settings or select one of the compatible pipelines above.")
    else:
        min_peak = min(STANDARD_PROFILE_PEAKS.values())
        lines.append(
            f"\nNo standard pipeline profiles can run with {alloc_str} RAM "
            f"(minimum requirement is {format_gib(min_peak)} for FreeSurfer 7 + Volume)."
        )
        lines.append("Tip: Increase RAM % in Runtime Settings or allocate more memory to the server.")

    return "\n".join(lines)
