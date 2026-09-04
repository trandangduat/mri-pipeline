from __future__ import annotations

import argparse
import os
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TypeAlias
from urllib.parse import parse_qs, urlparse

from app_backend.config_store import ConfigStore
from app_backend.environment import LocalEnvironmentService
from app_backend.jobs import LocalJobService
from app_backend.licenses import LicenseStore
from app_backend.local_browse import browse_local_path
from app_backend.metadata import get_app_metadata
from app_backend.neuroflow_config_validator import validate_neuroflow_config
from app_backend.progress import LocalJobProgressService
from app_backend.remote import RemoteJobService
from app_backend.run_request import prepare_run_request
from app_backend.tools import LocalToolService

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

MAX_REQUEST_BYTES = 1_000_000


class AppBackendHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        local_job_service: LocalJobService | None = None,
        local_progress_service: LocalJobProgressService | None = None,
        config_store: ConfigStore | None = None,
        remote_job_service: RemoteJobService | None = None,
        local_tool_service: LocalToolService | None = None,
        local_environment_service: LocalEnvironmentService | None = None,
        license_store: LicenseStore | None = None,
    ) -> None:
        super().__init__(server_address, AppBackendRequestHandler)
        self.local_job_service = local_job_service or LocalJobService()
        self.local_progress_service = local_progress_service or LocalJobProgressService(self.local_job_service.jobs_root)
        self.config_store = config_store or ConfigStore()
        self.remote_job_service = remote_job_service or RemoteJobService(
            register_remote_job=self.local_job_service.upsert_remote_job,
        )
        self.local_tool_service = local_tool_service or LocalToolService()
        self.local_environment_service = local_environment_service or LocalEnvironmentService()
        self.license_store = license_store or LicenseStore()


