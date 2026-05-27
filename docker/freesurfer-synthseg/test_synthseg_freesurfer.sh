#!/bin/bash
docker run --rm \
  -v ~/data:/input \
  -v ~/outputs_test/member1/sub-001:/output \
  -v ~/work/member1/sub-001:/work \
  -v ~/license:/license \
  mri-synthseg-freesurfer:latest \
  --input /input/001.mgz \
  --output-dir /output \
  --work-dir /work \
  --subject-id sub-001 \
  --threads 4 \
  --device cpu
