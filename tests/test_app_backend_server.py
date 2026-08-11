from __future__ import annotations

import json
import http.client
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app_backend.config_store import ConfigStore
from app_backend.environment import LocalEnvironmentService
from app_backend.jobs import LocalJobService, ProcessHandle
from app_backend.remote import RemoteJobService
from app_backend.server import make_server
from app_backend.tools import LocalToolService


class FakeProcessRunner:
    def __init__(self, pid: int = 2468) -> None:
        self.pid = pid

    def __call__(self, command: list[str]) -> ProcessHandle:
        return ProcessHandle(pid=self.pid)


def _serve_in_thread(
    local_job_service: LocalJobService | None = None,
    config_store: ConfigStore | None = None,
    remote_job_service: RemoteJobService | None = None,
    local_tool_service: LocalToolService | None = None,
    local_environment_service: LocalEnvironmentService | None = None,
) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    server = make_server(
        "127.0.0.1",
        0,
        local_job_service=local_job_service,
        config_store=config_store,
        remote_job_service=remote_job_service,
        local_tool_service=local_tool_service,
        local_environment_service=local_environment_service,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_address[1]}"


def _get_json(url: str) -> dict[str, object]:
    with urlopen(url, timeout=5) as response:
        assert response.headers["Content-Type"].startswith("application/json")
        return json.loads(response.read().decode("utf-8"))


def _get_with_origin(url: str) -> tuple[int, str | None, dict[str, object]]:
    request = Request(url, headers={"Origin": "http://127.0.0.1:1420"})
    with urlopen(request, timeout=5) as response:
        return response.status, response.headers.get("Access-Control-Allow-Origin"), json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        assert response.headers["Content-Type"].startswith("application/json")
        return json.loads(response.read().decode("utf-8"))


