#!/bin/bash
# Run one T1 image through a FreeSurfer 7 diagnostic workflow. The early
# deep-learning FreeSurfer 8 steps are replaced with the corresponding
# traditional FS7 recon-all commands, then the surface/stat stages continue
# with the standalone tool calls.
#
# Usage:
#   ./run_fs7_standalone.sh --input <T1.nii.gz> --output <dir> [options]
#
# Options:
#   --input     FILE     Input T1 image (required)
#   --output    DIR      Output directory (default: ./fs7_output)
#   --subject   ID       Subject ID (default: derived from filename)
#   --threads   N        CPU threads (default: 4)
#   --license   DIR      Directory containing license.txt (default: ./license)
#   --start     N        Start from stage N, 1-9 (default: 1)
#   --help               Show this help

set -euo pipefail

usage() {
    cat << 'USAGE'
Run one T1 image through a FreeSurfer 7 diagnostic workflow. The early
deep-learning FreeSurfer 8 steps are replaced with the corresponding
traditional FS7 recon-all commands, then the surface/stat stages continue
with the standalone tool calls.

Usage:
  ./run_fs7_standalone.sh --input <T1.nii.gz> --output <dir> [options]

Options:
  --input     FILE     Input T1 image (required)
  --output    DIR      Output directory (default: ./fs7_output)
  --subject   ID       Subject ID (default: derived from filename)
  --threads   N        CPU threads (default: 4)
  --license   DIR      Directory containing license.txt (default: ./license)
  --start     N        Start from stage N, 1-9 (default: 1)
  --help               Show this help
USAGE
}

INPUT=""
OUTPUT="$(pwd)/fs7_output"
SUBJECT=""
THREADS=4
LICENSE_DIR="$(pwd)/license"
START_STAGE=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --input) INPUT="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        --subject) SUBJECT="$2"; shift 2 ;;
        --threads) THREADS="$2"; shift 2 ;;
        --license) LICENSE_DIR="$2"; shift 2 ;;
        --start) START_STAGE="$2"; shift 2 ;;
        --help) usage; exit 0 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

[[ -f "$INPUT" ]] || { echo "ERROR: --input file not found: $INPUT"; exit 1; }
[[ -d "$LICENSE_DIR" ]] || { echo "ERROR: --license dir not found: $LICENSE_DIR"; exit 1; }
[[ -f "$LICENSE_DIR/license.txt" ]] || { echo "ERROR: $LICENSE_DIR/license.txt not found"; exit 1; }
[[ "$START_STAGE" -ge 1 && "$START_STAGE" -le 9 ]] || { echo "ERROR: --start must be 1-9"; exit 1; }

if [[ -z "$SUBJECT" ]]; then
    base=$(basename "$INPUT")
    SUBJECT="${base%.nii.gz}"
    SUBJECT="${SUBJECT%.nii}"
    SUBJECT="${SUBJECT%.*}"
    SUBJECT="${SUBJECT//_/-}"
fi

mkdir -p "$OUTPUT"
OUTPUT="$(cd "$OUTPUT" && pwd)"
INPUT="$(cd "$(dirname "$INPUT")" && pwd)/$(basename "$INPUT")"
LICENSE_DIR="$(cd "$LICENSE_DIR" && pwd)"

echo "============================================================"
echo "FreeSurfer 7 diagnostic run of FS8 reduced 54-command pipeline"
echo "Input:    $INPUT"
echo "Output:   $OUTPUT"
echo "Subject:  $SUBJECT"
echo "Threads:  $THREADS"
echo "Start:    stage $START_STAGE"
echo "Image:    mkdayyyy/mri-fs741:7.4.1-min"
echo "============================================================"

INNER_SCRIPT=$(mktemp /tmp/fs7_reduced54_XXXXXX.sh)

cat > "$INNER_SCRIPT" << 'INNERSCRIPT'
#!/bin/bash
set -euo pipefail

export SUBJECTS_DIR=/output/freesurfer

SUBJ="$1"
THR="$2"
START="$3"
SD="$SUBJECTS_DIR/$SUBJ"

mkdir -p "$SD"/{mri,surf,label,stats,tmp,scripts}
mkdir -p "$SD/mri/transforms"

if [[ -L "$SUBJECTS_DIR/fsaverage" ]]; then
    rm "$SUBJECTS_DIR/fsaverage"
