from __future__ import annotations

import shlex

from .config import SURFACE_ATLAS_STEMS, ToolContext

SURFACE_STATS_ATLAS_LIST = " ".join(SURFACE_ATLAS_STEMS)

FS8_REDUCED54_IMAGE = "mkdayyyy/mri-fs8-all:latest"
FS7_RECON_STYLE_IMAGE = "mkdayyyy/mri-fs7-all:latest"


def _q(value: str) -> str:
    return shlex.quote(str(value))


def _fs8r_common(ctx: ToolContext) -> str:
    subject = _q(ctx.subject_id)
    return (
        "set -e; "
        "export SUBJECTS_DIR=/output/freesurfer; "
        f"SUBJ={subject}; "
        "SD=\"$SUBJECTS_DIR/$SUBJ\"; "
        "mkdir -p \"$SD\"/mri \"$SD\"/surf \"$SD\"/label \"$SD\"/stats \"$SD\"/tmp \"$SD\"/scripts \"$SD/mri/transforms\" /output/stats; "
        "if [ -L \"$SUBJECTS_DIR/fsaverage\" ]; then rm \"$SUBJECTS_DIR/fsaverage\"; fi; "
        "if [ ! -e \"$SUBJECTS_DIR/fsaverage\" ] && [ -d \"$FREESURFER_HOME/subjects/fsaverage\" ]; then ln -s \"$FREESURFER_HOME/subjects/fsaverage\" \"$SUBJECTS_DIR/fsaverage\"; fi; "
        "GCA=\"$FREESURFER_HOME/average/RB_all_2020-01-02.gca\"; "
        "MNI305=\"$FREESURFER_HOME/average/mni305.cor.mgz\"; "
        "if [ -f \"$FREESURFER_HOME/average/mni305.cor.stripped.mgz\" ]; then MNI305=\"$FREESURFER_HOME/average/mni305.cor.stripped.mgz\"; fi; "
        "cd \"$SD/mri\"; "
    )


def _fs8r_sync_aliases() -> str:
    return (
        "if [ -f synthseg.rca.mgz ]; then "
        "ln -sf synthseg.rca.mgz aseg.auto.mgz; "
        "ln -sf synthseg.rca.mgz aseg.auto_noCCseg.mgz; "
        "ln -sf synthseg.rca.mgz aseg.presurf.mgz; "
        "fi; "
    )


def _fs8r_atlas_lookup() -> str:
    return (
        "first_existing() { for pattern in \"$@\"; do for match in $pattern; do [ -f \"$match\" ] && printf '%s\\n' \"$match\" && return 0; done; done; return 1; }; "
        "LH_FOLDING_ATLAS=$(first_existing \"$FREESURFER_HOME/average/lh.folding.atlas.acfb40.noaparc.i12*.tif\" \"$FREESURFER_HOME/average/lh.folding.atlas*.tif\") || { echo Missing lh folding atlas; exit 1; }; "
        "RH_FOLDING_ATLAS=$(first_existing \"$FREESURFER_HOME/average/rh.folding.atlas.acfb40.noaparc.i12*.tif\" \"$FREESURFER_HOME/average/rh.folding.atlas*.tif\") || { echo Missing rh folding atlas; exit 1; }; "
        "LH_DK_ATLAS=$(first_existing \"$FREESURFER_HOME/average/lh.DKaparc.atlas.acfb40.noaparc.i12*.gcs\" \"$FREESURFER_HOME/average/lh.DKaparc.atlas*.gcs\") || { echo Missing lh DKaparc atlas; exit 1; }; "
        "RH_DK_ATLAS=$(first_existing \"$FREESURFER_HOME/average/rh.DKaparc.atlas.acfb40.noaparc.i12*.gcs\" \"$FREESURFER_HOME/average/rh.DKaparc.atlas*.gcs\") || { echo Missing rh DKaparc atlas; exit 1; }; "
    )


def _fs8r_stage1(ctx: ToolContext) -> str:
    dicom_flags = ""
    if ctx.dicom_list_path:
        dicom_flags = f"-no-dcm2niix -dicomread2 --sdcmlist {_q(ctx.dicom_list_path)} "
    return (
        _fs8r_common(ctx)
        + f"mri_convert {dicom_flags}{_q(ctx.input_path)} 001.mgz; "
        "mri_convert 001.mgz orig.mgz --conform; "
        "test -s orig.mgz"
    )


def _fs8r_stage2(ctx: ToolContext) -> str:
    return _fs8r_common(ctx) + f"mri_synthstrip --threads {ctx.threads} -i orig.mgz -o synthstrip.mgz; test -s synthstrip.mgz"


def _fs8r_stage3(ctx: ToolContext) -> str:
    return (
        _fs8r_common(ctx)
        + f"mri_synthseg --i orig.mgz --o synthseg.rca.mgz --threads {ctx.threads} --vol synthseg.vol.csv --keepgeom --addctab --cpu; "
        + _fs8r_sync_aliases()
        + "test -s synthseg.rca.mgz"
    )


def _fs8_synthseg(ctx: ToolContext) -> str:
    subject = _q(ctx.subject_id)
    input_path = _q(ctx.input_path)
    cpu_flag = "--cpu" if ctx.device == "cpu" else ""
    volume_parc_flag = " --parc" if not ctx.enabled_stats.get("cortical_thickness", False) else ""
    return (
        "set -e; "
        "export SUBJECTS_DIR=/output/freesurfer; "
        f"SUBJ={subject}; "
        "SD=\"$SUBJECTS_DIR/$SUBJ\"; "
        "if [ -s \"$SD/mri/orig.mgz\" ]; then "
        "cd \"$SD/mri\"; "
        f"mri_synthseg --i orig.mgz --o synthseg.rca.mgz --threads {ctx.threads} --vol synthseg.vol.csv --keepgeom --addctab{volume_parc_flag} --cpu; "
        + _fs8r_sync_aliases()
        + "test -s synthseg.rca.mgz; "
        "else "
        f"mri_synthseg --i {input_path} --o /work/03_freesurfer_synthseg_segmentation.nii.gz "
        f"--vol /work/03_freesurfer_synthseg_volumes.csv --parc --threads {ctx.threads} --crop 160 {cpu_flag}; "
        "python3 /app/normalize_volumes.py /work/03_freesurfer_synthseg_volumes.csv "
        f"/output/stats/subcortical_volume.tsv /output/stats/cortical_volume.tsv {subject} FreeSurferSynthSeg; "
        "fi"
    )


def _fs8r_stage4(ctx: ToolContext) -> str:
    return (
        _fs8r_common(ctx)
        + f"fs-synthmorph-reg --i synthstrip.mgz --t \"$MNI305\" --affine-only --o transforms/synthmorph.mni305 --threads {ctx.threads}; "
        "for candidate in transforms/synthmorph.mni305/aff.lta transforms/synthmorph.mni305/*aff*.lta; do if [ -f \"$candidate\" ]; then cp \"$candidate\" transforms/aff.lta; break; fi; done; "
        "if [ ! -s transforms/aff.lta ]; then lta_convert --inlta identity.nofile --src orig.mgz --trg orig.mgz --outlta transforms/aff.lta --subject \"$SUBJ\"; fi; "
        "lta_convert --inlta transforms/aff.lta --outmni transforms/talairach.xfm --src synthstrip.mgz --trg \"$MNI305\" || cp transforms/aff.lta transforms/talairach.xfm; "
        "lta_convert --inlta transforms/aff.lta --outlta transforms/talairach.lta --src synthstrip.mgz --trg \"$MNI305\"; "
        "test -s transforms/talairach.lta"
    )


