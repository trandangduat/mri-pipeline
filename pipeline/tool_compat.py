"""Tool-compatibility contracts for Custom-mode pipeline validation.

A selected combination of per-stage tools is runnable only when every enabled
tool's required upstream artifacts are produced by other *enabled* tools in the
chain. Contracts are family-scoped artifact tokens (FastSurfer vs FreeSurfer 7
vs FreeSurfer 8 outputs are NOT interchangeable), derived from the shell
command builders in ``registry`` and kept in sync by drift-guard tests in
``tests/test_tool_compat.py``.
"""

from dataclasses import dataclass

from .presets import PRESET_CONFIGS
from .registry import stage_order_for_tools, tool_display_name

RAW_INPUT = "raw_input"
ORIG_MGZ = "orig_mgz"
NIFTI_VOLUME = "nifti_volume"
CAT12_SEG = "cat12_seg"
SEG_FASTSURFER = "seg_fastsurfer"
SEG_SYNTHSEG_RCA = "seg_synthseg_rca"
SEG_NIFTI = "seg_nifti"
SEG_FS7 = "seg_fs7"
BE_FS7_BRAINMASK = "be_fs7_brainmask"
BE_SYNTHSTRIP_MGZ = "be_synthstrip_mgz"
BE_NIFTI = "be_nifti"
TALAIRACH_XFM = "talairach_xfm"
NU_TALAIRACH = "nu_talairach"
BIAS_NORM_FS = "bias_norm_fs"
WM_FILLED = "wm_filled"
SURFACES_PREAPARC_FS7 = "surfaces_preaparc_fs7"
SURFACES_FINAL = "surfaces_final"
SPHERE_REG = "sphere_reg"
DKT_ANNOTS = "dkt_annots"
STATS_TSVS = "stats_tsvs"
STATS_APARC = "stats_aparc"

TOKEN_LABELS = {
    ORIG_MGZ: "conformed orig.mgz (enable a Reorientation step)",
    NIFTI_VOLUME: "a NIfTI volume from an earlier step",
    CAT12_SEG: "CAT12 segmentation outputs (cat_*.xml / catROI_*.xml)",
    SEG_FASTSURFER: "FastSurfer segmentation outputs (aparc.DKTatlas+aseg.deep.mgz)",
    SEG_SYNTHSEG_RCA: "SynthSeg RCA outputs (synthseg.rca.mgz)",
    SEG_NIFTI: "a standalone NIfTI segmentation",
    SEG_FS7: "FreeSurfer 7 atlas segmentation (aseg.presurf.mgz)",
    BE_FS7_BRAINMASK: "FreeSurfer 7 brain mask (brainmask.mgz)",
    BE_SYNTHSTRIP_MGZ: "SynthStrip skull-stripped volume (synthstrip.mgz)",
    BE_NIFTI: "a skull-stripped NIfTI brain",
    TALAIRACH_XFM: "Talairach transform (transforms/talairach.xfm) from Template Registration",
    NU_TALAIRACH: "nu.mgz intensity-corrected against the Talairach transform",
    BIAS_NORM_FS: "bias-corrected FreeSurfer volumes (norm.mgz / brain.finalsurfs.mgz)",
    WM_FILLED: "white-matter segmentation (wm.mgz / filled.mgz)",
    SURFACES_PREAPARC_FS7: "FreeSurfer 7 pre-parcellation surfaces (lh/rh.white.preaparc)",
    SURFACES_FINAL: "final surfaces (lh/rh.white, lh/rh.pial, thickness)",
    SPHERE_REG: "registered spheres (lh/rh.sphere.reg)",
    DKT_ANNOTS: "DKTatlas mapped annotations (lh/rh.aparc.DKTatlas.mapped.annot)",
    STATS_TSVS: "volume stats tables (subcortical/cortical_volume.tsv)",
    STATS_APARC: "parcellation stats files (lh/rh.aparc.stats)",
}


@dataclass(frozen=True)
class ToolContract:
    requires: frozenset
    produces: frozenset


def _c(requires=(), produces=()):
    return ToolContract(frozenset(requires), frozenset(produces))


