from pathlib import Path
from unittest.mock import MagicMock

import pytest

import normalize_volumes as normalize
from packaging_resources import collect_core_info_datas
from pipeline.config import PipelineConfig
from pipeline.registry import TOOL_DEFS
from pipeline.runner import _build_execution_request
from remote.remote_runner import RemoteRunConfig, RemoteRunner
from remote.ssh_client import SSHConfig

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("atlases", [{}, {"subcortical_volume": ["cat12_neuromorphometrics"]}])
def test_cat12_dictionary_is_uploaded_without_size_shortcuts(atlases):
    ssh = MagicMock()
    ssh.expand_path.side_effect = lambda value: value
    ssh.sftp.stat.side_effect = OSError("fresh server")
    runner = RemoteRunner(RemoteRunConfig(
        ssh=SSHConfig(host="mock"), remote_workspace="/home/tester/work",
        stats_vector_config={"atlases": atlases}))
    runner._upload_code(ssh, "/home/tester/work/code")
    assert any(Path(call.args[0]).name == "cat12_tissue_flags.txt"
               and call.args[1] == "/home/tester/work/code/info/cat12_tissue_flags.txt"
               for call in ssh.upload_file.call_args_list)


def test_cat12_dictionary_is_packaged():
    assert (str(ROOT / "info/cat12_tissue_flags.txt"), "info") in collect_core_info_datas(ROOT)


@pytest.mark.parametrize("tool_key", ["cat12_volume_stats_extraction", "cat12_full_stats_extraction", "mri_convert_fs7"])
def test_only_cat12_execution_requires_tissue_dictionary(tmp_path, monkeypatch, tool_key):
    import pipeline.runner as runner
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    (tmp_path / "normalize_volumes.py").write_text("# normalizer")
    cfg = PipelineConfig(input_file=str(tmp_path / "input"), output_dir=str(tmp_path / "out"), subject_id="s")
    kwargs = dict(tool_key=tool_key, tool=TOOL_DEFS[tool_key], config=cfg,
                  subject_dir=str(tmp_path / "out/s"), logs_dir=str(tmp_path / "logs"),
                  input_for_next_step=None, license_mount=[], memory_limit_bytes=None)
    if tool_key.startswith("cat12"):
        with pytest.raises(RuntimeError, match="CAT12 resource"):
            _build_execution_request(**kwargs)
    else:
        _build_execution_request(**kwargs)


@pytest.mark.parametrize("content", [None, b"", b"atlas\\troi_name\\tvgm\\tvwm\\tvcsf\n",
                                     b"atlas broken\n", b"a\tr\t2\t0\t0\n", b"\xff"])
def test_cat12_volume_rejects_missing_or_invalid_dictionary(tmp_path, monkeypatch, content):
    monkeypatch.setenv("NEUROFLOW_RESOURCE_ROOT", str(tmp_path))
    monkeypatch.setattr(normalize, "__file__", str(tmp_path / "normalize_volumes.py"))
    if content is not None:
        (tmp_path / "info").mkdir()
        (tmp_path / "info/cat12_tissue_flags.txt").write_bytes(content)
    report, roi = tmp_path / "report.xml", tmp_path / "roi.xml"
    report.write_text("<cat/>")
    roi.write_text("<catROI/>")
    with pytest.raises(RuntimeError, match="CAT12 tissue dictionary"):
        normalize._write_cat12_xml(str(report), str(roi), str(tmp_path / "sub.tsv"),
                                  str(tmp_path / "cort.tsv"), "s")
    assert not (tmp_path / "sub.tsv").exists()
