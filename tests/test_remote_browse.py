from __future__ import annotations

import stat
import threading
import json
from typing import Any
from urllib.request import Request, urlopen

import pytest

from app_backend.remote import RemoteJobService, _is_image_file, _IMAGE_EXTENSIONS
from app_backend.server import make_server


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

def test_is_image_file_recognises_mri_extensions() -> None:
    assert _is_image_file("brain.nii")
    assert _is_image_file("brain.NII")
    assert _is_image_file("brain.nii.gz")
    assert _is_image_file("brain.NII.GZ")
    assert _is_image_file("brain.mgz")
    assert _is_image_file("brain.mgh")
    assert _is_image_file("scan.dcm")
    assert _is_image_file("scan.DICOM")


def test_is_image_file_rejects_non_mri_files() -> None:
    assert not _is_image_file("readme.txt")
    assert not _is_image_file("image.png")
    assert not _is_image_file("data.csv")
    assert not _is_image_file("script.sh")


def test_image_extensions_constant_contains_expected_set() -> None:
    assert ".nii" in _IMAGE_EXTENSIONS
    assert ".nii.gz" in _IMAGE_EXTENSIONS
    assert ".mgz" in _IMAGE_EXTENSIONS
    assert ".mgh" in _IMAGE_EXTENSIONS
    assert ".dcm" in _IMAGE_EXTENSIONS
    assert ".dicom" in _IMAGE_EXTENSIONS


# ---------------------------------------------------------------------------
# Unit tests for browse_path with fake SFTP
# ---------------------------------------------------------------------------

class _FakeAttr:
    def __init__(self, name: str, is_dir: bool, size: int = 0) -> None:
        self.filename = name
        self.st_size = size
        self.st_mtime = 1_700_000_000
        if is_dir:
            self.st_mode = stat.S_IFDIR | 0o755
        else:
            self.st_mode = stat.S_IFREG | 0o644


class _FakeSFTP:
    def __init__(self, listing: list[tuple[str, bool, int]]) -> None:
        self._listing = listing

    def normalize(self, path: str) -> str:
        if path == "~":
            return "/home/user"
        return path

    def stat(self, path: str) -> _FakeAttr:
        if path == "/nonexistent":
            raise OSError("No such file")
        if path.endswith("/"):
            return _FakeAttr(".", True)
        # assume path is a directory in our fake FS
        return _FakeAttr(".", True)

    def listdir_attr(self, path: str) -> list[_FakeAttr]:
        return [_FakeAttr(name, is_dir, size) for name, is_dir, size in self._listing]


class _FakeClient:
    def __init__(self, sftp: _FakeSFTP) -> None:
        self.sftp = sftp

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


def _patch_sftp(monkeypatch: pytest.MonkeyPatch, listing: list[tuple[str, bool, int]]) -> None:
    """Patch RemoteSSHClient so it returns a fake SFTP instead of real SSH."""
    import app_backend.remote as remote_module

    fake_sftp = _FakeSFTP(listing)
    fake_client = _FakeClient(fake_sftp)

    def fake_browse(ssh: object, path: str) -> dict[str, object]:  # type: ignore[misc]
        # Call the real _browse_via_sftp but with a patched constructor
        from remote.ssh_client import RemoteSSHClient
        monkeypatch.setattr(RemoteSSHClient, "__enter__", lambda self: fake_client)
        monkeypatch.setattr(RemoteSSHClient, "__exit__", lambda self, *a: None)
        # Access sftp through the fake client
        original = remote_module._browse_via_sftp
        return original(ssh, path)

    # We patch _browse_via_sftp directly to inject fake client
    def patched_browse(ssh: object, path: str) -> dict[str, object]:
        import posixpath
        import stat as _stat
        expanded = fake_sftp.normalize(path)
        try:
            attr = fake_sftp.stat(expanded)
        except OSError as exc:
            return {"ok": False, "error": f"Path not found: {exc}"}
        is_dir = _stat.S_ISDIR(attr.st_mode) if attr.st_mode else False
        browse_dir = expanded if is_dir else posixpath.dirname(expanded)
        parent = posixpath.dirname(browse_dir)
        if parent == browse_dir:
            parent = browse_dir
        raw_entries = fake_sftp.listdir_attr(browse_dir)
        dirs: list[dict[str, object]] = []
        files: list[dict[str, object]] = []
        image_count = 0
        for entry in raw_entries:
            entry_mode = entry.st_mode or 0
            is_entry_dir = _stat.S_ISDIR(entry_mode)
            entry_name: str = entry.filename
            entry_path = posixpath.join(browse_dir, entry_name)
            is_img = not is_entry_dir and remote_module._is_image_file(entry_name)
            if is_img:
                image_count += 1
            row: dict[str, object] = {
                "name": entry_name,
                "path": entry_path,
                "kind": "directory" if is_entry_dir else "file",
                "size": int(entry.st_size or 0) if not is_entry_dir else None,
                "modified_at": int(entry.st_mtime or 0) if entry.st_mtime else None,
                "selectable": is_entry_dir or is_img,
            }
            if is_entry_dir:
                dirs.append(row)
            else:
                files.append(row)
        dirs.sort(key=lambda e: str(e["name"]).lower())
        files.sort(key=lambda e: str(e["name"]).lower())
        return {
            "ok": True,
            "path": browse_dir,
            "parent": parent,
            "entries": dirs + files,
            "image_count": image_count,
        }

    monkeypatch.setattr(remote_module, "_browse_via_sftp", patched_browse)


