#!/bin/bash
# Run one T1 image through the reduced 54-command FreeSurfer 8 standalone flow.
# This intentionally follows the "Rut gon 54 lenh" sheet, not the full 120-command sheet.
#
# Usage:
#   ./run_fs8_standalone.sh --input <T1.nii.gz> --output <dir> [options]
#
# Options:
#   --input     FILE     Input T1 image (required)
#   --output    DIR      Output directory (default: ./fs8_output)
#   --subject   ID       Subject ID (default: derived from filename)
#   --threads   N        CPU threads (default: 4)
#   --license   DIR      Directory containing license.txt (default: ./license)
#   --start     N        Start from stage N, 1-9 (default: 1)
#   --help               Show this help

set -euo pipefail

INPUT=""
OUTPUT="$(pwd)/fs8_output"
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
        --help) sed -n '/^# /,/^$/p' "$0" | sed 's/^# //'; exit 0 ;;
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
echo "FreeSurfer 8 reduced 54-command pipeline"
echo "Input:    $INPUT"
echo "Output:   $OUTPUT"
echo "Subject:  $SUBJECT"
echo "Threads:  $THREADS"
echo "Start:    stage $START_STAGE"
echo "============================================================"

INNER_SCRIPT=$(mktemp /tmp/fs8_reduced54_XXXXXX.sh)

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

# Minimal file aliases required by the reduced sheet outputs. These are not
# FreeSurfer processing commands and are not counted as C01-C54.
sync_synthseg_aliases() {
    cd "$SD/mri"
    [[ -f synthseg.rca.mgz ]] || return 0
    ln -sf synthseg.rca.mgz aseg.auto.mgz
    ln -sf synthseg.rca.mgz aseg.auto_noCCseg.mgz
    ln -sf synthseg.rca.mgz aseg.presurf.mgz
}

make_talairach_fallback() {
    cd "$SD/mri"
    if [[ ! -s transforms/aff.lta ]]; then
        lta_convert --inlta identity.nofile --src orig.mgz --trg orig.mgz --outlta transforms/aff.lta --subject "$SUBJ"
    fi
}

# Stage 1: Reorientation & Resize (commands 01-02)
stage=1
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "01" "mri_convert /input/image.nii.gz 001.mgz"
    run "$stage" "02" "mri_convert 001.mgz orig.mgz --conform"
else
    skip_stage "$stage"
fi

# Stage 2: Brain Extraction (command 03)
stage=2
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "03" "mri_synthstrip --threads $THR -i orig.mgz -o synthstrip.mgz"
else
    skip_stage "$stage"
fi

# Stage 3: Subcortical Segmentation (command 04)
stage=3
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "04" "mri_synthseg --i orig.mgz --o synthseg.rca.mgz --threads $THR --vol synthseg.vol.csv --keepgeom --addctab --cpu"
    sync_synthseg_aliases
else
    skip_stage "$stage"
fi

