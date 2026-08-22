import pytest

from pipeline.presets import PRESET_CONFIGS
from pipeline.registry import TOOL_DEFS, enabled_tools_for_stage
from pipeline.tool_compat import (
    ORIG_MGZ,
    STATS_TSVS,
    SURFACES_PREAPARC_FS7,
    TOOL_CONTRACTS,
    TALAIRACH_XFM,
    tool_contracts_payload,
    validate_tool_combo,
)


def _full_map(**overrides):
    tools = {stage: "" for stage in [
        "reorientation",
        "brain_extraction",
        "segmentation",
        "template_registration",
        "bias_correction",
        "white_matter_segmentation",
        "surface_reconstruction",
        "surface_registration",
        "stats_extraction",
    ]}
    tools.update(overrides)
    return tools


@pytest.mark.parametrize("mode", sorted(PRESET_CONFIGS))
def test_every_named_preset_validates_clean(mode):
    assert validate_tool_combo(PRESET_CONFIGS[mode]["tools"]) == []


def test_every_registered_tool_has_contract():
    visible_or_preset = set()
    for stage in TOOL_DEFS and {tool["stage"] for tool in TOOL_DEFS.values()}:
        visible_or_preset.update(enabled_tools_for_stage(stage))
    hidden = {
        key
        for key, tool in TOOL_DEFS.items()
        if tool.get("hidden_from_stage_select") or tool.get("hidden_from_tool_list")
    }
    expected = visible_or_preset | hidden | set(PRESET_CONFIGS["FreeSurfer 8 + Volume"]["tools"].values())
    missing = {key for key in expected if key} - set(TOOL_CONTRACTS)
    assert not missing, f"tools without contracts: {sorted(missing)}"


def test_empty_selection_is_violation():
    violations = validate_tool_combo({})
    assert len(violations) == 1
    assert violations[0]["stage"] == "*"


def test_known_bad_fs7_stats_without_surfaces():
    tools = _full_map(
        reorientation="fs7_recon_style_reorientation",
        brain_extraction="fs7_recon_style_brain_extraction",
        segmentation="fs7_recon_style_segmentation",
        template_registration="fs7_recon_style_template_registration",
        bias_correction="fs7_recon_style_bias_correction",
        white_matter_segmentation="fs7_recon_style_wm_segmentation",
        stats_extraction="fs7_recon_style_stats",
    )
    violations = validate_tool_combo(tools)
    assert [v["stage"] for v in violations] == ["stats_extraction"]
    assert SURFACES_PREAPARC_FS7 in violations[0]["missing"]


def test_disabling_fs7_template_cascades():
    tools = _full_map(
        reorientation="fs7_recon_style_reorientation",
        brain_extraction="fs7_recon_style_brain_extraction",
        segmentation="fs7_recon_style_segmentation",
        template_registration="",
        bias_correction="fs7_recon_style_bias_correction",
        white_matter_segmentation="fs7_recon_style_wm_segmentation",
        surface_reconstruction="fs7_recon_style_surface_reconstruction",
        surface_registration="fs7_recon_style_surface_registration",
        stats_extraction="fs7_recon_style_stats",
    )
    stages = [v["stage"] for v in validate_tool_combo(tools)]
    # talairach.xfm lost -> brain extraction fails -> everything downstream cascades.
    assert stages == [
        "brain_extraction",
        "segmentation",
        "bias_correction",
        "white_matter_segmentation",
        "surface_reconstruction",
        "surface_registration",
        "stats_extraction",
    ]
    first = validate_tool_combo(tools)[0]
    assert TALAIRACH_XFM in first["missing"]


def test_fs8_template_registration_needs_brain_extraction():
    tools = _full_map(
        reorientation="fs8_reduced54_reorientation",
        segmentation="synthseg_freesurfer_fs8",
        template_registration="fs8_reduced54_template_registration",
    )
    violations = validate_tool_combo(tools)
    assert [v["stage"] for v in violations] == ["template_registration"]


