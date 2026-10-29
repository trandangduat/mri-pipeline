from pathlib import Path
import ast
import csv
import json

import pytest

from normalize_volumes import _write_cat12_xml
from pipeline.config import BatchImageResult, StatsVectorConfig
from pipeline.reports import BatchReportContext, write_batch_reports
from pipeline.stats import StatsGenerator, _read_cat12_atlas_values


def normalize(tmp_path, body):
    report, roi = tmp_path / "report.xml", tmp_path / "roi.xml"
    report.write_text("<cat/>")
    roi.write_text("<catROI>" + body + "</catROI>")
    stats = tmp_path / "subject/stats"
    _write_cat12_xml(str(report), str(roi), str(stats / "subcortical_volume.tsv"),
                     str(stats / "cortical_volume.tsv"), "s",
                     out_sub_by_atlas=str(stats / "cat12_subcortical_volume_by_atlas.tsv"),
                     out_cort_by_atlas=str(stats / "cat12_cortical_volume_by_atlas.tsv"))
    return stats


def rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def test_native_aal_ids_and_hemispheres_reach_vector(tmp_path):
    stats = normalize(tmp_path, "<aal3><ids>[1;2]</ids><names><item>lPreCG</item><item>rPreCG</item></names>"
                      "<data><Vgm>[1.5;1.6]</Vgm></data></aal3>")
    table = rows(stats / "cat12_cortical_volume_by_atlas.tsv")
    assert [(r["roi_id"], r["region"], r["hemisphere"], r["volume_mm3"]) for r in table] == [
        ("1", "lPreCG", "lh", "1500"), ("2", "rPreCG", "rh", "1600")]
    cfg = StatsVectorConfig(enabled_stats={"cortical_volume": True}, atlases={"cortical_volume": ["cat12_aal3"]})
    StatsGenerator(cfg).generate(str(stats.parent), "s")
    values = {r["feature"]: r["value"] for r in rows(stats / "vectors/cortical_volume_cat12_aal3_features.tsv")}
    assert values["lh_PreCG"] == "1500.0" and values["rh_PreCG"] == "1600.0"


def test_hammers_has_separate_anatomical_vectors(tmp_path):
    stats = normalize(tmp_path, "<hammers><ids>[2;32]</ids><names><item>TL hippocampus L</item>"
                      "<item>PL angular gyrus L</item></names><data><Vgm>[2;3]</Vgm>"
                      "<Vwm>[99;99]</Vwm><Vcsf>[88;88]</Vcsf></data></hammers>")
    assert rows(stats / "cat12_subcortical_volume_by_atlas.tsv")[0]["roi_id"] == "2"
    assert rows(stats / "cat12_cortical_volume_by_atlas.tsv")[0]["roi_id"] == "32"
    cfg = StatsVectorConfig(enabled_stats={"subcortical_volume": True, "cortical_volume": True},
                            atlases={"subcortical_volume": ["cat12_hammers"], "cortical_volume": ["cat12_hammers"]})
    StatsGenerator(cfg).generate(str(stats.parent), "s")
    sub = rows(stats / "vectors/subcortical_volume_cat12_hammers_features.tsv")
    cort = rows(stats / "vectors/cortical_volume_cat12_hammers_features.tsv")
    assert len(sub) == 25 and len(cort) == 70
    assert next(r["value"] for r in sub if r["feature"] == "TL hippocampus L") == "2000.0"
    assert next(r["value"] for r in cort if r["feature"] == "lh_PL angular gyrus") == "102000.0"
    manifest = json.loads((stats / "vectors/stats_vectors_manifest.json").read_text())
    assert manifest["column_feature_files"]["cortical_volume_cat12_hammers"] == "cat12_hammers_cortical_volume_feats.txt"