def _fs8r_stage5(ctx: ToolContext) -> str:
    return (
        _fs8r_common(ctx)
        + _fs8r_sync_aliases()
        + "mri_nu_correct.mni --i orig.mgz --o nu.mgz --uchar transforms/talairach.xfm --n 2 --ants-n4; "
        "mri_add_xform_to_header -c transforms/talairach.xfm nu.mgz nu.mgz; "
        "mri_normalize -g 1 -seed 1234 -mprage nu.mgz T1.mgz; "
        "mri_mask T1.mgz synthstrip.mgz brainmask.mgz; "
        "mri_em_register -uns 3 -mask brainmask.mgz nu.mgz \"$GCA\" transforms/talairach.lta; "
        "mri_ca_normalize -c ctrl_pts.mgz -mask brainmask.mgz nu.mgz \"$GCA\" transforms/talairach.lta norm.mgz; "
        "mri_normalize -seed 1234 -mprage -aseg aseg.presurf.mgz -mask brainmask.mgz norm.mgz brain.mgz; "
        "AntsDenoiseImageFs -i brain.mgz -o antsdn.brain.mgz; "
        "mri_mask -T 5 brain.mgz brainmask.mgz brain.finalsurfs.mgz; "
        "test -s brain.finalsurfs.mgz"
    )


def _fs8r_stage6(ctx: ToolContext) -> str:
    return (
        _fs8r_common(ctx)
        + _fs8r_sync_aliases()
        + "mri_segment -wsizemm 13 -mprage antsdn.brain.mgz wm.seg.mgz; "
        "mri_edit_wm_with_aseg -fill-seg-wm -fix-scm-ha 1 wm.seg.mgz brain.mgz aseg.presurf.mgz wm.asegedit.mgz; "
        "mri_pretess wm.asegedit.mgz wm norm.mgz wm.mgz; "
        "mri_fill -a ponscc.cut.log -xform transforms/talairach.lta -segmentation aseg.presurf.mgz wm.mgz filled.mgz; "
        "mri_pretess filled.mgz 255 norm.mgz filled-pretess255.mgz; "
        "mri_pretess filled.mgz 127 norm.mgz filled-pretess127.mgz; "
        "test -s filled.mgz"
    )


def _fs8r_stage7(ctx: ToolContext) -> str:
    return (
        _fs8r_common(ctx)
        + "mri_tessellate filled-pretess255.mgz 255 ../surf/lh.orig.nofix; "
        "mri_tessellate filled-pretess127.mgz 127 ../surf/rh.orig.nofix; "
        "mris_smooth -nw -seed 1234 ../surf/lh.orig.nofix ../surf/lh.smoothwm.nofix; "
        "mris_smooth -nw -seed 1234 ../surf/rh.orig.nofix ../surf/rh.smoothwm.nofix; "
        "mris_inflate -no-save-sulc ../surf/lh.smoothwm.nofix ../surf/lh.inflated.nofix; "
        "mris_inflate -no-save-sulc ../surf/rh.smoothwm.nofix ../surf/rh.inflated.nofix; "
        "mris_sphere -q -p 6 -a 128 -seed 1234 ../surf/lh.inflated.nofix ../surf/lh.qsphere.nofix; "
        "mris_sphere -q -p 6 -a 128 -seed 1234 ../surf/rh.inflated.nofix ../surf/rh.qsphere.nofix; "
        "cd \"$SD\"; "
        "mris_fix_topology -threads 1 -mgz -sphere qsphere.nofix -inflated inflated.nofix -orig orig.nofix -out orig.premesh -ga -seed 1234 \"$SUBJ\" lh; "
        "mris_remesh --remesh --iters 3 --input surf/lh.orig.premesh --output surf/lh.orig; "
        "mris_remove_intersection surf/lh.orig surf/lh.orig; "
        "mris_autodet_gwstats --o surf/autodet.gw.stats.lh.dat --i mri/brain.finalsurfs.mgz --wm mri/wm.mgz --surf surf/lh.orig; "
        "cd \"$SD/mri\"; "
        "mris_place_surface --adgws-in ../surf/autodet.gw.stats.lh.dat --wm wm.mgz --threads 1 --invol brain.finalsurfs.mgz --lh --i ../surf/lh.orig --o ../surf/lh.white --white --seg aseg.presurf.mgz --nsmooth 5 --restore-255 --rip-bg-no-annot --rip-bg --rip-bg-lof --outvol mrisps.wpa.lh.mgz; "
        "mris_place_surface --adgws-in ../surf/autodet.gw.stats.lh.dat --seg aseg.presurf.mgz --threads 1 --wm wm.mgz --invol brain.finalsurfs.mgz --lh --i ../surf/lh.white --o ../surf/lh.pial --pial --nsmooth 0 --repulse-surf ../surf/lh.white --white-surf ../surf/lh.white --restore-255; "
        "mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness; "
        "cd \"$SD\"; "
        "mris_fix_topology -threads 1 -mgz -sphere qsphere.nofix -inflated inflated.nofix -orig orig.nofix -out orig.premesh -ga -seed 1234 \"$SUBJ\" rh; "
        "mris_remesh --remesh --iters 3 --input surf/rh.orig.premesh --output surf/rh.orig; "
        "mris_remove_intersection surf/rh.orig surf/rh.orig; "
        "mris_autodet_gwstats --o surf/autodet.gw.stats.rh.dat --i mri/brain.finalsurfs.mgz --wm mri/wm.mgz --surf surf/rh.orig; "
        "cd \"$SD/mri\"; "
        "mris_place_surface --adgws-in ../surf/autodet.gw.stats.rh.dat --wm wm.mgz --threads 1 --invol brain.finalsurfs.mgz --rh --i ../surf/rh.orig --o ../surf/rh.white --white --seg aseg.presurf.mgz --nsmooth 5 --restore-255 --rip-bg-no-annot --rip-bg --rip-bg-lof --outvol mrisps.wpa.rh.mgz; "
        "mris_place_surface --adgws-in ../surf/autodet.gw.stats.rh.dat --seg aseg.presurf.mgz --threads 1 --wm wm.mgz --invol brain.finalsurfs.mgz --rh --i ../surf/rh.white --o ../surf/rh.pial --pial --nsmooth 0 --repulse-surf ../surf/rh.white --white-surf ../surf/rh.white --restore-255; "
        "mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness; "
        "test -s ../surf/lh.thickness; test -s ../surf/rh.thickness"
    )


def _fs8r_stage8(ctx: ToolContext) -> str:
    return (
        _fs8r_common(ctx)
        + _fs8r_atlas_lookup()
        + "cd \"$SD\"; "
        + f"mris_smooth -n 3 -nw -seed 1234 surf/lh.white surf/lh.smoothwm; "
        f"mris_inflate surf/lh.smoothwm surf/lh.inflated; "
        f"mris_sphere -threads {ctx.threads} -seed 1234 surf/lh.inflated surf/lh.sphere; "
        f"mris_register -curv -threads {ctx.threads} surf/lh.sphere \"$LH_FOLDING_ATLAS\" surf/lh.sphere.reg; "
        "mris_smooth -n 3 -nw -seed 1234 surf/rh.white surf/rh.smoothwm; "
        "mris_inflate surf/rh.smoothwm surf/rh.inflated; "
        f"mris_sphere -threads {ctx.threads} -seed 1234 surf/rh.inflated surf/rh.sphere; "
        f"mris_register -curv -threads {ctx.threads} surf/rh.sphere \"$RH_FOLDING_ATLAS\" surf/rh.sphere.reg; "
        "test -s surf/lh.sphere.reg; test -s surf/rh.sphere.reg"
    )


