from __future__ import annotations

import json
from pathlib import Path


def test_backend_bundles_neuroflow_configs_on_all_platforms() -> None:
    for platform in ("linux", "macos", "windows"):
        spec = Path("packaging") / platform / "neuroflow-backend.spec"
        content = spec.read_text(encoding="utf-8")

        assert '(os.path.join(PROJECT_ROOT, "configs", "neuroflow"), "configs/neuroflow")' in content


def test_tauri_bundles_neuroflow_configs() -> None:
    config = json.loads(Path("tauri-app/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))

    assert "../../configs/neuroflow" in config["bundle"]["resources"]
