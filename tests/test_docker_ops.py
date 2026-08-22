from __future__ import annotations

from types import SimpleNamespace

from pipeline.docker_ops import check_freesurfer_license


def test_check_freesurfer_license_runs_lightweight_command(tmp_path, mocker) -> None:
    license_file = tmp_path / "license.txt"
    license_file.write_text("license", encoding="utf-8")
    mocker.patch("pipeline.docker_ops.image_exists", return_value=True)
    run = mocker.patch(
        "pipeline.docker_ops.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    ok, detail = check_freesurfer_license(
        {"segmentation": "fs7_recon_style_segmentation"},
        str(license_file),
    )

    assert ok is True
    assert detail == "FreeSurfer license check passed."
    command = run.call_args.args[0]
    assert command[:5] == ["docker", "run", "--rm", "--entrypoint", "/bin/bash"]
    assert "mkdayyyy/mri-fs7-all:latest" in command
    assert "recon-all -version" in command[-1]
    assert f"{license_file}:/license/license.txt:ro" in command


def test_check_freesurfer_license_reports_command_failure(tmp_path, mocker) -> None:
    license_file = tmp_path / "license.txt"
    license_file.write_text("invalid", encoding="utf-8")
    mocker.patch("pipeline.docker_ops.image_exists", return_value=True)
    mocker.patch(
        "pipeline.docker_ops.subprocess.run",
        return_value=SimpleNamespace(returncode=1, stdout="", stderr="license invalid"),
    )

    ok, detail = check_freesurfer_license(
        {"segmentation": "fs7_recon_style_segmentation"},
        str(license_file),
    )

    assert ok is False
    assert detail == "FreeSurfer license check failed (fs7_recon_style_segmentation): license invalid"


def test_check_freesurfer_license_skips_unlicensed_tools(mocker) -> None:
    run = mocker.patch("pipeline.docker_ops.subprocess.run")

    ok, detail = check_freesurfer_license({"segmentation": "cat12_volume_segmentation"}, "")

    assert ok is True
    assert detail == "No FreeSurfer license is required for the selected tools."
    run.assert_not_called()