def _fs8r_stage9(ctx: ToolContext) -> str:
    volume_only = not ctx.enabled_stats.get("cortical_thickness", False)
    if volume_only:
        return (
            _fs8r_common(ctx)
            + "cd \"$SD\"; "
            "mri_segstats --seg mri/aseg.auto.mgz --sum stats/aseg.stats --ctab \"$FREESURFER_HOME/ASegStatsLUT.txt\" || mri_segstats --seg mri/aseg.auto.mgz --sum stats/aseg.stats; "
            "python3 /app/normalize_volumes.py mri/synthseg.vol.csv /output/stats/subcortical_volume.tsv /output/stats/cortical_volume.tsv \"$SUBJ\" FreeSurferSynthSeg; "
            "cp mri/synthseg.vol.csv /output/stats/ 2>/dev/null || true; "
            "test -s stats/aseg.stats; test -s /output/stats/subcortical_volume.tsv; test -s /output/stats/cortical_volume.tsv"
        )
    return (
        _fs8r_common(ctx)
        + _fs8r_atlas_lookup()
        + "cd \"$SD\"; "
        "mri_label2label --srcsubject fsaverage --srclabel \"$FREESURFER_HOME/subjects/fsaverage/label/lh.cortex.label\" --trgsubject \"$SUBJ\" --trglabel label/lh.cortex.label --hemi lh --regmethod surface; "
        "mris_ca_label -l label/lh.cortex.label -aseg mri/aseg.presurf.mgz -seed 1234 \"$SUBJ\" lh surf/lh.sphere.reg \"$LH_DK_ATLAS\" label/lh.aparc.annot; "
        "mris_anatomical_stats -a label/lh.aparc.annot -f stats/lh.aparc.stats \"$SUBJ\" lh; "
        "mri_label2label --srcsubject fsaverage --srclabel \"$FREESURFER_HOME/subjects/fsaverage/label/rh.cortex.label\" --trgsubject \"$SUBJ\" --trglabel label/rh.cortex.label --hemi rh --regmethod surface; "
        "mris_ca_label -l label/rh.cortex.label -aseg mri/aseg.presurf.mgz -seed 1234 \"$SUBJ\" rh surf/rh.sphere.reg \"$RH_DK_ATLAS\" label/rh.aparc.annot; "
        "mris_anatomical_stats -a label/rh.aparc.annot -f stats/rh.aparc.stats \"$SUBJ\" rh; "
        "mri_segstats --seg mri/aseg.auto.mgz --sum stats/aseg.stats --ctab \"$FREESURFER_HOME/ASegStatsLUT.txt\" || mri_segstats --seg mri/aseg.auto.mgz --sum stats/aseg.stats; "
        "cp stats/*.stats /output/stats/ 2>/dev/null || true; "
        "cp mri/synthseg.vol.csv /output/stats/ 2>/dev/null || true; "
        "test -s stats/lh.aparc.stats; test -s stats/rh.aparc.stats; test -s stats/aseg.stats"
    )


def _fs7r_common(ctx: ToolContext) -> str:
    subject = _q(ctx.subject_id)
    return (
        "set -e; "
        "export SUBJECTS_DIR=/output/freesurfer; "
        f"SUBJ={subject}; "
        "SD=\"$SUBJECTS_DIR/$SUBJ\"; "
        "mkdir -p \"$SD\"/mri \"$SD\"/surf \"$SD\"/label \"$SD\"/stats \"$SD\"/tmp \"$SD\"/scripts \"$SD/mri/transforms\" /output/stats; "
        "if [ -L \"$SUBJECTS_DIR/fsaverage\" ]; then rm \"$SUBJECTS_DIR/fsaverage\"; fi; "
        "if [ ! -e \"$SUBJECTS_DIR/fsaverage\" ] && [ -d \"$FREESURFER_HOME/subjects/fsaverage\" ]; then ln -s \"$FREESURFER_HOME/subjects/fsaverage\" \"$SUBJECTS_DIR/fsaverage\"; fi; "
        "GCA=\"$FREESURFER_HOME/average/RB_all_2020-01-02.gca\"; "
        "GCA_WITH_SKULL=\"$FREESURFER_HOME/average/RB_all_withskull_2020_01_02.gca\"; "
        "SUBCORT_LUT=\"$FREESURFER_HOME/SubCorticalMassLUT.txt\"; "
        "MNI305=\"$FREESURFER_HOME/average/mni305.cor.mgz\"; "
        "if [ -f \"$FREESURFER_HOME/average/mni305.cor.stripped.mgz\" ]; then MNI305=\"$FREESURFER_HOME/average/mni305.cor.stripped.mgz\"; fi; "
        "cd \"$SD/mri\"; "
    )


def _fs7r_atlas_lookup() -> str:
    return (
        "first_existing() { for pattern in \"$@\"; do for match in $pattern; do [ -f \"$match\" ] && printf '%s\\n' \"$match\" && return 0; done; done; return 1; }; "
        "LH_FOLDING_ATLAS=$(first_existing \"$FREESURFER_HOME/average/lh.folding.atlas.acfb40.noaparc.i12*.tif\" \"$FREESURFER_HOME/average/lh.folding.atlas*.tif\") || { echo Missing lh folding atlas; exit 1; }; "
        "RH_FOLDING_ATLAS=$(first_existing \"$FREESURFER_HOME/average/rh.folding.atlas.acfb40.noaparc.i12*.tif\" \"$FREESURFER_HOME/average/rh.folding.atlas*.tif\") || { echo Missing rh folding atlas; exit 1; }; "
        "LH_DK_ATLAS=$(first_existing \"$FREESURFER_HOME/average/lh.DKaparc.atlas.acfb40.noaparc.i12*.gcs\" \"$FREESURFER_HOME/average/lh.DKaparc.atlas*.gcs\") || { echo Missing lh DKaparc atlas; exit 1; }; "
        "RH_DK_ATLAS=$(first_existing \"$FREESURFER_HOME/average/rh.DKaparc.atlas.acfb40.noaparc.i12*.gcs\" \"$FREESURFER_HOME/average/rh.DKaparc.atlas*.gcs\") || { echo Missing rh DKaparc atlas; exit 1; }; "
    )


def _fs7r_stage1(ctx: ToolContext) -> str:
    dicom_flags = ""
    if ctx.dicom_list_path:
        dicom_flags = f"-no-dcm2niix -dicomread2 --sdcmlist {_q(ctx.dicom_list_path)} "
    return (
        _fs7r_common(ctx)
        + f"mri_convert {dicom_flags}{_q(ctx.input_path)} 001.mgz; "
        "mri_convert 001.mgz orig.mgz --conform; "
        "test -s orig.mgz"
    )


