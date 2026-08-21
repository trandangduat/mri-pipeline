#!/bin/bash
# Run one T1 image through the FastSurfer standalone flow, divided into 9 stages.
#
# Usage:
#   ./run_fastsurfer_standalone.sh --input <T1.nii.gz> --output <dir> [options]
#
# Options:
#   --input     FILE     Input T1 image (required)
#   --output    DIR      Output directory (default: ./fastsurfer_output)
#   --subject   ID       Subject ID (default: derived from filename)
#   --threads   N        CPU threads (default: 4)
#   --license   DIR      Directory containing license.txt (default: ./license)
#   --start     N        Start from stage N, 1-9 (default: 1)
#   --fastsurfer DIR     FastSurfer home directory (default: /fastsurfer or ./FastSurfer)
#   --help               Show this help

set -euo pipefail

INPUT=""
OUTPUT="$(pwd)/fastsurfer_output"
SUBJECT=""
THREADS=4
LICENSE_DIR="$(pwd)/license"
START_STAGE=1
FASTSURFER_HOME_ARG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --input) INPUT="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        --subject) SUBJECT="$2"; shift 2 ;;
        --threads) THREADS="$2"; shift 2 ;;
        --license) LICENSE_DIR="$2"; shift 2 ;;
        --start) START_STAGE="$2"; shift 2 ;;
        --fastsurfer) FASTSURFER_HOME_ARG="$2"; shift 2 ;;
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

if [[ -n "$FASTSURFER_HOME_ARG" ]]; then
    echo "Warning: --fastsurfer is ignored when running via Docker."
fi

echo "============================================================"
echo "FastSurfer standalone 9-stage pipeline"
echo "Input:      $INPUT"
echo "Output:     $OUTPUT"
echo "Subject:    $SUBJECT"
echo "Threads:    $THREADS"
echo "Start:      stage $START_STAGE"
echo "FastSurfer: duattran05/mri-fastsurfervinn:latest (Docker)"
echo "============================================================"

INNER_SCRIPT=$(mktemp /tmp/fastsurfer_standalone_XXXXXX.sh)

cat > "$INNER_SCRIPT" << 'INNERSCRIPT'
#!/bin/bash
set -euo pipefail

export SUBJECTS_DIR=/output/freesurfer
export FASTSURFER_HOME=/fastsurfer
export PYTHONPATH="$FASTSURFER_HOME${PYTHONPATH:+:$PYTHONPATH}"

export FREESURFER_HOME=/opt/freesurfer
if [[ -f "$FREESURFER_HOME/SetUpFreeSurfer.sh" ]]; then
    set +eu
    source "$FREESURFER_HOME/SetUpFreeSurfer.sh" >/dev/null
    set -eu
fi

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

log() { printf '[S%s C%s] %s\n' "$1" "$2" "$3"; }
run() {
    local stage="$1"
    local cid="$2"
    local command="$3"
    log "$stage" "$cid" "$command"
    eval "$command"
}
skip_stage() { printf '[S%s] SKIP (--start > %s)\n' "$1" "$1"; }

sync_synthseg_aliases() {
    cd "$SD/mri"
    [[ -f aparc.DKTatlas+aseg.deep.mgz ]] || return 0
    ln -sf aparc.DKTatlas+aseg.deep.mgz aseg.auto_noCCseg.mgz
    ln -sf aparc.DKTatlas+aseg.deep.mgz aseg.presurf.mgz
    ln -sf aparc.DKTatlas+aseg.deep.mgz aparc.DKTatlas+aseg.orig.mgz
}

# Stage 1: Reorientation & Resize (commands 01-02)
stage=1
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "01" "mri_convert /input/image.nii.gz 001.mgz"
    run "$stage" "02" "python3 $FASTSURFER_HOME/FastSurferCNN/data_loader/conform.py -i 001.mgz -o orig.mgz"
else
    skip_stage "$stage"
fi

# Stage 2: Brain Extraction (command 03)
stage=2
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "03" "echo 'Brain mask will be extracted automatically from FastSurferVINN segmentation in Stage 3'"
else
    skip_stage "$stage"
fi

# Stage 3: Subcortical Segmentation (command 04)
stage=3
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "04" "python3 $FASTSURFER_HOME/FastSurferCNN/run_prediction.py --t1 $SD/mri/orig.mgz --sid $SUBJ --sd $SUBJECTS_DIR --asegdkt_segfile $SD/mri/aparc.DKTatlas+aseg.deep.mgz --conformed_name $SD/mri/orig.mgz --brainmask_name $SD/mri/mask.mgz --aseg_name $SD/mri/aseg.auto_noCCseg.mgz --threads $THR"
    sync_synthseg_aliases
else
    skip_stage "$stage"
fi

# Stage 4: Template Registration (commands 05-06)
stage=4
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    run "$stage" "05" "python3 $FASTSURFER_HOME/recon_surf/N4_bias_correct.py --in orig.mgz --rescale orig_nu.mgz --aseg aparc.DKTatlas+aseg.orig.mgz --threads $THR"
    run "$stage" "06" "bash $FASTSURFER_HOME/recon_surf/talairach-reg.sh /dev/null --dir . --conformed_name orig.mgz --norm_name orig_nu.mgz --py python3 --asegdkt_segfile aparc.DKTatlas+aseg.orig.mgz --edits"