def test_fastsurfer_stats_without_surface_registration():
    tools = _full_map(
        reorientation="fastsurfer_reorientation",
        segmentation="fastsurfer_segmentation",
        template_registration="fastsurfer_template_registration",
        bias_correction="fastsurfer_standardization",
        white_matter_segmentation="fastsurfer_wm_segmentation",
        surface_reconstruction="fastsurfer_surface_reconstruction",
        stats_extraction="fastsurfer_stats_extraction",
    )
    violations = validate_tool_combo(tools)
    assert [v["stage"] for v in violations] == ["stats_extraction"]


def test_cross_family_stats_hazard():
    tools = _full_map(
        reorientation="fastsurfer_reorientation",
        segmentation="fastsurfer_segmentation",
        stats_extraction="fs8_reduced54_stats",
    )
    violations = validate_tool_combo(tools)
    assert violations
    assert any(v["stage"] == "stats_extraction" for v in violations)


def test_nifti_chain_known_good():
    tools = _full_map(
        reorientation="mri_convert_fs7",
        brain_extraction="hdbet",
        segmentation="synthseg_freesurfer_fs7",
        stats_extraction="freesurfer_stats_fs7",
    )
    assert validate_tool_combo(tools) == []


def test_custom_map_equal_to_preset_short_circuits():
    tools = dict(PRESET_CONFIGS["FastSurfer + Volume"]["tools"])
    assert validate_tool_combo(tools) == []


def test_contract_payload_shape():
    payload = tool_contracts_payload()
    entry = payload["fastsurfer_reorientation"]
    assert ORIG_MGZ in entry["produces"]
    assert isinstance(entry["requires"], list)


def test_produces_tokens_groundable_in_registry_outputs():
    """Drift guard: every produces token must still be derivable from declared outputs."""
    grounding = {
        "orig_mgz": ("fastsurfer_reorientation", "orig.mgz"),
        "nifti_volume": ("mri_convert_fs7", "01_reoriented.nii.gz"),
        "be_synthstrip_mgz": ("fs8_reduced54_brain_extraction", "synthstrip.mgz"),
        "be_fs7_brainmask": ("fs7_recon_style_brain_extraction", "brainmask.mgz"),
        "be_nifti": ("hdbet", "02_hdbet_brain.nii.gz"),
        "cat12_seg": ("cat12_volume_segmentation", "cat_"),
        "seg_fastsurfer": ("fastsurfer_segmentation", "aseg.auto.mgz"),
        "seg_synthseg_rca": ("fs8_reduced54_segmentation", "synthseg.rca.mgz"),
        "seg_nifti": ("synthseg_standalone", "03_synthseg_standalone_segmentation.nii.gz"),
        "seg_fs7": ("fs7_recon_style_segmentation", "aseg.presurf.mgz"),
        "talairach_xfm": ("fastsurfer_template_registration", "talairach.lta"),
        "nu_talairach": ("fs7_recon_style_template_registration", "orig_nu.mgz"),
        "bias_norm_fs": ("fastsurfer_standardization", "norm.mgz"),
        "wm_filled": ("fastsurfer_wm_segmentation", "wm.mgz"),
        "wm_nifti": ("mri_binarize", "06_wm_mask.nii.gz"),
        "surfaces_preaparc_fs7": ("fs7_recon_style_surface_reconstruction", "lh.white.preaparc"),
        "surfaces_final": ("fastsurfer_surface_reconstruction", "lh.thickness"),
        "sphere_reg": ("fastsurfer_surface_registration", "lh.sphere.reg"),
        # dkt_annots intentionally omitted: produced inside the stage-7 builder
        # (sample_parc.py) but not declared as a registry output glob.
        "stats_tsvs": ("fastsurfer_volume_stats_extraction", "subcortical_volume.tsv"),
        "stats_aparc": ("fs7_recon_style_stats", "lh.aparc.stats"),
    }
    for token, (tool_key, fragment) in grounding.items():
        tool = TOOL_DEFS[tool_key]
        declared = list(tool.get("output_files", [])) + list(tool.get("output_globs", []))
        assert any(fragment in item for item in declared), f"token {token} no longer produced by {tool_key}"


def test_volume_tsvs_requirement_via_checker():
    tools = _full_map(stats_extraction="freesurfer_stats_fs7")
    violations = validate_tool_combo(tools)
    assert violations
    assert STATS_TSVS in violations[0]["missing"]