def _fs7r_stage2(ctx: ToolContext) -> str:
    return (
        _fs7r_common(ctx)
        + "mri_nu_correct.mni --no-rescale --i orig.mgz --o orig_nu.mgz --ants-n4 --n 1 --proto-iters 1000 --distance 50; "
        "talairach_avi --i orig_nu.mgz --xfm transforms/talairach.auto.xfm; "
        "cp transforms/talairach.auto.xfm transforms/talairach.xfm; "
        "lta_convert --src orig.mgz --trg \"$MNI305\" --inxfm transforms/talairach.xfm --outlta transforms/talairach.xfm.lta --subject fsaverage --ltavox2vox; "
        "talairach_afd -T 0.005 -xfm transforms/talairach.xfm; "
        "mri_nu_correct.mni --i orig.mgz --o nu.mgz --uchar transforms/talairach.xfm --n 2 --ants-n4; "
        "mri_add_xform_to_header -c transforms/talairach.xfm nu.mgz nu.mgz; "
        "mri_normalize -g 1 -seed 1234 -mprage nu.mgz T1.mgz; "
        "mri_em_register -skull nu.mgz \"$GCA_WITH_SKULL\" transforms/talairach_with_skull.lta; "
        "mri_watershed -T1 -brain_atlas \"$GCA_WITH_SKULL\" transforms/talairach_with_skull.lta T1.mgz brainmask.auto.mgz; "
        "cp brainmask.auto.mgz brainmask.mgz; "
        "test -s brainmask.mgz"
    )


def _fs7r_stage3(ctx: ToolContext) -> str:
    return (
        _fs7r_common(ctx)
        + "mri_em_register -uns 3 -mask brainmask.mgz nu.mgz \"$GCA\" transforms/talairach.lta; "
        "mri_ca_normalize -c ctrl_pts.mgz -mask brainmask.mgz nu.mgz \"$GCA\" transforms/talairach.lta norm.mgz; "
        "mri_ca_register -nobigventricles -T transforms/talairach.lta -align-after -mask brainmask.mgz norm.mgz \"$GCA\" transforms/talairach.m3z; "
        "mri_ca_label -relabel_unlikely 9 .3 -prior 0.5 -align norm.mgz transforms/talairach.m3z \"$GCA\" aseg.auto_noCCseg.mgz; "
        "mri_cc -aseg aseg.auto_noCCseg.mgz -o aseg.auto.mgz -lta transforms/cc_up.lta \"$SUBJ\"; "
        "rm -f aseg.presurf.mgz; cp aseg.auto.mgz aseg.presurf.mgz; "
        "test -s aseg.presurf.mgz"
    )


def _fs7r_stage4(ctx: ToolContext) -> str:
    return (
        _fs7r_common(ctx)
        + "test -s transforms/talairach.xfm; "
        "test -s transforms/talairach.xfm.lta; "
        "test -s transforms/talairach.lta"
    )


def _fs7r_stage5(ctx: ToolContext) -> str:
    return (
        _fs7r_common(ctx)
        + "mri_normalize -seed 1234 -mprage -aseg aseg.presurf.mgz -mask brainmask.mgz norm.mgz brain.mgz; "
        "AntsDenoiseImageFs -i brain.mgz -o antsdn.brain.mgz; "
        "mri_mask -T 5 brain.mgz brainmask.mgz brain.finalsurfs.mgz; "
        "test -s brain.finalsurfs.mgz"
    )


def _fs7r_stage6(ctx: ToolContext) -> str:
    return (
        _fs7r_common(ctx)
        + "mri_segment -wsizemm 13 -mprage antsdn.brain.mgz wm.seg.mgz; "
        "mri_edit_wm_with_aseg -keep-in wm.seg.mgz brain.mgz aseg.presurf.mgz wm.asegedit.mgz; "
        "mri_pretess wm.asegedit.mgz wm norm.mgz wm.mgz; "
        "mri_fill -a ../scripts/ponscc.cut.log -xform transforms/talairach.lta -segmentation aseg.presurf.mgz -ctab \"$SUBCORT_LUT\" wm.mgz filled.mgz; "
        "mri_pretess filled.mgz 255 norm.mgz filled-pretess255.mgz; "
        "mri_pretess filled.mgz 127 norm.mgz filled-pretess127.mgz; "
        "test -s filled.mgz"
    )


def _fs7r_stage7(ctx: ToolContext) -> str:
    return (
        _fs7r_common(ctx)
        + "mri_tessellate filled-pretess255.mgz 255 ../surf/lh.orig.nofix; "
        "mri_tessellate filled-pretess127.mgz 127 ../surf/rh.orig.nofix; "
        "mris_extract_main_component ../surf/lh.orig.nofix ../surf/lh.orig.nofix; "
        "mris_extract_main_component ../surf/rh.orig.nofix ../surf/rh.orig.nofix; "
        "mris_smooth -nw -seed 1234 ../surf/lh.orig.nofix ../surf/lh.smoothwm.nofix; "
        "mris_smooth -nw -seed 1234 ../surf/rh.orig.nofix ../surf/rh.smoothwm.nofix; "
        "mris_inflate -no-save-sulc ../surf/lh.smoothwm.nofix ../surf/lh.inflated.nofix; "
        "mris_inflate -no-save-sulc ../surf/rh.smoothwm.nofix ../surf/rh.inflated.nofix; "
        "mris_sphere -q -p 6 -a 128 -seed 1234 ../surf/lh.inflated.nofix ../surf/lh.qsphere.nofix; "
        "mris_sphere -q -p 6 -a 128 -seed 1234 ../surf/rh.inflated.nofix ../surf/rh.qsphere.nofix; "
        "cd \"$SD\"; "
        "mris_fix_topology -mgz -sphere qsphere.nofix -inflated inflated.nofix -orig orig.nofix -out orig.premesh -ga -seed 1234 \"$SUBJ\" lh; "
        "mris_fix_topology -mgz -sphere qsphere.nofix -inflated inflated.nofix -orig orig.nofix -out orig.premesh -ga -seed 1234 \"$SUBJ\" rh; "
        "mris_euler_number surf/lh.orig.premesh; mris_euler_number surf/rh.orig.premesh; "
        "mris_remesh --remesh --iters 3 --input surf/lh.orig.premesh --output surf/lh.orig; "
        "mris_remesh --remesh --iters 3 --input surf/rh.orig.premesh --output surf/rh.orig; "
        "mris_remove_intersection surf/lh.orig surf/lh.orig; rm -f surf/lh.inflated; "
        "mris_remove_intersection surf/rh.orig surf/rh.orig; rm -f surf/rh.inflated; "
        "cd \"$SD/mri\"; "
        "mris_autodet_gwstats --o ../surf/autodet.gw.stats.lh.dat --i brain.finalsurfs.mgz --wm wm.mgz --surf ../surf/lh.orig.premesh; "
        "mris_autodet_gwstats --o ../surf/autodet.gw.stats.rh.dat --i brain.finalsurfs.mgz --wm wm.mgz --surf ../surf/rh.orig.premesh; "
        "mris_place_surface --adgws-in ../surf/autodet.gw.stats.lh.dat --wm wm.mgz --threads 1 --invol brain.finalsurfs.mgz --lh --i ../surf/lh.orig --o ../surf/lh.white.preaparc --white --seg aseg.presurf.mgz --nsmooth 5; "
        "mris_place_surface --adgws-in ../surf/autodet.gw.stats.rh.dat --wm wm.mgz --threads 1 --invol brain.finalsurfs.mgz --rh --i ../surf/rh.orig --o ../surf/rh.white.preaparc --white --seg aseg.presurf.mgz --nsmooth 5; "
        "mri_label2label --label-cortex ../surf/lh.white.preaparc aseg.presurf.mgz 0 ../label/lh.cortex.label; "
        "mri_label2label --label-cortex ../surf/lh.white.preaparc aseg.presurf.mgz 1 ../label/lh.cortex+hipamyg.label; "
        "mri_label2label --label-cortex ../surf/rh.white.preaparc aseg.presurf.mgz 0 ../label/rh.cortex.label; "
        "mri_label2label --label-cortex ../surf/rh.white.preaparc aseg.presurf.mgz 1 ../label/rh.cortex+hipamyg.label; "
        "test -s ../surf/lh.white.preaparc; test -s ../surf/rh.white.preaparc"
    )


