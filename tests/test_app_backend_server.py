from __future__ import annotations

import json
import base64
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
from app_backend.licenses import LicenseStore
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
    license_store: LicenseStore | None = None,
) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
    server = make_server(
        "127.0.0.1",
        0,
        local_job_service=local_job_service,
        config_store=config_store,
        remote_job_service=remote_job_service,
        local_tool_service=local_tool_service,
        local_environment_service=local_environment_service,
        license_store=license_store,
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
    license_file = tmp_path / "license.txt"
    image.write_text("fake", encoding="utf-8")
    license_file.write_text("license", encoding="utf-8")
    server, thread, base_url = _serve_in_thread()
    try:
        result = _post_json(
            f"{base_url}/run-request/prepare",
            {
                "input_path": str(image),
                "output_dir": str(tmp_path / "outputs"),
                "selected_tools": {"segmentation": "synthseg_freesurfer_fs7"},
                "license_dir": str(license_file),
            },
        )
        assert result["ok"] is True
        request = result["request"]
        assert isinstance(request, dict)
        assert request["input_file"] == str(image)
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_uploads_license_file_to_backend_store(tmp_path: Path) -> None:
    store = LicenseStore(tmp_path / "licenses")
    server, thread, base_url = _serve_in_thread(license_store=store)
    try:
        result = _post_json(
            f"{base_url}/licenses/upload",
            {
                "filename": "../license.txt",
                "content_base64": base64.b64encode(b"license-body").decode("ascii"),
            },
        )
        assert result["ok"] is True
        path = Path(str(result["path"]))
        assert path.parent == tmp_path / "licenses"
        assert path.name.endswith("-license.txt")
        assert path.read_bytes() == b"license-body"
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
    service = LocalJobService(jobs_root=jobs_root, process_runner=FakeProcessRunner(), clock=lambda: 456.0)
    def _fail() -> dict[str, JsonValue]:
        raise RuntimeError("boom")
    service.list_local_jobs = _fail  # type: ignore[method-assign]
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


def test_sidecar_remote_download_stream_endpoint() -> None:
    class FakeRemoteService(RemoteJobService):
        def stream_download_outputs(self, data: dict[str, object]):
            yield {"event": "step", "data": {"step": "connect", "status": "running", "detail": "Connecting..."}}
            yield {"event": "step", "data": {"step": "connect", "status": "done", "detail": "Connected"}}
            yield {"event": "step", "data": {"step": "copy", "status": "done", "detail": "Copied 3 file(s)", "copied_files": 3, "total_files": 3, "pct": 100}}
            yield {"event": "complete", "data": {"ok": True, "local_path": "/tmp/outputs", "copied_files": 3, "total_files": 3}}

    server, thread, base_url = _serve_in_thread(remote_job_service=FakeRemoteService())
    try:
        import http.client
        parsed = urlparse(f"{base_url}/remote/jobs/download/stream")
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=10)
        try:
            body = json.dumps({
                "host": "server",
                "port": 22,
                "username": "tester",
                "password": "",
                "key_path": "",
                "workspace": "~/mri-remote-jobs",
                "remote_python": "python3",
                "remote_job_dir": "/workspace/job_1",
                "local_target_dir": "/tmp/outputs",
            }).encode("utf-8")
            conn.putrequest("POST", parsed.path)
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", str(len(body)))
            conn.endheaders()
            conn.send(body)
            response = conn.getresponse()
            raw = response.read().decode("utf-8")
        finally:
            conn.close()

        assert response.status == 200
        assert response.getheader("Content-Type", "").startswith("text/event-stream")
        assert "event: step" in raw
        assert "event: complete" in raw
        assert '"ok": true' in raw
        assert "/tmp/outputs" in raw
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_remote_download_stream_missing_local_target() -> None:
    class FakeRemoteService(RemoteJobService):
        def stream_download_outputs(self, data: dict[str, object]):
            yield {"event": "step", "data": {"step": "connect", "status": "failed", "detail": "local_target_dir is required"}}
            yield {"event": "complete", "data": {"ok": False, "error": "local_target_dir is required"}}

    server, thread, base_url = _serve_in_thread(remote_job_service=FakeRemoteService())
    try:
        import http.client
        parsed = urlparse(f"{base_url}/remote/jobs/download/stream")
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=10)
        try:
            body = json.dumps({
                "host": "server",
                "port": 22,
                "username": "tester",
                "remote_job_dir": "/workspace/job_1",
            }).encode("utf-8")
            conn.putrequest("POST", parsed.path)
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", str(len(body)))
            conn.endheaders()
            conn.send(body)
            response = conn.getresponse()
            raw = response.read().decode("utf-8")
        finally:
            conn.close()

        assert response.status == 200
        assert '"ok": false' in raw
        assert "local_target_dir is required" in raw
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_local_start_stream_endpoint() -> None:
    class FakeLocalJobService(LocalJobService):
        def stream_start_job(self, run_request: dict[str, object]):
            yield {"event": "step", "data": {"step": "validate", "status": "done", "detail": "Valid"}}
            yield {"event": "complete", "data": {"ok": True, "job": {"job_id": "job-123"}}}

    server, thread, base_url = _serve_in_thread(local_job_service=FakeLocalJobService())
    try:
        import http.client
        parsed = urlparse(f"{base_url}/jobs/local/start/stream")
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=10)
        try:
            body = json.dumps({"input_path": "/fake/input.nii.gz"}).encode("utf-8")
            conn.putrequest("POST", parsed.path)
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", str(len(body)))
            conn.endheaders()
            conn.send(body)
            response = conn.getresponse()
            raw = response.read().decode("utf-8")
        finally:
            conn.close()

        assert response.status == 200
        assert response.getheader("Content-Type", "").startswith("text/event-stream")
        assert "event: step" in raw
        assert "event: complete" in raw
        assert '"ok": true' in raw
        assert "job-123" in raw
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_sidecar_remote_start_stream_endpoint() -> None:
    class FakeRemoteService(RemoteJobService):
        def stream_start_job(self, data: dict[str, object]):
            yield {"event": "step", "data": {"step": "ssh", "status": "done", "detail": "SSH ok"}}
            yield {"event": "complete", "data": {"ok": True, "job": {"job_id": "remote-job-123"}}}

    server, thread, base_url = _serve_in_thread(remote_job_service=FakeRemoteService())
    try:
        import http.client
        parsed = urlparse(f"{base_url}/remote/jobs/start/stream")
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=10)
        try:
            body = json.dumps({
                "host": "server",
                "port": 22,
                "username": "tester",
                "run_request": {"input_path": "/remote/input.nii.gz"},
            }).encode("utf-8")
            conn.putrequest("POST", parsed.path)
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", str(len(body)))
            conn.endheaders()
            conn.send(body)
            response = conn.getresponse()
            raw = response.read().decode("utf-8")
        finally:
            conn.close()

        assert response.status == 200
        assert response.getheader("Content-Type", "").startswith("text/event-stream")
        assert "event: step" in raw
        assert "event: complete" in raw
        assert '"ok": true' in raw
        assert "remote-job-123" in raw
    finally:
        server.shutdown()
        thread.join(timeout=5)



