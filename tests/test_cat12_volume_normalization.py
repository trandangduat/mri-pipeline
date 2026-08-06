from __future__ import annotations

import csv
import struct

from normalize_volumes import _write_cat12_xml


def test_write_cat12_xml_exports_report_and_roi_volumes(tmp_path) -> None:
    report = tmp_path / "cat_input.xml"
    roi = tmp_path / "catROI_input.xml"
    subcortical = tmp_path / "subcortical_volume.tsv"
    cortical = tmp_path / "cortical_volume.tsv"

    report.write_text(
        """
        <cat>
          <subjectmeasures>
            <vol_TIV>1512.5</vol_TIV>
            <vol_abs_CGW>322.1 612.2 578.3</vol_abs_CGW>
          </subjectmeasures>
        </cat>
        """,
        encoding="utf-8",
    )
    roi.write_text(
        """
        <catROI>
          <atlas>
            <name>Neuromorphometrics</name>
            <roi>
              <name>Left Hippocampus</name>
              <Vgm>3.4</Vgm>
            </roi>
            <roi>
              <label>Right Cortex</label>
              <volume>42.0</volume>
            </roi>
          </atlas>
        </catROI>
        """,
        encoding="utf-8",
    )

    _write_cat12_xml(str(report), str(roi), str(subcortical), str(cortical), "sub-01")

    with open(subcortical, encoding="utf-8", newline="") as f:
        sub_rows = list(csv.DictReader(f, delimiter="\t"))
    with open(cortical, encoding="utf-8", newline="") as f:
        cort_rows = list(csv.DictReader(f, delimiter="\t"))

    sub_values = {row["structure"]: row["volume_mm3"] for row in sub_rows}
    cort_values = {row["region"]: row["volume_mm3"] for row in cort_rows}

    assert sub_values["total intracranial"] == "1512.5"
    assert sub_values["gray matter"] == "612.2"
    assert sub_values["Left Hippocampus"] == "3.4"
    assert cort_values["Right Cortex"] == "42.0"


def test_write_cat12_xml_exports_vector_style_roi_volumes(tmp_path) -> None:
    report = tmp_path / "cat_input.xml"
    roi = tmp_path / "catROI_input.xml"
    subcortical = tmp_path / "subcortical_volume.tsv"
    cortical = tmp_path / "cortical_volume.tsv"

    report.write_text("<cat />", encoding="utf-8")
    roi.write_text(
        """
        <catROI>
          <atlas>
            <names>
              <item>Left Amygdala</item>
              <item>Right Frontal Cortex</item>
            </names>
            <Vgm>1.2 9.8</Vgm>
          </atlas>
        </catROI>
        """,
        encoding="utf-8",
    )

    _write_cat12_xml(str(report), str(roi), str(subcortical), str(cortical), "sub-01")

    with open(subcortical, encoding="utf-8", newline="") as f:
        sub_rows = list(csv.DictReader(f, delimiter="\t"))
    with open(cortical, encoding="utf-8", newline="") as f:
        cort_rows = list(csv.DictReader(f, delimiter="\t"))

    assert {row["structure"]: row["volume_mm3"] for row in sub_rows}["Left Amygdala"] == "1.2"
    assert {row["region"]: row["volume_mm3"] for row in cort_rows}["Right Frontal Cortex"] == "9.8"


def test_write_cat12_xml_exports_nested_data_roi_volumes(tmp_path) -> None:
    report = tmp_path / "cat_input.xml"
    roi = tmp_path / "catROI_input.xml"
    subcortical = tmp_path / "subcortical_volume.tsv"
    cortical = tmp_path / "cortical_volume.tsv"

    report.write_text("<cat />", encoding="utf-8")
    roi.write_text(
        """
        <S>
          <aal3>
            <names>
              <item>lPreCG</item>
              <item>rPreCG</item>
            </names>
            <data>
              <Vgm>[8.1;7.2]</Vgm>
            </data>
          </aal3>
          <neuromorphometrics>
            <names>
              <item>Left Amygdala</item>
            </names>
            <data>
              <Vgm>[1.4]</Vgm>
            </data>
          </neuromorphometrics>
        </S>
        """,
        encoding="utf-8",
    )

    _write_cat12_xml(str(report), str(roi), str(subcortical), str(cortical), "sub-01")

    with open(subcortical, encoding="utf-8", newline="") as f:
        sub_rows = list(csv.DictReader(f, delimiter="\t"))
    with open(cortical, encoding="utf-8", newline="") as f:
        cort_rows = list(csv.DictReader(f, delimiter="\t"))

    assert {row["structure"]: row["volume_mm3"] for row in sub_rows}["Left Amygdala"] == "1.4"
    assert {row["region"]: row["volume_mm3"] for row in cort_rows}["lPreCG"] == "8.1"
    assert {row["region"]: row["volume_mm3"] for row in cort_rows}["rPreCG"] == "7.2"


def test_write_cat12_xml_exports_roi_thickness_values(tmp_path) -> None:
    report = tmp_path / "cat_input.xml"
    roi = tmp_path / "catROI_input.xml"
    subcortical = tmp_path / "subcortical_volume.tsv"
    cortical = tmp_path / "cortical_volume.tsv"
    thickness = tmp_path / "cat12_cortical_thickness.tsv"

    report.write_text("<cat />", encoding="utf-8")
    roi.write_text(
        """
        <catROI>
          <atlas>
            <roi>
              <name>Left Superior Frontal Cortex</name>
              <thickness>2.45</thickness>
            </roi>
            <names>
              <item>ctx-rh-inferiorparietal</item>
              <item>Right Temporal Cortex</item>
            </names>
            <mean_thickness>2.51 2.72</mean_thickness>
          </atlas>
        </catROI>
        """,
        encoding="utf-8",
    )

    _write_cat12_xml(str(report), str(roi), str(subcortical), str(cortical), "sub-01", out_thickness=str(thickness))

    with open(thickness, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    values = {(row["hemisphere"], row["region"]): row["thickness_mm"] for row in rows}
    assert values[("lh", "Superior Frontal Cortex")] == "2.45"
    assert values[("rh", "inferiorparietal")] == "2.51"
    assert values[("rh", "Temporal Cortex")] == "2.72"


def test_write_cat12_xml_exports_surface_thickness_fallback(tmp_path) -> None:
    report = tmp_path / "cat_input.xml"
    roi = tmp_path / "catROI_input.xml"
    subcortical = tmp_path / "subcortical_volume.tsv"
    cortical = tmp_path / "cortical_volume.tsv"
    thickness = tmp_path / "cat12_cortical_thickness.tsv"
    surf = tmp_path / "surf"
    surf.mkdir()

    report.write_text("<cat />", encoding="utf-8")
    roi.write_text("<S />", encoding="utf-8")
    for name, values in {"lh.thickness.input": [2.0, 2.5], "rh.thickness.input": [3.0, 3.5]}.items():
        (surf / name).write_bytes(b"\xff\xff\xff" + struct.pack(">iii", len(values), 0, 1) + struct.pack(f">{len(values)}f", *values))

    _write_cat12_xml(
        str(report),
        str(roi),
        str(subcortical),
        str(cortical),
        "sub-01",
        out_thickness=str(thickness),
        surf_dir=str(surf),
    )

    with open(thickness, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    values = {(row["hemisphere"], row["region"]): row["thickness_mm"] for row in rows}
    assert values[("lh", "global cortical mean")] == "2.250000"
    assert values[("rh", "global cortical mean")] == "3.250000"
    assert values[("both", "global cortical mean")] == "2.750000"