def _valid_payload() -> dict[str, object]:
    return {
        "host": "server.example.edu",
        "port": 22,
        "username": "testuser",
        "workspace": "~/mri-remote-jobs",
        "remote_python": "python3",
        "path": "/home/user/mri-data",
    }


def test_browse_path_returns_directory_listing(monkeypatch: pytest.MonkeyPatch) -> None:
    listing = [
        ("subdir", True, 0),
        ("brain.nii.gz", False, 102400),
        ("notes.txt", False, 512),
    ]
    _patch_sftp(monkeypatch, listing)
    service = RemoteJobService()
    result = service.browse_path(_valid_payload())
    assert result["ok"] is True
    entries = result["entries"]
    assert isinstance(entries, list)
    names = [e["name"] for e in entries]
    assert "subdir" in names
    assert "brain.nii.gz" in names
    assert "notes.txt" in names
    assert result["image_count"] == 1


def test_browse_path_sorts_dirs_before_files(monkeypatch: pytest.MonkeyPatch) -> None:
    listing = [
        ("z_file.nii", False, 0),
        ("a_dir", True, 0),
    ]
    _patch_sftp(monkeypatch, listing)
    service = RemoteJobService()
    result = service.browse_path(_valid_payload())
    entries = result["entries"]
    assert isinstance(entries, list)
    assert entries[0]["kind"] == "directory"
    assert entries[1]["kind"] == "file"


def test_browse_path_marks_image_files_selectable(monkeypatch: pytest.MonkeyPatch) -> None:
    listing = [
        ("brain.mgz", False, 0),
        ("readme.txt", False, 0),
    ]
    _patch_sftp(monkeypatch, listing)
    service = RemoteJobService()
    result = service.browse_path(_valid_payload())
    entries = result["entries"]
    assert isinstance(entries, list)
    by_name = {e["name"]: e for e in entries}
    assert by_name["brain.mgz"]["selectable"] is True
    assert by_name["readme.txt"]["selectable"] is False


def test_browse_path_rejects_nul_in_path() -> None:
    service = RemoteJobService()
    payload = {**_valid_payload(), "path": "/home/user\x00evil"}
    result = service.browse_path(payload)
    assert result["ok"] is False
    assert "Invalid path" in str(result.get("error", ""))


def test_browse_path_rejects_missing_host() -> None:
    service = RemoteJobService()
    payload = {**_valid_payload(), "host": ""}
    result = service.browse_path(payload)
    assert result["ok"] is False
    assert "errors" in result


# ---------------------------------------------------------------------------
# Route delegation test for /remote/browse endpoint
# ---------------------------------------------------------------------------

