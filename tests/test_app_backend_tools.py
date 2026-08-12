from __future__ import annotations

from app_backend.tools import CommandResult, ImageInfo, LocalToolService


class FakeCommandRunner:
    def __init__(self, installed: set[str]) -> None:
        self.installed = installed
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> CommandResult:
        self.commands.append(command)
        image = command[-1]
        return CommandResult(returncode=0 if image in self.installed else 1)


def _fake_image_info(image: str) -> ImageInfo:
    return ImageInfo(size_bytes=1024 * 1024 * 100, image_id="sha256:abc123def45")


def test_local_tool_service_checks_selected_tool_images_without_shell() -> None:
    runner = FakeCommandRunner(installed={"mkdayyyy/mri-fs7-all:latest"})
    service = LocalToolService(command_runner=runner, image_info_provider=_fake_image_info)

    result = service.local_image_status({"segmentation": "fs7_recon_style_segmentation"})

    assert result == {
        "ok": True,
        "target": "Local",
        "images": [
            {
                "image": "mkdayyyy/mri-fs7-all:latest",
                "status": "Installed",
                "tools": ["fs7_recon_style_segmentation"],
                "tool_details": [{"key": "fs7_recon_style_segmentation", "name": "FS7 Recon Style Segmentation"}],
                "repo_size": "100.0 MB",
                "uncompressed_size": "100.0 MB",
                "image_id": "sha256:abc123def45",
            }
        ],
        "warnings": [],
    }
    assert runner.commands == [["docker", "image", "inspect", "mkdayyyy/mri-fs7-all:latest"]]


def test_local_tool_service_reports_missing_and_unknown_tools() -> None:
    runner = FakeCommandRunner(installed=set())
    service = LocalToolService(command_runner=runner, image_info_provider=_fake_image_info)

    result = service.local_image_status({"segmentation": "fs7_recon_style_segmentation", "bad": "missing_tool"})

    assert result["ok"] is True
    assert result["warnings"] == ["Unknown tool ignored: missing_tool"]
    images = result["images"]
    assert isinstance(images, list)
    assert images[0]["status"] == "Missing"


def test_local_tool_service_returns_safe_error_when_docker_unavailable() -> None:
    def runner(_command: list[str]) -> CommandResult:
        raise FileNotFoundError("docker")

    service = LocalToolService(command_runner=runner, image_info_provider=_fake_image_info)

    assert service.local_image_status({"segmentation": "fs7_recon_style_segmentation"}) == {
        "ok": False,
        "error": "Docker command failed",
    }


def test_local_tool_service_rejects_malformed_selected_tool_values() -> None:
    service = LocalToolService(command_runner=FakeCommandRunner(installed=set()), image_info_provider=_fake_image_info)

    assert service.local_image_status({"segmentation": {"bad": "shape"}}) == {
        "ok": False,
        "error": "selected_tools values must be strings",
    }


class FakeRemoteRunner:
    def __init__(self, installed_images: set[str]) -> None:
        self.installed_images = installed_images
        self.checked_images: list[str] = []

    def check_image_statuses(self, images: list[str]) -> dict[str, bool]:
        self.checked_images = images
        return {img: (img in self.installed_images) for img in images}


def test_tool_service_checks_server_target_images() -> None:
    fake_remote = FakeRemoteRunner(installed_images={"mkdayyyy/mri-fs7-all:latest"})
    service = LocalToolService(
        command_runner=FakeCommandRunner(installed=set()),
        remote_runner_factory=lambda _cfg: fake_remote,
        image_info_provider=_fake_image_info,
    )

    result = service.image_status(
        selected_tools={"segmentation": "fs7_recon_style_segmentation"},
        target="Server",
        remote={"host": "server", "username": "alice", "key_path": "/path/to/key"},
    )

    assert result == {
        "ok": True,
        "target": "Server",
        "images": [
            {
                "image": "mkdayyyy/mri-fs7-all:latest",
                "status": "Installed",
                "tools": ["fs7_recon_style_segmentation"],
                "tool_details": [{"key": "fs7_recon_style_segmentation", "name": "FS7 Recon Style Segmentation"}],
                "repo_size": None,
                "uncompressed_size": None,
                "image_id": None,
            }
        ],
        "warnings": [],
    }
    assert fake_remote.checked_images == ["mkdayyyy/mri-fs7-all:latest"]
