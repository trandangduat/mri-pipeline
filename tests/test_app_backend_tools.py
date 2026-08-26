from __future__ import annotations

import threading
import time

from app_backend.tools import CommandResult, ImageInfo, LocalToolService, _default_image_info_provider
from pipeline.registry import tool_display_name


class FakeCommandRunner:
    def __init__(self, installed: set[str]) -> None:
        self.installed = installed
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> CommandResult:
        self.commands.append(command)
        image = command[-1]
        return CommandResult(returncode=0 if image in self.installed else 1)


def _fake_image_info(image: str) -> ImageInfo:
    return ImageInfo(
        content_size_bytes=1024 * 1024 * 100,
        disk_usage="325.0 MB",
        image_id="sha256:abc123def45",
    )


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
                "tool_details": [{"key": "fs7_recon_style_segmentation", "name": tool_display_name("fs7_recon_style_segmentation")}],
                "disk_usage": "325.0 MB",
                "content_size": "100.0 MB",
                "image_id": "sha256:abc123def45",
            }
        ],
        "warnings": [],
    }
    assert runner.commands == [["docker", "image", "inspect", "mkdayyyy/mri-fs7-all:latest"]]


def test_default_image_info_provider_keeps_disk_usage_distinct(monkeypatch) -> None:
    from app_backend import tools as tools_module

    commands: list[list[str]] = []

    class Result:
        returncode = 0

        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def run(command: list[str], **_kwargs) -> Result:
        commands.append(command)
        if command[2] == "ls":
            return Result("325MB\n")
        return Result("sha256:abc123def456789\n")

    monkeypatch.setattr(tools_module, "image_size_bytes", lambda _image: 100 * 1024 * 1024)
    monkeypatch.setattr(tools_module.subprocess, "run", run)

    info = _default_image_info_provider("example/image:latest")

    assert info == ImageInfo(
        content_size_bytes=100 * 1024 * 1024,
        disk_usage="325MB",
        image_id="sha256:abc123def456",
    )
    assert commands[0] == [
        "docker",
        "image",
        "ls",
        "--format",
        "{{.Size}}",
        "example/image:latest",
    ]


def test_local_tool_service_reports_missing_and_unknown_tools() -> None:
    runner = FakeCommandRunner(installed=set())
    requested: list[str] = []

    def download_size(image: str) -> int:
        requested.append(image)
        return 13 * 1024**3 + 300 * 1024**2

    service = LocalToolService(
        command_runner=runner,
        image_info_provider=_fake_image_info,
        download_size_provider=download_size,
    )

    result = service.local_image_status({"segmentation": "fs7_recon_style_segmentation", "bad": "missing_tool"})

    assert result["ok"] is True
    assert result["warnings"] == ["Unknown tool ignored: missing_tool"]
    images = result["images"]
    assert isinstance(images, list)
    assert images[0]["status"] == "Missing"
    assert images[0]["download_size"] == "13.3 GB"
    service.local_image_status({"segmentation": "fs7_recon_style_segmentation"})
    assert requested == ["mkdayyyy/mri-fs7-all:latest"]


def test_local_tool_service_bounds_concurrent_download_size_lookups() -> None:
    lock = threading.Lock()
    active = 0
    peak_active = 0
    requested: list[str] = []

    def download_size(image: str) -> int:
        nonlocal active, peak_active
        with lock:
            requested.append(image)
            active += 1
            peak_active = max(peak_active, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return 1024

    service = LocalToolService(
        command_runner=FakeCommandRunner(installed=set()),
        image_info_provider=_fake_image_info,
        download_size_provider=download_size,
    )

    result = service.local_image_status()

    images = result["images"]
    assert isinstance(images, list)
    assert len(requested) == len({entry["image"] for entry in images})
    assert 1 < peak_active <= 4


def test_local_tool_service_keeps_download_size_failure_non_fatal() -> None:
    attempts = 0

    def fail(_image: str) -> int:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("registry unavailable")

    service = LocalToolService(
        command_runner=FakeCommandRunner(installed=set()),
        image_info_provider=_fake_image_info,
        download_size_provider=fail,
    )

    result = service.local_image_status({"segmentation": "fs7_recon_style_segmentation"})

    assert result["ok"] is True
    assert result["images"][0]["download_size"] is None
    service.local_image_status({"segmentation": "fs7_recon_style_segmentation"})
    assert attempts == 2


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

    def check_image_states(self, images: list[str]) -> dict[str, dict[str, object]]:
        self.checked_images = images
        states: dict[str, dict[str, object]] = {}
        for img in images:
            if img in self.installed_images:
                states[img] = {"status": "Installed", "pull_status": None}
            else:
                states[img] = {"status": "Missing", "pull_status": None}
        return states


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
                "tool_details": [{"key": "fs7_recon_style_segmentation", "name": tool_display_name("fs7_recon_style_segmentation")}],
                "disk_usage": None,
                "content_size": None,
                "image_id": None,
            }
        ],
        "warnings": [],
    }
    assert fake_remote.checked_images == ["mkdayyyy/mri-fs7-all:latest"]