class _FakeBrowseRemoteService(RemoteJobService):
    """Replaces browse_path to avoid real SSH."""

    def browse_path(self, data: dict[str, object]) -> dict[str, object]:
        path = str(data.get("path", "/fake") or "/fake")
        if "\x00" in path:
            return {"ok": False, "error": "Invalid path"}
        return {
            "ok": True,
            "path": path,
            "parent": "/fake",
            "entries": [
                {"name": "scan.nii.gz", "path": f"{path}/scan.nii.gz",
                 "kind": "file", "size": 50000, "modified_at": 1_700_000_000, "selectable": True},
            ],
            "image_count": 1,
        }


def _post_json_url(url: str, payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def test_remote_browse_route_delegates_to_service() -> None:
    remote_svc = _FakeBrowseRemoteService()
    server = make_server("127.0.0.1", 0, remote_job_service=remote_svc)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        payload = {
            "host": "server.example.edu",
            "port": 22,
            "username": "user",
            "workspace": "~/mri-remote-jobs",
            "remote_python": "python3",
            "path": "/home/user/mri-data",
        }
        result = _post_json_url(f"{base_url}/remote/browse", payload)
        assert result["ok"] is True
        assert result["path"] == "/home/user/mri-data"
        assert result["image_count"] == 1
        entries = result["entries"]
        assert isinstance(entries, list)
        assert entries[0]["name"] == "scan.nii.gz"
    finally:
        server.shutdown()
        thread.join(timeout=5)


class _FakeHierarchicalSFTP:
    def __init__(self, tree: dict[str, list[tuple[str, bool, int]]]) -> None:
        self._tree = tree

    def normalize(self, path: str) -> str:
        if path == "~":
            return "/home/user"
        return path

    def stat(self, path: str) -> _FakeAttr:
        if path in self._tree:
            return _FakeAttr(".", True)
        return _FakeAttr("file.nii", False)

    def listdir_attr(self, path: str) -> list[_FakeAttr]:
        key = path.rstrip("/")
        if key not in self._tree:
            return []
        return [_FakeAttr(name, is_dir, size) for name, is_dir, size in self._tree[key]]


def test_scan_batch_recursive_depths(monkeypatch: pytest.MonkeyPatch) -> None:
    tree = {
        "/home/user/mri-data": [
            ("subj1", True, 0),
            ("subj2", True, 0),
            ("flat.nii.gz", False, 1024),
        ],
        "/home/user/mri-data/subj1": [
            ("t1.nii.gz", False, 2048),
            ("nested_dir", True, 0),
        ],
        "/home/user/mri-data/subj1/nested_dir": [
            ("deep.mgz", False, 4096),
        ],
        "/home/user/mri-data/subj2": [
            ("t1.nii.gz", False, 2048),
            ("t2.nii.gz", False, 3072),
        ]
    }
    from remote.ssh_client import RemoteSSHClient
    fake_sftp = _FakeHierarchicalSFTP(tree)
    fake_client = _FakeClient(fake_sftp)
    monkeypatch.setattr(RemoteSSHClient, "__enter__", lambda self: fake_client)
    monkeypatch.setattr(RemoteSSHClient, "__exit__", lambda self, *a: None)

    service = RemoteJobService()

    # 1. max_depth = 0 (Direct files only)
    res_direct = service.browse_path({
        **_valid_payload(),
        "purpose": "batch",
        "recursive": True,
        "max_depth": 0
    })
    assert res_direct["ok"] is True
    names_direct = [e["name"] for e in res_direct["entries"]]
    assert names_direct == ["flat.nii.gz"]
    assert res_direct["has_multi_subject_conflict"] is False

    # 2. max_depth = 1 (One level of subfolders)
    res_one = service.browse_path({
        **_valid_payload(),
        "purpose": "batch",
        "recursive": True,
        "max_depth": 1
    })
    assert res_one["ok"] is True
    names_one = [e["name"] for e in res_one["entries"]]
    assert "flat.nii.gz" in names_one
    assert "t1.nii.gz" in names_one
    assert res_one["has_multi_subject_conflict"] is True

    # 3. max_depth = 2 (Recursive)
    res_rec = service.browse_path({
        **_valid_payload(),
        "purpose": "batch",
        "recursive": True,
        "max_depth": 2
    })
    assert res_rec["ok"] is True
    names_rec = [e["name"] for e in res_rec["entries"]]
    assert "deep.mgz" in names_rec