else
    skip_stage "$stage"
fi

# Stage 5: Image Standardization (commands 07-08)
stage=5
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    # Ensure aliases needed for FreeSurfer downstream tools are created
    [[ -f nu.mgz ]] || run "$stage" "07" "ln -sf orig_nu.mgz nu.mgz"
    run "$stage" "08" "mri_mask nu.mgz mask.mgz norm.mgz"
    run "$stage" "09" "mri_mask -T 5 norm.mgz mask.mgz brain.finalsurfs.mgz"
    run "$stage" "10" "ln -sf norm.mgz brainmask.mgz"
else
    skip_stage "$stage"
fi

# Stage 6: WM Segmentation & Fill (commands 09-10)
stage=6
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    # FastSurfer CC module to create aseg.auto.mgz
    run "$stage" "09" "python3 $FASTSURFER_HOME/CorpusCallosum/fastsurfer_cc.py --sd $SUBJECTS_DIR --sid $SUBJ --threads $THR --conformed_name $SD/mri/orig.mgz --aseg_name $SD/mri/aseg.auto_noCCseg.mgz --segmentation_in_orig $SD/mri/cc.mgz"
    run "$stage" "10" "python3 $FASTSURFER_HOME/CorpusCallosum/paint_cc_into_pred.py -in_cc $SD/mri/cc.mgz -in_pred $SD/mri/aparc.DKTatlas+aseg.orig.mgz -out $SD/mri/aparc.DKTatlas+aseg.deep.withCC.mgz -aseg $SD/mri/aseg.auto.mgz"
    # FastSurfer delegates WM segmentation and filled.mgz creation directly to recon-all
    run "$stage" "11" "recon-all -s $SUBJ -asegmerge -normalization2 -maskbfs -segmentation -fill -umask 0022 -threads $THR"
else
    skip_stage "$stage"
fi

# Stage 7: Surface Reconstruction (commands 10-27)
stage=7
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    # Left hemisphere
    run "$stage" "12" "mri_pretess filled.mgz 255 brain.mgz filled-pretess255.mgz"
    run "$stage" "13" "mri_mc filled-pretess255.mgz 255 ../surf/lh.orig.nofix"
    run "$stage" "12" "mris_extract_main_component ../surf/lh.orig.nofix ../surf/lh.orig.nofix"
    run "$stage" "13" "mris_smooth -n 10 -nw -seed 1234 ../surf/lh.orig.nofix ../surf/lh.smoothwm.nofix"
    run "$stage" "14" "mris_inflate -no-save-sulc ../surf/lh.smoothwm.nofix ../surf/lh.inflated.nofix"
    run "$stage" "15" "python3 $FASTSURFER_HOME/recon_surf/spherically_project.py -i ../surf/lh.inflated.nofix -o ../surf/lh.qsphere.nofix || mris_sphere -q -p 6 -a 128 -seed 1234 ../surf/lh.inflated.nofix ../surf/lh.qsphere.nofix"
    run "$stage" "16" "cp ../surf/lh.orig.nofix ../surf/lh.orig"
    run "$stage" "17" "mris_autodet_gwstats --o ../surf/autodet.gw.stats.lh.dat --i brain.finalsurfs.mgz --wm wm.mgz --surf ../surf/lh.orig"
    run "$stage" "18" "mris_place_surface --adgws-in ../surf/autodet.gw.stats.lh.dat --wm wm.mgz --threads 1 --invol brain.finalsurfs.mgz --lh --i ../surf/lh.orig --o ../surf/lh.white --white --seg aseg.presurf.mgz --max-cbv-dist 3.5"
    run "$stage" "19" "mris_place_surface --adgws-in ../surf/autodet.gw.stats.lh.dat --seg aseg.presurf.mgz --threads 1 --wm wm.mgz --invol brain.finalsurfs.mgz --lh --i ../surf/lh.white --o ../surf/lh.pial --pial --nsmooth 0 --repulse-surf ../surf/lh.white --white-surf ../surf/lh.white"
    run "$stage" "20" "mris_place_surface --thickness ../surf/lh.white ../surf/lh.pial 20 5 ../surf/lh.thickness"
    
    # Right hemisphere
    run "$stage" "21" "mri_pretess filled.mgz 127 brain.mgz filled-pretess127.mgz"
    run "$stage" "22" "mri_mc filled-pretess127.mgz 127 ../surf/rh.orig.nofix"
    run "$stage" "23" "mris_extract_main_component ../surf/rh.orig.nofix ../surf/rh.orig.nofix"
    run "$stage" "24" "mris_smooth -n 10 -nw -seed 1234 ../surf/rh.orig.nofix ../surf/rh.smoothwm.nofix"
    run "$stage" "25" "mris_inflate -no-save-sulc ../surf/rh.smoothwm.nofix ../surf/rh.inflated.nofix"
    run "$stage" "26" "python3 $FASTSURFER_HOME/recon_surf/spherically_project.py -i ../surf/rh.inflated.nofix -o ../surf/rh.qsphere.nofix || mris_sphere -q -p 6 -a 128 -seed 1234 ../surf/rh.inflated.nofix ../surf/rh.qsphere.nofix"
    run "$stage" "27" "cp ../surf/rh.orig.nofix ../surf/rh.orig"
    run "$stage" "28" "mris_autodet_gwstats --o ../surf/autodet.gw.stats.rh.dat --i brain.finalsurfs.mgz --wm wm.mgz --surf ../surf/rh.orig"
    run "$stage" "29" "mris_place_surface --adgws-in ../surf/autodet.gw.stats.rh.dat --wm wm.mgz --threads 1 --invol brain.finalsurfs.mgz --rh --i ../surf/rh.orig --o ../surf/rh.white --white --seg aseg.presurf.mgz --max-cbv-dist 3.5"
    run "$stage" "30" "mris_place_surface --adgws-in ../surf/autodet.gw.stats.rh.dat --seg aseg.presurf.mgz --threads 1 --wm wm.mgz --invol brain.finalsurfs.mgz --rh --i ../surf/rh.white --o ../surf/rh.pial --pial --nsmooth 0 --repulse-surf ../surf/rh.white --white-surf ../surf/rh.white"
    run "$stage" "31" "mris_place_surface --thickness ../surf/rh.white ../surf/rh.pial 20 5 ../surf/rh.thickness"
