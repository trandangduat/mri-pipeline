from __future__ import annotations

import json
from pathlib import Path

from packaging_resources import collect_core_info_datas, collect_python_source_datas
from pipeline.stats import VECTOR_SPECS


def test_backend_bundles_the_runtime_resource_contract_on_all_platforms() -> None:
    for platform in ("linux", "macos", "windows"):
        spec = Path("packaging") / platform / "neuroflow-backend.spec"
        content = spec.read_text(encoding="utf-8")

        assert '(os.path.join(PROJECT_ROOT, "configs", "neuroflow"), "configs/neuroflow")' in content
        assert "collect_core_info_datas(Path(PROJECT_ROOT))" in content
        assert 'collect_python_source_datas(Path(PROJECT_ROOT) / "pipeline", "pipeline")' in content
        assert '(os.path.join(PROJECT_ROOT, "normalize_volumes.py"), ".")' in content
        assert 'contents_directory="_internal"' in content
        assert '"pandas"' not in content
        assert '"PIL"' not in content
        assert '"psutil"' not in content

        build_script = Path("packaging") / platform / ("build-backend.ps1" if platform == "windows" else "build-backend.sh")
        build_content = build_script.read_text(encoding="utf-8")
        assert "NEUROFLOW_API_TOKEN" in build_content
        assert "Authorization" in build_content
        assert "_internal" in build_content
        assert "/metadata" in build_content


def test_core_info_selection_contains_all_vector_feature_contracts_but_not_research_csv() -> None:
    datas = collect_core_info_datas(Path("."))
    source_files = {Path(source) for source, _destination in datas}
    feature_files = {path.name for path in source_files}
    referenced_features = {str(spec["features"]) for spec in VECTOR_SPECS.values() if "features" in spec}

    assert referenced_features <= feature_files
    assert source_files
    assert all(path.suffix == ".txt" for path in source_files)
    assert Path("info/2026.05.17_ADNI.csv") not in source_files


def test_raw_pipeline_data_excludes_generated_bytecode(tmp_path: Path) -> None:
    package = tmp_path / "pipeline"
    package.mkdir()
    (package / "runner.py").write_text("VALUE = 1\n", encoding="utf-8")
    cache = package / "__pycache__"
    cache.mkdir()
    (cache / "runner.cpython-312.pyc").write_bytes(b"not-runtime-source")

    datas = collect_python_source_datas(package, "pipeline")

    assert datas == [(str(package / "runner.py"), "pipeline")]


def test_tauri_bundles_the_staged_one_directory_backend() -> None:
    config = json.loads(Path("tauri-app/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))

    assert config["bundle"]["resources"] == {
        "../../build/tauri-resources/backend": "backend"
    }
    assert "icons/icon.icns" in config["bundle"]["icon"]
    assert Path("tauri-app/src-tauri/icons/icon.icns").is_file()


def test_native_release_workflows_upload_one_platform_distribution_not_portable_archives() -> None:
    windows = Path(".github/workflows/package-windows.yml").read_text(encoding="utf-8")
    unix = Path(".github/workflows/package-unix.yml").read_text(encoding="utf-8")

    assert "bundle\\nsis" in windows
    assert "NeuroFlow-Windows-x64" in windows
    assert "unsigned-test" in windows
    assert "dist-portable" not in windows
    assert "bundle/appimage" in unix
    assert "bundle/dmg" in unix
    assert "NeuroFlow-Linux-x64" in unix
    assert "NeuroFlow-macOS-x64" in unix
    assert "NeuroFlow-macOS-arm64" in unix
    assert "unsigned-test" in unix
    assert "dist-portable" not in unix


def test_native_shell_sets_resource_root_to_pyinstaller_internal() -> None:
    """Guard the chosen contract: resource root is backend/_internal, not exe parent."""
    lib = Path("tauri-app/src-tauri/src/lib.rs").read_text(encoding="utf-8")
    assert "fn pyinstaller_resource_root" in lib
    assert 'backend_root.join("_internal")' in lib
    assert "NEUROFLOW_RESOURCE_ROOT" in lib
    # Reject the alternate COLLECT(contents_directory=".") contract unless
    # specs and shell are updated together.
    for platform in ("linux", "macos", "windows"):
        spec = Path("packaging") / platform / "neuroflow-backend.spec"
        assert 'contents_directory="_internal"' in spec.read_text(encoding="utf-8")
