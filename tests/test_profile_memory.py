import pytest
from pipeline.profile_memory import (
    STANDARD_PROFILE_PEAKS,
    build_resource_shortage,
    get_all_standard_profile_peaks,
    get_profile_peak_ram_mib,
    get_runnable_profiles,
    load_profile_peak_mib,
    recommended_ram_percent,
)


def test_standard_profile_peaks_defined() -> None:
    assert len(STANDARD_PROFILE_PEAKS) == 9
    assert STANDARD_PROFILE_PEAKS["FreeSurfer 7 + Volume"] == 2083
    assert STANDARD_PROFILE_PEAKS["FastSurfer + Volume"] == 6830
    assert STANDARD_PROFILE_PEAKS["FreeSurfer 8 + Volume"] == 16507


def test_load_profile_peak_mib_from_yaml() -> None:
    peak = load_profile_peak_mib("configs/neuroflow/profiles/freesurfer7_volumetrics_default.yaml")
    assert peak == 2083


def test_get_profile_peak_ram_mib_modes() -> None:
    assert get_profile_peak_ram_mib({"pipeline_mode": "FreeSurfer 7 + Volume"}) == 2083
    assert get_profile_peak_ram_mib({"pipeline_mode": "FastSurfer + Volume"}) == 6830
    assert get_profile_peak_ram_mib({"pipeline_mode": "FreeSurfer 8 + Volume + Cortical Thickness"}) == 14900


def test_get_profile_peak_ram_mib_custom_file(tmp_path) -> None:
    yaml_content = """schema_version: 1
profiles:
  - profile_id: task_1
    memory:
      peak_mib: 4500
  - profile_id: task_2
    memory:
      peak_mib: 8200
"""
    custom_yaml = tmp_path / "custom_profile.yaml"
    custom_yaml.write_text(yaml_content, encoding="utf-8")

    req = {"pipeline_mode": "Custom", "neuroflow_profile_file": str(custom_yaml)}
    assert get_profile_peak_ram_mib(req) == 8200


def test_get_all_standard_profile_peaks() -> None:
    peaks = get_all_standard_profile_peaks()
    assert len(peaks) == 9
    assert all(p > 0 for p in peaks.values())


def test_get_runnable_profiles() -> None:
    # 1. Very low RAM (1000 MiB) -> nothing runnable
    runnable_low = get_runnable_profiles(1000)
    assert len(runnable_low) == 0

    # 2. 8000 MiB (~7.8 GiB) -> FS7 Volumetrics (2083) and FastSurfer Volumetrics (6830)
    runnable_8g = get_runnable_profiles(8000)
    modes_8g = [mode for mode, _ in runnable_8g]
    assert modes_8g == ["FreeSurfer 7 + Volume", "FastSurfer + Volume"]

    # 3. 14000 MiB (~13.6 GiB) -> all FS7 and FastSurfer presets
    runnable_14g = get_runnable_profiles(14000)
    assert len(runnable_14g) == 6
    for mode, _ in runnable_14g:
        assert "FreeSurfer 8" not in mode

    # 4. 20000 MiB (~19.5 GiB) -> all 9 presets runnable
    runnable_20g = get_runnable_profiles(20000)
    assert len(runnable_20g) == 9


def test_recommended_ram_percent_is_the_smallest_increase_that_covers_the_peak() -> None:
    assert recommended_ram_percent(16384, 14900, 50) == 91
    assert (16384 * 91) // 100 >= 14900
    assert (16384 * 90) // 100 < 14900


def test_recommended_ram_percent_is_hidden_when_it_is_not_an_increase() -> None:
    assert recommended_ram_percent(8192, 14900, 100) is None
    assert recommended_ram_percent(16384, 14900, 91) is None
    assert recommended_ram_percent(16384, 14900, 95) is None


def test_build_resource_shortage_lists_compatible_presets_and_ram_increase() -> None:
    shortage = build_resource_shortage(
        allocated_ram_mib=8192,
        required_peak_mib=14900,
        total_ram_mib=16384,
        ram_percent=50,
    )
    assert shortage["summary"] == "Insufficient resources (8.0 GiB allocated, 14.6 GiB required)"
    assert shortage["increase_ram_percent"] == 91
    assert shortage["presets"][0] == "FreeSurfer 7 + Volume"
    assert "FastSurfer + Volume" in shortage["presets"]
    assert all("FreeSurfer 8" not in mode for mode in shortage["presets"])


def test_build_resource_shortage_without_actions_when_nothing_fits() -> None:
    shortage = build_resource_shortage(
        allocated_ram_mib=1024,
        required_peak_mib=14900,
        total_ram_mib=2048,
        ram_percent=50,
    )
    assert shortage["summary"] == "Insufficient resources (1.0 GiB allocated, 14.6 GiB required)"
    assert shortage["increase_ram_percent"] is None
    assert shortage["presets"] == []