class AppBackendRequestHandler(BaseHTTPRequestHandler):
    server_version = "MRIPipelineBackend/0.1"

    def do_GET(self) -> None:
        try:
            self._handle_get()
        except Exception as exc:
            self._write_exception(exc)

    def do_POST(self) -> None:
        try:
            self._handle_post()
        except Exception as exc:
            self._write_exception(exc)

    def _handle_get(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/health":
            self._write_json(HTTPStatus.OK, {"ok": True, "service": "mri-pipeline-backend", "pid": os.getpid()})
            return
        if path == "/metadata":
            self._write_json(HTTPStatus.OK, get_app_metadata())
            return
        if path == "/environment/local":
            self._write_json(HTTPStatus.OK, self._local_environment().status())
            return
        if path == "/jobs/local":
            self._write_json(HTTPStatus.OK, self._local_jobs().list_local_jobs())
            return
        if path == "/jobs/local/events":
            self._write_json(
                HTTPStatus.OK,
                self._local_progress().read_events(
                    _query_string(query, "job_id"),
                    offset=_query_int(query, "offset", 0),
                    limit=_query_int(query, "limit", 500),
                ),
            )
            return
        if path == "/jobs/local/log":
            self._write_json(
                HTTPStatus.OK,
                self._local_progress().read_log(
                    _query_string(query, "job_id"),
                    offset=_query_int(query, "offset", 0),
                    max_bytes=_query_int(query, "max_bytes", 65536),
                ),
            )
            return
        if path == "/jobs/local/metrics":
            self._write_json(
                HTTPStatus.OK,
                self._local_progress().read_metrics(
                    _query_string(query, "job_id"),
                    offset=_query_int(query, "offset", 0),
                    limit=_query_int(query, "limit", 500),
                    subject_id=_query_string(query, "subject_id"),
                    input_file=_query_string(query, "input_file"),
                ),
            )
            return
        if path == "/jobs/stream":
            self._handle_jobs_stream(query)
            return
        if path == "/config/workspaces":
            self._write_json(HTTPStatus.OK, self._configs().list_workspaces())
            return
        if path == "/config/workspaces/load":
            self._write_json(HTTPStatus.OK, self._configs().load_workspace(_query_string(query, "name")))
            return
        if path == "/config/presets":
            self._write_json(HTTPStatus.OK, self._configs().list_presets())
            return
        if path == "/config/presets/load":
            self._write_json(HTTPStatus.OK, self._configs().load_preset(_query_string(query, "name")))
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})

    def _handle_post(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            return
        if self.path == "/run-request/prepare":
            self._write_json(HTTPStatus.OK, prepare_run_request(payload))
            return
        if self.path == "/licenses/upload":
            self._write_json(HTTPStatus.OK, self._licenses().save_upload(payload))
            return
        if self.path == "/jobs/local/start":
            request = payload.get("run_request")
            if not isinstance(request, dict):
                self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "run_request must be an object"})
                return
            self._write_json(HTTPStatus.OK, self._local_jobs().start_local_job(request))
            return
        if self.path == "/jobs/local/stop":
            job_id = str(payload.get("job_id", "") or "")
            if not job_id:
                self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "job_id is required"})
                return
            result = self._local_jobs().stop_local_job(job_id)
            status = HTTPStatus.OK if result.get("ok") else HTTPStatus.NOT_FOUND
            self._write_json(status, result)
            return
        if self.path == "/jobs/local/delete":
            job_id = str(payload.get("job_id", "") or "")
            if not job_id:
                self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "job_id is required"})
                return
            result = self._local_jobs().delete_local_job(job_id)
            status = HTTPStatus.OK if result.get("ok") else HTTPStatus.NOT_FOUND
            self._write_json(status, result)
            return
        if self.path == "/config/workspaces/save":
            name = str(payload.get("name", "") or "")
            data = payload.get("data")
            if not isinstance(data, dict):
                self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "data must be an object"})
                return
            self._write_json(HTTPStatus.OK, self._configs().save_workspace(name, data))
            return
        if self.path == "/config/presets/save":
            name = str(payload.get("name", "") or "")
            data = payload.get("data")
            if not isinstance(data, dict):
                self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "data must be an object"})
                return
            self._write_json(HTTPStatus.OK, self._configs().save_preset(name, data))
            return
        if self.path == "/config/export":
            export_path = str(payload.get("path", "") or "")
            data = payload.get("data")
            if not isinstance(data, dict):
                self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "data must be an object"})
                return
            self._write_json(HTTPStatus.OK, self._configs().export_json(export_path, data))
            return
        if self.path == "/config/neuroflow/validate":
            path = payload.get("path")
            content = payload.get("content")
            kind = str(payload.get("kind", "") or "")
            result = validate_neuroflow_config(
                path=str(path) if path else None,
                content=str(content) if content is not None else None,
                kind=kind,
            )
            self._write_json(HTTPStatus.OK, result)
            return
        if self.path == "/remote/browse":
            self._write_json(HTTPStatus.OK, self._remote_jobs().browse_path(payload))
            return
        if self.path == "/remote/mkdir":
            self._write_json(HTTPStatus.OK, self._remote_jobs().remote_mkdir(payload))
            return
        if self.path == "/local/browse":
            self._write_json(HTTPStatus.OK, browse_local_path(payload))
            return
        if self.path == "/remote/validate":
            self._write_json(HTTPStatus.OK, self._remote_jobs().validate_config(payload))
            return
        if self.path == "/remote/jobs":
            self._write_json(HTTPStatus.OK, self._remote_jobs().list_jobs(payload))
            return
        if self.path == "/remote/jobs/delete":
            self._write_json(HTTPStatus.OK, self._remote_jobs().delete_job(payload))
            return
        if self.path == "/remote/jobs/stop":
            self._write_json(HTTPStatus.OK, self._remote_jobs().stop_job(payload))
            return
        if self.path == "/remote/jobs/events":
            self._write_json(HTTPStatus.OK, self._remote_jobs().read_job_events(payload))
            return
        if self.path == "/remote/jobs/log":
            self._write_json(HTTPStatus.OK, self._remote_jobs().read_job_log(payload))
            return
        if self.path == "/remote/jobs/metrics":
            self._write_json(HTTPStatus.OK, self._remote_jobs().read_job_metrics(payload))
            return
        if self.path == "/remote/jobs/upload/state":
            self._write_json(HTTPStatus.OK, self._remote_jobs().upload_state(payload))
            return
        if self.path == "/remote/jobs/upload/cancel":
            self._write_json(HTTPStatus.OK, self._remote_jobs().upload_cancel(payload))
            return
        if self.path == "/remote/jobs/upload/stage":
            self._write_json(HTTPStatus.OK, self._remote_jobs().upload_stage(payload))
            return
        if self.path == "/remote/jobs/start/stream":
            self._handle_remote_start_stream(payload)
            return
        if self.path == "/remote/jobs/download/stream":
            self._handle_remote_download_stream(payload)
            return
        if self.path == "/jobs/local/start/stream":
            self._handle_local_start_stream(payload)
            return
        if self.path == "/tools/local/images":
            selected_tools = payload.get("selected_tools")
            target = str(payload.get("target", "Local") or "Local")
            remote = payload.get("remote")

            if selected_tools is not None and not isinstance(selected_tools, dict):
                self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "selected_tools must be an object"})
                return
            if remote is not None and not isinstance(remote, dict):
                self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "remote must be an object"})
                return

            result = self._local_tools().image_status(selected_tools, target=target, remote=remote)
            self._write_json(HTTPStatus.OK, result)
            return
        if self.path == "/tools/local/pull":
            image = str(payload.get("image", "") or "")
            if not image:
                self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "image is required"})
                return
            target = str(payload.get("target", "Local") or "Local")
            remote = payload.get("remote")
            if target == "Server":
                self._write_sse_headers()
                try:
                    self._send_sse_event("step", {"step": "pull", "status": "running", "detail": f"Server pull status for {image}"})
                    result = self._local_tools().pull_image(image, target=target, remote=remote if isinstance(remote, dict) else None)
                    self._send_sse_event("complete", result)
                except Exception as exc:
                    self._send_sse_event("complete", {"ok": False, "error": str(exc)})
            else:
                self._handle_tools_pull_stream(image)
            return
        if self.path == "/tools/server/pull/status":
            image = str(payload.get("image", "") or "")
            if not image:
                self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "image is required"})
                return
            remote = payload.get("remote") if isinstance(payload.get("remote"), dict) else None
            try:
                log_offset = int(payload.get("log_offset", 0) or 0)
            except (TypeError, ValueError):
                log_offset = 0
            result = self._local_tools().server_pull_status(image, remote, log_offset=log_offset)
            self._write_json(HTTPStatus.OK, result)
            return
        if self.path == "/tools/local/remove":
            image = str(payload.get("image", "") or "")
            if not image:
                self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "image is required"})
                return
            target = str(payload.get("target", "Local") or "Local")
            remote = payload.get("remote")
            result = self._local_tools().remove_image(image, target=target, remote=remote if isinstance(remote, dict) else None)
            self._write_json(HTTPStatus.OK, result)
            return
        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def do_OPTIONS(self) -> None:
        self.send_response(int(HTTPStatus.NO_CONTENT))
        self._write_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        try:
            status = HTTPStatus(code)
        except ValueError:
            status = HTTPStatus.INTERNAL_SERVER_ERROR
        self._write_json(status, {"ok": False, "error": message or status.phrase})

    def _method_not_allowed(self) -> None:
        self._write_json(HTTPStatus.METHOD_NOT_ALLOWED, {"ok": False, "error": "Method not allowed"})

    def _write_exception(self, exc: Exception) -> None:
        try:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "Internal server error"})
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _local_jobs(self) -> LocalJobService:
        server = self.server
        if not isinstance(server, AppBackendHTTPServer):
            raise RuntimeError("Unexpected server type")
        return server.local_job_service

    def _local_progress(self) -> LocalJobProgressService:
        server = self.server
        if not isinstance(server, AppBackendHTTPServer):
            raise RuntimeError("Unexpected server type")
        return server.local_progress_service

    def _configs(self) -> ConfigStore:
        server = self.server
        if not isinstance(server, AppBackendHTTPServer):
            raise RuntimeError("Unexpected server type")
        return server.config_store

    def _remote_jobs(self) -> RemoteJobService:
        server = self.server
        if not isinstance(server, AppBackendHTTPServer):
            raise RuntimeError("Unexpected server type")
        return server.remote_job_service

    def _local_tools(self) -> LocalToolService:
        server = self.server
        if not isinstance(server, AppBackendHTTPServer):
            raise RuntimeError("Unexpected server type")
        return server.local_tool_service

    def _local_environment(self) -> LocalEnvironmentService:
        server = self.server
        if not isinstance(server, AppBackendHTTPServer):
            raise RuntimeError("Unexpected server type")
        return server.local_environment_service

    def _licenses(self) -> LicenseStore:
        server = self.server
        if not isinstance(server, AppBackendHTTPServer):
            raise RuntimeError("Unexpected server type")
        return server.license_store

    def _read_json_body(self) -> dict[str, object] | None:
        content_type = self.headers.get("Content-Type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            self._write_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"ok": False, "error": "Content-Type must be application/json"})
            return None

        try:
            content_length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Invalid Content-Length"})
            return None
        if content_length < 0 or content_length > MAX_REQUEST_BYTES:
            self._write_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"ok": False, "error": "Request body too large"})
            return None

        raw = self.rfile.read(content_length)
        if not raw:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Invalid JSON body"})
            return None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Invalid JSON body"})
            return None
        if not isinstance(payload, dict):
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "JSON body must be an object"})
            return None
        return payload

    def _write_json(self, status: HTTPStatus, payload: dict[str, JsonValue]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        accept_encoding = getattr(self, "headers", {}).get("Accept-Encoding", "") if hasattr(self, "headers") and self.headers else ""
        use_gzip = "gzip" in accept_encoding.lower() and len(body) > 1024
        if use_gzip:
            import gzip
            body = gzip.compress(body, compresslevel=6)
        self.send_response(int(status))
        self._write_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if use_gzip:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _write_sse_headers(self) -> None:
        self.send_response(200)
        self._write_cors_headers()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

    def _send_sse_event(self, event: str, data: dict[str, JsonValue]) -> None:
        payload = json.dumps(data, ensure_ascii=False)
        frame = f"event: {event}\ndata: {payload}\n\n"
        self.wfile.write(frame.encode("utf-8"))
        self.wfile.flush()

    def _handle_remote_start_stream(self, payload: dict[str, JsonValue]) -> None:
        self._write_sse_headers()
        try:
            for sse_event in self._remote_jobs().stream_start_job(payload):
                self._send_sse_event(str(sse_event["event"]), sse_event["data"])  # type: ignore[arg-type]
        except Exception as exc:
            self._send_sse_event("step", {"step": "error", "status": "failed", "detail": str(exc)})
            self._send_sse_event("complete", {"ok": False, "error": str(exc)})
        finally:
            self.close_connection = True

    def _handle_remote_download_stream(self, payload: dict[str, JsonValue]) -> None:
        self._write_sse_headers()
        try:
            for sse_event in self._remote_jobs().stream_download_outputs(payload):  # type: ignore[arg-type]
                self._send_sse_event(str(sse_event["event"]), sse_event["data"])  # type: ignore[arg-type]
        except Exception as exc:
            self._send_sse_event("step", {"step": "error", "status": "failed", "detail": str(exc)})
            self._send_sse_event("complete", {"ok": False, "error": str(exc)})
        finally:
            self.close_connection = True

    def _handle_local_start_stream(self, payload: dict[str, JsonValue]) -> None:
        self._write_sse_headers()
        try:
            for sse_event in self._local_jobs().stream_start_job(payload):
                self._send_sse_event(str(sse_event["event"]), sse_event["data"])  # type: ignore[arg-type]
        except Exception as exc:
            self._send_sse_event("step", {"step": "error", "status": "failed", "detail": str(exc)})
            self._send_sse_event("complete", {"ok": False, "error": str(exc)})
        finally:
            self.close_connection = True

    def _handle_jobs_stream(self, query: dict[str, list[str]]) -> None:
        job_id = _query_string(query, "job_id")
        if not job_id:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "job_id is required"})
            return
        event_offset = _query_int(query, "event_offset", 0)
        log_offset = _query_int(query, "log_offset", 0)
        self._write_sse_headers()
        try:
            import time
            last_ping = time.time()
            while True:
                now = time.time()
                ev_res = self._local_progress().read_events(job_id, offset=event_offset, limit=500)
                new_events = ev_res.get("events", []) if isinstance(ev_res, dict) else []
                new_ev_offset = int(ev_res.get("next_offset", event_offset)) if isinstance(ev_res, dict) else event_offset

                log_res = self._local_progress().read_log(job_id, offset=log_offset, max_bytes=65536)
                new_log_text = str(log_res.get("text", "") or "") if isinstance(log_res, dict) else ""
                new_log_offset = int(log_res.get("next_offset", log_offset)) if isinstance(log_res, dict) else log_offset

                has_update = bool(new_events) or bool(new_log_text)
                if has_update:
                    event_offset = new_ev_offset
                    log_offset = new_log_offset
                    self._send_sse_event("update", {
                        "job_id": job_id,
                        "events": new_events,
                        "event_offset": event_offset,
                        "log_text": new_log_text,
                        "log_offset": log_offset,
                    })

                if now - last_ping >= 15.0:
                    self._send_sse_event("ping", {"time": now})
                    last_ping = now

                time.sleep(1.0)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            try:
                self._send_sse_event("error", {"error": str(exc)})
            except Exception:
                pass
        finally:
            self.close_connection = True

    def _handle_tools_pull_stream(self, image: str) -> None:
        self._write_sse_headers()
        try:
            from app_backend.pull_stream import pull_image_events

            for event in pull_image_events(image):
                self._send_sse_event(event["event"], event["data"])
        except Exception as exc:
            self._send_sse_event("step", {"step": "pull", "status": "failed", "detail": str(exc)})
            self._send_sse_event("complete", {"ok": False, "error": str(exc)})
        finally:
            self.close_connection = True

    def _write_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def make_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    local_job_service: LocalJobService | None = None,
    local_progress_service: LocalJobProgressService | None = None,
    config_store: ConfigStore | None = None,
    remote_job_service: RemoteJobService | None = None,
    local_tool_service: LocalToolService | None = None,
    local_environment_service: LocalEnvironmentService | None = None,
    license_store: LicenseStore | None = None,
) -> AppBackendHTTPServer:
    return AppBackendHTTPServer(
        (host, port),
        local_job_service,
        local_progress_service,
        config_store,
        remote_job_service,
        local_tool_service,
        local_environment_service,
        license_store,
    )


def _query_string(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key, [])
    return values[0] if values else ""


def _query_int(query: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(_query_string(query, key) or default)
    except ValueError:
        return default


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MRI Pipeline backend sidecar.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    server = make_server(args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
