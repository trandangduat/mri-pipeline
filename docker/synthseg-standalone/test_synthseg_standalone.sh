#!/bin/bash
set -e

# Change to project root
cd "$(dirname "$0")/../.."

# Prepare models directory for Docker build context
echo "Copying local models to build context..."
mkdir -p docker/synthseg-standalone/models
cp models/synthseg/* docker/synthseg-standalone/models/ 2>/dev/null || echo "Warning: Could not copy models, build will proceed but weights might be downloaded at runtime."

echo "Building SynthSeg standalone..."
docker build -t mri-synthseg-standalone:latest docker/synthseg-standalone/

echo "Running SynthSeg standalone test..."
mkdir -p outputs_test/member2
mkdir -p work/member2
# Assuming dummy data/sub-001_T1w.nii.gz exists. If not, script will fail.
docker run --rm \
  -v "$(pwd)/data:/input" \
  -v "$(pwd)/outputs_test/member2:/output" \
  -v "$(pwd)/work/member2:/work" \
  mri-synthseg-standalone:latest \
  --input /input/sub-002_T1w.nii \
  --output-dir /output/sub-002 \
  --work-dir /work/sub-002 \
  --subject-id sub-002 \
  --threads 2 \
  --device cpu \
  --crop 96

echo "Checking outputs..."
ls -la outputs_test/member2/sub-002/work/
ls -la outputs_test/member2/sub-002/stats/
echo "Test done."