# One entry per tool in registry.TOOL_DEFS; drift-guard tests enforce coverage.
TOOL_CONTRACTS = {
    # --- reorientation -----------------------------------------------------
    "fastsurfer_reorientation": _c(produces={ORIG_MGZ}),
    "fs8_reduced54_reorientation": _c(produces={ORIG_MGZ}),
    "fs7_recon_style_reorientation": _c(produces={ORIG_MGZ}),
    "mri_convert_fs7": _c(produces={NIFTI_VOLUME}),
    "nibabel": _c(produces={NIFTI_VOLUME}),
    # --- brain extraction --------------------------------------------------
    "fs8_reduced54_brain_extraction": _c(requires={ORIG_MGZ}, produces={BE_SYNTHSTRIP_MGZ}),
    # fs7 builder consumes transforms/talairach.xfm -> only valid when the
    # fs7 recon-style order puts template_registration first.
    "fs7_recon_style_brain_extraction": _c(
        requires={ORIG_MGZ, TALAIRACH_XFM}, produces={BE_FS7_BRAINMASK}
    ),
    # Accepts any chained volume, including the raw NIfTI input.
    "synthstrip_fs7": _c(produces={BE_NIFTI}),
    "hdbet": _c(produces={BE_NIFTI}),
    # --- segmentation ------------------------------------------------------
    "cat12_volume_segmentation": _c(produces={CAT12_SEG}),
    "cat12_full_segmentation": _c(produces={CAT12_SEG}),
    "fastsurfer_segmentation": _c(requires={ORIG_MGZ}, produces={SEG_FASTSURFER}),
    "fs8_reduced54_segmentation": _c(requires={ORIG_MGZ}, produces={SEG_SYNTHSEG_RCA}),
    # Dual-mode: runs in-subject when orig.mgz exists, else standalone NIfTI.
    "synthseg_freesurfer_fs8": _c(produces={SEG_SYNTHSEG_RCA, SEG_NIFTI, STATS_TSVS}),
    "synthseg_freesurfer_fs7": _c(produces={SEG_NIFTI, STATS_TSVS}),
    "synthseg_standalone": _c(produces={SEG_NIFTI}),
    "fastsurfervinn": _c(produces={SEG_NIFTI}),
    "fs7_recon_style_segmentation": _c(requires={BE_FS7_BRAINMASK}, produces={SEG_FS7}),
    # --- template registration ----------------------------------------------
    "fastsurfer_template_registration": _c(
        requires={ORIG_MGZ, SEG_FASTSURFER},
        produces={TALAIRACH_XFM, NU_TALAIRACH},
    ),
    # fs-synthmorph-reg consumes synthstrip.mgz -> needs Brain Extraction.
    "fs8_reduced54_template_registration": _c(
        requires={BE_SYNTHSTRIP_MGZ}, produces={TALAIRACH_XFM}
    ),
    "fs7_recon_style_template_registration": _c(
        requires={ORIG_MGZ}, produces={TALAIRACH_XFM, NU_TALAIRACH}
    ),
    # --- bias correction ----------------------------------------------------
    "fastsurfer_standardization": _c(
        requires={SEG_FASTSURFER, NU_TALAIRACH}, produces={BIAS_NORM_FS}
    ),
    "ants_n4": _c(produces={NIFTI_VOLUME}),
    "fs8_reduced54_bias_correction": _c(
        requires={ORIG_MGZ, BE_SYNTHSTRIP_MGZ, TALAIRACH_XFM, SEG_SYNTHSEG_RCA},
        produces={BIAS_NORM_FS},
    ),
    "fs7_recon_style_bias_correction": _c(
        requires={BE_FS7_BRAINMASK, SEG_FS7}, produces={BIAS_NORM_FS}
    ),
    # --- white matter segmentation -------------------------------------------
    "fastsurfer_wm_segmentation": _c(
        requires={SEG_FASTSURFER, BIAS_NORM_FS}, produces={WM_FILLED}
    ),
    "fs8_reduced54_wm_segmentation": _c(
        requires={BIAS_NORM_FS, SEG_SYNTHSEG_RCA}, produces={WM_FILLED}
    ),
    "fs7_recon_style_wm_segmentation": _c(
        requires={BIAS_NORM_FS, SEG_FS7}, produces={WM_FILLED}
    ),
    "mri_binarize": _c(produces={"wm_nifti"}),
    # --- surface reconstruction ----------------------------------------------
    "fastsurfer_surface_reconstruction": _c(
        requires={WM_FILLED, BIAS_NORM_FS, SEG_FASTSURFER},
        produces={SURFACES_FINAL, DKT_ANNOTS},
    ),
    "fs8_reduced54_surface_reconstruction": _c(
        requires={WM_FILLED, BIAS_NORM_FS, SEG_SYNTHSEG_RCA},
        produces={SURFACES_FINAL},
    ),
    "fs7_recon_style_surface_reconstruction": _c(
        requires={WM_FILLED, BIAS_NORM_FS, SEG_FS7},
        produces={SURFACES_PREAPARC_FS7},
    ),
    # Self-healing input chain (falls back to raw input); permissive by design.
    "recon_all_fs7": _c(produces={SURFACES_FINAL}),
    "corticalflow": _c(produces={SURFACES_FINAL}),
    # --- surface registration -------------------------------------------------
    "fastsurfer_surface_registration": _c(
        requires={SURFACES_FINAL, DKT_ANNOTS}, produces={SPHERE_REG}
    ),
    "fs8_reduced54_surface_registration": _c(
        requires={SURFACES_FINAL}, produces={SPHERE_REG}
    ),
    "fs7_recon_style_surface_registration": _c(
        requires={SURFACES_PREAPARC_FS7}, produces={SPHERE_REG}
    ),
    # Stage is surface_registration but it emits parcellation stats files.
    "surface_stats_fs7": _c(
        requires={SURFACES_FINAL, SPHERE_REG}, produces={STATS_APARC}
    ),
    # Reads any FS-family white/pial under the shared SUBJECTS_DIR.
    "sugar": _c(requires={SURFACES_FINAL}, produces={SPHERE_REG}),
    # --- stats extraction -------------------------------------------------------
    "cat12_volume_stats_extraction": _c(requires={CAT12_SEG}, produces={STATS_TSVS}),
    "cat12_full_stats_extraction": _c(requires={CAT12_SEG}, produces={STATS_TSVS}),
    "fastsurfer_stats_extraction": _c(
        requires={SURFACES_FINAL, SPHERE_REG, DKT_ANNOTS},
        produces={STATS_TSVS, STATS_APARC},
    ),
    "fastsurfer_volume_stats_extraction": _c(
        requires={ORIG_MGZ, SEG_FASTSURFER}, produces={STATS_TSVS}
    ),
    # Needs norm.mgz for MNI projection; atlas products are optional extras.
    "fs8_mni_atlas_projection": _c(requires={BIAS_NORM_FS}, produces=set()),
    # Volume-only branch is the minimal requirement; the cortical-thickness
    # branch additionally needs surfaces at runtime (accepted limitation).
    "fs8_reduced54_stats": _c(requires={SEG_SYNTHSEG_RCA}, produces={STATS_TSVS, STATS_APARC}),
    "fs7_recon_style_stats": _c(
        requires={SURFACES_PREAPARC_FS7, WM_FILLED, BIAS_NORM_FS, SEG_FS7},
        produces={STATS_TSVS, STATS_APARC},
    ),
    "fs7_recon_style_subcortical_stats": _c(requires={SEG_FS7}, produces={STATS_TSVS}),
    # Pure checker: requires tsvs already produced by earlier steps.
    "freesurfer_stats_fs7": _c(requires={STATS_TSVS}, produces={STATS_TSVS}),
}


