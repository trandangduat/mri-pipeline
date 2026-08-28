from __future__ import annotations

from types import SimpleNamespace

import json

from pipeline.docker_ops import (
    check_freesurfer_license,
    docker_hub_repository_tag,
    image_download_size_bytes,
    manifest_download_size_bytes,
)


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
    assert "mri_convert" in command[-1]
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


def test_image_download_size_sums_single_manifest_layers(mocker) -> None:
    run = mocker.patch(
        "pipeline.docker_ops.subprocess.run",
        return_value=SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"OCIManifest": {"layers": [{"size": 100}, {"size": 250}, {"size": "bad"}]}}),
        ),
    )

    assert manifest_download_size_bytes("example/image:latest") == 350
    assert run.call_args.args[0] == ["docker", "manifest", "inspect", "--verbose", "example/image:latest"]


def test_image_download_size_supports_docker_schema_manifest(mocker) -> None:
    mocker.patch(
        "pipeline.docker_ops.subprocess.run",
        return_value=SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"SchemaV2Manifest": {"layers": [{"size": 125}, {"size": 75}]}}),
        ),
    )

    assert manifest_download_size_bytes("example/image:latest") == 200


def test_image_download_size_selects_runnable_amd64_manifest(mocker) -> None:
    manifests = [
        {
            "Descriptor": {"platform": {"os": "unknown", "architecture": "unknown"}},
            "OCIManifest": {"layers": [{"size": 999}]},
        },
        {
            "Descriptor": {"platform": {"os": "linux", "architecture": "arm64"}},
            "OCIManifest": {"layers": [{"size": 50}]},
        },
        {
            "Descriptor": {"platform": {"os": "linux", "architecture": "amd64"}},
            "OCIManifest": {"layers": [{"size": 100}, {"size": 200}]},
        },
    ]
    mocker.patch(
        "pipeline.docker_ops.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout=json.dumps(manifests)),
    )

    assert manifest_download_size_bytes("example/image:latest") == 300


def test_image_download_size_returns_none_for_invalid_json_or_failed_command(mocker) -> None:
    run = mocker.patch(
        "pipeline.docker_ops.subprocess.run",
        return_value=SimpleNamespace(returncode=0, stdout="not json"),
    )
    assert manifest_download_size_bytes("example/image:latest") is None

    run.return_value = SimpleNamespace(returncode=1, stdout="")
    assert manifest_download_size_bytes("example/image:latest") is None


def test_docker_hub_repository_tag_parses_scoped_references() -> None:
    assert docker_hub_repository_tag("namespace/repository:release") == ("namespace", "repository", "release")
    assert docker_hub_repository_tag("namespace/repository") == ("namespace", "repository", "latest")
    assert docker_hub_repository_tag("localhost:5000/repository:release") is None
    assert docker_hub_repository_tag("registry.example.com/namespace/repository:release") is None


def test_image_download_size_reads_linux_amd64_docker_hub_size(mocker) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "images": [
                        {"os": "unknown", "architecture": "unknown", "size": 999},
                        {"os": "linux", "architecture": "arm64", "size": 100},
                        {"os": "linux", "architecture": "amd64", "size": 14297922800},
                    ]
                }
            ).encode()

    urlopen = mocker.patch("pipeline.docker_ops.urllib.request.urlopen", return_value=Response())

    assert image_download_size_bytes("mkdayyyy/mri-fs8-all:latest") == 14297922800
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://hub.docker.com/v2/repositories/mkdayyyy/mri-fs8-all/tags/latest"
