#!/bin/bash
docker run --rm \
  -v "$(pwd)/data:/input" \
  -v "$(pwd)/outputs_test/member3/sub-002:/output" \
  -v "$(pwd)/work/member3/sub-002:/work" \
  mri-ants:latest \
  run_tool \
  --input /input/sub-002_T1w.nii \
  --output-dir /output \
  --work-dir /work \
  --subject-id sub-002 \
  --threads 4 \
  --device cpu
