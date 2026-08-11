#!/usr/bin/env bash
set -euo pipefail

IMAGE="jhuguetn/cat12:r2665-2"
INPUT_FILE=""
OUTPUT_DIR="cat12_docker_test_output"
RUN_SEGMENTATION=0
SURFACE_MODE=0
BATCH_KIND="segment"
CLEAN_OUTPUT=0

usage() {
  cat <<'EOF'
Usage: scripts/test_cat12_docker_image.sh [options]

Smoke-test a CAT12 Docker image for MRI pipeline integration.

Options:
  --image IMAGE          Docker image to test. Default: jhuguetn/cat12:r2665-2
  --input FILE          Optional T1 NIfTI input for segmentation test.
  --output-dir DIR      Host output directory. Default: cat12_docker_test_output
  --run-segmentation    Run CAT12 segmentation on --input after smoke tests.
  --surface-mode N      CAT12 surface extraction mode: 0=off, 1=default,
                        or 2=extended (resample to template + more surfaces).
                        Default: 0. Shorthand --surface means 1.
  --batch KIND          Segmentation batch: segment, enigma, or simple. Default: segment.
  --clean-output        Remove files under --output-dir before segmentation test.
  -h, --help            Show this help.

Examples:
  scripts/test_cat12_docker_image.sh
  scripts/test_cat12_docker_image.sh --image vnmd/cat12_26.0.rc3:latest
  scripts/test_cat12_docker_image.sh --input /data/sub-01_T1w.nii.gz --run-segmentation
  scripts/test_cat12_docker_image.sh --input /data/sub-01_T1w.nii --run-segmentation --surface-mode 2
  scripts/test_cat12_docker_image.sh --input /data/sub-01_T1w.nii --run-segmentation --batch enigma --surface-mode 2

Notes:
  - The smoke test pulls the image, checks the entrypoint/help, and verifies
    CAT standalone batch files inside the container.
  - The segmentation test copies the input into the writable output mount so
    CAT can write mri/report/label/surf outputs next to the image.
  - Surface processing (modes 1/2) can take much longer than volume-only
    segmentation. The container raises the stack limit (ulimit -s unlimited)
    and uses MCR_CACHE_ROOT under the output dir because both are common
    causes of segfaults in CAT_RefineMesh/CAT_FixTopology.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      IMAGE="${2:?missing value for --image}"
      shift 2
      ;;
    --input)
      INPUT_FILE="${2:?missing value for --input}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:?missing value for --output-dir}"
      shift 2
      ;;
    --run-segmentation)
      RUN_SEGMENTATION=1
      shift
      ;;
    --surface)
      SURFACE_MODE=1
      shift
      ;;
    --surface-mode)
      SURFACE_MODE="${2:?missing value for --surface-mode}"
      shift 2
      ;;
    --batch)
      BATCH_KIND="${2:?missing value for --batch}"
      shift 2
      ;;
    --clean-output)
      CLEAN_OUTPUT=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$SURFACE_MODE" != "0" && "$SURFACE_MODE" != "1" && "$SURFACE_MODE" != "2" ]]; then
  echo "--surface-mode must be 0, 1, or 2" >&2
  exit 2
fi

if [[ "$RUN_SEGMENTATION" == "1" && -z "$INPUT_FILE" ]]; then
  echo "--run-segmentation requires --input" >&2
  exit 2
fi

if [[ -n "$INPUT_FILE" && ! -f "$INPUT_FILE" ]]; then
  echo "Input file does not exist: $INPUT_FILE" >&2
  exit 2
fi

case "$BATCH_KIND" in
  segment|enigma|simple) ;;
  *) echo "--batch must be one of: segment, enigma, simple" >&2; exit 2 ;;
esac

echo "== CAT12 Docker image smoke test =="
echo "Image: $IMAGE"
echo

echo "== Pulling image =="
docker pull "$IMAGE"
echo

echo "== Docker image metadata =="
docker image inspect "$IMAGE" --format 'Entrypoint={{json .Config.Entrypoint}} Cmd={{json .Config.Cmd}} Size={{.Size}}'
echo

