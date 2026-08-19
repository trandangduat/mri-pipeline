from __future__ import annotations

from pipeline.config import ToolContext
from pipeline.presets import FREESURFER_8_SURFACE_TOOLS, FREESURFER_8_VOLUME_TOOLS, PRESET_CONFIGS
from pipeline.registry import (
    FREESURFER_RECON_STYLE_TIMEOUT,
    STAGE_ORDER,
    TOOL_DEFS,
    enabled_tools_for_stage,
    thickness_atlas_stats_stems,
    tool_display_name,
    tool_key_from_display,
)


def test_freesurfer8_surface_presets_use_surface_tools() -> None:
    expected_tools = {
        "reorientation": "fs8_reduced54_reorientation",
        "brain_extraction": "fs8_reduced54_brain_extraction",
        "segmentation": "synthseg_freesurfer_fs8",
        "template_registration": "fs8_reduced54_template_registration",
        "bias_correction": "fs8_reduced54_bias_correction",
        "white_matter_segmentation": "fs8_reduced54_wm_segmentation",
        "surface_reconstruction": "fs8_reduced54_surface_reconstruction",
        "surface_registration": "fs8_reduced54_surface_registration",
        "stats_extraction": "fs8_reduced54_stats",
    }

    assert FREESURFER_8_SURFACE_TOOLS == expected_tools
    assert PRESET_CONFIGS["FreeSurfer 8 + Cortical Thickness"]["tools"] == expected_tools
    assert PRESET_CONFIGS["FreeSurfer 8 + Volume + Cortical Thickness"]["tools"] == expected_tools


def test_freesurfer8_volume_preset_blanks_surface_stages() -> None:
    assert PRESET_CONFIGS["FreeSurfer 8 + Volume"]["tools"] == FREESURFER_8_VOLUME_TOOLS
    assert FREESURFER_8_VOLUME_TOOLS["reorientation"] == "fs8_reduced54_reorientation"
    assert FREESURFER_8_VOLUME_TOOLS["segmentation"] == "synthseg_freesurfer_fs8"
    assert FREESURFER_8_VOLUME_TOOLS["stats_extraction"] == "fs8_reduced54_stats"
    for stage in ("brain_extraction", "template_registration", "bias_correction", "white_matter_segmentation", "surface_reconstruction", "surface_registration"):
        assert FREESURFER_8_VOLUME_TOOLS[stage] == "", f"{stage} should be blank for volume-only preset"


def test_freesurfer8_surface_tools_cover_all_pipeline_stages() -> None:
    for stage in STAGE_ORDER:
        tool_key = FREESURFER_8_SURFACE_TOOLS[stage]
        tool = TOOL_DEFS[tool_key]
        assert tool["stage"] == stage
        assert tool["image"] == "mkdayyyy/mri-fs8-all:latest"
        assert tool["needs_license"] is True
        assert callable(tool["command_builder"])
        assert tool["output_files"] or tool.get("output_globs")


def test_freesurfer8_surface_outputs_are_pipeline_markers() -> None:
    assert TOOL_DEFS["fs8_reduced54_surface_reconstruction"]["output_globs"] == [
        "freesurfer/*/surf/lh.thickness",
        "freesurfer/*/surf/rh.thickness",
    ]
    assert TOOL_DEFS["fs8_reduced54_surface_registration"]["output_globs"] == [
        "freesurfer/*/surf/lh.sphere.reg",
        "freesurfer/*/surf/rh.sphere.reg",
    ]
    assert TOOL_DEFS["fs8_reduced54_stats"]["output_files"] == [
        "lh.aparc.stats",
        "rh.aparc.stats",
        "aseg.stats",
        "subcortical_volume.tsv",
        "cortical_volume.tsv",
        *[
            f"{hemi}.{stem}.stats"
            for stem in thickness_atlas_stats_stems()
            for hemi in ("lh", "rh")
        ],
    ]


def test_freesurfer8_long_surface_stages_use_recon_style_timeout() -> None:
    for tool_key in (
        "fs8_reduced54_bias_correction",
        "fs8_reduced54_wm_segmentation",
        "fs8_reduced54_surface_reconstruction",
        "fs8_reduced54_surface_registration",
    ):
        assert TOOL_DEFS[tool_key]["timeout"] == FREESURFER_RECON_STYLE_TIMEOUT


