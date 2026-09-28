from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from pipeline.atlas_content import (
    atlas_selection_errors,
    available_atlases_for_stat,
    is_atlas_content_available,
    kong2022_content_pack_atlas_keys,
)
from pipeline.content_packs import (
    CONTENT_PACK_ED25519_PUBLIC_KEY_B64,
    ContentPackError,
    install_pack_from_local,
    remove_pack,
    verify_detached_signature,
    decode_signature_blob,
    canonical_index_bytes,
)
from tests.content_pack_fixtures import (
    TEST_CONTENT_PACK_PUBLIC_KEY_B64,
    build_surface_atlases_fixture_files,
)


def test_release_public_key_is_pinned_and_decodable() -> None:
    raw = base64.b64decode(CONTENT_PACK_ED25519_PUBLIC_KEY_B64, validate=True)
    assert len(raw) == 32


def test_install_activate_and_flip_kong_pack_atlases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = build_surface_atlases_fixture_files(tmp_path / "fixture")
    data_root = tmp_path / "data"
    monkeypatch.setenv("NEUROFLOW_DATA_ROOT", str(data_root))

    # Before install, pack-only Kong options stay unavailable.
    key = kong2022_content_pack_atlas_keys()[0]
    assert is_atlas_content_available(key, resource_root=tmp_path) is False

    result = install_pack_from_local(
        pack_id="surface-atlases",
        archive_path=fixture["archive"],
        index_path=fixture["index"],
        signature_path=fixture["signature"],
        data_root=data_root,
        public_key_b64=TEST_CONTENT_PACK_PUBLIC_KEY_B64,
        max_archive_bytes=1024 * 1024,
        max_unpacked_bytes=1024 * 1024,
    )
    assert result["ok"] is True

    assert is_atlas_content_available(key) is True
    assert key in available_atlases_for_stat("cortical_thickness")
    assert atlas_selection_errors({"atlases": {"cortical_thickness": [key]}}) == []

    removed = remove_pack("surface-atlases", data_root=data_root)
    assert removed["ok"] is True
    assert is_atlas_content_available(key) is False


def test_reject_tampered_archive(tmp_path: Path) -> None:
    fixture = build_surface_atlases_fixture_files(tmp_path / "fixture", tamper_archive=True)
    with pytest.raises(ContentPackError, match="SHA-256"):
        install_pack_from_local(
            pack_id="surface-atlases",
            archive_path=fixture["archive"],
            index_path=fixture["index"],
            signature_path=fixture["signature"],
            data_root=tmp_path / "data",
            public_key_b64=TEST_CONTENT_PACK_PUBLIC_KEY_B64,
            max_archive_bytes=1024 * 1024,
            max_unpacked_bytes=1024 * 1024,
        )


def test_reject_bad_signature(tmp_path: Path) -> None:
    fixture = build_surface_atlases_fixture_files(tmp_path / "fixture")
    index_raw = json.loads(fixture["index"].read_text(encoding="utf-8"))
    bad_sig = decode_signature_blob(fixture["signature"].read_text(encoding="utf-8"))
    # Flip one byte.
    bad_sig = bytes([bad_sig[0] ^ 0xFF]) + bad_sig[1:]
    with pytest.raises(ContentPackError, match="signature"):
        verify_detached_signature(
            canonical_index_bytes(index_raw),
            bad_sig,
            public_key_b64=TEST_CONTENT_PACK_PUBLIC_KEY_B64,
        )


def test_reject_unknown_pack_id(tmp_path: Path) -> None:
    fixture = build_surface_atlases_fixture_files(tmp_path / "fixture")
    with pytest.raises(ContentPackError, match="Unknown content pack"):
        install_pack_from_local(
            pack_id="not-a-real-pack",
            archive_path=fixture["archive"],
            index_path=fixture["index"],
            signature_path=fixture["signature"],
            data_root=tmp_path / "data",
            public_key_b64=TEST_CONTENT_PACK_PUBLIC_KEY_B64,
        )


def test_content_pack_service_inline_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app_backend.content_packs import ContentPackService

    monkeypatch.setenv("NEUROFLOW_DATA_ROOT", str(tmp_path / "data"))
    fixture = build_surface_atlases_fixture_files(tmp_path / "fixture")
    service = ContentPackService(data_root=tmp_path / "data")
    result = service.install(
        {
            "pack_id": "surface-atlases",
            "archive_base64": base64.b64encode(fixture["archive"].read_bytes()).decode(),
            "index": json.loads(fixture["index"].read_text(encoding="utf-8")),
            "signature_base64": fixture["signature"].read_text(encoding="utf-8").strip(),
            "public_key_b64": TEST_CONTENT_PACK_PUBLIC_KEY_B64,
        }
    )
    assert result.get("ok") is True
    listed = service.list_packs()
    assert listed["ok"] is True
    packs = listed["packs"]
    assert packs and packs[0]["installed"] is True
    removed = service.remove({"pack_id": "surface-atlases"})
    assert removed.get("ok") is True