echo "== Entrypoint help/version probes =="
docker run --rm "$IMAGE" --help >/tmp/cat12_help.txt 2>&1 || true
sed -n '1,80p' /tmp/cat12_help.txt
echo
docker run --rm "$IMAGE" -V >/tmp/cat12_version.txt 2>&1 || true
sed -n '1,80p' /tmp/cat12_version.txt
echo

echo "== Internal CAT12 path probes =="
docker run --rm --entrypoint sh "$IMAGE" -lc '
set -eu
echo "PATH=$PATH"
echo "MCRROOT=${MCRROOT:-}"
echo "SPMROOT=${SPMROOT:-}"
for p in \
  /opt/spm/standalone/cat_standalone.sh \
  /opt/cat12/standalone/cat_standalone.sh \
  /opt/spm/run_spm25.sh \
  /opt/cat12/run_spm25.sh \
  /opt/mcr/v232 \
  /opt/mcr/R2023b; do
  if [ -e "$p" ]; then echo "FOUND $p"; fi
done
echo "Batch files:"
for d in /opt/spm/standalone /opt/cat12/standalone; do
  if [ -d "$d" ]; then ls "$d"/cat_standalone*.m 2>/dev/null | sort; fi
done
test -e /opt/spm/standalone/cat_standalone.sh || test -e /opt/cat12/standalone/cat_standalone.sh
'
echo

if [[ "$RUN_SEGMENTATION" != "1" ]]; then
  echo "Smoke test complete. Add --input FILE --run-segmentation to test CAT outputs."
  exit 0
fi

INPUT_ABS=$(realpath "$INPUT_FILE")
INPUT_DIR=$(dirname "$INPUT_ABS")
INPUT_BASE=$(basename "$INPUT_ABS")
OUTPUT_ABS=$(mkdir -p "$OUTPUT_DIR" && realpath "$OUTPUT_DIR")
HOST_UID=$(id -u)
HOST_GID=$(id -g)

echo "== Running CAT12 segmentation test =="
echo "Input: $INPUT_ABS"
echo "Output dir: $OUTPUT_ABS"
echo "Surface mode: $SURFACE_MODE"
echo "Batch kind: $BATCH_KIND"
echo

if [[ "$CLEAN_OUTPUT" == "1" ]]; then
  echo "Cleaning output directory: $OUTPUT_ABS"
  docker run --rm \
    --entrypoint bash \
    -e HOST_UID="$HOST_UID" \
    -e HOST_GID="$HOST_GID" \
    -v "$OUTPUT_ABS:/work" \
    "$IMAGE" \
    -lc 'set -eu; rm -rf /work/* /work/.[!.]* /work/..?*; chown -R "$HOST_UID:$HOST_GID" /work 2>/dev/null || true'
fi

docker run --rm \
  --entrypoint bash \
  -e INPUT_BASE="$INPUT_BASE" \
  -e SURFACE_MODE="$SURFACE_MODE" \
  -e BATCH_KIND="$BATCH_KIND" \
  -e HOST_UID="$HOST_UID" \
  -e HOST_GID="$HOST_GID" \
  -v "$INPUT_DIR:/input:ro" \
  -v "$OUTPUT_ABS:/work" \
  "$IMAGE" \
  -lc '
set -eu
trap '\''chown -R "$HOST_UID:$HOST_GID" /work 2>/dev/null || true'\'' EXIT
ulimit -s unlimited
export MCR_CACHE_ROOT=/work/.mcr_cache
mkdir -p "$MCR_CACHE_ROOT"
cd /work
case "$INPUT_BASE" in
  *.nii.gz) WORK_INPUT="input.nii.gz" ;;
  *.nii) WORK_INPUT="input.nii" ;;
  *) echo "CAT12 test expects .nii or .nii.gz input, got: $INPUT_BASE" >&2; exit 2 ;;
esac
cp "/input/$INPUT_BASE" "/work/$WORK_INPUT"

CAT_SCRIPT=""
for candidate in /opt/spm/standalone/cat_standalone.sh /opt/cat12/standalone/cat_standalone.sh; do
  if [ -x "$candidate" ]; then CAT_SCRIPT="$candidate"; break; fi
done
if [ -z "$CAT_SCRIPT" ]; then echo "CAT standalone script not found" >&2; exit 3; fi

