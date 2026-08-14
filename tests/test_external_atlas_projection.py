from __future__ import annotations

import csv
from pathlib import Path

from pipeline.config import (
    EXTERNAL_MNI_SUBCORTICAL_VOLUME_ATLASES,
    EXTERNAL_MNI_CORTICAL_VOLUME_ATLASES,
    FREESURFER_BUILTIN_SUBREGION_ATLASES,
    SUBCORTICAL_VOLUME_ATLASES,
    CORTICAL_VOLUME_ATLASES,
    STAT_VECTOR_DEFS,
    ATLAS_DEFS,
    StatsVectorConfig,
)
from pipeline.stats import VECTOR_SPECS, StatsGenerator, _read_projected_atlas_values


def test_external_mni_atlases_in_subcortical_volume_atlases() -> None:
    for atlas in EXTERNAL_MNI_SUBCORTICAL_VOLUME_ATLASES:
        assert atlas in SUBCORTICAL_VOLUME_ATLASES, f"{atlas} missing from SUBCORTICAL_VOLUME_ATLASES"


def test_external_mni_atlases_in_cortical_volume_atlases() -> None:
    for atlas in EXTERNAL_MNI_CORTICAL_VOLUME_ATLASES:
        assert atlas in CORTICAL_VOLUME_ATLASES, f"{atlas} missing from CORTICAL_VOLUME_ATLASES"


def test_builtin_subregion_atlases_in_subcortical_volume_atlases() -> None:
    for atlas in FREESURFER_BUILTIN_SUBREGION_ATLASES:
        assert atlas in SUBCORTICAL_VOLUME_ATLASES, f"{atlas} missing from SUBCORTICAL_VOLUME_ATLASES"


def test_mni_sclimbic_in_stat_vector_defs() -> None:
    assert "mni_sclimbic" in STAT_VECTOR_DEFS["subcortical_volume"]["atlases"]


def test_external_atlas_keys_in_atlas_defs() -> None:
    for atlas in EXTERNAL_MNI_SUBCORTICAL_VOLUME_ATLASES:
        assert atlas in ATLAS_DEFS, f"{atlas} missing from ATLAS_DEFS"
    for atlas in EXTERNAL_MNI_CORTICAL_VOLUME_ATLASES:
        assert atlas in ATLAS_DEFS, f"{atlas} missing from ATLAS_DEFS"
    for atlas in FREESURFER_BUILTIN_SUBREGION_ATLASES:
        assert atlas in ATLAS_DEFS, f"{atlas} missing from ATLAS_DEFS"


def test_external_atlas_vector_specs_have_requires_projection() -> None:
    for atlas in EXTERNAL_MNI_SUBCORTICAL_VOLUME_ATLASES:
        spec = VECTOR_SPECS.get(atlas)
        assert spec is not None, f"VECTOR_SPECS missing entry for {atlas}"
        assert spec.get("requires_projection") is True, f"{atlas} should have requires_projection=True"


def test_builtin_subregion_vector_specs_have_requires_native_segmentation() -> None:
    for atlas in FREESURFER_BUILTIN_SUBREGION_ATLASES:
        spec = VECTOR_SPECS.get(atlas)
        assert spec is not None, f"VECTOR_SPECS missing entry for {atlas}"
        assert spec.get("requires_native_segmentation") is True, f"{atlas} should have requires_native_segmentation=True"


def test_mni_sclimbic_vector_spec_has_template_space() -> None:
    spec = VECTOR_SPECS["mni_sclimbic"]
    assert spec["template_space"] == "mni152"
    assert spec["value"] == "volume_mm3"


def test_read_projected_atlas_values_reads_stats_file(tmp_path):
    stats_dir = tmp_path / "stats"
    mapping_dir = stats_dir / "atlas_mapping"
    mapping_dir.mkdir(parents=True)

    stats_text = (
        "# ColHeaders StructName SegId NVoxels Volume_mm3\n"
        "Left-Accumbens 1 100 500.5\n"
        "Right-Accumbens 2 95 475.3\n"
        "Left-Hippocampus 3 200 1000.1\n"
    )
    (mapping_dir / "mni_sclimbic.stats").write_text(stats_text, encoding="utf-8")

    values = _read_projected_atlas_values(stats_dir, "mni_sclimbic")
    assert values["Left-Accumbens"] == "500.5"
    assert values["Right-Accumbens"] == "475.3"
    assert values["Left-Hippocampus"] == "1000.1"


def test_read_projected_atlas_values_falls_back_to_stats_dir(tmp_path):
    stats_dir = tmp_path / "stats"
    stats_dir.mkdir(parents=True)

    stats_text = (
        "# ColHeaders StructName SegId NVoxels Volume_mm3\n"
        "Region-A 1 100 500.5\n"
    )
    (stats_dir / "cerebra.stats").write_text(stats_text, encoding="utf-8")

    values = _read_projected_atlas_values(stats_dir, "cerebra")
    assert values["Region-A"] == "500.5"