def _fs7r_stage8(ctx: ToolContext) -> str:
    return (
        _fs7r_common(ctx)
        + _fs7r_atlas_lookup()
        + "mris_smooth -n 3 -nw -seed 1234 ../surf/lh.white.preaparc ../surf/lh.smoothwm; "
        "mris_smooth -n 3 -nw -seed 1234 ../surf/rh.white.preaparc ../surf/rh.smoothwm; "
        "mris_inflate ../surf/lh.smoothwm ../surf/lh.inflated; "
        "mris_inflate ../surf/rh.smoothwm ../surf/rh.inflated; "
        "cd \"$SD/surf\"; "
        "mris_curvature -w -seed 1234 lh.white.preaparc; mris_curvature -seed 1234 -thresh .999 -n -a 5 -w -distances 10 10 lh.inflated; "
        "mris_curvature -w -seed 1234 rh.white.preaparc; mris_curvature -seed 1234 -thresh .999 -n -a 5 -w -distances 10 10 rh.inflated; "
        "mris_sphere -seed 1234 lh.inflated lh.sphere; "
        "mris_sphere -seed 1234 rh.inflated rh.sphere; "
        "mris_register -curv lh.sphere \"$LH_FOLDING_ATLAS\" lh.sphere.reg; ln -sf lh.sphere.reg lh.fsaverage.sphere.reg; "
        "mris_register -curv rh.sphere \"$RH_FOLDING_ATLAS\" rh.sphere.reg; ln -sf rh.sphere.reg rh.fsaverage.sphere.reg; "
        "mris_jacobian lh.white.preaparc lh.sphere.reg lh.jacobian_white; mrisp_paint -a 5 \"$LH_FOLDING_ATLAS\"#6 lh.sphere.reg lh.avg_curv; "
        "mris_jacobian rh.white.preaparc rh.sphere.reg rh.jacobian_white; mrisp_paint -a 5 \"$RH_FOLDING_ATLAS\"#6 rh.sphere.reg rh.avg_curv; "
        "cd \"$SD\"; "
        "mris_ca_label -l label/lh.cortex.label -aseg mri/aseg.presurf.mgz -seed 1234 \"$SUBJ\" lh surf/lh.sphere.reg \"$LH_DK_ATLAS\" label/lh.aparc.annot; "
        "mris_ca_label -l label/rh.cortex.label -aseg mri/aseg.presurf.mgz -seed 1234 \"$SUBJ\" rh surf/rh.sphere.reg \"$RH_DK_ATLAS\" label/rh.aparc.annot; "
        "test -s surf/lh.sphere.reg; test -s surf/rh.sphere.reg; test -s label/lh.aparc.annot; test -s label/rh.aparc.annot"
    )


def _fs7r_stage9(ctx: ToolContext) -> str:
    return (
        _fs7r_common(ctx)
        + "mris_place_surface --adgws-in ../surf/autodet.gw.stats.lh.dat --seg aseg.presurf.mgz --threads 1 --wm wm.mgz --invol brain.finalsurfs.mgz --lh --i ../surf/lh.white.preaparc --o ../surf/lh.white --white --nsmooth 0 --rip-label ../label/lh.cortex.label --rip-bg --rip-surf ../surf/lh.white.preaparc --aparc ../label/lh.aparc.annot; "
        "mris_place_surface --adgws-in ../surf/autodet.gw.stats.rh.dat --seg aseg.presurf.mgz --threads 1 --wm wm.mgz --invol brain.finalsurfs.mgz --rh --i ../surf/rh.white.preaparc --o ../surf/rh.white --white --nsmooth 0 --rip-label ../label/rh.cortex.label --rip-bg --rip-surf ../surf/rh.white.preaparc --aparc ../label/rh.aparc.annot; "
        "mris_place_surface --adgws-in ../surf/autodet.gw.stats.lh.dat --seg aseg.presurf.mgz --threads 1 --wm wm.mgz --invol brain.finalsurfs.mgz --lh --i ../surf/lh.white --o ../surf/lh.pial.T1 --pial --nsmooth 0 --rip-label ../label/lh.cortex+hipamyg.label --pin-medial-wall ../label/lh.cortex.label --aparc ../label/lh.aparc.annot --repulse-surf ../surf/lh.white --white-surf ../surf/lh.white; cd ../surf; ln -sf lh.pial.T1 lh.pial; cd ../mri; "
        "mris_place_surface --adgws-in ../surf/autodet.gw.stats.rh.dat --seg aseg.presurf.mgz --threads 1 --wm wm.mgz --invol brain.finalsurfs.mgz --rh --i ../surf/rh.white --o ../surf/rh.pial.T1 --pial --nsmooth 0 --rip-label ../label/rh.cortex+hipamyg.label --pin-medial-wall ../label/rh.cortex.label --aparc ../label/rh.aparc.annot --repulse-surf ../surf/rh.white --white-surf ../surf/rh.white; cd ../surf; ln -sf rh.pial.T1 rh.pial; cd ../mri; "
        "mris_place_surface --curv-map ../surf/lh.white 2 10 ../surf/lh.curv; mris_place_surface --area-map ../surf/lh.white ../surf/lh.area; mris_place_surface --curv-map ../surf/lh.pial 2 10 ../surf/lh.curv.pial; mris_place_surface --area-map ../surf/lh.pial ../surf/lh.area.pial; mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness; "
        "mris_place_surface --curv-map ../surf/rh.white 2 10 ../surf/rh.curv; mris_place_surface --area-map ../surf/rh.white ../surf/rh.area; mris_place_surface --curv-map ../surf/rh.pial 2 10 ../surf/rh.curv.pial; mris_place_surface --area-map ../surf/rh.pial ../surf/rh.area.pial; mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness; "
        "cd \"$SD\"; "
        "mris_anatomical_stats -th3 -mgz -cortex label/lh.cortex.label -f stats/lh.aparc.stats -b -a label/lh.aparc.annot -c label/aparc.annot.ctab \"$SUBJ\" lh white; "
        "mris_anatomical_stats -th3 -mgz -cortex label/lh.cortex.label -f stats/lh.aparc.pial.stats -b -a label/lh.aparc.annot -c label/aparc.annot.ctab \"$SUBJ\" lh pial; "
        "mris_anatomical_stats -th3 -mgz -cortex label/rh.cortex.label -f stats/rh.aparc.stats -b -a label/rh.aparc.annot -c label/aparc.annot.ctab \"$SUBJ\" rh white; "
        "mris_anatomical_stats -th3 -mgz -cortex label/rh.cortex.label -f stats/rh.aparc.pial.stats -b -a label/rh.aparc.annot -c label/aparc.annot.ctab \"$SUBJ\" rh pial; "
        "mris_volmask --aseg_name aseg.presurf --label_left_white 2 --label_left_ribbon 3 --label_right_white 41 --label_right_ribbon 42 --save_ribbon \"$SUBJ\"; "
        "cd \"$SD/mri\"; "
        "mri_relabel_hypointensities aseg.presurf.mgz ../surf aseg.presurf.hypos.mgz; "
        "mri_surf2volseg --o aseg.mgz --i aseg.presurf.hypos.mgz --fix-presurf-with-ribbon \"$SD/mri/ribbon.mgz\" --threads 1 --lh-cortex-mask \"$SD/label/lh.cortex.label\" --lh-white \"$SD/surf/lh.white\" --lh-pial \"$SD/surf/lh.pial\" --rh-cortex-mask \"$SD/label/rh.cortex.label\" --rh-white \"$SD/surf/rh.white\" --rh-pial \"$SD/surf/rh.pial\"; "
        "cd \"$SD\"; "
        "mri_segstats --seed 1234 --seg mri/aseg.mgz --sum stats/aseg.stats --pv mri/norm.mgz --empty --brainmask mri/brainmask.mgz --brain-vol-from-seg --excludeid 0 --excl-ctxgmwm --supratent --subcortgray --in mri/norm.mgz --in-intensity-name norm --in-intensity-units MR --etiv --surf-wm-vol --surf-ctx-vol --totalgray --euler --ctab \"$FREESURFER_HOME/ASegStatsLUT.txt\" --subject \"$SUBJ\"; "
        "cp stats/*.stats /output/stats/ 2>/dev/null || true; "
        "cp mri/aseg.auto.mgz /output/stats/ 2>/dev/null || true; "
        "cp mri/aseg.mgz /output/stats/ 2>/dev/null || true; "
        "test -s stats/lh.aparc.stats; test -s stats/rh.aparc.stats; test -s stats/aseg.stats"
    )