def test_tool_service_adds_download_size_to_missing_server_images() -> None:
    fake_remote = FakeRemoteRunner(installed_images=set())
    service = LocalToolService(
        command_runner=FakeCommandRunner(installed=set()),
        remote_runner_factory=lambda _cfg: fake_remote,
        image_info_provider=_fake_image_info,
        download_size_provider=lambda _image: 800 * 1024**2,
    )

    result = service.image_status(
        selected_tools={"segmentation": "fs7_recon_style_segmentation"},
        target="Server",
        remote={"host": "server", "username": "alice", "key_path": "/path/to/key"},
    )

    assert result["ok"] is True
    assert result["images"][0]["download_size"] == "800.0 MB"


def test_server_pull_status_reads_state_and_log_tail(monkeypatch) -> None:
    from app_backend import tools as tools_module

    class FakeSSH:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read_text(self, command: str):
            if ".json" in command:
                return 0, '{"status": "pulling", "pid": 42, "exit_code": null, "error": null}'
            return 0, "layer: Downloading 50MB/100MB\nlayer: Pull complete\n"

    class FakeConfig:
        class ssh:
            host = "server"
            port = 22
            username = "alice"
            password = ""
            key_path = ""

        remote_workspace = "~/ws"
        remote_python = "python3"
        output_dir = ""

    class FakeRunner:
        config = FakeConfig
        on_log = staticmethod(lambda _line: None)

    monkeypatch.setattr(tools_module, "RemoteSSHClient", FakeSSH)

    service = LocalToolService(
        command_runner=FakeCommandRunner(installed=set()),
        remote_runner_factory=lambda _cfg: FakeRunner(),
        image_info_provider=_fake_image_info,
    )

    result = service.server_pull_status(
        "mkdayyyy/mri-fs7-all:latest",
        {"host": "server", "username": "alice", "port": 22},
        log_offset=0,
    )

    assert result["ok"] is True
    assert result["status"] == "pulling"
    assert result["exit_code"] is None
    log_text = result["log_text"]
    assert isinstance(log_text, str) and "Pull complete" in log_text
    assert result["next_offset"] == len(log_text.encode("utf-8"))


def test_server_pull_status_reports_terminal_failure(monkeypatch) -> None:
    from app_backend import tools as tools_module

    class FakeSSH:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read_text(self, command: str):
            if ".json" in command:
                return 0, '{"status": "failed", "exit_code": 1, "error": "no space left on device"}'
            return 0, ""

    monkeypatch.setattr(tools_module, "RemoteSSHClient", FakeSSH)

    class FakeConfig:
        class ssh:
            host = "server"
            port = 22
            username = "alice"
            password = ""
            key_path = ""

        remote_workspace = "~/ws"
        remote_python = "python3"
        output_dir = ""

    class FakeRunner:
        config = FakeConfig
        on_log = staticmethod(lambda _line: None)

    service = LocalToolService(
        command_runner=FakeCommandRunner(installed=set()),
        remote_runner_factory=lambda _cfg: FakeRunner(),
        image_info_provider=_fake_image_info,
    )

    result = service.server_pull_status(
        "mkdayyyy/mri-fs7-all:latest",
        {"host": "server", "username": "alice", "port": 22},
    )

    assert result["ok"] is True
    assert result["exit_code"] == 1
    assert result["error"] == "no space left on device"
