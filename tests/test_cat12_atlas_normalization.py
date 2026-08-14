from __future__ import annotations

import csv
from pathlib import Path

from normalize_volumes import _write_cat12_xml


def test_write_cat12_xml_exports_atlas_aware_subcortical_tsv(tmp_path):
    report = tmp_path / "cat_input.xml"
    roi = tmp_path / "catROI_input.xml"
    subcortical = tmp_path / "subcortical_volume.tsv"
    cortical = tmp_path / "cortical_volume.tsv"
    sub_by_atlas = tmp_path / "cat12_subcortical_volume_by_atlas.tsv"

    report.write_text("<cat />", encoding="utf-8")
    roi.write_text(
        """
        <catROI>
          <neuromorphometrics>
            <names>
              <item>Left Hippocampus</item>
              <item>Right Amygdala</item>
            </names>
            <data>
              <Vgm>[3.4;2.1]</Vgm>
            </data>
          </neuromorphometrics>
        </catROI>
        """,
        encoding="utf-8",
    )

    _write_cat12_xml(
        str(report), str(roi), str(subcortical), str(cortical), "sub-01",
        out_sub_by_atlas=str(sub_by_atlas),
    )

    with open(sub_by_atlas, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    assert len(rows) == 2
    assert rows[0]["atlas"] == "cat12_neuromorphometrics"
    assert rows[0]["structure"] == "Left Hippocampus"
    assert rows[0]["volume"] == "3.4"
    assert rows[1]["atlas"] == "cat12_neuromorphometrics"
    assert rows[1]["structure"] == "Right Amygdala"
    assert rows[1]["volume"] == "2.1"


def test_write_cat12_xml_exports_atlas_aware_cortical_tsv(tmp_path):
    report = tmp_path / "cat_input.xml"
    roi = tmp_path / "catROI_input.xml"
    subcortical = tmp_path / "subcortical_volume.tsv"
    cortical = tmp_path / "cortical_volume.tsv"
    cort_by_atlas = tmp_path / "cat12_cortical_volume_by_atlas.tsv"

    report.write_text("<cat />", encoding="utf-8")
    roi.write_text(
        """
        <catROI>
          <Schaefer2018_200Parcels_17Networks_order>
            <names>
              <item>ctx-lh-7Networks_LH_Vis_1</item>
              <item>ctx-rh-7Networks_RH_Vis_1</item>
            </names>
            <data>
              <Vgm>[1.5;1.6]</Vgm>
            </data>
          </Schaefer2018_200Parcels_17Networks_order>
        </catROI>
        """,
        encoding="utf-8",
    )

    _write_cat12_xml(
        str(report), str(roi), str(subcortical), str(cortical), "sub-01",
        out_cort_by_atlas=str(cort_by_atlas),
    )

    with open(cort_by_atlas, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    assert len(rows) == 2
    assert rows[0]["atlas"] == "cat12_schaefer2018_200parcels_17networks"
    assert rows[0]["region"] == "7Networks_LH_Vis_1"
    assert rows[0]["hemisphere"] == "lh"
    assert rows[0]["volume"] == "1.5"
    assert rows[1]["atlas"] == "cat12_schaefer2018_200parcels_17networks"
    assert rows[1]["region"] == "7Networks_RH_Vis_1"
    assert rows[1]["hemisphere"] == "rh"
    assert rows[1]["volume"] == "1.6"


def test_write_cat12_xml_atlas_aware_preserves_multiple_atlases(tmp_path):
    report = tmp_path / "cat_input.xml"
    roi = tmp_path / "catROI_input.xml"
    subcortical = tmp_path / "subcortical_volume.tsv"
    cortical = tmp_path / "cortical_volume.tsv"
    sub_by_atlas = tmp_path / "cat12_subcortical_volume_by_atlas.tsv"
    cort_by_atlas = tmp_path / "cat12_cortical_volume_by_atlas.tsv"

    report.write_text("<cat />", encoding="utf-8")
    roi.write_text(
        """
        <S>
          <neuromorphometrics>
            <names>
              <item>Left Hippocampus</item>
            </names>
            <data>
              <Vgm>[3.4]</Vgm>
            </data>
          </neuromorphometrics>
          <aal3>
            <names>
              <item>lPreCG</item>
            </names>
            <data>
              <Vgm>[8.1]</Vgm>
            </data>
          </aal3>
        </S>
        """,
        encoding="utf-8",
    )

    _write_cat12_xml(
        str(report), str(roi), str(subcortical), str(cortical), "sub-01",
        out_sub_by_atlas=str(sub_by_atlas),
        out_cort_by_atlas=str(cort_by_atlas),
    )

    with open(sub_by_atlas, encoding="utf-8", newline="") as f:
        sub_rows = list(csv.DictReader(f, delimiter="\t"))
    with open(cort_by_atlas, encoding="utf-8", newline="") as f:
        cort_rows = list(csv.DictReader(f, delimiter="\t"))

    sub_by_atlas_name = {r["atlas"]: r for r in sub_rows}
    cort_by_atlas_name = {r["atlas"]: r for r in cort_rows}

    assert "cat12_neuromorphometrics" in sub_by_atlas_name
    assert sub_by_atlas_name["cat12_neuromorphometrics"]["structure"] == "Left Hippocampus"
    assert "cat12_aal3" in cort_by_atlas_name
    assert cort_by_atlas_name["cat12_aal3"]["region"] == "lPreCG"


def test_write_cat12_xml_atlas_aware_still_produces_generic_tsvs(tmp_path):
    report = tmp_path / "cat_input.xml"
    roi = tmp_path / "catROI_input.xml"
    subcortical = tmp_path / "subcortical_volume.tsv"
    cortical = tmp_path / "cortical_volume.tsv"
    sub_by_atlas = tmp_path / "cat12_subcortical_volume_by_atlas.tsv"
    cort_by_atlas = tmp_path / "cat12_cortical_volume_by_atlas.tsv"

    report.write_text(
        """
        <cat>
          <subjectmeasures>
            <vol_TIV>1512.5</vol_TIV>
          </subjectmeasures>
        </cat>
        """,
        encoding="utf-8",
    )
    roi.write_text(
        """
        <catROI>
          <neuromorphometrics>
            <names>
              <item>Left Hippocampus</item>
            </names>
            <data>
              <Vgm>[3.4]</Vgm>
            </data>
          </neuromorphometrics>
        </catROI>
        """,
        encoding="utf-8",
    )

    _write_cat12_xml(
        str(report), str(roi), str(subcortical), str(cortical), "sub-01",
        out_sub_by_atlas=str(sub_by_atlas),
        out_cort_by_atlas=str(cort_by_atlas),
    )

    assert subcortical.exists()
    assert cortical.exists()
    assert sub_by_atlas.exists()
    assert cort_by_atlas.exists()

    with open(subcortical, encoding="utf-8", newline="") as f:
        generic_sub = list(csv.DictReader(f, delimiter="\t"))
    assert any(r["structure"] == "total intracranial" for r in generic_sub)
    assert any(r["structure"] == "Left Hippocampus" for r in generic_sub)