def test_freesurfer8_surface_tool_names_do_not_expose_reduced54() -> None:
    selected_tool_names = [tool_display_name(tool) for tool in FREESURFER_8_SURFACE_TOOLS.values()]
    assert all("Reduced54" not in name for name in selected_tool_names)
    assert "FreeSurfer 8 SynthSeg" in selected_tool_names
    assert "fs8_reduced54_segmentation" not in enabled_tools_for_stage("segmentation")


def test_old_freesurfer8_tools_are_removed() -> None:
    removed_tool_keys = {
        "mri_convert_fs8",
        "synthstrip_fs8",
        "synthmorph_fs8",
        "mri_binarize_fs8",
        "recon_all_fs8",
        "surface_stats_fs8",
        "freesurfer_stats_fs8",
    }
    assert removed_tool_keys.isdisjoint(TOOL_DEFS)


def test_freesurfer8_volume_synthseg_uses_parc() -> None:
    command = TOOL_DEFS["synthseg_freesurfer_fs8"]["command_builder"](
        ToolContext(
            input_path="/input.nii",
            subject_id="subj",
            threads=4,
            device="cpu",
            enabled_stats={"cortical_volume": True, "subcortical_volume": True, "cortical_thickness": False},
        )
    )

    assert "--keepgeom --addctab --parc --cpu" in command


def test_freesurfer8_bias_correction_matches_reduced54_stage5() -> None:
    command = TOOL_DEFS["fs8_reduced54_bias_correction"]["command_builder"](
        ToolContext(
            input_path="/input.nii",
            subject_id="subj",
            threads=4,
            device="cpu",
            enabled_stats={"cortical_volume": True, "subcortical_volume": True, "cortical_thickness": True},
        )
    )

    assert "mri_ca_normalize" in command
    assert "mri_ca_register" not in command
    assert "mri_normalize -seed 1234 -mprage -aseg aseg.presurf.mgz" in command


def test_freesurfer8_template_registration_matches_recon_all_synthmorph() -> None:
    command = TOOL_DEFS["fs8_reduced54_template_registration"]["command_builder"](
        ToolContext(input_path="/input.nii", subject_id="subj", threads=4, device="cpu")
    )

    assert 'fs-synthmorph-reg --i synthstrip.mgz --t "$MNI305" --affine-only' in command
    assert 'lta_convert --ltavox2vox --inlta transforms/synthmorph.mni305/aff.lta' in command
    assert 'fs-synthmorph-reg --s "$SUBJ" --threads 4 --i "$SD/mri/orig.mgz" --test' in command
    assert "warp.to.mni152.1.0mm.1.0mm.inv.nii.gz" in command


def test_freesurfer8_stats_stage_includes_a2009s_when_thickness_enabled() -> None:
    command = TOOL_DEFS["fs8_reduced54_stats"]["command_builder"](
        ToolContext(
            input_path="/input.nii",
            subject_id="subj",
            threads=4,
            device="cpu",
            enabled_stats={"cortical_volume": True, "subcortical_volume": True, "cortical_thickness": True},
        )
    )

    assert "destrieux/lh.destrieux.simple.2009-07-29.gcs" in command
    assert "lh.aparc.a2009s.annot" in command
    assert "lh.aparc.a2009s.stats" in command
    assert "rh.aparc.a2009s.stats" in command
    assert "LH_DK_ATLAS" in command
    assert "lh.aparc.annot" in command


def test_freesurfer8_stats_stage_includes_asset_atlases_when_thickness_enabled() -> None:
    command = TOOL_DEFS["fs8_reduced54_stats"]["command_builder"](
        ToolContext(
            input_path="/input.nii",
            subject_id="subj",
            threads=4,
            device="cpu",
            enabled_stats={
                "cortical_volume": True,
                "subcortical_volume": True,
                "cortical_thickness": True,
                "selected_atlases": ["aparc", "aparc_a2009s", "yale", "kong", "schaefer2018_400parcels_17networks"],
            },
        )
    )

    assert "/atlas-assets" in command
    assert "lh.YBA_696parcels.annot" in command
    assert "lh.YBA_696parcels.stats" in command
    assert "YBA_696_LH_fsaverage_new.annot" in command
    assert "200Parcels_Kong2022_17Networks" in command
    assert "lh.schaefer400_17network.stats" in command
    assert "Schaefer2018_400Parcels_17Networks.gcs" in command
    assert "mri_surf2surf --srcsubject fsaverage" in command
    assert "mris_ca_label" in command


