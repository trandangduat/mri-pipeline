from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app_backend.run_request import RunRequestInput, prepare_run_request
from pipeline.config import ExportConfig, StatsVectorConfig
from pipeline.presets import PRESET_CONFIGS, normalize_stats_vector_config_for_pipeline_mode


def _base_config(tmp_path: Path, **overrides: object) -> RunRequestInput:
    license_dir = tmp_path / "license"
    license_dir.mkdir(exist_ok=True)
    data: dict[str, object] = {
        "input_path": str(tmp_path / "image.nii.gz"),
        "output_dir": str(tmp_path / "outputs"),
        "license_dir": str(license_dir),
        "selected_tools": {"segmentation": "synthseg_freesurfer_fs7"},
        "export_config": ExportConfig(enabled=False).to_dict(),
        "stats_vector_config": StatsVectorConfig().to_dict(),
    }
    data.update(overrides)
    return RunRequestInput.from_dict(data)


def _ok_request(result: dict[str, object]) -> dict[str, object]:
    assert result["ok"] is True
    assert result["errors"] == []
    request = result["request"]
    assert isinstance(request, dict)
    return request


def test_prepare_run_request_builds_local_file_request(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    license_dir = tmp_path / "license"
    image.write_text("fake", encoding="utf-8")
    license_dir.mkdir()

    result = prepare_run_request(_base_config(tmp_path))
    request = _ok_request(result)

    assert request["mode"] == "file"
    assert request["input_file"] == str(image)
    assert request["output_dir"] == str(tmp_path / "outputs")
    assert request["effective_output_dir"] == str(tmp_path / "outputs")
    assert request["license_dir"] == str(tmp_path / "license")
    assert request["threads"] == 4
    assert request["ram_percent"] == 100
    json.dumps(result)


def test_prepare_run_request_preserves_neuroflow_configuration_files(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    preset = tmp_path / "preset.yaml"
    profile = tmp_path / "profile.yaml"
    image.write_text("fake", encoding="utf-8")
    preset.write_text("pipeline", encoding="utf-8")
    profile.write_text("profile", encoding="utf-8")

    request = _ok_request(
        prepare_run_request(
            _base_config(
                tmp_path,
                neuroflow_preset_file=str(preset),
                neuroflow_profile_file=str(profile),
            )
        )
    )

    assert request["neuroflow_preset_file"] == str(preset)
    assert request["neuroflow_profile_file"] == str(profile)


def test_custom_neuroflow_configuration_keeps_custom_pipeline_mode(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    preset = tmp_path / "custom-preset.yaml"
    profile = tmp_path / "custom-profile.yaml"
    image.write_text("fake", encoding="utf-8")
    preset.write_text("pipeline", encoding="utf-8")
    profile.write_text("profile", encoding="utf-8")

    request = _ok_request(
        prepare_run_request(
            _base_config(
                tmp_path,
                pipeline_mode="Custom",
                neuroflow_enabled=True,
                neuroflow_preset_file=str(preset),
                neuroflow_profile_file=str(profile),
            )
        )
    )

    assert request["pipeline_mode"] == "Custom"
    assert request["neuroflow_enabled"] is True


def test_prepare_run_request_requires_existing_license_for_licensed_tools(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    image.write_text("fake", encoding="utf-8")

    result = prepare_run_request(_base_config(tmp_path, license_dir=str(tmp_path / "missing-license.txt")))

    assert result["ok"] is False
    assert result["request"] is None
    assert result["errors"] == ["FreeSurfer license file or directory does not exist."]


def test_run_request_module_is_tkinter_free_in_fresh_process() -> None:
    code = (
        "import sys; "
        "from app_backend.run_request import RunRequestInput, prepare_run_request; "
        "prepare_run_request(RunRequestInput(input_path='')); "
        "raise SystemExit(1 if any(name == 'tkinter' or name.startswith('tkinter.') for name in sys.modules) else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr or result.stdout


def test_prepare_run_request_uses_preset_tools_over_custom_selection(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    image.write_text("fake", encoding="utf-8")

    result = prepare_run_request(
        _base_config(
            tmp_path,
            pipeline_mode="FreeSurfer 7 + Volume",
            selected_tools={"segmentation": "cat12_volume_segmentation"},
        )
    )
    request = _ok_request(result)

    assert request["selected_tools"] == PRESET_CONFIGS["FreeSurfer 7 + Volume"]["tools"]
    assert request["stats_vector_config"] == {
        "enabled_stats": {
            "cortical_thickness": False,
            "cortical_volume": False,
            "subcortical_volume": True,
        },
        "atlases": {
            "cortical_thickness": [],
            "cortical_volume": [],
            "subcortical_volume": ["freesurfer_aseg"],
        },
    }


def test_prepare_run_request_builds_local_multi_file_request(tmp_path: Path) -> None:
    first = tmp_path / "a.nii"
    second = tmp_path / "nested" / "b.mgz"
    first.write_text("fake", encoding="utf-8")
    second.parent.mkdir()
    second.write_text("fake", encoding="utf-8")

    result = prepare_run_request(
        _base_config(
            tmp_path,
            input_mode="files",
            input_path=f"{first};{second}",
            selected_files=[str(first), str(second)],
        )
    )
    request = _ok_request(result)

    assert request["mode"] == "files"
    assert request["input_files"] == [str(first), str(second)]
    assert request["input_dir"] == str(tmp_path)


def test_prepare_run_request_accepts_selected_files_without_input_path(tmp_path: Path) -> None:
    image = tmp_path / "image.nii"
    image.write_text("fake", encoding="utf-8")

    result = prepare_run_request(_base_config(tmp_path, input_path="", selected_files=[str(image)]))
    request = _ok_request(result)

    assert request["mode"] == "file"
    assert request["input_file"] == str(image)


def test_prepare_run_request_normalizes_multi_file_dicom_selection_to_series_dirs(tmp_path: Path) -> None:
    first_series = tmp_path / "series1"
    second_series = tmp_path / "series2"
    first_series.mkdir()
    second_series.mkdir()
    first_dicom = first_series / "IM0001.dcm"
    duplicate_dicom = first_series / "IM0002.dcm"
    second_dicom = second_series / "IM0001.dcm"
    for path in (first_dicom, duplicate_dicom, second_dicom):
        path.write_text("fake", encoding="utf-8")

    result = prepare_run_request(
        _base_config(
            tmp_path,
            input_mode="files",
            input_path="",
            selected_files=[str(first_dicom), str(duplicate_dicom), str(second_dicom)],
        )
    )
    request = _ok_request(result)

    assert request["input_files"] == [str(first_series), str(second_series)]
    assert request["input_dir"] == str(tmp_path)


def test_prepare_run_request_builds_batch_dir_request(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()

    result = prepare_run_request(
        _base_config(
            tmp_path,
            input_mode="dir",
            input_path=str(input_dir),
            non_recursive=False,
            batch_timestamp="20260811_120000",
        )
    )
    request = _ok_request(result)

    assert request["mode"] == "dir"
    assert request["input_dir"] == str(input_dir)
    assert request["recursive"] is True
    assert request["is_batch"] is True
    assert request["batch_output_name"] == "batch_20260811_120000"
    assert request["effective_output_dir"] == str(tmp_path / "outputs" / "batch_20260811_120000")


def test_prepare_run_request_validates_selected_files_when_dir_mode_switches_to_files(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    missing = input_dir / "missing.nii.gz"

    result = prepare_run_request(
        _base_config(
            tmp_path,
            input_mode="dir",
            input_path=str(input_dir),
            selected_files=[str(missing)],
        )
    )

    assert result["ok"] is False
    assert result["request"] is None
    assert result["errors"] == ["One or more selected input files or DICOM folders do not exist."]


def test_prepare_run_request_normalizes_single_dicom_file_to_series_dir(tmp_path: Path) -> None:
    dicom_dir = tmp_path / "dicom"
    dicom_dir.mkdir()
    dicom_file = dicom_dir / "IM0001.dcm"
    dicom_file.write_text("fake", encoding="utf-8")

    result = prepare_run_request(_base_config(tmp_path, input_path=str(dicom_file), selected_files=[str(dicom_file)]))
    request = _ok_request(result)

    assert request["mode"] == "dir"
    assert request["is_batch"] is False
    assert request["input_file"] == str(dicom_dir)
    assert request["input_dir"] == str(dicom_dir)
    assert request["recursive"] is False


def test_prepare_run_request_normalizes_extensionless_dicom_file_to_series_dir(tmp_path: Path) -> None:
    dicom_dir = tmp_path / "dicom"
    dicom_dir.mkdir()
    dicom_file = dicom_dir / "IM0001"
    dicom_file.write_bytes(b"\0" * 128 + b"DICM" + b"fake")

    result = prepare_run_request(_base_config(tmp_path, input_path=str(dicom_file), selected_files=[str(dicom_file)]))
    request = _ok_request(result)

    assert request["mode"] == "dir"
    assert request["input_file"] == str(dicom_dir)
    assert request["input_dir"] == str(dicom_dir)
    assert request["recursive"] is False


def test_prepare_run_request_returns_validation_errors_without_dialogs(tmp_path: Path) -> None:
    result = prepare_run_request(_base_config(tmp_path, input_path=str(tmp_path / "missing.nii.gz")))

    assert result["ok"] is False
    assert result["request"] is None
    assert result["errors"] == ["Input file or DICOM folder does not exist."]


def test_run_request_input_parses_boolean_strings() -> None:
    config = RunRequestInput.from_dict({"non_recursive": "false", "neuroflow_enabled": "false"})

    assert config.non_recursive is False
    assert config.neuroflow_enabled is False


def test_prepare_run_request_allows_remote_with_server_input(tmp_path: Path) -> None:
    result = prepare_run_request(
        _base_config(
            tmp_path,
            input_source="Server",
            run_target="Server",
            input_path="/data/image.nii.gz",
        )
    )

    assert result["ok"] is True
    assert result["request"] is not None
    assert result["errors"] == []
    assert result["request"]["run_target"] == "Server"
    assert result["request"]["input_source"] == "Server"


def test_prepare_run_request_rejects_remote_with_local_input_without_staging(tmp_path: Path) -> None:
    result = prepare_run_request(
        _base_config(
            tmp_path,
            input_source="Local",
            run_target="Server",
            input_path="/local/data/image.nii.gz",
            output_dir=str(tmp_path / "out"),
        )
    )

    assert result["ok"] is False
    assert result["request"] is None
    assert any("staging" in e.lower() for e in result["errors"])


def test_prepare_run_request_accepts_remote_local_input_with_staging(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    image.write_text("fake", encoding="utf-8")

    result = prepare_run_request(
        _base_config(
            tmp_path,
            input_source="Local",
            run_target="Server",
            input_path=str(image),
            output_dir=str(tmp_path / "out"),
            input_server_dir="~/mri-uploads",
            neuroflow_enabled=True,
        )
    )

    request = _ok_request(result)
    assert request["input_source"] == "Local"
    assert request["input_server_dir"] == "~/mri-uploads"
    assert request["run_target"] == "Server"


def test_prepare_run_request_rejects_local_with_server_input(tmp_path: Path) -> None:
    result = prepare_run_request(
        _base_config(
            tmp_path,
            input_source="Server",
            run_target="Local",
            input_path="/data/image.nii.gz",
            output_dir=str(tmp_path / "out"),
        )
    )

    assert result["ok"] is False
    assert result["request"] is None
    assert any("local" in e.lower() for e in result["errors"])


def test_prepare_run_request_disables_neuroflow_for_unsupported_custom_mode(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    image.write_text("fake", encoding="utf-8")

    result = prepare_run_request(
        _base_config(
            tmp_path,
            pipeline_mode="Custom",
            neuroflow_enabled=True,
            neuroflow_max_concurrent_tasks=4,
        )
    )
    request = _ok_request(result)

    assert request["neuroflow_enabled"] is False
    assert request["neuroflow_max_concurrent_tasks"] == 4


def test_prepare_run_request_keeps_neuroflow_for_supported_preset(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    image.write_text("fake", encoding="utf-8")

    result = prepare_run_request(
        _base_config(
            tmp_path,
            pipeline_mode="FreeSurfer 7 + Volume",
            neuroflow_enabled=True,
        )
    )
    request = _ok_request(result)

    assert request["neuroflow_enabled"] is True


def test_prepare_run_request_rejects_invalid_neuroflow_numeric_settings(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    image.write_text("fake", encoding="utf-8")

    result = prepare_run_request(
        _base_config(
            tmp_path,
            pipeline_mode="FreeSurfer 7 + Volume",
            neuroflow_enabled=True,
            neuroflow_max_retries=9,
            neuroflow_estimation_mode="extreme",
        )
    )

    assert result["ok"] is False
    assert result["request"] is None
    assert result["errors"] == ["NeuroFLOW max retries must be between 0 and 5."]


def test_prepare_run_request_rejects_invalid_neuroflow_estimation_mode(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    image.write_text("fake", encoding="utf-8")

    result = prepare_run_request(
        _base_config(
            tmp_path,
            pipeline_mode="FreeSurfer 7 + Volume",
            neuroflow_enabled=True,
            neuroflow_max_retries=3,
            neuroflow_estimation_mode="extreme",
        )
    )

    assert result["ok"] is False
    assert result["request"] is None
    assert result["errors"] == ["NeuroFLOW estimation mode must be balanced, conservative, or aggressive."]


def test_prepare_run_request_normalizes_dicom_series_dir_input(tmp_path: Path) -> None:
    dicom_dir = tmp_path / "sub-01_dicom"
    dicom_dir.mkdir()
    (dicom_dir / "slice_001.dcm").write_text("fake", encoding="utf-8")
    (dicom_dir / "slice_002.dcm").write_text("fake", encoding="utf-8")

    result = prepare_run_request(
        _base_config(
            tmp_path,
            input_mode="file",
            input_path=str(dicom_dir),
            selected_files=[str(dicom_dir)],
        )
    )
    request = _ok_request(result)

    assert request["mode"] == "dir"
    assert request["is_batch"] is False
    assert request["input_file"] == str(dicom_dir)
    assert request["input_dir"] == str(dicom_dir)
    assert request["recursive"] is False


def test_normalize_stats_vector_config_infers_preset_enabled_stats_from_raw_atlases() -> None:
    raw = {"atlases": {"subcortical_volume": ["freesurfer_aseg"]}}

    normalized = normalize_stats_vector_config_for_pipeline_mode("FreeSurfer 7 + Volume", raw)

    assert normalized == {
        "enabled_stats": {
            "cortical_thickness": False,
            "cortical_volume": False,
            "subcortical_volume": True,
        },
        "atlases": {
            "cortical_thickness": [],
            "cortical_volume": [],
            "subcortical_volume": ["freesurfer_aseg"],
        },
    }


def test_prepare_run_request_preserves_pipeline_mode_for_remote_preset() -> None:
    result = prepare_run_request(
        {
            "input_source": "Server",
            "run_target": "Server",
            "input_mode": "file",
            "input_path": "/data/sub-01.nii",
            "output_dir": "/out",
            "pipeline_mode": "FreeSurfer 8 + Volume + Cortical Thickness",
            "neuroflow_enabled": True,
            "license_dir": "/license/license.txt",
        }
    )

    assert result["ok"] is True
    request = result["request"]
    assert request["pipeline_mode"] == "FreeSurfer 8 + Volume + Cortical Thickness"
    assert request["neuroflow_enabled"] is True


def test_normalize_stats_vector_config_filters_invalid_atlases_for_preset() -> None:
    raw = {"atlases": {"subcortical_volume": ["freesurfer_aseg", "not_a_real_atlas"]}}

    normalized = normalize_stats_vector_config_for_pipeline_mode("FreeSurfer 7 + Volume", raw)

    assert normalized["atlases"]["subcortical_volume"] == ["freesurfer_aseg"]


def test_normalize_stats_vector_config_preserves_custom_config() -> None:
    custom = {
        "enabled_stats": {"subcortical_volume": True},
        "atlases": {"subcortical_volume": ["freesurfer_aseg"], "cortical_volume": ["freesurfer_aparc"]},
    }

    assert normalize_stats_vector_config_for_pipeline_mode("Custom", custom) == custom


def test_normalize_stats_vector_config_ignores_missing_config_for_preset() -> None:
    normalized = normalize_stats_vector_config_for_pipeline_mode("FreeSurfer 7 + Volume", None)

    assert normalized == {
        "enabled_stats": {
            "cortical_thickness": False,
            "cortical_volume": False,
            "subcortical_volume": True,
        },
        "atlases": {
            "cortical_thickness": [],
            "cortical_volume": [],
            "subcortical_volume": ["freesurfer_aseg"],
        },
    }


def test_prepare_run_request_rejects_invalid_custom_tool_combo(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    image.write_text("fake", encoding="utf-8")

    result = prepare_run_request(
        _base_config(
            tmp_path,
            pipeline_mode="Custom",
            selected_tools={
                "reorientation": "fastsurfer_reorientation",
                "segmentation": "fastsurfer_segmentation",
                "stats_extraction": "fs8_reduced54_stats",
            },
        )
    )

    assert result["ok"] is False
    errors = result["errors"]
    assert isinstance(errors, list) and errors
    assert "Invalid tool combination" in str(errors[0])
    assert "stats_extraction" in str(errors[0])


def test_prepare_run_request_accepts_custom_combo_matching_preset(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    image.write_text("fake", encoding="utf-8")
    preset_tools = dict(PRESET_CONFIGS["FastSurfer + Volume"]["tools"])

    result = prepare_run_request(
        _base_config(tmp_path, pipeline_mode="Custom", selected_tools=preset_tools)
    )

    request = _ok_request(result)
    assert request["selected_tools"]["segmentation"] == "fastsurfer_segmentation"


def test_prepare_run_request_skips_combo_check_when_custom_infers_named_preset(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    image.write_text("fake", encoding="utf-8")
    preset_tools = dict(PRESET_CONFIGS["FreeSurfer 8 + Volume"]["tools"])

    result = prepare_run_request(
        _base_config(tmp_path, pipeline_mode="Custom", selected_tools=preset_tools, neuroflow_enabled=True)
    )

    _ok_request(result)


def test_prepare_run_request_rejects_empty_tool_selection(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    image.write_text("fake", encoding="utf-8")

    result = prepare_run_request(_base_config(tmp_path, pipeline_mode="Custom", selected_tools={}))

    assert result["ok"] is False
    errors = result["errors"]
    assert isinstance(errors, list) and errors
    assert "No pipeline steps selected" in str(errors[0])
