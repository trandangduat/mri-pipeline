from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app_backend.run_request import RunRequestInput, prepare_run_request
from pipeline.config import ExportConfig, StatsVectorConfig
from pipeline.presets import PRESET_CONFIGS


def _base_config(tmp_path: Path, **overrides: object) -> RunRequestInput:
    data: dict[str, object] = {
        "input_path": str(tmp_path / "image.nii.gz"),
        "output_dir": str(tmp_path / "outputs"),
        "license_dir": str(tmp_path / "license"),
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
    image.write_text("fake", encoding="utf-8")

    result = prepare_run_request(_base_config(tmp_path))
    request = _ok_request(result)

    assert request["mode"] == "file"
    assert request["input_file"] == str(image)
    assert request["output_dir"] == str(tmp_path / "outputs")
    assert request["effective_output_dir"] == str(tmp_path / "outputs")
    assert request["threads"] == 4
    assert request["ram_percent"] == 100
    json.dumps(result)


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


def test_prepare_run_request_blocks_remote_until_remote_phase(tmp_path: Path) -> None:
    result = prepare_run_request(
        _base_config(
            tmp_path,
            input_source="Server",
            run_target="Server",
            input_path="/data/image.nii.gz",
        )
    )

    assert result["ok"] is False
    assert result["request"] is None
    assert result["errors"] == ["Remote run request preparation is deferred to the remote migration phase."]