TOOL_DEFS: dict[str, dict] = {
    "fs8_reduced54_reorientation": {
        "display_name": "FreeSurfer 8 Reorientation",
        "image": FS8_REDUCED54_IMAGE,
        "stage": "reorientation",
        "needs_license": True,
        "command_builder": _fs8r_stage1,
        "output_files": [],
        "output_globs": ["freesurfer/*/mri/orig.mgz"],
    },
    "fs8_reduced54_brain_extraction": {
        "display_name": "FreeSurfer 8 Brain Extraction",
        "image": FS8_REDUCED54_IMAGE,
        "stage": "brain_extraction",
        "needs_license": True,
        "command_builder": _fs8r_stage2,
        "output_files": [],
        "output_globs": ["freesurfer/*/mri/synthstrip.mgz"],
    },
    "fs8_reduced54_segmentation": {
        "display_name": "FreeSurfer 8 SynthSeg",
        "image": FS8_REDUCED54_IMAGE,
        "stage": "segmentation",
        "needs_license": True,
        "hidden_from_stage_select": True,
        "command_builder": _fs8r_stage3,
        "output_files": [],
        "output_globs": ["freesurfer/*/mri/synthseg.rca.mgz", "freesurfer/*/mri/synthseg.vol.csv"],
    },
    "fs8_reduced54_template_registration": {
        "display_name": "FreeSurfer 8 Template Registration",
        "image": FS8_REDUCED54_IMAGE,
        "stage": "template_registration",
        "needs_license": True,
        "command_builder": _fs8r_stage4,
        "output_files": [],
        "output_globs": ["freesurfer/*/mri/transforms/talairach.lta", "freesurfer/*/mri/transforms/talairach.xfm"],
    },
    "fs8_reduced54_bias_correction": {
        "display_name": "FreeSurfer 8 Image Standardization",
        "image": FS8_REDUCED54_IMAGE,
        "stage": "bias_correction",
        "needs_license": True,
        "command_builder": _fs8r_stage5,
        "output_files": [],
        "output_globs": ["freesurfer/*/mri/brain.finalsurfs.mgz", "freesurfer/*/mri/antsdn.brain.mgz"],
    },
    "fs8_reduced54_wm_segmentation": {
        "display_name": "FreeSurfer 8 WM Segmentation",
        "image": FS8_REDUCED54_IMAGE,
        "stage": "white_matter_segmentation",
        "needs_license": True,
        "command_builder": _fs8r_stage6,
        "output_files": [],
        "output_globs": ["freesurfer/*/mri/filled.mgz", "freesurfer/*/mri/wm.mgz"],
    },
    "fs8_reduced54_surface_reconstruction": {
        "display_name": "FreeSurfer 8 Surface Reconstruction",
        "image": FS8_REDUCED54_IMAGE,
        "stage": "surface_reconstruction",
        "needs_license": True,
        "command_builder": _fs8r_stage7,
        "output_files": [],
        "output_globs": ["freesurfer/*/surf/lh.thickness", "freesurfer/*/surf/rh.thickness"],
    },
    "fs8_reduced54_surface_registration": {
        "display_name": "FreeSurfer 8 Surface Registration",
        "image": FS8_REDUCED54_IMAGE,
        "stage": "surface_registration",
        "needs_license": True,
        "command_builder": _fs8r_stage8,
        "output_files": [],
        "output_globs": ["freesurfer/*/surf/lh.sphere.reg", "freesurfer/*/surf/rh.sphere.reg"],
    },
    "fs8_reduced54_stats": {
        "display_name": "FreeSurfer 8 Stats",
        "image": FS8_REDUCED54_IMAGE,
        "stage": "stats_extraction",
        "needs_license": True,
        "command_builder": _fs8r_stage9,
        "output_files": ["lh.aparc.stats", "rh.aparc.stats", "aseg.stats", "subcortical_volume.tsv", "cortical_volume.tsv"],
        "output_globs": ["freesurfer/*/stats/lh.aparc.stats", "freesurfer/*/stats/rh.aparc.stats", "freesurfer/*/stats/aseg.stats"],
    },
    "fs7_recon_style_reorientation": {
        "display_name": "FreeSurfer 7 Reorientation",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "reorientation",
        "needs_license": True,
        "command_builder": _fs7r_stage1,
        "output_files": [],
        "output_globs": ["freesurfer/*/mri/orig.mgz"],
    },
    "fs7_recon_style_brain_extraction": {
        "display_name": "FreeSurfer 7 Brain Extraction",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "brain_extraction",
        "needs_license": True,
        "command_builder": _fs7r_stage2,
        "output_files": [],
        "output_globs": ["freesurfer/*/mri/brainmask.mgz"],
    },
    "fs7_recon_style_segmentation": {
        "display_name": "FreeSurfer 7 Atlas Segmentation",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "segmentation",
        "needs_license": True,
        "command_builder": _fs7r_stage3,
        "output_files": [],
        "output_globs": ["freesurfer/*/mri/aseg.presurf.mgz", "freesurfer/*/mri/aseg.auto.mgz"],
    },
    "fs7_recon_style_template_registration": {
        "display_name": "FreeSurfer 7 Template Registration",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "template_registration",
        "needs_license": True,
        "command_builder": _fs7r_stage4,
        "output_files": [],
        "output_globs": ["freesurfer/*/mri/transforms/talairach.lta", "freesurfer/*/mri/transforms/talairach.xfm"],
    },
    "fs7_recon_style_bias_correction": {
        "display_name": "FreeSurfer 7 Image Standardization",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "bias_correction",
        "needs_license": True,
        "command_builder": _fs7r_stage5,
        "output_files": [],
        "output_globs": ["freesurfer/*/mri/brain.finalsurfs.mgz", "freesurfer/*/mri/antsdn.brain.mgz"],
    },
    "fs7_recon_style_wm_segmentation": {
        "display_name": "FreeSurfer 7 WM Segmentation",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "white_matter_segmentation",
        "needs_license": True,
        "command_builder": _fs7r_stage6,
        "output_files": [],
        "output_globs": ["freesurfer/*/mri/filled.mgz", "freesurfer/*/mri/wm.mgz"],
    },
    "fs7_recon_style_surface_reconstruction": {
        "display_name": "FreeSurfer 7 Surface Reconstruction",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "surface_reconstruction",
        "needs_license": True,
        "command_builder": _fs7r_stage7,
        "output_files": [],
        "output_globs": ["freesurfer/*/surf/lh.white.preaparc", "freesurfer/*/surf/rh.white.preaparc"],
    },
    "fs7_recon_style_surface_registration": {
        "display_name": "FreeSurfer 7 Surface Registration",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "surface_registration",
        "needs_license": True,
        "command_builder": _fs7r_stage8,
        "output_files": [],
        "output_globs": ["freesurfer/*/surf/lh.sphere.reg", "freesurfer/*/surf/rh.sphere.reg"],
    },
    "fs7_recon_style_stats": {
        "display_name": "FreeSurfer 7 Stats",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "stats_extraction",
        "needs_license": True,
        "command_builder": _fs7r_stage9,
        "output_files": ["lh.aparc.stats", "rh.aparc.stats", "aseg.stats"],
        "output_globs": ["freesurfer/*/stats/lh.aparc.stats", "freesurfer/*/stats/rh.aparc.stats", "freesurfer/*/stats/aseg.stats"],
    },
    "mri_convert_fs7": {
        "display_name": "MRI Convert FreeSurfer7",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "reorientation",
        "needs_license": True,
        "command_builder": lambda ctx: f"mri_convert {'-no-dcm2niix -dicomread2 --sdcmlist ' + ctx.dicom_list_path + ' ' if ctx.dicom_list_path else ''}{ctx.input_path} /work/01_reoriented.nii.gz",
        "output_files": ["01_reoriented.nii.gz"],
    },
    "nibabel": {
        "display_name": "NiBabel",
        "image": "duattran05/mri-nibabel-utils:latest",
        "dockerfile": "docker/nibabel-utils",
        "stage": "reorientation",
        "needs_license": False,
        "output_files": ["01_nibabel_reoriented.nii.gz"],
    },
    "synthstrip_fs7": {
        "display_name": "SynthStrip FreeSurfer7",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "brain_extraction",
        "needs_license": True,
        "command_builder": lambda ctx: (
            f"mri_synthstrip -i {ctx.input_path} "
            f"-o /work/02_synthstrip_brain.nii.gz "
            f"-m /work/02_synthstrip_brain_mask.nii.gz "
            f"{'-g' if ctx.device != 'cpu' else ''}"
        ),
        "output_files": ["02_synthstrip_brain.nii.gz", "02_synthstrip_brain_mask.nii.gz"],
    },
    "hdbet": {
        "display_name": "HD-BET",
        "image": "duattran05/mri-hdbet:latest",
        "dockerfile": "docker/hdbet",
        "stage": "brain_extraction",
        "needs_license": False,
        "entrypoint": "",
        "shell": "sh",
        "command_builder": lambda ctx: (
            f"hd-bet -i {ctx.input_path} "
            f"-o /work/02_hdbet_brain.nii.gz "
            f"-device {'cpu' if ctx.device == 'cpu' else '0'} "
            f"--save_bet_mask "
            f"{'--disable_tta' if ctx.device == 'cpu' else ''}"
        ),
        "output_files": ["02_hdbet_brain.nii.gz", "02_hdbet_brain_mask.nii.gz"],
        "extra_mounts": {"hdbet_weights": "/root/.cache/torch/hub/checkpoints"},
    },
    "synthseg_freesurfer_fs8": {
        "display_name": "FreeSurfer 8 SynthSeg",
        "image": "mkdayyyy/mri-fs8-all:latest",
        "stage": "segmentation",
        "needs_license": True,
        "command_builder": _fs8_synthseg,
        "output_files": ["03_freesurfer_synthseg_segmentation.nii.gz"],
        "output_globs": ["freesurfer/*/mri/synthseg.rca.mgz", "freesurfer/*/mri/synthseg.vol.csv"],
    },
    "synthseg_freesurfer_fs7": {
        "display_name": "SynthSeg FreeSurfer7",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "segmentation",
        "needs_license": True,
        "command_builder": lambda ctx: (
            f"mri_synthseg --i {ctx.input_path} --o /work/03_freesurfer_synthseg_segmentation.nii.gz "
            f"--vol /work/03_freesurfer_synthseg_volumes.csv --parc --threads {ctx.threads} --crop 160 "
            f"{'--cpu' if ctx.device == 'cpu' else ''} "
            f"&& python3 /app/normalize_volumes.py /work/03_freesurfer_synthseg_volumes.csv "
            f"/output/stats/subcortical_volume.tsv /output/stats/cortical_volume.tsv {ctx.subject_id} FreeSurferSynthSeg"
        ),
        "output_files": ["03_freesurfer_synthseg_segmentation.nii.gz"],
    },
    "synthseg_standalone": {
        "display_name": "SynthSeg Standalone",
        "image": "duattran05/mri-synthseg-standalone:latest",
        "dockerfile": "docker/synthseg-standalone",
        "stage": "segmentation",
        "needs_license": False,
        "output_files": ["03_synthseg_standalone_segmentation.nii.gz"],
    },
    "fastsurfervinn": {
        "display_name": "FastSurferVINN",
        "image": "duattran05/mri-fastsurfervinn:latest",
        "dockerfile": "docker/fastsurfervinn",
        "stage": "segmentation",
        "needs_license": True,
        "output_files": ["03_fastsurfervinn_segmentation.nii.gz", "aparc.DKTatlas+aseg.deep.mgz"],
    },
    "ants_n4": {
        "display_name": "ANTs N4",
        "image": "duattran05/mri-ants:latest",
        "dockerfile": "docker/ants",
        "stage": "bias_correction",
        "needs_license": False,
        "output_files": ["05_standardized.nii.gz"],
    },
    "mri_binarize": {
        "display_name": "MRI Binarize FreeSurfer7",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "white_matter_segmentation",
        "needs_license": True,
        "command_builder": lambda ctx: f"mri_binarize --i {ctx.input_path} --wm --o /work/06_wm_mask.nii.gz",
        "output_files": ["06_wm_mask.nii.gz"],
    },
    "recon_all_fs7": {
        "display_name": "Recon-All FreeSurfer7",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "surface_reconstruction",
        "needs_license": True,
        "command_builder": lambda ctx: (
            "set -e; "
            "export SUBJECTS_DIR=/output/freesurfer; "
            "mkdir -p \"$SUBJECTS_DIR\" /output/stats; "
            "input=/work/mri/01_reoriented.nii.gz; "
            "if [ ! -s \"$input\" ]; then input=/work/mri/05_standardized.nii.gz; fi; "
            f"if [ ! -s \"$input\" ]; then input={ctx.input_path}; fi; "
            f"if [ -d \"$SUBJECTS_DIR/{ctx.subject_id}\" ] && [ ! -s \"$SUBJECTS_DIR/{ctx.subject_id}/surf/lh.thickness\" ]; then rm -rf \"$SUBJECTS_DIR/{ctx.subject_id}\"; fi; "
            f"recon-all -sd \"$SUBJECTS_DIR\" -s {ctx.subject_id} -i \"$input\" -all -parallel -openmp {ctx.threads}; "
            f"cp \"$SUBJECTS_DIR/{ctx.subject_id}/stats/\"*.stats /output/stats/ 2>/dev/null || true"
        ),
        "output_files": [],
        "output_globs": [
            "freesurfer/*/surf/lh.thickness",
            "freesurfer/*/surf/rh.thickness",
            "freesurfer/*/stats/lh.aparc.stats",
            "freesurfer/*/stats/rh.aparc.stats",
        ],
    },
    "surface_stats_fs7": {
        "display_name": "Surface Stats FreeSurfer7",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "surface_registration",
        "needs_license": True,
        "command_builder": lambda ctx: (
            "set -e; "
            "export SUBJECTS_DIR=/output/freesurfer; "
            "mkdir -p /output/stats; "
            "if [ -L \"$SUBJECTS_DIR/fsaverage\" ]; then rm \"$SUBJECTS_DIR/fsaverage\"; fi; "
            "if [ ! -e \"$SUBJECTS_DIR/fsaverage\" ] && [ -d \"$FREESURFER_HOME/subjects/fsaverage\" ]; then ln -s \"$FREESURFER_HOME/subjects/fsaverage\" \"$SUBJECTS_DIR/fsaverage\"; fi; "
            f"test -s \"$SUBJECTS_DIR/{ctx.subject_id}/surf/lh.thickness\"; "
            f"test -s \"$SUBJECTS_DIR/{ctx.subject_id}/surf/rh.thickness\"; "
            f"cp \"$SUBJECTS_DIR/{ctx.subject_id}/stats/\"*.stats /output/stats/; "
            f"for atlas in {SURFACE_STATS_ATLAS_LIST}; do for hemi in lh rh; do annot=\"$SUBJECTS_DIR/{ctx.subject_id}/label/$hemi.$atlas.annot\"; fsavg=\"$SUBJECTS_DIR/fsaverage/label/$hemi.$atlas.annot\"; if [ ! -s \"$annot\" ] && [ -s \"$fsavg\" ]; then mri_surf2surf --srcsubject fsaverage --trgsubject {ctx.subject_id} --hemi \"$hemi\" --sval-annot \"$fsavg\" --tval \"$annot\" >/tmp/mri_surf2surf.log 2>&1 || true; fi; if [ -s \"$annot\" ]; then mris_anatomical_stats -a \"$annot\" -f \"/output/stats/$hemi.$atlas.stats\" {ctx.subject_id} \"$hemi\" >/tmp/mris_anatomical_stats.log 2>&1 || true; fi; done; done; "
            "test -s /output/stats/lh.aparc.stats; "
            "test -s /output/stats/rh.aparc.stats"
        ),
        "output_files": ["lh.aparc.stats", "rh.aparc.stats"],
    },
    "freesurfer_stats_fs7": {
        "display_name": "FreeSurfer Stats FreeSurfer7",
        "image": FS7_RECON_STYLE_IMAGE,
        "stage": "stats_extraction",
        "needs_license": True,
        "command_builder": lambda ctx: "test -s /output/stats/subcortical_volume.tsv && test -s /output/stats/cortical_volume.tsv",
        "output_files": [
            "subcortical_volume.tsv",
            "cortical_volume.tsv",
        ],
    },
    "corticalflow": {
        "display_name": "CorticalFlow++",
        "image": "duattran05/mri-corticalflow:latest",
        "dockerfile": "docker/corticalflow",
        "stage": "surface_reconstruction",
        "needs_license": False,
        "entrypoint": "",
        "shell": "bash",
        "command_builder": lambda ctx: (
            f"cd /app && python3 predict.py inputs.data_type=list inputs.path={ctx.input_path} "
            f"inputs.split_name={ctx.subject_id} outputs.output_dir=/work/corticalflow_out "
            f"inputs.device={'cuda:0' if ctx.device != 'cpu' else 'cpu'}"
        ),
        "output_files": [],
        "output_globs": ["corticalflow_out/*/*white*", "corticalflow_out/*/*pial*"],
    },
    "sugar": {
        "display_name": "SUGAR",
        "image": "ninganme/sugar:latest",
        "dockerfile": "docker/sugar",
        "stage": "surface_registration",
        "needs_license": False,
        "entrypoint": "",
        "shell": "bash",
        "command_builder": lambda ctx: (
            "PREDICT=$(find / -name predict.py -path '*/SUGAR/predict.py' | head -n 1); "
            f"python3 $PREDICT --sd /output/freesurfer --out /work/sugar_out --fsd /usr/local/freesurfer "
            f"--sid {ctx.subject_id} --hemi lh --device {'cuda' if ctx.device != 'cpu' else 'cpu'} && "
            f"python3 $PREDICT --sd /output/freesurfer --out /work/sugar_out --fsd /usr/local/freesurfer "
            f"--sid {ctx.subject_id} --hemi rh --device {'cuda' if ctx.device != 'cpu' else 'cpu'}"
        ),
        "output_files": [],
        "output_globs": ["sugar_out/*"],
    },
}