def test_duplicate_julich_abbreviations_use_native_ids(tmp_path):
    stats = normalize(tmp_path, "<julichbrain3><ids>[261;281]</ids><names><item>lCM</item><item>lCM</item>"
                      "</names><data><Vgm>[11;22]</Vgm><Vwm>[33;44]</Vwm></data></julichbrain3>")
    table = rows(stats / "cat12_subcortical_volume_by_atlas.tsv")
    assert [(r["roi_id"], r["volume_mm3"]) for r in table] == [("261", "11000"), ("281", "22000")]
    values = _read_cat12_atlas_values(stats, "cat12_julichbrain3", "subcortical_volume")
    assert values["Left CM (Thalamus, centromedian Nucleus)"] == "11000"
    assert values["Left CM (Amygdala)"] == "22000"


def test_native_id_name_mismatch_is_explicit(tmp_path):
    with pytest.raises(ValueError, match="ROI ID/name mismatch"):
        normalize(tmp_path, "<aal3><ids>[2]</ids><names><item>lPreCG</item></names>"
                  "<data><Vgm>[9]</Vgm></data></aal3>")


@pytest.mark.parametrize("region,expected", [("Left Amygdala", "1000"), ("Brain Stem", "2000"),
                                          ("3rd Ventricle", "4000"), ("Right Ventral DC", "3000")])
def test_native_tissue_selection_and_unit_conversion(tmp_path, region, expected):
    stats = normalize(tmp_path, "<neuromorphometrics><names><item>" + region + "</item></names>"
                      "<data><Vgm>[1]</Vgm><Vwm>[2]</Vwm><Vcsf>[4]</Vcsf></data></neuromorphometrics>")
    assert rows(stats / "cat12_subcortical_volume_by_atlas.tsv")[0]["volume_mm3"] == expected


def test_missing_designated_tissue_stays_unavailable(tmp_path):
    stats = normalize(tmp_path, "<neuromorphometrics><names><item>Brain Stem</item></names>"
                      "<data><Vgm>[9]</Vgm></data></neuromorphometrics>")
    assert rows(stats / "cat12_subcortical_volume_by_atlas.tsv")[0]["volume_mm3"] == "NA"


def test_selected_atlas_never_borrows_generic_values(tmp_path):
    (tmp_path / "subcortical_volume.tsv").write_text("structure\tvolume_mm3\nLeft Amygdala\t999999\n")
    assert _read_cat12_atlas_values(tmp_path, "cat12_neuromorphometrics", "subcortical_volume") == {}
    (tmp_path / "cat12_subcortical_volume_by_atlas.tsv").write_text(
        "atlas\tstructure\tvolume_mm3\ncat12_hammers\tTL amygdala L\t777\n")
    assert _read_cat12_atlas_values(tmp_path, "cat12_neuromorphometrics", "subcortical_volume") == {}


def test_old_vector_indices_cannot_relabel_values(tmp_path):
    subject = tmp_path / "subject"
    vectors = subject / "stats/vectors"
    vectors.mkdir(parents=True)
    old = vectors / "cortical_volume_cat12_aal3_features.tsv"
    original = "index\tfeature\tvalue\n1\trh_PreCG\t100\n2\tlh_PreCG\t200\n"
    old.write_text(original)
    cfg = StatsVectorConfig(enabled_stats={"cortical_volume": True}, atlases={"cortical_volume": ["cat12_aal3"]})
    result = BatchImageResult(input_file="input", subject_id="s", subject_dir=str(subject), success=True, duration_sec=1)
    write_batch_reports(BatchReportContext(str(tmp_path / "batch"), ["input"], [result], {"input": "s"}, "", cfg))
    with (tmp_path / "batch/stats_vectors_wide.csv").open() as stream:
        wide = next(csv.DictReader(stream))
    assert wide["cortical_volume_cat12_aal3_lh_PreCG"] == "200.0"
    assert wide["cortical_volume_cat12_aal3_rh_PreCG"] == "100.0"
    with (tmp_path / "batch/stats_vectors_summary.csv").open() as stream:
        summary = next(csv.DictReader(stream))
    assert ast.literal_eval(summary["cortical_volume_cat12_aal3"])[:2] == [200.0, 100.0]
    assert old.read_text() == original
