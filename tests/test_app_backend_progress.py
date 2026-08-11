from __future__ import annotations

import json
from pathlib import Path

from app_backend.progress import LocalJobProgressService
from pipeline.jobs import write_json


def _job(tmp_path: Path) -> tuple[LocalJobProgressService, Path, str]:
    jobs_root = tmp_path / "jobs"
    job_dir = jobs_root / "job_1"
    job_dir.mkdir(parents=True)
    write_json(
        jobs_root / "job_registry.json",
        {
            "version": 1,
            "jobs": [
                {
                    "job_id": "job_1",
                    "target": "Local",
                    "state": "running",
                    "job_dir": str(job_dir),
                    "updated_at": 1.0,
                }
            ],
        },
    )
    return LocalJobProgressService(jobs_root), job_dir, "job_1"


def test_read_events_returns_events_and_next_offset(tmp_path: Path) -> None:
    service, job_dir, job_id = _job(tmp_path)
    lines = [
        json.dumps({"kind": "progress", "stage": "segmentation"}),
        "not json",
        json.dumps({"kind": "metrics", "cpu_pct": 12.5}),
    ]
    (job_dir / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    event_text = "\n".join(lines) + "\n"
    result = service.read_events(job_id, offset=0, limit=10)

    assert result["ok"] is True
    assert result["next_offset"] == len(event_text.encode("utf-8"))
    assert result["events"] == [
        {"kind": "progress", "stage": "segmentation"},
        {"kind": "metrics", "cpu_pct": 12.5},
    ]
    assert result["warnings"] == ["Skipped malformed event line"]


def test_read_events_respects_offset_and_limit(tmp_path: Path) -> None:
    service, job_dir, job_id = _job(tmp_path)
    first_line = json.dumps({"idx": 0}) + "\n"
    lines = [first_line, *(json.dumps({"idx": idx}) + "\n" for idx in range(1, 5))]
    (job_dir / "events.jsonl").write_text("".join(lines), encoding="utf-8")

    result = service.read_events(job_id, offset=len(first_line.encode("utf-8")), limit=2)

    assert result["ok"] is True
    assert result["next_offset"] == len("".join(lines[:3]).encode("utf-8"))
    assert result["events"] == [{"idx": 1}, {"idx": 2}]


def test_read_events_is_bounded_by_bytes_and_rejects_large_line(tmp_path: Path) -> None:
    service, job_dir, job_id = _job(tmp_path)
    (job_dir / "events.jsonl").write_text("{" + "x" * 1_100_000, encoding="utf-8")

    result = service.read_events(job_id, offset=0, limit=10)

    assert result["ok"] is True
    assert result["events"] == []
    assert result["warnings"] == ["Stopped at oversized event line"]


def test_read_events_rejects_symlinked_event_file(tmp_path: Path) -> None:
    service, job_dir, job_id = _job(tmp_path)
    outside = tmp_path / "outside.jsonl"
    outside.write_text(json.dumps({"kind": "progress"}) + "\n", encoding="utf-8")
    (job_dir / "events.jsonl").symlink_to(outside)

    result = service.read_events(job_id)

    assert result == {"ok": False, "error": "Progress file is not safe"}


def test_read_log_is_bounded_by_offset_and_max_bytes(tmp_path: Path) -> None:
    service, job_dir, job_id = _job(tmp_path)
    (job_dir / "run.log").write_text("abcdef", encoding="utf-8")

    result = service.read_log(job_id, offset=2, max_bytes=3)

    assert result == {"ok": True, "text": "cde", "next_offset": 5, "truncated": True}


def test_read_log_rejects_symlinked_log_file(tmp_path: Path) -> None:
    service, job_dir, job_id = _job(tmp_path)
    outside = tmp_path / "outside.log"
    outside.write_text("do not read", encoding="utf-8")
    (job_dir / "run.log").symlink_to(outside)

    result = service.read_log(job_id)

    assert result == {"ok": False, "error": "Progress file is not safe"}


def test_progress_service_rejects_unknown_or_unsafe_job(tmp_path: Path) -> None:
    service = LocalJobProgressService(tmp_path / "jobs")

    assert service.read_events("missing") == {"ok": False, "error": "Local job not found"}
