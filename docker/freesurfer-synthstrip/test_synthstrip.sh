#!/bin/bash
docker run --rm \
  -v ~/data:/input \
  -v ~/outputs_test/member1/sub-001:/output \
  -v ~/work/member1/sub-001:/work \
  -v ~/license:/license \
  mri-synthstrip:latest \
  --input /input/001.mgz \
  --output-dir /output \
  --work-dir /work \
  --subject-id sub-001 \
  --threads 8 \
  --device cpu