def _nonempty_tools(selected_tools) -> dict:
    return {
        str(stage): str(tool).strip()
        for stage, tool in (selected_tools or {}).items()
        if str(tool or "").strip()
    }


def _matches_named_preset(tools: dict) -> bool:
    if not tools:
        return False
    for config in PRESET_CONFIGS.values():
        if _nonempty_tools(config.get("tools")) == tools:
            return True
    return False


def validate_tool_combo(selected_tools) -> list:
    """Validate a Custom-mode tool selection.

    Returns a list of violation dicts:
      {"stage", "tool", "reason", "missing"} — empty list means valid.
    Named presets (exact tool-map matches) are valid by construction.
    Disabled intermediate stages bypass cleanly: requirements are satisfied
    from the union of all enabled upstream producers, mirroring how
    ``run_pipeline`` chains ``input_for_next_step`` across skipped stages.
    """
    tools = _nonempty_tools(selected_tools)
    if not tools:
        return [
            {
                "stage": "*",
                "tool": "",
                "reason": "No pipeline steps selected.",
                "missing": [],
            }
        ]
    if _matches_named_preset(tools):
        return []

    available = {RAW_INPUT}
    violations = []
    for stage in stage_order_for_tools(tools):
        tool_key = tools.get(stage)
        if not tool_key:
            continue
        contract = TOOL_CONTRACTS.get(tool_key)
        if contract is None:
            violations.append(
                {
                    "stage": stage,
                    "tool": tool_key,
                    "reason": f"{tool_display_name(tool_key) or tool_key} has no compatibility contract.",
                    "missing": [],
                }
            )
            continue
        missing = sorted(contract.requires - available)
        if missing:
            labels = ", ".join(TOKEN_LABELS.get(token, token) for token in missing)
            violations.append(
                {
                    "stage": stage,
                    "tool": tool_key,
                    "reason": (
                        f"{tool_display_name(tool_key) or tool_key} cannot run: "
                        f"the selection does not produce {labels}."
                    ),
                    "missing": missing,
                }
            )
            continue
        available |= set(contract.produces)
    return violations


def tool_contracts_payload() -> dict:
    """JSON-ready contracts for the /metadata endpoint."""
    return {
        tool_key: {
            "requires": sorted(contract.requires),
            "produces": sorted(contract.produces),
        }
        for tool_key, contract in TOOL_CONTRACTS.items()
    }