TOOL_DISPLAY_ALIASES = {
    "Mri Convert FS7": "mri_convert_fs7",
    "Mri Convert Fs7": "mri_convert_fs7",
    "FreeSurfer SynthSeg FS8": "synthseg_freesurfer_fs8",
    "FreeSurfer 8 SynthSeg": "synthseg_freesurfer_fs8",
    "FreeSurfer8 Reduced54 SynthSeg": "synthseg_freesurfer_fs8",
    "FreeSurfer SynthSeg FS7": "synthseg_freesurfer_fs7",
    "FreeSurfer SynthSeg Fs8": "synthseg_freesurfer_fs8",
    "FreeSurfer SynthSeg Fs7": "synthseg_freesurfer_fs7",
    "Mri Binarize": "mri_binarize",
    "MRI Binarize": "mri_binarize",
    "FreeSurfer Stats FS7": "freesurfer_stats_fs7",
    "CorticalFlow": "corticalflow",
    "CorticalFlow++": "corticalflow",
    "Sugar": "sugar",
    "SUGAR": "sugar",
}

DISABLED_DOCKER_IMAGES: set[str] = set()

STAGE_ORDER = [
    "reorientation",
    "brain_extraction",
    "segmentation",
    "template_registration",
    "bias_correction",
    "white_matter_segmentation",
    "surface_reconstruction",
    "surface_registration",
    "stats_extraction",
]

