#!/bin/bash
set -e

# Change to project root
cd "$(dirname "$0")/../.."

echo "Building FastSurferVINN..."
docker build -t mri-fastsurfervinn:latest docker/fastsurfervinn/

echo "Running FastSurferVINN test..."
mkdir -p outputs_test/member2
mkdir -p work/member2
# Assuming dummy data/sub-001_T1w.nii.gz exists. If not, script will fail.
docker run --rm \
  --gpus all \
  -v "$(pwd)/data:/input" \
  -v "$(pwd)/outputs_test/member2:/output" \
  -v "$(pwd)/work/member2:/work" \
  -v "$(pwd)/license:/license" \
  mri-fastsurfervinn:latest \
  --input /input/sub-002_T1w.nii \
  --output-dir /output/sub-002 \
  --work-dir /work/sub-002 \
  --subject-id sub-002 \
  --threads 4 \
  --device cuda

echo "Checking outputs..."
ls -la outputs_test/member2/sub-002/work/
ls -la outputs_test/member2/sub-002/stats/
echo "Test done."
