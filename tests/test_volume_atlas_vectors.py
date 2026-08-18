from __future__ import annotations

import csv
from pathlib import Path

from pipeline.config import StatsVectorConfig
from pipeline.stats import StatsGenerator, VECTOR_SPECS, _atlas_column_name


def _write_aseg_stats(stats_dir: Path) -> None:
    text = (
        "# ColHeaders StructName NumSeg SurfArea GrayVol ThickAvg ThickStd MeanCurv GausCurv FoldInd CurvInd\n"
        "Left-Hippocampus 1243 798 1994 2.509 0.871 0.100 0.021 11 1.0\n"
        "Right-Hippocampus 1244 799 2000 2.510 0.872 0.101 0.022 12 1.1\n"
    )
    (stats_dir / "aseg.stats").write_text(text, encoding="utf-8")


def _write_aparc_stats(stats_dir: Path) -> None:
    for hemi in ("lh", "rh"):
        text = (
            "# ColHeaders StructName NumVert SurfArea GrayVol ThickAvg ThickStd MeanCurv GausCurv FoldInd CurvInd\n"
            "bankssts 1243 798 1994 2.509 0.871 0.100 0.021 11 1.0\n"
            "caudalanteriorcingulate 1244 799 2000 2.510 0.872 0.101 0.022 12 1.1\n"
        )
        (stats_dir / f"{hemi}.aparc.stats").write_text(text, encoding="utf-8")


def test_stats_generator_produces_one_vector_per_selected_subcortical_volume_atlas(tmp_path):
    subject_dir = tmp_path / "subject"
    stats_dir = subject_dir / "stats"
    stats_dir.mkdir(parents=True)
    _write_aseg_stats(stats_dir)

    config = StatsVectorConfig(
        enabled_stats={"subcortical_volume": True, "cortical_volume": False, "cortical_thickness": False},
        atlases={"subcortical_volume": ["freesurfer_aseg"], "cortical_volume": [], "cortical_thickness": []},
    )
    result = StatsGenerator(config).generate(str(subject_dir), "subject")

    vectors_dir = stats_dir / "vectors"
    assert (vectors_dir / "subcortical_volume.txt").exists()
    assert (vectors_dir / "subcortical_volume_features.tsv").exists()

    csv_path = vectors_dir / "stats_vectors.csv"
    assert csv_path.exists()
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert "subcortical_volume" in row


def test_stats_generator_produces_one_vector_per_selected_cortical_volume_atlas(tmp_path):
    subject_dir = tmp_path / "subject"
    stats_dir = subject_dir / "stats"
    stats_dir.mkdir(parents=True)
    _write_aparc_stats(stats_dir)

    config = StatsVectorConfig(
        enabled_stats={"subcortical_volume": False, "cortical_volume": True, "cortical_thickness": False},
        atlases={"subcortical_volume": [], "cortical_volume": ["freesurfer_aparc"], "cortical_thickness": []},
    )
    result = StatsGenerator(config).generate(str(subject_dir), "subject")

    vectors_dir = stats_dir / "vectors"
    assert (vectors_dir / "cortical_volume.txt").exists()
    assert (vectors_dir / "cortical_volume_features.tsv").exists()


def test_stats_generator_produces_multiple_vectors_for_multiple_volume_atlases(tmp_path):
    subject_dir = tmp_path / "subject"
    stats_dir = subject_dir / "stats"
    stats_dir.mkdir(parents=True)
    _write_aseg_stats(stats_dir)
    _write_aparc_stats(stats_dir)

    config = StatsVectorConfig(
        enabled_stats={"subcortical_volume": True, "cortical_volume": True, "cortical_thickness": False},
        atlases={
            "subcortical_volume": ["freesurfer_aseg"],
            "cortical_volume": ["freesurfer_aparc"],
            "cortical_thickness": [],
        },
    )
    result = StatsGenerator(config).generate(str(subject_dir), "subject")

    csv_path = stats_dir / "vectors" / "stats_vectors.csv"
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert "subcortical_volume" in row
    assert "cortical_volume" in row