STAGE_LABELS = {
    "reorientation": "Reorientation, resize",
    "brain_extraction": "Brain Extraction",
    "segmentation": "Subcortical Segmentation",
    "template_registration": "Template Registration",
    "bias_correction": "Image standardization",
    "white_matter_segmentation": "WM Segmentation",
    "surface_reconstruction": "Surface Reconstruction",
    "surface_registration": "Surface Registration",
    "stats_extraction": "Statistics & Atlas Mapping",
}

def tool_display_name(tool_key: str) -> str:
    tool = TOOL_DEFS.get(tool_key)
    if not tool:
        return ""
    return str(tool.get("display_name") or tool_key.replace("_", " ").title())

def tool_key_from_display(value: str) -> str:
    if value in {"Skipped", "Not available"}:
        return ""
    if value in TOOL_DEFS:
        return value
    if value in TOOL_DISPLAY_ALIASES:
        return TOOL_DISPLAY_ALIASES[value]
    for tool_key in TOOL_DEFS:
        if tool_display_name(tool_key) == value:
            return tool_key
    return ""

def is_tool_enabled(tool_key: str) -> bool:
    tool = TOOL_DEFS.get(tool_key)
    if not tool:
        return False
    return tool.get("image") not in DISABLED_DOCKER_IMAGES and not tool.get("disabled", False)

def is_tool_visible(tool_key: str) -> bool:
    tool = TOOL_DEFS.get(tool_key)
    if not tool:
        return False
    return not tool.get("hidden_from_stage_select", False) and not tool.get("hidden_from_tool_list", False)

def enabled_tools_for_stage(stage: str) -> list[str]:
    return [
        key
        for key, tool in TOOL_DEFS.items()
        if tool["stage"] == stage and is_tool_enabled(key) and is_tool_visible(key)
    ]