else
    skip_stage "$stage"
fi

# Stage 8: Surface Registration (commands 34-39)
stage=8
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    ln -sf ../surf/lh.white ../surf/lh.white.preaparc
    ln -sf ../surf/rh.white ../surf/rh.white.preaparc
    run "$stage" "34" "recon-all -subject $SUBJ -hemi lh -cortex-label -smooth2 -inflate2 -curvHK -sphere -no-isrunning" || true
    run "$stage" "35" "recon-all -subject $SUBJ -hemi rh -cortex-label -smooth2 -inflate2 -curvHK -sphere -no-isrunning" || true
    run "$stage" "36" "mris_register -curv -norot ../surf/lh.qsphere.nofix \$LH_FOLDING_ATLAS ../surf/lh.sphere.reg" || true
    run "$stage" "37" "mris_jacobian ../surf/lh.white ../surf/lh.sphere.reg ../surf/lh.jacobian_white" || true
    run "$stage" "38" "mris_register -curv -norot ../surf/rh.qsphere.nofix \$RH_FOLDING_ATLAS ../surf/rh.sphere.reg" || true
    run "$stage" "39" "mris_jacobian ../surf/rh.white ../surf/rh.sphere.reg ../surf/rh.jacobian_white" || true
else
    skip_stage "$stage"
fi

# Stage 9: Statistics & Atlas Mapping (commands 40-43)
stage=9
if [[ $START -le $stage ]]; then
    cd "$SD/mri"
    mkdir -p ../label ../stats
    run "$stage" "40" "mris_ca_label -aseg aseg.presurf.mgz -seed 1234 $SUBJ lh ../surf/lh.sphere.reg \$LH_DK_ATLAS ../label/lh.aparc.annot" || true
    run "$stage" "41" "mris_anatomical_stats -th3 -mgz -f ../stats/lh.aparc.stats -b -a ../label/lh.aparc.annot -c ../label/aparc.annot.ctab $SUBJ lh white" || true
    run "$stage" "42" "mris_ca_label -aseg aseg.presurf.mgz -seed 1234 $SUBJ rh ../surf/rh.sphere.reg \$RH_DK_ATLAS ../label/rh.aparc.annot" || true
    run "$stage" "43" "mris_anatomical_stats -th3 -mgz -f ../stats/rh.aparc.stats -b -a ../label/rh.aparc.annot -c ../label/aparc.annot.ctab $SUBJ rh white" || true
else
    skip_stage "$stage"
fi

INNERSCRIPT
chmod +x "$INNER_SCRIPT"

# Execute inner script via Docker
echo "Starting inner script execution via Docker..."
set +e
docker run --rm --entrypoint /bin/bash \
    -v "$INPUT:/input/image.nii.gz:ro" \
    -v "$OUTPUT:/output" \
    -v "$LICENSE_DIR:/license:ro" \
    -v "$INNER_SCRIPT:/app/fastsurfer_standalone.sh:ro" \
    -e SUBJECTS_DIR=/output/freesurfer \
    -e FS_LICENSE=/license/license.txt \
    "duattran05/mri-fastsurfervinn:latest" \
    /app/fastsurfer_standalone.sh "$SUBJECT" "$THREADS" "$START_STAGE"
res=$?
set -e

rm -f "$INNER_SCRIPT"

if [[ $res -eq 0 ]]; then
    echo "============================================================"
    echo "FastSurfer pipeline completed successfully!"
    echo "Outputs are in: $OUTPUT/freesurfer/$SUBJECT"
    echo "============================================================"
else
    echo "============================================================"
    echo "Pipeline FAILED with exit code $res"
    echo "============================================================"
    exit $res
fi