# Stage 4: Template Registration (commands 05-07)
stage=4
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "05" "fs-synthmorph-reg --i synthstrip.mgz --t $MNI305 --affine-only --o transforms/synthmorph.mni305 --threads $THR"
    for candidate in transforms/synthmorph.mni305/aff.lta transforms/synthmorph.mni305/*aff*.lta; do
        if [[ -f "$candidate" ]]; then
            cp "$candidate" transforms/aff.lta
            break
        fi
    done
    run "$stage" "06" "make_talairach_fallback; lta_convert --inlta transforms/aff.lta --outmni transforms/talairach.xfm --src synthstrip.mgz --trg $MNI305 || cp transforms/aff.lta transforms/talairach.xfm"
    run "$stage" "07" "lta_convert --inlta transforms/aff.lta --outlta transforms/talairach.lta --src synthstrip.mgz --trg $MNI305"
else
    skip_stage "$stage"
fi

# Stage 5: Image Standardization (commands 08-15 and 25)
stage=5
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    sync_synthseg_aliases
    run "$stage" "08" "mri_nu_correct.mni --i orig.mgz --o nu.mgz --uchar transforms/talairach.xfm --n 2 --ants-n4"
    run "$stage" "09" "mri_add_xform_to_header -c transforms/talairach.xfm nu.mgz nu.mgz"
    run "$stage" "10" "mri_normalize -g 1 -seed 1234 -mprage nu.mgz T1.mgz"
    run "$stage" "11" "mri_mask T1.mgz synthstrip.mgz brainmask.mgz"
    run "$stage" "12" "mri_em_register -uns 3 -mask brainmask.mgz nu.mgz $GCA transforms/talairach.lta"
    run "$stage" "13" "mri_ca_normalize -c ctrl_pts.mgz -mask brainmask.mgz nu.mgz $GCA transforms/talairach.lta norm.mgz"
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
    sync_synthseg_aliases
    run "$stage" "16" "mri_segment -wsizemm 13 -mprage antsdn.brain.mgz wm.seg.mgz"
    run "$stage" "17" "mri_edit_wm_with_aseg -fill-seg-wm -fix-scm-ha 1 wm.seg.mgz brain.mgz aseg.presurf.mgz wm.asegedit.mgz"
    run "$stage" "18" "mri_pretess wm.asegedit.mgz wm norm.mgz wm.mgz"
    run "$stage" "19" "mri_fill -a ponscc.cut.log -xform transforms/talairach.lta -segmentation aseg.presurf.mgz wm.mgz filled.mgz"
    run "$stage" "20" "mri_pretess filled.mgz 255 norm.mgz filled-pretess255.mgz; mri_pretess filled.mgz 127 norm.mgz filled-pretess127.mgz"
else
    skip_stage "$stage"
fi

# Stage 7: Surface Reconstruction (commands 21-39)
stage=7
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "21" "mri_tessellate filled-pretess255.mgz 255 ../surf/lh.orig.nofix; mri_tessellate filled-pretess127.mgz 127 ../surf/rh.orig.nofix"
    run "$stage" "22" "mris_smooth -nw -seed 1234 ../surf/lh.orig.nofix ../surf/lh.smoothwm.nofix; mris_smooth -nw -seed 1234 ../surf/rh.orig.nofix ../surf/rh.smoothwm.nofix"
    run "$stage" "23" "mris_inflate -no-save-sulc ../surf/lh.smoothwm.nofix ../surf/lh.inflated.nofix; mris_inflate -no-save-sulc ../surf/rh.smoothwm.nofix ../surf/rh.inflated.nofix"
    run "$stage" "24" "mris_sphere -q -p 6 -a 128 -seed 1234 ../surf/lh.inflated.nofix ../surf/lh.qsphere.nofix; mris_sphere -q -p 6 -a 128 -seed 1234 ../surf/rh.inflated.nofix ../surf/rh.qsphere.nofix"
    cd "$SD"
    run "$stage" "26" "mris_fix_topology -threads 1 -mgz -sphere qsphere.nofix -inflated inflated.nofix -orig orig.nofix -out orig.premesh -ga -seed 1234 $SUBJ lh"
    run "$stage" "27" "mris_remesh --remesh --iters 3 --input surf/lh.orig.premesh --output surf/lh.orig"
    run "$stage" "28" "mris_remove_intersection surf/lh.orig surf/lh.orig"
    run "$stage" "29" "mris_autodet_gwstats --o surf/autodet.gw.stats.lh.dat --i mri/brain.finalsurfs.mgz --wm mri/wm.mgz --surf surf/lh.orig"
    cd "$SD/mri"
    run "$stage" "30" "mris_place_surface --adgws-in ../surf/autodet.gw.stats.lh.dat --wm wm.mgz --threads 1 --invol brain.finalsurfs.mgz --lh --i ../surf/lh.orig --o ../surf/lh.white --white --seg aseg.presurf.mgz --nsmooth 5 --restore-255 --rip-bg-no-annot --rip-bg --rip-bg-lof --outvol mrisps.wpa.lh.mgz"
    run "$stage" "31" "mris_place_surface --adgws-in ../surf/autodet.gw.stats.lh.dat --seg aseg.presurf.mgz --threads 1 --wm wm.mgz --invol brain.finalsurfs.mgz --lh --i ../surf/lh.white --o ../surf/lh.pial --pial --nsmooth 0 --repulse-surf ../surf/lh.white --white-surf ../surf/lh.white --restore-255"
    run "$stage" "32" "mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness"
    cd "$SD"
    run "$stage" "33" "mris_fix_topology -threads 1 -mgz -sphere qsphere.nofix -inflated inflated.nofix -orig orig.nofix -out orig.premesh -ga -seed 1234 $SUBJ rh"
    run "$stage" "34" "mris_remesh --remesh --iters 3 --input surf/rh.orig.premesh --output surf/rh.orig"
    run "$stage" "35" "mris_remove_intersection surf/rh.orig surf/rh.orig"
    run "$stage" "36" "mris_autodet_gwstats --o surf/autodet.gw.stats.rh.dat --i mri/brain.finalsurfs.mgz --wm mri/wm.mgz --surf surf/rh.orig"
    cd "$SD/mri"
    run "$stage" "37" "mris_place_surface --adgws-in ../surf/autodet.gw.stats.rh.dat --wm wm.mgz --threads 1 --invol brain.finalsurfs.mgz --rh --i ../surf/rh.orig --o ../surf/rh.white --white --seg aseg.presurf.mgz --nsmooth 5 --restore-255 --rip-bg-no-annot --rip-bg --rip-bg-lof --outvol mrisps.wpa.rh.mgz"
    run "$stage" "38" "mris_place_surface --adgws-in ../surf/autodet.gw.stats.rh.dat --seg aseg.presurf.mgz --threads 1 --wm wm.mgz --invol brain.finalsurfs.mgz --rh --i ../surf/rh.white --o ../surf/rh.pial --pial --nsmooth 0 --repulse-surf ../surf/rh.white --white-surf ../surf/rh.white --restore-255"
    run "$stage" "39" "mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness"
else
    skip_stage "$stage"
fi

# Stage 8: Surface Registration (commands 40-43 and 47-50)
stage=8
if [[ $START -le $stage ]]; then
    cd "$SD"
    run "$stage" "40" "mris_smooth -n 3 -nw -seed 1234 surf/lh.white surf/lh.smoothwm"
    run "$stage" "41" "mris_inflate surf/lh.smoothwm surf/lh.inflated"
    run "$stage" "42" "mris_sphere -threads $THR -seed 1234 surf/lh.inflated surf/lh.sphere"
    run "$stage" "43" "mris_register -curv -threads $THR surf/lh.sphere $LH_FOLDING_ATLAS surf/lh.sphere.reg"
    run "$stage" "47" "mris_smooth -n 3 -nw -seed 1234 surf/rh.white surf/rh.smoothwm"
    run "$stage" "48" "mris_inflate surf/rh.smoothwm surf/rh.inflated"
    run "$stage" "49" "mris_sphere -threads $THR -seed 1234 surf/rh.inflated surf/rh.sphere"
    run "$stage" "50" "mris_register -curv -threads $THR surf/rh.sphere $RH_FOLDING_ATLAS surf/rh.sphere.reg"
else
    skip_stage "$stage"
fi

# Stage 9: Statistics & Atlas Mapping (commands 44-46, 51-54)
stage=9
if [[ $START -le $stage ]]; then
    cd "$SD"
    run "$stage" "44" "mri_label2label --srcsubject fsaverage --srclabel $FREESURFER_HOME/subjects/fsaverage/label/lh.cortex.label --trgsubject $SUBJ --trglabel label/lh.cortex.label --hemi lh --regmethod surface"
    run "$stage" "45" "mris_ca_label -l label/lh.cortex.label -aseg mri/aseg.presurf.mgz -seed 1234 $SUBJ lh surf/lh.sphere.reg $LH_DK_ATLAS label/lh.aparc.annot"
    run "$stage" "46" "mris_anatomical_stats -a label/lh.aparc.annot -f stats/lh.aparc.stats $SUBJ lh"
    run "$stage" "51" "mri_label2label --srcsubject fsaverage --srclabel $FREESURFER_HOME/subjects/fsaverage/label/rh.cortex.label --trgsubject $SUBJ --trglabel label/rh.cortex.label --hemi rh --regmethod surface"
    run "$stage" "52" "mris_ca_label -l label/rh.cortex.label -aseg mri/aseg.presurf.mgz -seed 1234 $SUBJ rh surf/rh.sphere.reg $RH_DK_ATLAS label/rh.aparc.annot"
    run "$stage" "53" "mris_anatomical_stats -a label/rh.aparc.annot -f stats/rh.aparc.stats $SUBJ rh"
    run "$stage" "54" "mri_segstats --seg mri/aseg.auto.mgz --sum stats/aseg.stats --ctab $FREESURFER_HOME/ASegStatsLUT.txt || mri_segstats --seg mri/aseg.auto.mgz --sum stats/aseg.stats"
else
    skip_stage "$stage"
fi

mkdir -p /output/stats
cp "$SD/stats/"*.stats /output/stats/ 2>/dev/null || true
cp "$SD/mri/synthseg.vol.csv" /output/stats/ 2>/dev/null || true

echo "============================================================"
echo "FreeSurfer 8 reduced 54-command pipeline finished"
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
    -v "$INNER_SCRIPT:/app/fs8_reduced54.sh:ro" \
    -e SUBJECTS_DIR=/output/freesurfer \
    -e FS_LICENSE=/license/license.txt \
    "mkdayyyy/mri-fs8-all:latest" \
    /app/fs8_reduced54.sh "$SUBJECT" "$THREADS" "$START_STAGE"
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
