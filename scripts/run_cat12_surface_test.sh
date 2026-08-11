#!/usr/bin/env bash
set -euo pipefail

IMAGE="vnmd/cat12_26.0.rc3:latest"
INPUT_FILE=""
OUTPUT_DIR="cat12_surface_test_output"
LOG_FILE="cat12_surface_test.log"
SURFACE_MODE=2

usage() {
  cat <<'EOF'
Usage: scripts/run_cat12_surface_test.sh --input FILE [options]

Run CAT12 segmentation with surface extraction enabled and verify cortical
surface/thickness outputs before integrating CAT12 into the pipeline.

Options:
  --input FILE       T1 NIfTI input (.nii or .nii.gz). Required.
  --output-dir DIR   Output directory. Default: cat12_surface_test_output
  --image IMAGE      CAT12 Docker image. Default: vnmd/cat12_26.0.rc3:latest
  --log-file FILE    Log file path. Default: cat12_surface_test.log
  --surface-mode N   CAT12 surface mode: 1=default or 2=extended (default 2).
  --batch KIND       Segmentation batch: segment (default) or enigma.
  -h, --help         Show this help.

Example:
  scripts/run_cat12_surface_test.sh \
    --input /home/catcd1/duat-jobs/run-cat12/input/I776974.nii \
    --output-dir /home/catcd1/duat-jobs/run-cat12/cat12_surface_test_output \
    --log-file /home/catcd1/duat-jobs/run-cat12/cat12_surface_test.log
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input)
      INPUT_FILE="${2:?missing value for --input}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:?missing value for --output-dir}"
      shift 2
      ;;
    --image)
      IMAGE="${2:?missing value for --image}"
      shift 2
      ;;
    --log-file)
      LOG_FILE="${2:?missing value for --log-file}"
      shift 2
      ;;
    --surface-mode)
      SURFACE_MODE="${2:?missing value for --surface-mode}"
      shift 2
      ;;
    --batch)
      BATCH_KIND="${2:?missing value for --batch}"
      shift 2
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

if [[ -z "$INPUT_FILE" ]]; then
  echo "--input is required" >&2
  usage >&2
  exit 2
fi

if [[ ! -f "$INPUT_FILE" ]]; then
  echo "Input file does not exist: $INPUT_FILE" >&2
  exit 2
fi

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TEST_SCRIPT="$SCRIPT_DIR/test_cat12_docker_image.sh"
if [[ ! -x "$TEST_SCRIPT" ]]; then
  echo "Required test script is missing or not executable: $TEST_SCRIPT" >&2
  exit 2
fi

mkdir -p "$(dirname "$LOG_FILE")" "$OUTPUT_DIR"

echo "== CAT12 surface test ==" | tee "$LOG_FILE"
echo "Image: $IMAGE" | tee -a "$LOG_FILE"
echo "Input: $INPUT_FILE" | tee -a "$LOG_FILE"
echo "Output: $OUTPUT_DIR" | tee -a "$LOG_FILE"
echo "Started: $(date -Is)" | tee -a "$LOG_FILE"
echo | tee -a "$LOG_FILE"

set +e
"$TEST_SCRIPT" \
  --image "$IMAGE" \
  --input "$INPUT_FILE" \
  --output-dir "$OUTPUT_DIR" \
  --run-segmentation \
  --surface-mode "$SURFACE_MODE" \
  --clean-output \
  --batch "${BATCH_KIND:-segment}" 2>&1 | tee -a "$LOG_FILE"
status=${PIPESTATUS[0]}
set -e

echo | tee -a "$LOG_FILE"
echo "Finished: $(date -Is)" | tee -a "$LOG_FILE"
echo "Exit status: $status" | tee -a "$LOG_FILE"

if [[ "$status" != "0" ]]; then
  echo "CAT12 surface test failed. See log: $LOG_FILE" >&2
  exit "$status"
fi

echo "== Verifying surface outputs ==" | tee -a "$LOG_FILE"
surface_files=$(find "$OUTPUT_DIR" -maxdepth 4 -type f \( -path "*/surf/*" -o -name "*thickness*" -o -name "*.gii" \) | sort)
if [[ -z "$surface_files" ]]; then
  echo "No surface/thickness outputs found under $OUTPUT_DIR" | tee -a "$LOG_FILE" >&2
  exit 20
fi
printf '%s\n' "$surface_files" | tee -a "$LOG_FILE"

echo "== Verifying ROI/report outputs ==" | tee -a "$LOG_FILE"
find "$OUTPUT_DIR" -maxdepth 4 -type f \( -name "catROI_*.xml" -o -name "cat_*.xml" -o -name "catreport_*.pdf" \) | sort | tee -a "$LOG_FILE"

echo "CAT12 surface test passed. Log: $LOG_FILE" | tee -a "$LOG_FILE"