def test_read_projected_atlas_values_empty_when_no_file(tmp_path):
    stats_dir = tmp_path / "stats"
    stats_dir.mkdir(parents=True)
    values = _read_projected_atlas_values(stats_dir, "mni_sclimbic")
    assert values == {}


def test_stats_generator_produces_vector_for_projected_atlas(tmp_path):
    subject_dir = tmp_path / "subject"
    stats_dir = subject_dir / "stats"
    mapping_dir = stats_dir / "atlas_mapping"
    mapping_dir.mkdir(parents=True)

    stats_text = (
        "# ColHeaders StructName SegId NVoxels Volume_mm3\n"
        "Left-Accumbens 1 100 500.5\n"
        "Right-Accumbens 2 95 475.3\n"
        "Left-Hippocampus 3 200 1000.1\n"
        "Right-Hippocampus 4 190 950.0\n"
        "Left-Amygdala 5 80 400.2\n"
        "Right-Amygdala 6 75 375.1\n"
        "Left-Caudate 7 120 600.3\n"
        "Right-Caudate 8 115 575.2\n"
        "Left-Pallidum 9 40 200.1\n"
        "Right-Pallidum 10 38 190.0\n"
        "Left-Putamen 11 130 650.4\n"
        "Right-Putamen 12 125 625.3\n"
        "Left-Thalamus 13 150 750.5\n"
        "Right-Thalamus 14 145 725.4\n"
        "Left-Hypothalamus 15 30 150.2\n"
        "Right-Hypothalamus 16 28 140.1\n"
        "Left-Fornix 17 20 100.3\n"
        "Right-Fornix 18 18 90.2\n"
        "Left-Mammillary-Body 19 5 25.1\n"
        "Right-Mammillary-Body 20 4 20.0\n"
        "Anterior-Commissure 21 10 50.2\n"
        "Left-Basal-Forebrain 22 15 75.3\n"
        "Right-Basal-Forebrain 23 14 70.2\n"
        "Left-Septal-Nuclei 24 8 40.1\n"
        "Right-Septal-Nuclei 25 7 35.0\n"
    )
    (mapping_dir / "mni_sclimbic.stats").write_text(stats_text, encoding="utf-8")

    config = StatsVectorConfig(
        enabled_stats={"subcortical_volume": True, "cortical_volume": False, "cortical_thickness": False},
        atlases={"subcortical_volume": ["mni_sclimbic"], "cortical_volume": [], "cortical_thickness": []},
    )
    result = StatsGenerator(config).generate(str(subject_dir), "subject")

    csv_path = stats_dir / "vectors" / "stats_vectors.csv"
    assert csv_path.exists()
    with open(csv_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert "mni_sclimbic_subcortical_volume" in row

    features_path = stats_dir / "vectors" / "mni_sclimbic_subcortical_volume_features.tsv"
    assert features_path.exists()
    with open(features_path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    values = {r["feature"]: r["value"] for r in rows}
    assert values["Left-Accumbens"] == "500.5"


def test_fs8_stage9_command_includes_atlas_projection_when_sclimbic_selected():
    from pipeline.config import ToolContext
    from pipeline.registry import TOOL_DEFS

    ctx = ToolContext(
        input_path="/input.nii",
        subject_id="subj",
        threads=4,
        device="cpu",
        enabled_stats={
            "cortical_thickness": False,
            "cortical_volume": False,
            "subcortical_volume": True,
            "selected_atlases": ["mni_sclimbic"],
        },
    )
    command = TOOL_DEFS["fs8_reduced54_stats"]["command_builder"](ctx)
    assert "sclimbic" in command
    assert "mri_synthmorph register" in command
    assert "mri_vol2vol" in command
    assert "mri_segstats" in command
    assert "atlas_mapping/mni_sclimbic.stats" in command


def test_fs8_stage9_command_skips_atlas_projection_when_not_selected():
    from pipeline.config import ToolContext
    from pipeline.registry import TOOL_DEFS

    ctx = ToolContext(
        input_path="/input.nii",
        subject_id="subj",
        threads=4,
        device="cpu",
        enabled_stats={
            "cortical_thickness": False,
            "cortical_volume": False,
            "subcortical_volume": True,
            "selected_atlases": [],
        },
    )
    command = TOOL_DEFS["fs8_reduced54_stats"]["command_builder"](ctx)
    assert "mri_synthmorph register" not in command
    assert "mri_vol2vol" not in command


def test_fs8_atlas_projection_tool_exists_in_tool_defs():
    from pipeline.registry import TOOL_DEFS

    assert "fs8_mni_atlas_projection" in TOOL_DEFS
    tool = TOOL_DEFS["fs8_mni_atlas_projection"]
    assert tool["stage"] == "stats_extraction"
    assert "mkdayyyy/mri-fs8-all" in tool["image"]
    assert tool["needs_license"] is True