def _post_raw(url: str, body: bytes, content_type: str) -> tuple[int, dict[str, object]]:
    request = Request(
        url,
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _post_declared_oversized_json(url: str) -> tuple[int, dict[str, object]]:
    parsed = urlparse(url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
    try:
        connection.putrequest("POST", parsed.path)
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", "1000001")
        connection.endheaders()
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


def _request_without_body(method: str, url: str) -> tuple[int, str, dict[str, object]]:
    parsed = urlparse(url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
    try:
        connection.request(method, parsed.path)
        response = connection.getresponse()
        return response.status, response.getheader("Content-Type", ""), json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


def _options(url: str) -> tuple[int, str | None, str | None]:
    parsed = urlparse(url)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
    try:
        connection.request(
            "OPTIONS",
            parsed.path,
            headers={
                "Origin": "http://127.0.0.1:1420",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        response = connection.getresponse()
        response.read()
        return response.status, response.getheader("Access-Control-Allow-Origin"), response.getheader("Access-Control-Allow-Headers")
    finally:
        connection.close()


def test_sidecar_health_and_metadata_endpoints() -> None:
    server, thread, base_url = _serve_in_thread()
    try:
        health = _get_json(f"{base_url}/health")
        assert health["ok"] is True
        assert health["service"] == "mri-pipeline-backend"
        assert isinstance(health["pid"], int)
        metadata = _get_json(f"{base_url}/metadata")
        assert metadata["version"] == 1
        assert "pipeline_modes" in metadata
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_allows_tauri_dev_origin_and_json_preflight() -> None:
    server, thread, base_url = _serve_in_thread()
    try:
        status, origin, payload = _get_with_origin(f"{base_url}/health")
        assert status == 200
        assert origin == "*"
        assert payload["ok"] is True
        assert payload["service"] == "mri-pipeline-backend"
        assert isinstance(payload["pid"], int)

        options_status, options_origin, options_headers = _options(f"{base_url}/run-request/prepare")
        assert options_status == 204
        assert options_origin == "*"
        assert options_headers is not None
        assert "Content-Type" in options_headers
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_prepare_run_request_endpoint(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    image.write_text("fake", encoding="utf-8")
    server, thread, base_url = _serve_in_thread()
    try:
        result = _post_json(
            f"{base_url}/run-request/prepare",
            {
                "input_path": str(image),
                "output_dir": str(tmp_path / "outputs"),
                "selected_tools": {"segmentation": "synthseg_freesurfer_fs7"},
            },
        )
        assert result["ok"] is True
        request = result["request"]
        assert isinstance(request, dict)
        assert request["input_file"] == str(image)
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_local_job_start_list_and_stop_endpoints(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    image.write_text("fake", encoding="utf-8")
    service = LocalJobService(jobs_root=tmp_path / "jobs", process_runner=FakeProcessRunner(), clock=lambda: 456.0)
    server, thread, base_url = _serve_in_thread(service)
    try:
        start_result = _post_json(
            f"{base_url}/jobs/local/start",
            {
                "run_request": {
                    "mode": "file",
                    "input_file": str(image),
                    "output_dir": str(tmp_path / "outputs"),
                    "effective_output_dir": str(tmp_path / "outputs"),
                    "selected_tools": {"segmentation": "synthseg_freesurfer_fs7"},
                    "pipeline_mode": "Custom",
                }
            },
        )
        assert start_result["ok"] is True
        job = start_result["job"]
        assert isinstance(job, dict)
        assert job["state"] == "running"

        list_result = _get_json(f"{base_url}/jobs/local")
        assert list_result["ok"] is True
        jobs = list_result["jobs"]
        assert isinstance(jobs, list)
        assert jobs[0]["job_id"] == job["job_id"]

        stop_result = _post_json(f"{base_url}/jobs/local/stop", {"job_id": job["job_id"]})
        assert stop_result["ok"] is True
        assert stop_result["accepted"] is True
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_local_job_events_and_log_endpoints(tmp_path: Path) -> None:
    image = tmp_path / "image.nii.gz"
    image.write_text("fake", encoding="utf-8")
    service = LocalJobService(jobs_root=tmp_path / "jobs", process_runner=FakeProcessRunner(), clock=lambda: 456.0)
    started = service.start_local_job(
        {
            "mode": "file",
            "input_file": str(image),
            "output_dir": str(tmp_path / "outputs"),
            "effective_output_dir": str(tmp_path / "outputs"),
        }
    )
    job = started["job"]
    assert isinstance(job, dict)
    job_dir = Path(str(job["job_dir"]))
    (job_dir / "events.jsonl").write_text(json.dumps({"kind": "progress"}) + "\n", encoding="utf-8")
    (job_dir / "run.log").write_text("abcdef", encoding="utf-8")
    server, thread, base_url = _serve_in_thread(service)
    job_id = quote(str(job["job_id"]))
    try:
        events = _get_json(f"{base_url}/jobs/local/events?job_id={job_id}&offset=0&limit=10")
        assert events["ok"] is True
        assert events["events"] == [{"kind": "progress"}]

        log = _get_json(f"{base_url}/jobs/local/log?job_id={job_id}&offset=2&max_bytes=3")
        assert log == {"ok": True, "text": "cde", "next_offset": 5, "truncated": True}
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_service_errors_return_json(tmp_path: Path) -> None:
    jobs_root = tmp_path / "jobs"
    jobs_root.mkdir()
    (jobs_root / "job_registry.json").write_text("not json", encoding="utf-8")
    service = LocalJobService(jobs_root=jobs_root, process_runner=FakeProcessRunner(), clock=lambda: 456.0)
    server, thread, base_url = _serve_in_thread(service)
    try:
        try:
            _get_json(f"{base_url}/jobs/local")
        except HTTPError as exc:
            assert exc.code == 500
            assert exc.headers["Content-Type"].startswith("application/json")
            payload = json.loads(exc.read().decode("utf-8"))
            assert payload == {"ok": False, "error": "Internal server error"}
        else:
            raise AssertionError("Expected 500")
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_workspace_config_endpoints(tmp_path: Path) -> None:
    store = ConfigStore(config_root=tmp_path / "configs")
    server, thread, base_url = _serve_in_thread(config_store=store)
    try:
        saved = _post_json(
            f"{base_url}/config/workspaces/save",
            {"name": "workspace one", "data": {"remote": {"host": "server", "password": "secret"}}},
        )
        assert saved["ok"] is True
        assert saved["name"] == "workspace_one"

        listed = _get_json(f"{base_url}/config/workspaces")
        assert listed["ok"] is True
        assert listed["items"] == [{"name": "workspace_one", "path": str(tmp_path / "configs" / "workspaces" / "workspace_one.json")}]

        loaded = _get_json(f"{base_url}/config/workspaces/load?name=workspace_one")
        assert loaded["ok"] is True
        data = loaded["data"]
        assert isinstance(data, dict)
        assert data["remote"] == {"host": "server"}
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_remote_validate_and_jobs_endpoints() -> None:
    class FakeRemoteService(RemoteJobService):
        def validate_config(self, data: dict[str, object]) -> dict[str, object]:
            return {"ok": True, "config": {"host": data.get("host", "")}}

        def list_jobs(self, data: dict[str, object]) -> dict[str, object]:
            return {"ok": True, "jobs": [{"target": "Server", "state": "running", "remote_job_dir": "/workspace/job_1"}]}

    server, thread, base_url = _serve_in_thread(remote_job_service=FakeRemoteService())
    try:
        validated = _post_json(f"{base_url}/remote/validate", {"host": "server", "username": "alice", "password": "secret"})
        assert validated == {"ok": True, "config": {"host": "server"}}

        jobs = _post_json(f"{base_url}/remote/jobs", {"host": "server", "username": "alice", "password": "secret"})
        assert jobs == {"ok": True, "jobs": [{"target": "Server", "state": "running", "remote_job_dir": "/workspace/job_1"}]}
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_local_tool_image_status_endpoint() -> None:
    class FakeToolService(LocalToolService):
        def image_status(
            self,
            selected_tools: dict[str, object] | None = None,
            target: str = "Local",
            remote: dict[str, object] | None = None,
        ) -> dict[str, object]:
            return {
                "ok": True,
                "target": target,
                "images": [{"image": "example:latest", "status": "Installed"}],
                "selected": selected_tools or {},
                "remote_host": str(remote.get("host", "")) if isinstance(remote, dict) else "",
            }

    server, thread, base_url = _serve_in_thread(local_tool_service=FakeToolService())
    try:
        result = _post_json(
            f"{base_url}/tools/local/images",
            {"target": "Server", "selected_tools": {"segmentation": "tool"}, "remote": {"host": "server"}},
        )
        assert result == {
            "ok": True,
            "target": "Server",
            "images": [{"image": "example:latest", "status": "Installed"}],
            "selected": {"segmentation": "tool"},
            "remote_host": "server",
        }
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_local_environment_status_endpoint() -> None:
    service = LocalEnvironmentService(
        which=lambda command: f"/bin/{command}" if command in {"python3", "docker", "ssh"} else None,
        python_version=lambda: "3.12.3",
    )
    server, thread, base_url = _serve_in_thread(local_environment_service=service)
    try:
        result = _get_json(f"{base_url}/environment/local")
        assert result["ok"] is True
        assert result["python"] == {"ok": True, "path": "/bin/python3", "version": "3.12.3"}
        assert result["docker"] == {"ok": True, "path": "/bin/docker"}
        assert result["ssh"] == {"ok": True, "path": "/bin/ssh"}
        assert isinstance(result["hardware"], dict)
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_unknown_route_returns_json_error() -> None:
    server, thread, base_url = _serve_in_thread()
    try:
        try:
            _get_json(f"{base_url}/missing")
        except HTTPError as exc:
            assert exc.code == 404
            payload = json.loads(exc.read().decode("utf-8"))
            assert payload == {"ok": False, "error": "Not found"}
        else:
            raise AssertionError("Expected 404")
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_rejects_non_json_and_oversized_bodies() -> None:
    server, thread, base_url = _serve_in_thread()
    try:
        status, payload = _post_raw(f"{base_url}/run-request/prepare", b"x", "text/plain")
        assert status == 415
        assert payload == {"ok": False, "error": "Content-Type must be application/json"}

        status, payload = _post_raw(f"{base_url}/run-request/prepare", b"{}", "text/application/json-plus")
        assert status == 415
        assert payload == {"ok": False, "error": "Content-Type must be application/json"}

        status, payload = _post_raw(f"{base_url}/run-request/prepare", b"", "application/json")
        assert status == 400
        assert payload == {"ok": False, "error": "Invalid JSON body"}

        status, payload = _post_raw(f"{base_url}/run-request/prepare", b"{}", "application/json")
        assert status == 200
        assert payload["ok"] is False

        status, payload = _post_declared_oversized_json(f"{base_url}/run-request/prepare")
        assert status == 413
        assert payload == {"ok": False, "error": "Request body too large"}
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_unsupported_methods_return_json_error() -> None:
    server, thread, base_url = _serve_in_thread()
    try:
        status, content_type, payload = _request_without_body("PUT", f"{base_url}/health")
        assert status == 405
        assert content_type.startswith("application/json")
        assert payload == {"ok": False, "error": "Method not allowed"}
    finally:
        server.shutdown()
        thread.join(timeout=5)