SPM_ROOT="/opt/spm"
[ -d /opt/cat12 ] && SPM_ROOT="/opt/cat12"
MCR_ROOT=""
for candidate in /opt/mcr/v232 /opt/mcr/R2023b; do
  if [ -d "$candidate" ]; then MCR_ROOT="$candidate"; break; fi
done
if [ -z "$MCR_ROOT" ]; then echo "MCR root not found" >&2; exit 3; fi

BATCH_SRC=""
case "$BATCH_KIND" in
  enigma) BATCH_NAMES="cat_standalone_segment_enigma.m cat_standalone_segment.m" ;;
  simple) BATCH_NAMES="cat_standalone_simple.m cat_standalone_segment.m" ;;
  *) BATCH_NAMES="cat_standalone_segment.m cat_standalone_segment_enigma.m" ;;
esac
for batch_name in $BATCH_NAMES; do
  candidate="$SPM_ROOT/standalone/$batch_name"
  if [ -f "$candidate" ]; then BATCH_SRC="$candidate"; break; fi
done
if [ -z "$BATCH_SRC" ]; then echo "CAT segment batch not found" >&2; exit 3; fi

BATCH="/work/cat12_segment_test.m"
cp "$BATCH_SRC" "$BATCH"
if [ "$SURFACE_MODE" = "0" ]; then
  sed -i "s/output\.surface = [0-9]/output.surface = 0/g" "$BATCH" || true
else
  sed -i "s/output\.surface = [0-9]/output.surface = $SURFACE_MODE/g" "$BATCH" || true
fi

echo "CAT_SCRIPT=$CAT_SCRIPT"
echo "SPM_ROOT=$SPM_ROOT"
echo "MCR_ROOT=$MCR_ROOT"
echo "BATCH_SRC=$BATCH_SRC"
echo "BATCH=$BATCH"
grep "output.surface" "$BATCH" | head -5 || true

set +e
"$CAT_SCRIPT" -s "$SPM_ROOT" -m "$MCR_ROOT" -b "$BATCH" "/work/$WORK_INPUT" 2>&1 | tee /work/cat12_run.log
cat_status=${PIPESTATUS[0]}
set -e

cat_error_markers=0
if grep -E "CAT Preprocessing error|Cannot gunzip|No executable modules|Error using|MATLAB:|SPM failed" /work/cat12_run.log >/work/cat12_error_matches.txt 2>/dev/null; then
  cat_error_markers=1
  echo "== CAT12 error markers found ==" >&2
  cat /work/cat12_error_matches.txt >&2
fi
if grep -E "Segmentation fault|SIGSEGV|core dumped" /work/cat12_run.log >/work/cat12_sigsegv_matches.txt 2>/dev/null; then
  echo "== CAT12 segfault markers found ==" >&2
  cat /work/cat12_sigsegv_matches.txt >&2
  exit 11
fi
if [ "$cat_status" != "0" ]; then
  echo "CAT standalone exited with status $cat_status" >&2
  exit "$cat_status"
fi
if [ "$SURFACE_MODE" = "0" ] && [ "$cat_error_markers" = "1" ]; then
  exit 10
fi

echo "== Output files =="
find /work -maxdepth 3 -type f | sort | sed -n "1,200p"
find /work -maxdepth 3 -type d -name report | grep -q .
find /work -maxdepth 3 -type d -name mri | grep -q .
find /work -maxdepth 4 -type f -name "cat_*.xml" | grep -q .
find /work -maxdepth 4 -type f -name "catROI_*.xml" | grep -q .
if [ "$SURFACE_MODE" != "0" ]; then
  echo "== Surface outputs =="
  find /work -maxdepth 4 -type d -name surf | grep -q .
  find /work -maxdepth 5 -type f \( -name "?h.thickness.*" -o -name "*.gii" \) | sed -n "1,60p"
  if ! find /work -maxdepth 5 -type f -name "*thickness*" | grep -q .; then
    echo "No CAT12 thickness outputs found after surface mode $SURFACE_MODE" >&2
    [ "$cat_error_markers" = "1" ] && exit 10
    exit 20
  fi
  if [ "$cat_error_markers" = "1" ]; then
    echo "CAT12 reported preprocessing markers, but thickness outputs exist; keeping this run for inspection." >&2
  fi
fi
'

echo
echo "Segmentation test complete. Outputs are in: $OUTPUT_ABS"
