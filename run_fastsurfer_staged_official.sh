#!/bin/bash
# Run one T1 image through a staged FastSurfer flow using the official
# FastSurfer recon_surf commands as the source of truth.
#
# Usage:
#   ./run_fastsurfer_staged_official.sh --input <T1.nii.gz> --output <dir> [options]
#
# Options:
#   --input     FILE     Input T1 image (required)
#   --output    DIR      Output directory (default: ./fastsurfer_staged_output)
#   --subject   ID       Subject ID (default: derived from filename)
#   --threads   N        CPU threads (default: 4)
#   --license   DIR      Directory containing license.txt (default: ./license)
#   --image     IMAGE    Docker image (default: duattran05/mri-fastsurfervinn:latest)
#   --device    DEVICE   FastSurferVINN device: auto, cpu, cuda, cuda:0... (default: auto)
#   --start     N        Start from stage N, 1-9 (default: 1)
#   --stop      N        Stop after stage N, 1-9 (default: 9)
#   --help               Show this help

set -euo pipefail

INPUT=""
OUTPUT="$(pwd)/fastsurfer_staged_output"
SUBJECT=""
THREADS=4
LICENSE_DIR="$(pwd)/license"
IMAGE="duattran05/mri-fastsurfervinn:latest"
DEVICE="auto"
START_STAGE=1
STOP_STAGE=9

while [[ $# -gt 0 ]]; do
    case "$1" in
        --input) INPUT="${2:-}"; shift 2 ;;
        --output) OUTPUT="${2:-}"; shift 2 ;;
        --subject) SUBJECT="${2:-}"; shift 2 ;;
        --threads) THREADS="${2:-}"; shift 2 ;;
        --license) LICENSE_DIR="${2:-}"; shift 2 ;;
        --image) IMAGE="${2:-}"; shift 2 ;;
        --device) DEVICE="${2:-}"; shift 2 ;;
        --start) START_STAGE="${2:-}"; shift 2 ;;
        --stop) STOP_STAGE="${2:-}"; shift 2 ;;
        --help) sed -n '/^# /,/^$/p' "$0" | sed -e 's/^# //' -e 's/^#$//'; exit 0 ;;
        *) echo "ERROR: Unknown argument: $1"; exit 1 ;;
    esac
done

