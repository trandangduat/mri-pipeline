from __future__ import annotations

import json
from pathlib import Path

from app_backend.config_store import ConfigStore


def test_workspace_save_load_list_and_password_redaction(tmp_path: Path) -> None:
    store = ConfigStore(config_root=tmp_path / "configs")

    saved = store.save_workspace(
        "research workspace",
        {
            "type": "mri-pipeline-workspace",
            "remote": {"host": "server", "password": "secret"},
            "remote_password": "secret",
            "remotePassword": "secret",
            "sshPassword": "secret",
            "keyPassword": "secret",
        },
    )

    assert saved["ok"] is True
    assert saved["name"] == "research_workspace"
    loaded = store.load_workspace("research_workspace")
    assert loaded["ok"] is True
    assert loaded["data"] == {
        "type": "mri-pipeline-workspace",
        "name": "research_workspace",
        "remote": {"host": "server"},
    }
    assert store.list_workspaces()["items"] == [{"name": "research_workspace", "path": str(tmp_path / "configs" / "workspaces" / "research_workspace.json")}]
    raw = json.loads((tmp_path / "configs" / "workspaces" / "research_workspace.json").read_text(encoding="utf-8"))
    assert "secret" not in json.dumps(raw)


def test_preset_save_load_uses_preset_type(tmp_path: Path) -> None:
    store = ConfigStore(config_root=tmp_path / "configs")

    saved = store.save_preset("fs7", {"pipeline_mode": "FreeSurfer 7 + Volume"})

    assert saved["ok"] is True
    loaded = store.load_preset("fs7")
    assert loaded["ok"] is True
    assert loaded["data"] == {
        "type": "mri-pipeline-preset",
        "name": "fs7",
        "pipeline_mode": "FreeSurfer 7 + Volume",
    }


def test_config_store_rejects_path_traversal_names(tmp_path: Path) -> None:
    store = ConfigStore(config_root=tmp_path / "configs")

    assert store.save_workspace("../evil", {}) == {"ok": False, "error": "Invalid config name"}
    assert store.load_workspace("../evil") == {"ok": False, "error": "Invalid config name"}
    assert not (tmp_path / "evil.json").exists()