def _make_download_service(runner_factory=None):
    """Create a RemoteJobService with a custom runner_factory for download tests."""
    from remote.remote_runner import RemoteRunConfig

    class FakeRunner:
        def __init__(self, config: RemoteRunConfig, on_log=None):
            self.config = config
            self.on_log = on_log or (lambda _line: None)
            self.remote_job_dir = ""
            self.remote_output_dir = ""
            self.attached = False
            self.downloaded_to = None
            self.download_count = 3

        def list_background_jobs(self):
            return []

        def attach_job(self, remote_job_dir, remote_output_dir=""):
            self.remote_job_dir = remote_job_dir
            self.remote_output_dir = remote_output_dir
            self.attached = True

        def count_download_files(self):
            return self.download_count

        def download_outputs(self, local_target_dir=None):
            self.downloaded_to = local_target_dir
            from pathlib import Path
            p = Path(local_target_dir)
            p.mkdir(parents=True, exist_ok=True)
            for i in range(self.download_count):
                self.on_log(f"Downloading file: /remote/file{i}.nii -> {p}/file{i}.nii")
                (p / f"file{i}.nii").write_text(f"data{i}")
            return p

    created_runners: list[FakeRunner] = []

    def factory(config: RemoteRunConfig):
        r = FakeRunner(config)
        created_runners.append(r)
        return r

    service = RemoteJobService(runner_factory=runner_factory or factory)
    return service, created_runners