[[ -f "$INPUT" ]] || { echo "ERROR: --input file not found: $INPUT"; exit 1; }
[[ -d "$LICENSE_DIR" ]] || { echo "ERROR: --license dir not found: $LICENSE_DIR"; exit 1; }
[[ -f "$LICENSE_DIR/license.txt" ]] || { echo "ERROR: $LICENSE_DIR/license.txt not found"; exit 1; }
[[ "$THREADS" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: --threads must be a positive integer"; exit 1; }
[[ "$START_STAGE" =~ ^[1-9]$ ]] || { echo "ERROR: --start must be 1-9"; exit 1; }
[[ "$STOP_STAGE" =~ ^[1-9]$ ]] || { echo "ERROR: --stop must be 1-9"; exit 1; }
[[ "$START_STAGE" -le "$STOP_STAGE" ]] || { echo "ERROR: --start must be <= --stop"; exit 1; }

if [[ -z "$SUBJECT" ]]; then
    base=$(basename "$INPUT")
    SUBJECT="${base%.nii.gz}"
    SUBJECT="${SUBJECT%.nii}"
    SUBJECT="${SUBJECT%.*}"
    SUBJECT="${SUBJECT//_/-}"
fi

[[ "$SUBJECT" =~ ^[A-Za-z0-9._-]+$ ]] || {
    echo "ERROR: --subject may only contain letters, numbers, '.', '_' and '-'"
    exit 1
}
[[ "$SUBJECT" != "subject" ]] || { echo "ERROR: --subject cannot be 'subject'"; exit 1; }

mkdir -p "$OUTPUT"
OUTPUT="$(cd "$OUTPUT" && pwd)"
INPUT="$(cd "$(dirname "$INPUT")" && pwd)/$(basename "$INPUT")"
LICENSE_DIR="$(cd "$LICENSE_DIR" && pwd)"

INNER_SCRIPT=$(mktemp /tmp/fastsurfer_staged_official_XXXXXX.sh)
trap 'rm -f "$INNER_SCRIPT"' EXIT

cat > "$INNER_SCRIPT" << 'INNERSCRIPT'
#!/bin/bash
set -euo pipefail

SUBJ="$1"
THR="$2"
START="$3"
STOP="$4"
DEVICE="$5"

export SUBJECTS_DIR=/output/freesurfer
export FASTSURFER_HOME=${FASTSURFER_HOME:-/fastsurfer}
if [[ -z "${FREESURFER_HOME:-}" ]]; then
    if [[ -d /opt/freesurfer ]]; then
        FREESURFER_HOME=/opt/freesurfer
    elif [[ -d /usr/local/freesurfer ]]; then
        FREESURFER_HOME=/usr/local/freesurfer
    elif [[ -d /freesurfer ]]; then
        FREESURFER_HOME=/freesurfer
    else
        FREESURFER_HOME=/opt/freesurfer
    fi
fi
export FREESURFER_HOME
export FS_LICENSE=${FS_LICENSE:-/license/license.txt}
export PYTHONUNBUFFERED=${PYTHONUNBUFFERED:-0}
export PYTHONPATH="$FASTSURFER_HOME${PYTHONPATH:+:$PYTHONPATH}"
export FREESURFER="$FREESURFER_HOME"

PY=(python3 -s)
SD="$SUBJECTS_DIR/$SUBJ"
MDIR="$SD/mri"
SDIR="$SD/surf"
LDIR="$SD/label"
STATSDIR="$SD/stats"
SCRIPTDIR="$SD/scripts"
LF="$SCRIPTDIR/fastsurfer-staged-official.log"

if [[ -f "$FREESURFER_HOME/SetUpFreeSurfer.sh" ]]; then
    set +eu
    source "$FREESURFER_HOME/SetUpFreeSurfer.sh" >/dev/null
    set -eu
fi

mkdir -p "$MDIR/transforms" "$MDIR/tmp" "$SDIR" "$LDIR" "$STATSDIR" "$SCRIPTDIR" /output/stats
touch "$LF"

log() { printf '[S%s] %s\n' "$1" "$2" | tee -a "$LF"; }
run_cmd() {
    local stage="$1"
    shift
    log "$stage" "+ $*"
    "$@" 2>&1 | tee -a "$LF"
    local status=${PIPESTATUS[0]}
    if [[ "$status" -ne 0 ]]; then
        log "$stage" "ERROR: command failed with exit code $status"
        exit "$status"
    fi
}
require_file() {
    local stage="$1"
    local file="$2"
    if [[ ! -s "$file" ]]; then
        log "$stage" "ERROR: required output missing or empty: $file"
        exit 1
    fi
}
should_run() { [[ "$START" -le "$1" && "$STOP" -ge "$1" ]]; }
skip_stage() { log "$1" "SKIP"; }

check_runtime() {
    local missing=0
    for path in \
        "$FASTSURFER_HOME/FastSurferCNN/run_prediction.py" \
        "$FASTSURFER_HOME/CorpusCallosum/fastsurfer_cc.py" \
        "$FASTSURFER_HOME/recon_surf/recon-surf.sh" \
        "$FASTSURFER_HOME/recon_surf/talairach-reg.sh" \
        "$FASTSURFER_HOME/recon_surf/rotate_sphere.py" \
        "$FREESURFER_HOME/subjects/fsaverage" \
        "$FS_LICENSE"
    do
        if [[ ! -e "$path" ]]; then
            log 0 "ERROR: runtime path missing: $path"
            missing=1
        fi
    done
    for tool in recon-all mri_convert mri_mask mris_register mri_surf2volseg; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            log 0 "ERROR: command not found in container PATH: $tool"
            missing=1
        fi
    done
    [[ "$missing" -eq 0 ]] || exit 1
}

check_runtime

add_fs_flags() {
    local -n out=$1
    [[ -n "${HIRESFLAG:-}" ]] && out+=("$HIRESFLAG")
    if [[ "${THREAD_FLAGS_READY:-false}" == "true" ]]; then
        out+=("${FSTHREADS[@]}")
    fi
}

init_recon_state() {
    mkdir -p "$MDIR/transforms" "$MDIR/tmp" "$SDIR" "$LDIR" "$STATSDIR" "$SCRIPTDIR"
    if [[ -L "$SUBJECTS_DIR/fsaverage" ]]; then
        rm "$SUBJECTS_DIR/fsaverage"
    fi
    if [[ ! -e "$SUBJECTS_DIR/fsaverage" && -d "$FREESURFER_HOME/subjects/fsaverage" ]]; then
        ln -s "$FREESURFER_HOME/subjects/fsaverage" "$SUBJECTS_DIR/fsaverage"
    fi

    if [[ -s "$MDIR/orig.mgz" ]]; then
        VOX_SIZE=$("${PY[@]}" -c "from nibabel import load; print(load('$MDIR/orig.mgz').header.get_zooms()[0])")
    else
        VOX_SIZE=1
    fi
    if "${PY[@]}" -c "import sys; sys.exit(0 if float('$VOX_SIZE') < 0.999 else 1)"; then
        HIRESFLAG="-hires"
        NOCONFORM_IF_HIRES=(-noconform)
        HIRES_SURFACE_SUFFIX=".predec"
    else
        HIRESFLAG=""
        NOCONFORM_IF_HIRES=()
        HIRES_SURFACE_SUFFIX=""
    fi

    FSTHREADS=()
    if [[ "$THR" -gt 1 ]]; then
        FSTHREADS=(-threads "$THR" -itkthreads "$THR")
    fi
    THREAD_FLAGS_READY=true

    if [[ "$THR" -gt 1 ]]; then
        PARALLEL_HEMI=true
        THREADS_HEMI=$((THR / 2))
        [[ "$THREADS_HEMI" -lt 1 ]] && THREADS_HEMI=1
    else
        PARALLEL_HEMI=false
        THREADS_HEMI=1
    fi
    FSTHREADS_HEMI=()
    if [[ "$THREADS_HEMI" -gt 1 ]]; then
        FSTHREADS_HEMI=(-threads "$THREADS_HEMI" -itkthreads "$THREADS_HEMI")
    fi
}

stage1() {
    local stage=1
    log "$stage" "Reorientation and conform"
    run_cmd "$stage" mri_convert /input/image.nii.gz "$MDIR/001.mgz"
    run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/FastSurferCNN/data_loader/conform.py" -i "$MDIR/001.mgz" -o "$MDIR/orig.mgz"
    require_file "$stage" "$MDIR/orig.mgz"
}

stage2() {
    local stage=2
    log "$stage" "Brain mask is produced by FastSurferVINN in stage 3"
}

stage3() {
    local stage=3
    log "$stage" "FastSurferVINN segmentation and Corpus Callosum prerequisite"
    require_file "$stage" "$MDIR/orig.mgz"

    local device_args=()
    if [[ "$DEVICE" != "auto" ]]; then
        device_args=(--device "$DEVICE")
    fi
    run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/FastSurferCNN/run_prediction.py" \
        --t1 "$MDIR/orig.mgz" \
        --sid "$SUBJ" \
        --sd "$SUBJECTS_DIR" \
        --asegdkt_segfile "$MDIR/aparc.DKTatlas+aseg.deep.mgz" \
        --conformed_name "$MDIR/orig.mgz" \
        --brainmask_name "$MDIR/mask.mgz" \
        --aseg_name "$MDIR/aseg.auto_noCCseg.mgz" \
        --threads "$THR" \
        "${device_args[@]}"
    require_file "$stage" "$MDIR/aparc.DKTatlas+aseg.deep.mgz"
    require_file "$stage" "$MDIR/aseg.auto_noCCseg.mgz"
    require_file "$stage" "$MDIR/mask.mgz"

    run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/CorpusCallosum/fastsurfer_cc.py" \
        --sd "$SUBJECTS_DIR" \
        --sid "$SUBJ" \
        --threads "$THR" \
        --conformed_name "$MDIR/orig.mgz" \
        --aseg_name "$MDIR/aseg.auto_noCCseg.mgz" \
        --segmentation_in_orig "$MDIR/callosum.CC.orig.mgz"
    run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/CorpusCallosum/paint_cc_into_pred.py" \
        -in_cc "$MDIR/callosum.CC.orig.mgz" \
        -in_pred "$MDIR/aparc.DKTatlas+aseg.deep.mgz" \
        -out "$MDIR/aparc.DKTatlas+aseg.deep.withCC.mgz" \
        -aseg "$MDIR/aseg.auto.mgz"
    require_file "$stage" "$MDIR/aseg.auto.mgz"
}

stage4() {
    local stage=4
    log "$stage" "Official recon-surf setup, QC, N4 bias correction and Talairach"
    require_file "$stage" "$MDIR/orig.mgz"
    require_file "$stage" "$MDIR/aparc.DKTatlas+aseg.deep.mgz"
    require_file "$stage" "$MDIR/aseg.auto.mgz"

    init_recon_state
    run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/FastSurferCNN/quick_qc.py" --asegdkt_segfile "$MDIR/aparc.DKTatlas+aseg.deep.mgz"
    run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/FastSurferCNN/data_loader/conform.py" -i "$MDIR/orig.mgz" --check_only --vox_size min --verbose
    run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/FastSurferCNN/data_loader/conform.py" -i "$MDIR/aparc.DKTatlas+aseg.deep.mgz" --check_only --vox_size "$VOX_SIZE" --dtype any --verbose

    run_cmd "$stage" mri_convert "$MDIR/aparc.DKTatlas+aseg.deep.mgz" "$MDIR/aparc.DKTatlas+aseg.orig.mgz"
    ln -sf orig.mgz "$MDIR/rawavg.mgz"

    if [[ ! -s "$MDIR/orig_nu.mgz" ]]; then
        run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/recon_surf/N4_bias_correct.py" \
            --in "$MDIR/orig.mgz" \
            --rescale "$MDIR/orig_nu.mgz" \
            --aseg "$MDIR/aparc.DKTatlas+aseg.orig.mgz" \
            --threads "$THR"
    else
        log "$stage" "Using existing $MDIR/orig_nu.mgz"
    fi

    if [[ ! -s "$MDIR/transforms/talairach.lta" || ! -s "$MDIR/transforms/talairach_with_skull.lta" || ! -s "$MDIR/nu.mgz" ]]; then
        run_cmd "$stage" "$FASTSURFER_HOME/recon_surf/talairach-reg.sh" "$LF" \
            --dir "$MDIR" \
            --conformed_name "$MDIR/orig.mgz" \
            --norm_name "$MDIR/orig_nu.mgz" \
            --py "python3 -s" \
            --asegdkt_segfile "$MDIR/aparc.DKTatlas+aseg.deep.mgz"
    else
        log "$stage" "Using existing Talairach outputs"
    fi

    require_file "$stage" "$MDIR/aparc.DKTatlas+aseg.orig.mgz"
    require_file "$stage" "$MDIR/orig_nu.mgz"
    require_file "$stage" "$MDIR/nu.mgz"
    require_file "$stage" "$MDIR/transforms/talairach.xfm"
    require_file "$stage" "$MDIR/transforms/talairach.lta"
}

stage5() {
    local stage=5
    log "$stage" "Brainmask, norm and T1 generation"
    init_recon_state
    require_file "$stage" "$MDIR/nu.mgz"
    require_file "$stage" "$MDIR/mask.mgz"

    run_cmd "$stage" mri_mask "$MDIR/nu.mgz" "$MDIR/mask.mgz" "$MDIR/norm.mgz"
    run_cmd "$stage" mri_normalize -g 1 -seed 1234 -mprage "$MDIR/nu.mgz" "$MDIR/T1.mgz" "${NOCONFORM_IF_HIRES[@]}"
    run_cmd "$stage" mri_mask "$MDIR/T1.mgz" "$MDIR/mask.mgz" "$MDIR/brainmask.mgz"

    require_file "$stage" "$MDIR/norm.mgz"
    require_file "$stage" "$MDIR/T1.mgz"
    require_file "$stage" "$MDIR/brainmask.mgz"
}

stage6() {
    local stage=6
    log "$stage" "White matter segmentation and filled volume"
    init_recon_state
    require_file "$stage" "$MDIR/aseg.auto.mgz"
    require_file "$stage" "$MDIR/norm.mgz"
    require_file "$stage" "$MDIR/brainmask.mgz"

    local cmd=(recon-all -s "$SUBJ" -asegmerge -normalization2 -maskbfs -segmentation -fill -umask 0022)
    add_fs_flags cmd
    run_cmd "$stage" "${cmd[@]}"

    require_file "$stage" "$MDIR/wm.mgz"
    require_file "$stage" "$MDIR/filled.mgz"
    require_file "$stage" "$MDIR/brain.finalsurfs.mgz"
    require_file "$stage" "$MDIR/aseg.presurf.mgz"
}

stage7_hemi() {
    local hemi="$1"
    local stage=7
    local hemivalue=255
    [[ "$hemi" == "rh" ]] && hemivalue=127
    local outmesh="$SDIR/${hemi}.orig.nofix${HIRES_SURFACE_SUFFIX}"

    run_cmd "$stage" mri_pretess "$MDIR/filled.mgz" "$hemivalue" "$MDIR/brain.mgz" "$MDIR/filled-pretess${hemivalue}.mgz"
    run_cmd "$stage" mri_mc "$MDIR/filled-pretess${hemivalue}.mgz" "$hemivalue" "$outmesh"
    run_cmd "$stage" mris_extract_main_component "$outmesh" "$outmesh"
    if [[ -n "$HIRES_SURFACE_SUFFIX" ]]; then
        run_cmd "$stage" mris_remesh --desired-face-area 0.5 --input "$outmesh" --output "$SDIR/${hemi}.orig.nofix"
    fi
    run_cmd "$stage" mris_smooth -n 10 -nw -seed 1234 "$SDIR/${hemi}.orig.nofix" "$SDIR/${hemi}.smoothwm.nofix"

    local cmd=(recon-all -subject "$SUBJ" -hemi "$hemi" -inflate1 -no-isrunning -umask 0022)
    [[ -n "$HIRESFLAG" ]] && cmd+=("$HIRESFLAG")
    cmd+=("${FSTHREADS_HEMI[@]}")
    run_cmd "$stage" "${cmd[@]}"

    run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/recon_surf/spherically_project_wrapper.py" \
        --hemi "$hemi" --sd "$SUBJECTS_DIR" --subject "$SUBJ" --threads "$THREADS_HEMI"

    cmd=(recon-all -subject "$SUBJ" -hemi "$hemi" -fix -no-isrunning -umask 0022)
    [[ -n "$HIRESFLAG" ]] && cmd+=("$HIRESFLAG")
    cmd+=("${FSTHREADS_HEMI[@]}")
    run_cmd "$stage" "${cmd[@]}"
    [[ -f "$SDIR/${hemi}.orig.premesh" ]] && run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/recon_surf/rewrite_oriented_surface.py" --file "$SDIR/${hemi}.orig.premesh" --backup "$SDIR/${hemi}.orig.premesh.noorient"
    [[ -f "$SDIR/${hemi}.orig" ]] && run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/recon_surf/rewrite_oriented_surface.py" --file "$SDIR/${hemi}.orig" --backup "$SDIR/${hemi}.orig.noorient"

    cmd=(recon-all -subject "$SUBJ" -hemi "$hemi" -autodetgwstats -white-preaparc -no-isrunning -umask 0022)
    [[ -n "$HIRESFLAG" ]] && cmd+=("$HIRESFLAG")
    cmd+=("${FSTHREADS_HEMI[@]}")
    run_cmd "$stage" "${cmd[@]}"

    cmd=(recon-all -subject "$SUBJ" -hemi "$hemi" -cortex-label -smooth2 -inflate2 -curvHK -no-isrunning -umask 0022)
    [[ -n "$HIRESFLAG" ]] && cmd+=("$HIRESFLAG")
    cmd+=("${FSTHREADS_HEMI[@]}")
    run_cmd "$stage" "${cmd[@]}"

    run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/recon_surf/sample_parc.py" \
        --inseg "$MDIR/aparc.DKTatlas+aseg.orig.mgz" \
        --insurf "$SDIR/${hemi}.white.preaparc" \
        --incort "$LDIR/${hemi}.cortex.label" \
        --outaparc "$LDIR/${hemi}.aparc.DKTatlas.mapped.annot" \
        --seglut "$FASTSURFER_HOME/recon_surf/${hemi}.DKTatlaslookup.txt" \
        --surflut "$FASTSURFER_HOME/recon_surf/DKTatlaslookup.txt" \
        --projmm 0.6 \
        --radius 2

    run_cmd "$stage" mris_place_surface \
        --adgws-in "$SDIR/autodet.gw.stats.${hemi}.dat" \
        --seg "$MDIR/aseg.presurf.mgz" \
        --threads "$THREADS_HEMI" \
        --wm "$MDIR/wm.mgz" \
        --invol "$MDIR/brain.finalsurfs.mgz" \
        --"$hemi" \
        --i "$SDIR/${hemi}.white.preaparc" \
        --o "$SDIR/${hemi}.white" \
        --white \
        --nsmooth 0 \
        --rip-label "$LDIR/${hemi}.cortex.label" \
        --rip-bg \
        --rip-surf "$SDIR/${hemi}.white.preaparc" \
        --aparc "$LDIR/${hemi}.aparc.DKTatlas.mapped.annot"

    run_cmd "$stage" mris_place_surface \
        --adgws-in "$SDIR/autodet.gw.stats.${hemi}.dat" \
        --seg "$MDIR/aseg.presurf.mgz" \
        --threads "$THREADS_HEMI" \
        --wm "$MDIR/wm.mgz" \
        --invol "$MDIR/brain.finalsurfs.mgz" \
        --"$hemi" \
        --i "$SDIR/${hemi}.white" \
        --o "$SDIR/${hemi}.pial.T1" \
        --pial \
        --nsmooth 0 \
        --rip-label "$LDIR/${hemi}.cortex+hipamyg.label" \
        --pin-medial-wall "$LDIR/${hemi}.cortex.label" \
        --aparc "$LDIR/${hemi}.aparc.DKTatlas.mapped.annot" \
        --repulse-surf "$SDIR/${hemi}.white" \
        --white-surf "$SDIR/${hemi}.white"
    ln -sf "${hemi}.pial.T1" "$SDIR/${hemi}.pial"

    run_cmd "$stage" mris_place_surface --curv-map "$SDIR/${hemi}.white" 2 10 "$SDIR/${hemi}.curv"
    run_cmd "$stage" mris_place_surface --area-map "$SDIR/${hemi}.white" "$SDIR/${hemi}.area"
    run_cmd "$stage" mris_place_surface --curv-map "$SDIR/${hemi}.pial" 2 10 "$SDIR/${hemi}.curv.pial"
    run_cmd "$stage" mris_place_surface --area-map "$SDIR/${hemi}.pial" "$SDIR/${hemi}.area.pial"
    run_cmd "$stage" mris_place_surface --thickness "$SDIR/${hemi}.white" "$SDIR/${hemi}.pial" 20 5 "$SDIR/${hemi}.thickness"

    cmd=(recon-all -subject "$SUBJ" -hemi "$hemi" -curvstats -no-isrunning -umask 0022)
    [[ -n "$HIRESFLAG" ]] && cmd+=("$HIRESFLAG")
    cmd+=("${FSTHREADS_HEMI[@]}")
    run_cmd "$stage" "${cmd[@]}"
}

stage7() {
    local stage=7
    log "$stage" "Surface reconstruction from official recon-surf blocks"
    init_recon_state
    require_file "$stage" "$MDIR/filled.mgz"
    require_file "$stage" "$MDIR/brain.mgz"
    require_file "$stage" "$MDIR/wm.mgz"
    require_file "$stage" "$MDIR/brain.finalsurfs.mgz"
    require_file "$stage" "$MDIR/aseg.presurf.mgz"
    require_file "$stage" "$MDIR/aparc.DKTatlas+aseg.orig.mgz"

    export OMP_NUM_THREADS="$THREADS_HEMI"
    export ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS="$THREADS_HEMI"
    stage7_hemi lh
    stage7_hemi rh
    export OMP_NUM_THREADS="$THR"
    export ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS="$THR"

    require_file "$stage" "$SDIR/lh.white"
    require_file "$stage" "$SDIR/rh.white"
    require_file "$stage" "$SDIR/lh.pial"
    require_file "$stage" "$SDIR/rh.pial"
    require_file "$stage" "$SDIR/lh.thickness"
    require_file "$stage" "$SDIR/rh.thickness"
    require_file "$stage" "$LDIR/lh.aparc.DKTatlas.mapped.annot"
    require_file "$stage" "$LDIR/rh.aparc.DKTatlas.mapped.annot"
}

stage8() {
    local stage=8
    log "$stage" "Official FastSurfer surface registration"
    init_recon_state
    for hemi in lh rh; do
        require_file "$stage" "$SDIR/${hemi}.inflated"
        require_file "$stage" "$LDIR/${hemi}.aparc.DKTatlas.mapped.annot"
        local cmd=(recon-all -subject "$SUBJ" -hemi "$hemi" -sphere -no-isrunning -umask 0022)
        [[ -n "$HIRESFLAG" ]] && cmd+=("$HIRESFLAG")
        cmd+=("${FSTHREADS_HEMI[@]}")
        run_cmd "$stage" "${cmd[@]}"
        run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/recon_surf/rotate_sphere.py" \
            --srcsphere "$SDIR/${hemi}.sphere" \
            --srcaparc "$LDIR/${hemi}.aparc.DKTatlas.mapped.annot" \
            --trgsphere "$FREESURFER_HOME/subjects/fsaverage/surf/${hemi}.sphere" \
            --trgaparc "$FREESURFER_HOME/subjects/fsaverage/label/${hemi}.aparc.annot" \
            --out "$SDIR/${hemi}.angles.txt"
        read -r rot_a rot_b rot_c < "$SDIR/${hemi}.angles.txt"
        run_cmd "$stage" mris_register -curv -norot -rotate "$rot_a" "$rot_b" "$rot_c" \
            "$SDIR/${hemi}.sphere" \
            "$FREESURFER_HOME/average/${hemi}.folding.atlas.acfb40.noaparc.i12.2016-08-02.tif" \
            "$SDIR/${hemi}.sphere.reg"
        cmd=(recon-all -subject "$SUBJ" -hemi "$hemi" -jacobian_white -avgcurv -no-isrunning -umask 0022)
        [[ -n "$HIRESFLAG" ]] && cmd+=("$HIRESFLAG")
        cmd+=("${FSTHREADS_HEMI[@]}")
        run_cmd "$stage" "${cmd[@]}"
        require_file "$stage" "$SDIR/${hemi}.sphere.reg"
        require_file "$stage" "$SDIR/${hemi}.jacobian_white"
    done
}

stage9() {
    local stage=9
    log "$stage" "Ribbon, mapped volumes, stats, symlinks and BA labels"
    init_recon_state
    for hemi in lh rh; do
        require_file "$stage" "$SDIR/${hemi}.sphere.reg"
        require_file "$stage" "$SDIR/${hemi}.white"
        require_file "$stage" "$SDIR/${hemi}.pial"
        require_file "$stage" "$LDIR/${hemi}.aparc.DKTatlas.mapped.annot"
    done

    local cmd=(recon-all -subject "$SUBJ" -cortribbon -umask 0022)
    add_fs_flags cmd
    run_cmd "$stage" "${cmd[@]}"

    for hemi in lh rh; do
        run_cmd "$stage" mris_anatomical_stats -th3 -mgz \
            -cortex "$LDIR/${hemi}.cortex.label" \
            -f "$STATSDIR/${hemi}.aparc.DKTatlas.mapped.stats" \
            -b \
            -a "$LDIR/${hemi}.aparc.DKTatlas.mapped.annot" \
            -c "$LDIR/aparc.annot.mapped.ctab" \
            "$SUBJ" "$hemi" white
    done

    ln -sf lh.aparc.DKTatlas.mapped.annot "$LDIR/lh.aparc.annot"
    ln -sf rh.aparc.DKTatlas.mapped.annot "$LDIR/rh.aparc.annot"
    run_cmd "$stage" pctsurfcon --s "$SUBJ" --lh-only
    run_cmd "$stage" pctsurfcon --s "$SUBJ" --rh-only
    rm -f "$LDIR/lh.aparc.annot" "$LDIR/rh.aparc.annot"

    cmd=(recon-all -subject "$SUBJ" -hyporelabel -apas2aseg -umask 0022)
    add_fs_flags cmd
    run_cmd "$stage" "${cmd[@]}"

    run_cmd "$stage" mri_surf2volseg \
        --o "$MDIR/aparc.DKTatlas+aseg.mapped.mgz" \
        --label-cortex \
        --i "$MDIR/aseg.mgz" \
        --threads "$THR" \
        --lh-annot "$LDIR/lh.aparc.DKTatlas.mapped.annot" 1000 \
        --lh-cortex-mask "$LDIR/lh.cortex.label" \
        --lh-white "$SDIR/lh.white" \
        --lh-pial "$SDIR/lh.pial" \
        --rh-annot "$LDIR/rh.aparc.DKTatlas.mapped.annot" 2000 \
        --rh-cortex-mask "$LDIR/rh.cortex.label" \
        --rh-white "$SDIR/rh.white" \
        --rh-pial "$SDIR/rh.pial"

    run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/FastSurferCNN/segstats.py" \
        --sid "$SUBJ" \
        --segfile "$MDIR/aseg.mgz" \
        --segstatsfile "$STATSDIR/aseg.stats" \
        --pvfile "$MDIR/norm.mgz" \
        --normfile "$MDIR/norm.mgz" \
        --threads "$THR" \
        --excludeid 0 2 3 41 42 \
        --lut "$FREESURFER_HOME/ASegStatsLUT.txt" \
        --empty \
        measures \
        --compute BrainSeg BrainSegNotVent VentricleChoroidVol lhCortex rhCortex Cortex \
                  lhCerebralWhiteMatter rhCerebralWhiteMatter CerebralWhiteMatter SubCortGray TotalGray \
                  SupraTentorial SupraTentorialNotVent "Mask($MDIR/mask.mgz)" BrainSegVol-to-eTIV \
                  MaskVol-to-eTIV lhSurfaceHoles rhSurfaceHoles SurfaceHoles EstimatedTotalIntraCranialVol

    run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/FastSurferCNN/segstats.py" \
        --sid "$SUBJ" \
        --segfile "$MDIR/aseg.mgz" \
        --pvfile "$MDIR/norm.mgz" \
        --measure_only \
        --threads "$THR" \
        --segstatsfile "$STATSDIR/brainvol.stats" \
        measures \
        --file "$STATSDIR/aseg.stats" \
        --import BrainSeg BrainSegNotVent SupraTentorial SupraTentorialNotVent SubCortGray lhCortex rhCortex \
                 Cortex TotalGray lhCerebralWhiteMatter rhCerebralWhiteMatter CerebralWhiteMatter Mask \
        --compute SupraTentorialNotVentVox BrainSegNotVentSurf VentricleChoroidVol

    run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/FastSurferCNN/segstats.py" \
        --sid "$SUBJ" \
        --segfile "$MDIR/aseg.presurf.hypos.mgz" \
        --normfile "$MDIR/norm.mgz" \
        --pvfile "$MDIR/norm.mgz" \
        --segstatsfile "$STATSDIR/aseg.presurf.hypos.stats" \
        --excludeid 0 2 3 41 42 \
        --lut "$FREESURFER_HOME/ASegStatsLUT.txt" \
        --threads "$THR" \
        --empty \
        --volume_precision 1 \
        measures --file "$STATSDIR/aseg.stats" --import all

    run_cmd "$stage" mri_surf2volseg \
        --o "$MDIR/wmparc.DKTatlas.mapped.mgz" \
        --label-wm \
        --i "$MDIR/aparc.DKTatlas+aseg.mapped.mgz" \
        --threads "$THR" \
        --lh-annot "$LDIR/lh.aparc.DKTatlas.mapped.annot" 3000 \
        --lh-cortex-mask "$LDIR/lh.cortex.label" \
        --lh-white "$SDIR/lh.white" \
        --lh-pial "$SDIR/lh.pial" \
        --rh-annot "$LDIR/rh.aparc.DKTatlas.mapped.annot" 4000 \
        --rh-cortex-mask "$LDIR/rh.cortex.label" \
        --rh-white "$SDIR/rh.white" \
        --rh-pial "$SDIR/rh.pial"

    run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/FastSurferCNN/segstats.py" \
        --sid "$SUBJ" \
        --sd "$SUBJECTS_DIR" \
        --pvfile "$MDIR/norm.mgz" \
        --segfile "$MDIR/wmparc.DKTatlas.mapped.mgz" \
        --normfile "$MDIR/norm.mgz" \
        --lut "$FREESURFER_HOME/WMParcStatsLUT.txt" \
        --threads "$THR" \
        --segstatsfile "$STATSDIR/wmparc.DKTatlas.mapped.stats" \
        --volume_precision 1 \
        measures \
        --file "$STATSDIR/brainvol.stats" \
        --import Mask VentricleChoroidVol rhCerebralWhiteMatter lhCerebralWhiteMatter CerebralWhiteMatter

    ln -sf aparc.DKTatlas+aseg.mapped.mgz "$MDIR/aparc.DKTatlas+aseg.mgz"
    ln -sf aparc.DKTatlas+aseg.mapped.mgz "$MDIR/aparc+aseg.mgz"
    ln -sf wmparc.DKTatlas.mapped.mgz "$MDIR/wmparc.mgz"
    ln -sf lh.aparc.DKTatlas.mapped.annot "$LDIR/lh.aparc.DKTatlas.annot"
    ln -sf rh.aparc.DKTatlas.mapped.annot "$LDIR/rh.aparc.DKTatlas.annot"

    run_cmd "$stage" "${PY[@]}" "$FASTSURFER_HOME/recon_surf/fs_balabels.py" --sd "$SUBJECTS_DIR" --sid "$SUBJ"

    require_file "$stage" "$STATSDIR/aseg.stats"
    require_file "$stage" "$STATSDIR/brainvol.stats"
    require_file "$stage" "$STATSDIR/lh.aparc.DKTatlas.mapped.stats"
    require_file "$stage" "$STATSDIR/rh.aparc.DKTatlas.mapped.stats"
    require_file "$stage" "$STATSDIR/wmparc.DKTatlas.mapped.stats"
    require_file "$stage" "$MDIR/aparc.DKTatlas+aseg.mapped.mgz"
    require_file "$stage" "$MDIR/wmparc.DKTatlas.mapped.mgz"

    cp "$STATSDIR"/*.stats /output/stats/
}

for stage in 1 2 3 4 5 6 7 8 9; do
    if should_run "$stage"; then
        "stage${stage}"
    else
        skip_stage "$stage"
    fi
done

echo "============================================================" | tee -a "$LF"
echo "FastSurfer staged official flow finished" | tee -a "$LF"
echo "Subject dir: $SD" | tee -a "$LF"
echo "Stats dir:   /output/stats" | tee -a "$LF"
echo "============================================================" | tee -a "$LF"
INNERSCRIPT

chmod +x "$INNER_SCRIPT"

echo "============================================================"
echo "FastSurfer staged official pipeline"
echo "Input:   $INPUT"
echo "Output:  $OUTPUT"
echo "Subject: $SUBJECT"
echo "Threads: $THREADS"
echo "Device:  $DEVICE"
echo "Stages:  $START_STAGE-$STOP_STAGE"
echo "Image:   $IMAGE"
echo "============================================================"

set +e
docker run --rm --entrypoint /bin/bash \
    -v "$INPUT:/input/image.nii.gz:ro" \
    -v "$OUTPUT:/output" \
    -v "$LICENSE_DIR:/license:ro" \
    -v "$INNER_SCRIPT:/app/fastsurfer_staged_official.sh:ro" \
    -e SUBJECTS_DIR=/output/freesurfer \
    -e FS_LICENSE=/license/license.txt \
    "$IMAGE" \
    /app/fastsurfer_staged_official.sh "$SUBJECT" "$THREADS" "$START_STAGE" "$STOP_STAGE" "$DEVICE"
DOCKER_EXIT=$?
set -e

if [[ "$DOCKER_EXIT" -eq 0 ]]; then
    echo "SUCCESS: $OUTPUT"
    echo "Subject dir: $OUTPUT/freesurfer/$SUBJECT"
    echo "Stats dir:   $OUTPUT/stats"
else
    echo "FAILED: Docker exited with code $DOCKER_EXIT"
    echo "If the subject directory was created, inspect: $OUTPUT/freesurfer/$SUBJECT/scripts/fastsurfer-staged-official.log"
fi

exit "$DOCKER_EXIT"