def test_stats_generator_defaults_to_freesurfer_aseg_when_no_subcortical_atlas_selected(tmp_path):
    subject_dir = tmp_path / "subject"
    stats_dir = subject_dir / "stats"
    stats_dir.mkdir(parents=True)
    _write_aseg_stats(stats_dir)

    config = StatsVectorConfig(
        enabled_stats={"subcortical_volume": True, "cortical_volume": False, "cortical_thickness": False},
        atlases={"subcortical_volume": [], "cortical_volume": [], "cortical_thickness": []},
    )
    result = StatsGenerator(config).generate(str(subject_dir), "subject")

    csv_path = stats_dir / "vectors" / "stats_vectors.csv"
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert "subcortical_volume" in row


def test_stats_generator_uses_short_name_for_non_default_volume_atlas(tmp_path):
    subject_dir = tmp_path / "subject"
    stats_dir = subject_dir / "stats"
    mapping_dir = stats_dir / "atlas_mapping"
    mapping_dir.mkdir(parents=True)
    _write_aseg_stats(stats_dir)
    (mapping_dir / "harvard_oxford_sub.stats").write_text(
        "# ColHeaders StructName SegId NVoxels Volume_mm3\n"
        "Left-Hippocampus 1 100 500.5\n",
        encoding="utf-8",
    )

    config = StatsVectorConfig(
        enabled_stats={"subcortical_volume": True, "cortical_volume": False, "cortical_thickness": False},
        atlases={
            "subcortical_volume": ["freesurfer_aseg", "harvard_oxford_subcortical"],
            "cortical_volume": [],
            "cortical_thickness": [],
        },
    )
    StatsGenerator(config).generate(str(subject_dir), "subject")

    csv_path = stats_dir / "vectors" / "stats_vectors.csv"
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert "subcortical_volume" in row
    assert "subcortical_volume_harvard_oxford_sub" in row


def test_stats_generator_keeps_default_cort_vector_when_other_atlases_selected(tmp_path):
    subject_dir = tmp_path / "subject"
    stats_dir = subject_dir / "stats"
    stats_dir.mkdir(parents=True)
    _write_aparc_stats(stats_dir)

    config = StatsVectorConfig(
        enabled_stats={"subcortical_volume": False, "cortical_volume": True, "cortical_thickness": False},
        atlases={
            "subcortical_volume": [],
            "cortical_volume": ["harvard_oxford_cortical", "brainnetome246"],
            "cortical_thickness": [],
        },
    )
    StatsGenerator(config).generate(str(subject_dir), "subject")

    csv_path = stats_dir / "vectors" / "stats_vectors.csv"
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert "cortical_volume" in row
    assert "cortical_volume_harvard_oxford_cort" in row
    assert "cortical_volume_brainnetome246" in row


def test_stats_generator_volume_vector_specs_have_correct_columns():
    assert VECTOR_SPECS["freesurfer_aseg"]["column"] == "freesurfer_aseg_subcortical_volume"
    assert VECTOR_SPECS["freesurfer_aparc"]["column"] == "freesurfer_aparc_cortical_volume"
    assert VECTOR_SPECS["fastsurfer_dkt"]["column"] == "fastsurfer_dkt_volume"
    assert VECTOR_SPECS["cat12_neuromorphometrics"]["column"] == "cat12_neuromorphometrics_volume"
    assert VECTOR_SPECS["cat12_schaefer2018_200parcels_17networks"]["column"] == "cat12_schaefer2018_200parcels_17networks_cortical_volume"


def test_stats_generator_cat12_vector_specs_use_volume_value():
    for key in ["cat12_neuromorphometrics", "cat12_aal3", "cat12_hammers"]:
        assert VECTOR_SPECS[key]["value"] == "volume"


def test_atlas_column_name_uses_vector_type_for_default_atlas():
    assert _atlas_column_name("subcortical_volume", "freesurfer_aseg", True) == "subcortical_volume"
    assert _atlas_column_name("cortical_volume", "freesurfer_aparc", True) == "cortical_volume"


def test_atlas_column_name_uses_short_name_for_non_default_atlas():
    assert (
        _atlas_column_name("subcortical_volume", "harvard_oxford_subcortical", False)
        == "subcortical_volume_harvard_oxford_sub"
    )