def test_download_service_valid_payload(tmp_path) -> None:
    from app_backend.remote import RemoteJobService

    service, runners = _make_download_service()
    events = list(service.stream_download_outputs({
        "host": "server",
        "port": 22,
        "username": "tester",
        "password": "",
        "key_path": "",
        "workspace": "~/mri-remote-jobs",
        "remote_python": "python3",
        "remote_job_dir": "/workspace/job_abc",
        "local_target_dir": str(tmp_path / "outputs"),
        "job_id": "remote_job_abc",
    }))

    event_types = [(e["event"], e["data"].get("step"), e["data"].get("status")) for e in events]
    assert ("step", "connect", "running") in event_types
    assert ("step", "connect", "done") in event_types
    assert ("step", "count", "running") in event_types
    assert ("step", "count", "done") in event_types
    assert ("step", "copy", "running") in event_types
    assert ("step", "copy", "done") in event_types

    complete_events = [e for e in events if e["event"] == "complete"]
    assert len(complete_events) == 1
    assert complete_events[0]["data"]["ok"] is True
    local_path = complete_events[0]["data"]["local_path"]
    assert "remote_job_abc" in local_path

    download_runner = runners[1]
    assert download_runner.downloaded_to is not None
    assert "remote_job_abc" in str(download_runner.downloaded_to)


def test_download_service_missing_local_target(tmp_path) -> None:
    service, _ = _make_download_service()
    events = list(service.stream_download_outputs({
        "host": "server",
        "port": 22,
        "username": "tester",
        "remote_job_dir": "/workspace/job_1",
    }))
    complete_events = [e for e in events if e["event"] == "complete"]
    assert len(complete_events) == 1
    assert complete_events[0]["data"]["ok"] is False
    assert "local_target_dir" in str(complete_events[0]["data"].get("error", ""))


def test_download_service_missing_remote_job_dir(tmp_path) -> None:
    service, _ = _make_download_service()
    events = list(service.stream_download_outputs({
        "host": "server",
        "port": 22,
        "username": "tester",
        "local_target_dir": str(tmp_path / "outputs"),
    }))
    complete_events = [e for e in events if e["event"] == "complete"]
    assert len(complete_events) == 1
    assert complete_events[0]["data"]["ok"] is False
    assert "remote_job_dir" in str(complete_events[0]["data"].get("error", ""))


def test_download_service_uses_job_id_for_final_path(tmp_path) -> None:
    service, runners = _make_download_service()
    events = list(service.stream_download_outputs({
        "host": "server",
        "port": 22,
        "username": "tester",
        "password": "",
        "key_path": "",
        "workspace": "~/mri-remote-jobs",
        "remote_python": "python3",
        "remote_job_dir": "/workspace/job_xyz",
        "local_target_dir": str(tmp_path / "dest"),
        "job_id": "my_job_123",
    }))
    complete_events = [e for e in events if e["event"] == "complete"]
    assert complete_events[0]["data"]["ok"] is True
    local_path = str(complete_events[0]["data"]["local_path"])
    assert "my_job_123" in local_path

    download_runner = runners[1]
    assert "my_job_123" in str(download_runner.downloaded_to)


def test_download_service_falls_back_to_remote_dir_basename(tmp_path) -> None:
    service, runners = _make_download_service()
    events = list(service.stream_download_outputs({
        "host": "server",
        "port": 22,
        "username": "tester",
        "password": "",
        "key_path": "",
        "workspace": "~/mri-remote-jobs",
        "remote_python": "python3",
        "remote_job_dir": "/workspace/job_fallback_test",
        "local_target_dir": str(tmp_path / "dest"),
    }))
    complete_events = [e for e in events if e["event"] == "complete"]
    assert complete_events[0]["data"]["ok"] is True
    local_path = str(complete_events[0]["data"]["local_path"])
    assert "job_fallback_test" in local_path


def test_sidecar_neuroflow_validate_endpoint(tmp_path: Path) -> None:
    server, thread, base_url = _serve_in_thread(LocalJobService(jobs_root=tmp_path / "jobs"))
    try:
        preset_file = tmp_path / "preset.yaml"
        preset_file.write_text("pipeline_id: fs8_test\nstages:\n  - id: s1\n", encoding="utf-8")

        result = _post_json(f"{base_url}/config/neuroflow/validate", {
            "path": str(preset_file),
            "kind": "preset",
        })
        assert result["ok"] is True
        assert result["id"] == "fs8_test"

        bad_result = _post_json(f"{base_url}/config/neuroflow/validate", {
            "path": str(preset_file),
            "kind": "profile",
        })
        assert bad_result["ok"] is False
    finally:
        server.shutdown()
        thread.join(timeout=5)