fi
if [[ ! -e "$SUBJECTS_DIR/fsaverage" && -d "$FREESURFER_HOME/subjects/fsaverage" ]]; then
    ln -s "$FREESURFER_HOME/subjects/fsaverage" "$SUBJECTS_DIR/fsaverage"
fi

GCA="$FREESURFER_HOME/average/RB_all_2020-01-02.gca"
GCA_WITH_SKULL="$FREESURFER_HOME/average/RB_all_withskull_2020_01_02.gca"
SUBCORT_LUT="$FREESURFER_HOME/SubCorticalMassLUT.txt"
MNI305="$FREESURFER_HOME/average/mni305.cor.mgz"
if [[ -f "$FREESURFER_HOME/average/mni305.cor.stripped.mgz" ]]; then
    MNI305="$FREESURFER_HOME/average/mni305.cor.stripped.mgz"
fi

first_existing() {
    local pattern
    shopt -s nullglob
    for pattern in "$@"; do
        local matches=( $pattern )
        if [[ ${#matches[@]} -gt 0 ]]; then
            printf '%s\n' "${matches[0]}"
            return 0
        fi
    done
    return 1
}

LH_FOLDING_ATLAS=$(first_existing \
    "$FREESURFER_HOME/average/lh.folding.atlas.acfb40.noaparc.i12*.tif" \
    "$FREESURFER_HOME/average/lh.folding.atlas*.tif") || { echo "Missing lh folding atlas"; exit 1; }
RH_FOLDING_ATLAS=$(first_existing \
    "$FREESURFER_HOME/average/rh.folding.atlas.acfb40.noaparc.i12*.tif" \
    "$FREESURFER_HOME/average/rh.folding.atlas*.tif") || { echo "Missing rh folding atlas"; exit 1; }
LH_DK_ATLAS=$(first_existing \
    "$FREESURFER_HOME/average/lh.DKaparc.atlas.acfb40.noaparc.i12*.gcs" \
    "$FREESURFER_HOME/average/lh.DKaparc.atlas*.gcs") || { echo "Missing lh DKaparc atlas"; exit 1; }
RH_DK_ATLAS=$(first_existing \
    "$FREESURFER_HOME/average/rh.DKaparc.atlas.acfb40.noaparc.i12*.gcs" \
    "$FREESURFER_HOME/average/rh.DKaparc.atlas*.gcs") || { echo "Missing rh DKaparc atlas"; exit 1; }

echo "LH folding atlas: $LH_FOLDING_ATLAS"
echo "RH folding atlas: $RH_FOLDING_ATLAS"
echo "LH DK atlas:      $LH_DK_ATLAS"
echo "RH DK atlas:      $RH_DK_ATLAS"

log() { printf '[S%s C%s] %s\n' "$1" "$2" "$3"; }
run() {
    local stage="$1"
    local cid="$2"
    local command="$3"
    log "$stage" "$cid" "$command"
    eval "$command"
}
skip_stage() { printf '[S%s] SKIP (--start > %s)\n' "$1" "$1"; }

# Stage 1: Reorientation & Resize (commands 01-02)
stage=1
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "01" "mri_convert /input/image.nii.gz 001.mgz"
    run "$stage" "02" "mri_convert 001.mgz orig.mgz --conform"
else
    skip_stage "$stage"
fi

# Stage 2: FS7 Talairach, intensity prep, and skull stripping.
stage=2
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "03a" "mri_nu_correct.mni --no-rescale --i orig.mgz --o orig_nu.mgz --ants-n4 --n 1 --proto-iters 1000 --distance 50"
    run "$stage" "03b" "talairach_avi --i orig_nu.mgz --xfm transforms/talairach.auto.xfm"
    run "$stage" "03c" "cp transforms/talairach.auto.xfm transforms/talairach.xfm"
    run "$stage" "03d" "lta_convert --src orig.mgz --trg $MNI305 --inxfm transforms/talairach.xfm --outlta transforms/talairach.xfm.lta --subject fsaverage --ltavox2vox"
    run "$stage" "03e" "talairach_afd -T 0.005 -xfm transforms/talairach.xfm"
    run "$stage" "08" "mri_nu_correct.mni --i orig.mgz --o nu.mgz --uchar transforms/talairach.xfm --n 2 --ants-n4"
    run "$stage" "09" "mri_add_xform_to_header -c transforms/talairach.xfm nu.mgz nu.mgz"
    run "$stage" "10" "mri_normalize -g 1 -seed 1234 -mprage nu.mgz T1.mgz"
    run "$stage" "11a" "mri_em_register -skull nu.mgz $GCA_WITH_SKULL transforms/talairach_with_skull.lta"
    run "$stage" "11b" "mri_watershed -T1 -brain_atlas $GCA_WITH_SKULL transforms/talairach_with_skull.lta T1.mgz brainmask.auto.mgz"
    run "$stage" "11c" "cp brainmask.auto.mgz brainmask.mgz"
else
    skip_stage "$stage"
fi

# Stage 3: FS7 atlas-based subcortical segmentation.
stage=3
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "12" "mri_em_register -uns 3 -mask brainmask.mgz nu.mgz $GCA transforms/talairach.lta"
    run "$stage" "13" "mri_ca_normalize -c ctrl_pts.mgz -mask brainmask.mgz nu.mgz $GCA transforms/talairach.lta norm.mgz"
    run "$stage" "13a" "mri_ca_register -nobigventricles -T transforms/talairach.lta -align-after -mask brainmask.mgz norm.mgz $GCA transforms/talairach.m3z"
    run "$stage" "04a" "mri_ca_label -relabel_unlikely 9 .3 -prior 0.5 -align norm.mgz transforms/talairach.m3z $GCA aseg.auto_noCCseg.mgz"
    run "$stage" "04b" "mri_cc -aseg aseg.auto_noCCseg.mgz -o aseg.auto.mgz -lta transforms/cc_up.lta $SUBJ"
    run "$stage" "04c" "rm -f aseg.presurf.mgz; cp aseg.auto.mgz aseg.presurf.mgz"
else
    skip_stage "$stage"
fi

# Stage 4: Registration artifact validation. FS7 does not have fs-synthmorph-reg.
stage=4
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "05" "test -s transforms/talairach.xfm"
    run "$stage" "06" "test -s transforms/talairach.xfm.lta"
    run "$stage" "07" "test -s transforms/talairach.lta"
else
    skip_stage "$stage"
fi

# Stage 5: Final intensity normalization and brain mask for surfaces.
stage=5
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "14" "mri_normalize -seed 1234 -mprage -aseg aseg.presurf.mgz -mask brainmask.mgz norm.mgz brain.mgz"
    run "$stage" "15" "AntsDenoiseImageFs -i brain.mgz -o antsdn.brain.mgz"
    run "$stage" "25" "mri_mask -T 5 brain.mgz brainmask.mgz brain.finalsurfs.mgz"
else
    skip_stage "$stage"
fi

# Stage 6: WM Segmentation (commands 16-20)
stage=6
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "16" "mri_segment -wsizemm 13 -mprage antsdn.brain.mgz wm.seg.mgz"
    run "$stage" "17" "mri_edit_wm_with_aseg -keep-in wm.seg.mgz brain.mgz aseg.presurf.mgz wm.asegedit.mgz"
    run "$stage" "18" "mri_pretess wm.asegedit.mgz wm norm.mgz wm.mgz"
    run "$stage" "19" "mri_fill -a ../scripts/ponscc.cut.log -xform transforms/talairach.lta -segmentation aseg.presurf.mgz -ctab $SUBCORT_LUT wm.mgz filled.mgz"
    run "$stage" "20" "mri_pretess filled.mgz 255 norm.mgz filled-pretess255.mgz; mri_pretess filled.mgz 127 norm.mgz filled-pretess127.mgz"
else
    skip_stage "$stage"
fi

# Stage 7: FS7 initial surface reconstruction through white.preaparc.
stage=7
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "21" "mri_tessellate filled-pretess255.mgz 255 ../surf/lh.orig.nofix; mri_tessellate filled-pretess127.mgz 127 ../surf/rh.orig.nofix"
    run "$stage" "21a" "mris_extract_main_component ../surf/lh.orig.nofix ../surf/lh.orig.nofix; mris_extract_main_component ../surf/rh.orig.nofix ../surf/rh.orig.nofix"
    run "$stage" "22" "mris_smooth -nw -seed 1234 ../surf/lh.orig.nofix ../surf/lh.smoothwm.nofix; mris_smooth -nw -seed 1234 ../surf/rh.orig.nofix ../surf/rh.smoothwm.nofix"
    run "$stage" "23" "mris_inflate -no-save-sulc ../surf/lh.smoothwm.nofix ../surf/lh.inflated.nofix; mris_inflate -no-save-sulc ../surf/rh.smoothwm.nofix ../surf/rh.inflated.nofix"
    run "$stage" "24" "mris_sphere -q -p 6 -a 128 -seed 1234 ../surf/lh.inflated.nofix ../surf/lh.qsphere.nofix; mris_sphere -q -p 6 -a 128 -seed 1234 ../surf/rh.inflated.nofix ../surf/rh.qsphere.nofix"
    cd "$SD"
    run "$stage" "26" "mris_fix_topology -mgz -sphere qsphere.nofix -inflated inflated.nofix -orig orig.nofix -out orig.premesh -ga -seed 1234 $SUBJ lh"
    run "$stage" "33" "mris_fix_topology -mgz -sphere qsphere.nofix -inflated inflated.nofix -orig orig.nofix -out orig.premesh -ga -seed 1234 $SUBJ rh"
    run "$stage" "26a" "mris_euler_number surf/lh.orig.premesh; mris_euler_number surf/rh.orig.premesh"
    run "$stage" "27" "mris_remesh --remesh --iters 3 --input surf/lh.orig.premesh --output surf/lh.orig"
    run "$stage" "34" "mris_remesh --remesh --iters 3 --input surf/rh.orig.premesh --output surf/rh.orig"
    run "$stage" "28" "mris_remove_intersection surf/lh.orig surf/lh.orig; rm -f surf/lh.inflated"
    run "$stage" "35" "mris_remove_intersection surf/rh.orig surf/rh.orig; rm -f surf/rh.inflated"
    cd "$SD/mri"
    run "$stage" "29" "mris_autodet_gwstats --o ../surf/autodet.gw.stats.lh.dat --i brain.finalsurfs.mgz --wm wm.mgz --surf ../surf/lh.orig.premesh"
    run "$stage" "36" "mris_autodet_gwstats --o ../surf/autodet.gw.stats.rh.dat --i brain.finalsurfs.mgz --wm wm.mgz --surf ../surf/rh.orig.premesh"
    run "$stage" "30" "mris_place_surface --adgws-in ../surf/autodet.gw.stats.lh.dat --wm wm.mgz --threads 1 --invol brain.finalsurfs.mgz --lh --i ../surf/lh.orig --o ../surf/lh.white.preaparc --white --seg aseg.presurf.mgz --nsmooth 5"
    run "$stage" "37" "mris_place_surface --adgws-in ../surf/autodet.gw.stats.rh.dat --wm wm.mgz --threads 1 --invol brain.finalsurfs.mgz --rh --i ../surf/rh.orig --o ../surf/rh.white.preaparc --white --seg aseg.presurf.mgz --nsmooth 5"
    run "$stage" "30a" "mri_label2label --label-cortex ../surf/lh.white.preaparc aseg.presurf.mgz 0 ../label/lh.cortex.label"
    run "$stage" "30b" "mri_label2label --label-cortex ../surf/lh.white.preaparc aseg.presurf.mgz 1 ../label/lh.cortex+hipamyg.label"
    run "$stage" "37a" "mri_label2label --label-cortex ../surf/rh.white.preaparc aseg.presurf.mgz 0 ../label/rh.cortex.label"
    run "$stage" "37b" "mri_label2label --label-cortex ../surf/rh.white.preaparc aseg.presurf.mgz 1 ../label/rh.cortex+hipamyg.label"
else
    skip_stage "$stage"
fi

# Stage 8: FS7 surface registration and aparc annotation.
stage=8
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "40" "mris_smooth -n 3 -nw -seed 1234 ../surf/lh.white.preaparc ../surf/lh.smoothwm"
    run "$stage" "47" "mris_smooth -n 3 -nw -seed 1234 ../surf/rh.white.preaparc ../surf/rh.smoothwm"
    run "$stage" "41" "mris_inflate ../surf/lh.smoothwm ../surf/lh.inflated"
    run "$stage" "48" "mris_inflate ../surf/rh.smoothwm ../surf/rh.inflated"
    cd "$SD/surf"
    run "$stage" "41a" "mris_curvature -w -seed 1234 lh.white.preaparc; mris_curvature -seed 1234 -thresh .999 -n -a 5 -w -distances 10 10 lh.inflated"
    run "$stage" "48a" "mris_curvature -w -seed 1234 rh.white.preaparc; mris_curvature -seed 1234 -thresh .999 -n -a 5 -w -distances 10 10 rh.inflated"
    run "$stage" "42" "mris_sphere -seed 1234 lh.inflated lh.sphere"
    run "$stage" "49" "mris_sphere -seed 1234 rh.inflated rh.sphere"
    run "$stage" "43" "mris_register -curv lh.sphere $LH_FOLDING_ATLAS lh.sphere.reg; ln -sf lh.sphere.reg lh.fsaverage.sphere.reg"
    run "$stage" "50" "mris_register -curv rh.sphere $RH_FOLDING_ATLAS rh.sphere.reg; ln -sf rh.sphere.reg rh.fsaverage.sphere.reg"
    run "$stage" "43a" "mris_jacobian lh.white.preaparc lh.sphere.reg lh.jacobian_white; mrisp_paint -a 5 $LH_FOLDING_ATLAS#6 lh.sphere.reg lh.avg_curv"
    run "$stage" "50a" "mris_jacobian rh.white.preaparc rh.sphere.reg rh.jacobian_white; mrisp_paint -a 5 $RH_FOLDING_ATLAS#6 rh.sphere.reg rh.avg_curv"
    cd "$SD"
    run "$stage" "45" "mris_ca_label -l label/lh.cortex.label -aseg mri/aseg.presurf.mgz -seed 1234 $SUBJ lh surf/lh.sphere.reg $LH_DK_ATLAS label/lh.aparc.annot"
    run "$stage" "52" "mris_ca_label -l label/rh.cortex.label -aseg mri/aseg.presurf.mgz -seed 1234 $SUBJ rh surf/rh.sphere.reg $RH_DK_ATLAS label/rh.aparc.annot"
else
    skip_stage "$stage"
fi

# Stage 9: FS7 final white/pial surfaces, thickness, and stats.
stage=9
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "31" "mris_place_surface --adgws-in ../surf/autodet.gw.stats.lh.dat --seg aseg.presurf.mgz --threads 1 --wm wm.mgz --invol brain.finalsurfs.mgz --lh --i ../surf/lh.white.preaparc --o ../surf/lh.white --white --nsmooth 0 --rip-label ../label/lh.cortex.label --rip-bg --rip-surf ../surf/lh.white.preaparc --aparc ../label/lh.aparc.annot"
    run "$stage" "38" "mris_place_surface --adgws-in ../surf/autodet.gw.stats.rh.dat --seg aseg.presurf.mgz --threads 1 --wm wm.mgz --invol brain.finalsurfs.mgz --rh --i ../surf/rh.white.preaparc --o ../surf/rh.white --white --nsmooth 0 --rip-label ../label/rh.cortex.label --rip-bg --rip-surf ../surf/rh.white.preaparc --aparc ../label/rh.aparc.annot"
    run "$stage" "32a" "mris_place_surface --adgws-in ../surf/autodet.gw.stats.lh.dat --seg aseg.presurf.mgz --threads 1 --wm wm.mgz --invol brain.finalsurfs.mgz --lh --i ../surf/lh.white --o ../surf/lh.pial.T1 --pial --nsmooth 0 --rip-label ../label/lh.cortex+hipamyg.label --pin-medial-wall ../label/lh.cortex.label --aparc ../label/lh.aparc.annot --repulse-surf ../surf/lh.white --white-surf ../surf/lh.white; cd ../surf; ln -sf lh.pial.T1 lh.pial; cd ../mri"
    run "$stage" "39a" "mris_place_surface --adgws-in ../surf/autodet.gw.stats.rh.dat --seg aseg.presurf.mgz --threads 1 --wm wm.mgz --invol brain.finalsurfs.mgz --rh --i ../surf/rh.white --o ../surf/rh.pial.T1 --pial --nsmooth 0 --rip-label ../label/rh.cortex+hipamyg.label --pin-medial-wall ../label/rh.cortex.label --aparc ../label/rh.aparc.annot --repulse-surf ../surf/rh.white --white-surf ../surf/rh.white; cd ../surf; ln -sf rh.pial.T1 rh.pial; cd ../mri"
    run "$stage" "32" "mris_place_surface --curv-map ../surf/lh.white 2 10 ../surf/lh.curv; mris_place_surface --area-map ../surf/lh.white ../surf/lh.area; mris_place_surface --curv-map ../surf/lh.pial 2 10 ../surf/lh.curv.pial; mris_place_surface --area-map ../surf/lh.pial ../surf/lh.area.pial; mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness"
    run "$stage" "39" "mris_place_surface --curv-map ../surf/rh.white 2 10 ../surf/rh.curv; mris_place_surface --area-map ../surf/rh.white ../surf/rh.area; mris_place_surface --curv-map ../surf/rh.pial 2 10 ../surf/rh.curv.pial; mris_place_surface --area-map ../surf/rh.pial ../surf/rh.area.pial; mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness"
    cd "$SD"
    run "$stage" "46" "mris_anatomical_stats -th3 -mgz -cortex label/lh.cortex.label -f stats/lh.aparc.stats -b -a label/lh.aparc.annot -c label/aparc.annot.ctab $SUBJ lh white"
    run "$stage" "46p" "mris_anatomical_stats -th3 -mgz -cortex label/lh.cortex.label -f stats/lh.aparc.pial.stats -b -a label/lh.aparc.annot -c label/aparc.annot.ctab $SUBJ lh pial"
    run "$stage" "53" "mris_anatomical_stats -th3 -mgz -cortex label/rh.cortex.label -f stats/rh.aparc.stats -b -a label/rh.aparc.annot -c label/aparc.annot.ctab $SUBJ rh white"
    run "$stage" "53p" "mris_anatomical_stats -th3 -mgz -cortex label/rh.cortex.label -f stats/rh.aparc.pial.stats -b -a label/rh.aparc.annot -c label/aparc.annot.ctab $SUBJ rh pial"
    run "$stage" "54a" "mris_volmask --aseg_name aseg.presurf --label_left_white 2 --label_left_ribbon 3 --label_right_white 41 --label_right_ribbon 42 --save_ribbon $SUBJ"
    cd "$SD/mri"
    run "$stage" "54b" "mri_relabel_hypointensities aseg.presurf.mgz ../surf aseg.presurf.hypos.mgz"
    run "$stage" "54c" "mri_surf2volseg --o aseg.mgz --i aseg.presurf.hypos.mgz --fix-presurf-with-ribbon $SD/mri/ribbon.mgz --threads 1 --lh-cortex-mask $SD/label/lh.cortex.label --lh-white $SD/surf/lh.white --lh-pial $SD/surf/lh.pial --rh-cortex-mask $SD/label/rh.cortex.label --rh-white $SD/surf/rh.white --rh-pial $SD/surf/rh.pial"
    cd "$SD"
    run "$stage" "54" "mri_segstats --seed 1234 --seg mri/aseg.mgz --sum stats/aseg.stats --pv mri/norm.mgz --empty --brainmask mri/brainmask.mgz --brain-vol-from-seg --excludeid 0 --excl-ctxgmwm --supratent --subcortgray --in mri/norm.mgz --in-intensity-name norm --in-intensity-units MR --etiv --surf-wm-vol --surf-ctx-vol --totalgray --euler --ctab $FREESURFER_HOME/ASegStatsLUT.txt --subject $SUBJ"
else
    skip_stage "$stage"
fi

mkdir -p /output/stats
cp "$SD/stats/"*.stats /output/stats/ 2>/dev/null || true
cp "$SD/mri/aseg.auto.mgz" /output/stats/ 2>/dev/null || true
cp "$SD/mri/aseg.mgz" /output/stats/ 2>/dev/null || true

echo "============================================================"
echo "FreeSurfer 7 diagnostic run finished"
echo "Subject dir: /output/freesurfer/$SUBJ"
echo "Stats dir:   /output/stats"
echo "============================================================"
INNERSCRIPT

chmod +x "$INNER_SCRIPT"

set +e
docker run --rm \
    -v "$INPUT:/input/image.nii.gz:ro" \
    -v "$OUTPUT:/output" \
    -v "$LICENSE_DIR:/license:ro" \
    -v "$INNER_SCRIPT:/app/fs7_recon_style.sh:ro" \
    -e SUBJECTS_DIR=/output/freesurfer \
    -e FS_LICENSE=/license/license.txt \
    "mkdayyyy/mri-fs741:7.4.1-min" \
    /app/fs7_recon_style.sh "$SUBJECT" "$THREADS" "$START_STAGE"
DOCKER_EXIT=$?
set -e

rm -f "$INNER_SCRIPT"

if [[ $DOCKER_EXIT -eq 0 ]]; then
    echo "SUCCESS: $OUTPUT"
    echo "Subject dir: $OUTPUT/freesurfer/$SUBJECT"
    echo "Stats dir:   $OUTPUT/stats"
else
    echo "FAILED: Docker exited with code $DOCKER_EXIT"
fi

exit $DOCKER_EXIT