def test_freesurfer8_stats_stage_skips_a2009s_when_volume_only() -> None:
    command = TOOL_DEFS["fs8_reduced54_stats"]["command_builder"](
        ToolContext(
            input_path="/input.nii",
            subject_id="subj",
            threads=4,
            device="cpu",
            enabled_stats={"cortical_volume": True, "subcortical_volume": True, "cortical_thickness": False},
        )
    )

    assert "A2009S" not in command
    assert "YBA_696parcels" not in command


def test_freesurfer7_surface_stats_loop_covers_extra_atlases() -> None:
    command = TOOL_DEFS["surface_stats_fs7"]["command_builder"](
        ToolContext(
            input_path="/input.nii",
            subject_id="subj",
            threads=4,
            device="cpu",
            enabled_stats={
                "cortical_thickness": True,
                "selected_atlases": ["aparc", "aparc_a2009s", "yale", "kong", "schaefer2018_400parcels_17networks"],
            },
        )
    )

    assert "surf2surf" in command
    assert "YBA_696parcels" in command
    assert "200Parcels_Kong2022_17Networks" in command
    assert "schaefer2018_400parcels_17networks" in command
    assert "destrieux.simple" in command
    assert "YA2009S_ATLAS" not in command
    assert 'cp "$SUBJECTS_DIR/subj/stats/"*.stats /output/stats/' in command
    assert "test -s /output/stats/lh.aparc.stats" in command


def test_freesurfer7_surface_stats_skips_aparc_ca_label() -> None:
    command = TOOL_DEFS["surface_stats_fs7"]["command_builder"](
        ToolContext(
            input_path="/input.nii",
            subject_id="subj",
            threads=4,
            device="cpu",
            enabled_stats={"cortical_thickness": True, "selected_atlases": ["aparc"]},
        )
    )

    assert "aparc.annot" not in command
    assert "test -s /output/stats/lh.aparc.stats" in command


def test_fastsurfer_stats_stage_includes_extra_thickness_atlases() -> None:
    command = TOOL_DEFS["fastsurfer_stats_extraction"]["command_builder"](
        ToolContext(
            input_path="/input.nii",
            subject_id="subj",
            threads=4,
            device="cpu",
            enabled_stats={
                "cortical_thickness": True,
                "selected_atlases": ["aparc", "aparc_a2009s", "yale", "schaefer2018_400parcels_17networks"],
            },
        )
    )

    assert "/atlas-assets" in command
    assert "YBA_696parcels" in command
    assert "schaefer2018_400parcels_17networks" in command
    assert "destrieux.simple" in command
    assert "DKTatlas.mapped.annot" in command


def test_fastsurfer_stats_stage_runs_full_aparc_and_asset_a2009s() -> None:
    command = TOOL_DEFS["fastsurfer_stats_extraction"]["command_builder"](
        ToolContext(
            input_path="/input.nii",
            subject_id="subj",
            threads=4,
            device="cpu",
            enabled_stats={
                "cortical_thickness": True,
                "selected_atlases": ["aparc", "aparc_a2009s"],
            },
        )
    )

    assert "mris_ca_label" in command
    assert "lh.aparc.stats" in command
    assert "LH_DK_ATLAS" in command
    assert "destrieux/lh.destrieux.simple.2009-07-29.gcs" in command
    assert "lh.aparc.a2009s.stats" in command
    assert "rh.aparc.a2009s.stats" in command


def test_kong_feats_exclude_medial_wall() -> None:
    from pipeline.stats import _load_vector_features

    lines = _load_vector_features("200Parcels_Kong2022_17Networks_feats.txt")
    assert len(lines) == 200
    assert not any("Medial_Wall" in line for line in lines)


def test_skipped_display_value_maps_to_no_tool() -> None:
    assert tool_key_from_display("Skipped") == ""


def test_thickness_atlas_feature_lists_present():
    from pipeline.registry import THICKNESS_ATLAS_DEFS
    from pipeline.config import PROJECT_ROOT
    from pipeline.stats import VECTOR_SPECS
    info = PROJECT_ROOT / "info"
    for key, defn in THICKNESS_ATLAS_DEFS.items():
        spec = VECTOR_SPECS.get(key)
        assert spec, f"missing vector spec for atlas {key}"
        feats = info / str(spec["features"])
        assert feats.exists(), f"missing feature list {feats.name} for atlas {key}"
        lines = [l.strip() for l in feats.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert lines, f"empty feature list {feats.name}"
