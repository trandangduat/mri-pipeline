from __future__ import annotations

from pathlib import Path
import pytest

from app_backend.dev_cleanup import _is_own_backend_process, cleanup_stale_backend


def test_is_own_backend_process_matches_module_args(tmp_path: Path) -> None:
    cmdline = ["python3", "-m", "app_backend.server", "--host", "127.0.0.1"]
    assert _is_own_backend_process(cmdline, str(tmp_path), tmp_path) is True


def test_is_own_backend_process_matches_script_args(tmp_path: Path) -> None:
    script_path = str(tmp_path / "app_backend" / "server.py")
    cmdline = ["python3", script_path, "--port", "8765"]
    assert _is_own_backend_process(cmdline, str(tmp_path), tmp_path) is True


def test_is_own_backend_process_rejects_unrelated_process(tmp_path: Path) -> None:
    cmdline = ["node", "server.js"]
    assert _is_own_backend_process(cmdline, str(tmp_path), tmp_path) is False


def test_is_own_backend_process_rejects_different_cwd(tmp_path: Path) -> None:
    other_dir = tmp_path.parent / "other_project"
    cmdline = ["python3", "-m", "app_backend.server"]
    assert _is_own_backend_process(cmdline, str(other_dir), tmp_path) is False


def test_cleanup_stale_backend_skips_unrelated_listener(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeConn:
        laddr = type("Addr", (), {"ip": "127.0.0.1", "port": 8765})()

    class FakeProc:
        pid = 99999

        def info(self) -> dict[str, object]:
            return {
                "pid": self.pid,
                "name": "node",
                "cmdline": ["node", "express.js"],
                "cwd": str(tmp_path),
            }

        def net_connections(self, kind: str = "inet") -> list[FakeConn]:
            return [FakeConn()]

    monkeypatch.setattr("psutil.process_iter", lambda _attrs: [FakeProc()])

    res = cleanup_stale_backend("127.0.0.1", 8765, tmp_path)
    assert res["killed"] == []
    assert len(res["errors"]) == 1
    assert "occupied by non-NeuroFlow process" in str(res["errors"][0])
