from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from app_backend.jobs import BatchSummaryCache
from pipeline.job_worker import _save_job_summary
from remote.ssh_client import SSHConfig, SSHConnectionPool


def test_batch_summary_cache_incremental(tmp_path: Path) -> None:
    cache = BatchSummaryCache()
    job_dir = tmp_path / "job_01"
    job_dir.mkdir()
    events_file = job_dir / "events.jsonl"

    summary1 = cache.get_or_update(job_dir, ["/data/sub1.nii.gz", "/data/sub2.nii.gz"])
    assert summary1["total"] == 2
    assert summary1["pending"] == 2
    assert summary1["running"] == 0

    with open(events_file, "a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "image_start", "input_file": "/data/sub1.nii.gz", "idx": 1, "total": 2}) + "\n")

    summary2 = cache.get_or_update(job_dir, ["/data/sub1.nii.gz", "/data/sub2.nii.gz"])
    assert summary2["running"] == 1
    assert summary2["pending"] == 1

    summary3 = cache.get_or_update(job_dir, ["/data/sub1.nii.gz", "/data/sub2.nii.gz"])
    assert summary3 is summary2

    with open(events_file, "a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "image_done", "input_file": "/data/sub1.nii.gz", "success": True, "idx": 1, "total": 2}) + "\n")

    summary4 = cache.get_or_update(job_dir, ["/data/sub1.nii.gz", "/data/sub2.nii.gz"])
    assert summary4["success"] == 1
    assert summary4["running"] == 0
    assert summary4["pending"] == 1


def test_batch_summary_cache_reads_job_summary_json(tmp_path: Path) -> None:
    cache = BatchSummaryCache()
    job_dir = tmp_path / "job_02"
    job_dir.mkdir()
    sum_file = job_dir / "job_summary.json"
    sum_file.write_text(
        json.dumps({
            "total": 5,
            "success": 3,
            "failed": 1,
            "running": 1,
            "stopped": 0,
            "pending": 0,
        }),
        encoding="utf-8",
    )

    summary = cache.get_or_update(job_dir, [])
    assert summary["total"] == 5
    assert summary["success"] == 3
    assert summary["failed"] == 1
    assert summary["running"] == 1
    assert summary["pending"] == 0


def test_job_worker_save_job_summary(tmp_path: Path) -> None:
    job_dir = tmp_path / "job_worker_test"
    job_dir.mkdir()
    image_states = {
        "/path/a.nii.gz": "success",
        "/path/b.nii.gz": "running",
    }
    summary = _save_job_summary(job_dir, 4, image_states, "running")
    assert summary["total"] == 4
    assert summary["success"] == 1
    assert summary["running"] == 1
    assert summary["pending"] == 2

    sum_file = job_dir / "job_summary.json"
    assert sum_file.exists()
    loaded = json.loads(sum_file.read_text(encoding="utf-8"))
    assert loaded["total"] == 4
    assert loaded["success"] == 1
    assert loaded["running"] == 1


def test_ssh_connection_pool_lifecycle() -> None:
    pool = SSHConnectionPool()
    config = SSHConfig(host="10.0.0.1", port=22, username="user1")

    mock_client = MagicMock()
    mock_transport = MagicMock()
    mock_transport.is_active.return_value = True
    mock_client.get_transport.return_value = mock_transport
    mock_sftp = MagicMock()

    pool._create_connection = MagicMock(return_value=(mock_client, mock_sftp))

    c1, s1 = pool.acquire(config)
    assert c1 is mock_client
    assert s1 is mock_sftp
    assert pool._create_connection.call_count == 1

    c2, s2 = pool.acquire(config)
    assert c2 is mock_client
    assert s2 is mock_sftp
    assert pool._create_connection.call_count == 1

    pool.close_all()
    mock_client.close.assert_called_once()
    mock_sftp.close.assert_called_once()


def test_gzip_compression_header() -> None:
    from http import HTTPStatus
    from unittest.mock import MagicMock
    from app_backend.server import AppBackendRequestHandler

    handler = AppBackendRequestHandler.__new__(AppBackendRequestHandler)
    handler.headers = {"Accept-Encoding": "gzip, deflate"}
    handler.send_response = MagicMock()
    handler._write_cors_headers = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()
    handler.wfile = MagicMock()

    large_payload = {"data": "x" * 2000}
    handler._write_json(HTTPStatus.OK, large_payload)

    calls = handler.send_header.call_args_list
    assert any(c[0] == ("Content-Encoding", "gzip") for c in calls)
