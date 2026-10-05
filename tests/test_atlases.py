from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app_backend.atlases import (
    ATLAS_PACKS,
    AtlasService,
    candidate_surface_atlas_dirs,
    find_surface_atlas_file,
    surface_atlases_data_dir,
)
from pipeline.config import SCHAEFER2018_ATLAS_VARIANTS


def test_surface_atlases_data_dir_respects_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom_dir = tmp_path / "custom_atlases"
    monkeypatch.setenv("NEUROFLOW_SURFACE_ATLAS_DIR", str(custom_dir))
    assert surface_atlases_data_dir() == custom_dir


def test_candidate_surface_atlas_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data" / "atlases" / "surface"
    monkeypatch.setenv("NEUROFLOW_SURFACE_ATLAS_DIR", str(data_dir))
    candidates = candidate_surface_atlas_dirs()
    assert len(candidates) >= 1
    assert candidates[0] == data_dir


def test_atlas_service_list_packs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NEUROFLOW_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("NEUROFLOW_SURFACE_ATLAS_DIR", str(tmp_path / "atlases"))
    service = AtlasService()
    packs = service.list_packs(res_root=tmp_path)
    assert len(packs) == len(ATLAS_PACKS)
    # With empty directory, packs should have missing files
    schaefer = next(p for p in packs if p["id"] == "schaefer2018_400parcels_17networks")
    assert schaefer["is_default"] is True
    assert "lh.Schaefer2018_400Parcels_17Networks.gcs" in schaefer["missing_files"][0]


def test_atlas_service_get_pack_for_atlas_key() -> None:
    service = AtlasService()
    p1 = service.get_pack_for_atlas_key("schaefer2018_400parcels_17networks")
    assert p1 is not None and p1.id == "schaefer2018_400parcels_17networks"

    p2 = service.get_pack_for_atlas_key("destrieux")
    assert p2 is not None and p2.id == "destrieux"

    p3 = service.get_pack_for_atlas_key("kong")
    assert p3 is not None and p3.id == "kong2022"

    p4 = service.get_pack_for_atlas_key("yale")
    assert p4 is not None and p4.id == "yale"

    p5 = service.get_pack_for_atlas_key("schaefer2018_600parcels_17networks")
    assert p5 is not None and p5.id == "schaefer2018_600parcels_17networks"

    p6 = service.get_pack_for_atlas_key("schaefer2018")
    assert p6 is not None and p6.id == "schaefer2018"

    p_none = service.get_pack_for_atlas_key("unknown_atlas_xyz")
    assert p_none is None


def test_atlas_packs_list_each_schaefer_variant_separately() -> None:
    schaefer_ids = {p.id for p in ATLAS_PACKS if p.category == "schaefer"}
    expected = {key for key, _p, _n, _s in SCHAEFER2018_ATLAS_VARIANTS}
    assert schaefer_ids == expected
    assert "schaefer2018_all" not in schaefer_ids
    assert len(ATLAS_PACKS) == len(SCHAEFER2018_ATLAS_VARIANTS) + 3


def test_atlas_service_import_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target_data = tmp_path / "target_atlases"
    monkeypatch.setenv("NEUROFLOW_SURFACE_ATLAS_DIR", str(target_data))

    source_dir = tmp_path / "source_atlases" / "schaefer"
    source_dir.mkdir(parents=True)
    sample_file = source_dir / "lh.Schaefer2018_400Parcels_17Networks.gcs"
    sample_file.write_bytes(b"dummy gcs data")

    service = AtlasService()
    result = service.import_local_folder(str(source_dir.parent))
    assert result["ok"] is True
    assert result["imported_count"] >= 1

    dest_file = target_data / "schaefer" / "lh.Schaefer2018_400Parcels_17Networks.gcs"
    assert dest_file.is_file()
    assert dest_file.read_bytes() == b"dummy gcs data"


def test_atlas_service_import_zip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target_data = tmp_path / "target_atlases"
    monkeypatch.setenv("NEUROFLOW_SURFACE_ATLAS_DIR", str(target_data))

    zip_path = tmp_path / "test_atlas.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("schaefer/rh.Schaefer2018_400Parcels_17Networks.gcs", b"dummy rh data")

    service = AtlasService()
    result = service.import_local_folder(str(zip_path))
    assert result["ok"] is True
    assert result["imported_count"] == 1

    dest_file = target_data / "schaefer" / "rh.Schaefer2018_400Parcels_17Networks.gcs"
    assert dest_file.is_file()
    assert dest_file.read_bytes() == b"dummy rh data"


def test_atlas_service_download_stream_unknown_pack() -> None:
    service = AtlasService()
    events = list(service.download_pack_stream("invalid_pack_id"))
    assert len(events) == 1
    assert events[0]["step"] == "error"


def test_server_atlas_endpoints(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import json
    import threading
    from urllib.request import Request, urlopen
    from app_backend.server import make_server

    monkeypatch.setenv("NEUROFLOW_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("NEUROFLOW_SURFACE_ATLAS_DIR", str(tmp_path / "atlases"))

    token = "test-token"
    server = make_server("127.0.0.1", 0, api_token=token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"

    try:
        # GET /atlases/status
        req = Request(f"{base_url}/atlases/status", headers={"Authorization": f"Bearer {token}"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["ok"] is True
            assert len(data["packs"]) == len(ATLAS_PACKS)

        # POST /atlases/import
        zip_path = tmp_path / "test_import.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("schaefer/lh.Schaefer2018_400Parcels_17Networks.gcs", b"dummy")

        post_req = Request(
            f"{base_url}/atlases/import",
            data=json.dumps({"path": str(zip_path)}).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            method="POST",
        )
        with urlopen(post_req, timeout=5) as resp:
            import_data = json.loads(resp.read().decode("utf-8"))
            assert import_data["ok"] is True
            assert import_data["imported_count"] == 1
    finally:
        server.shutdown()
        server.server_close()

