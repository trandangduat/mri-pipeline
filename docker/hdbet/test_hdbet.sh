#!/bin/bash
mkdir -p work/member3/hdbet_weights

docker run --rm \
  -v "$(pwd)/data:/input" \
  -v "$(pwd)/outputs_test/member3/sub-002:/output" \
  -v "$(pwd)/work/member3/sub-002:/work" \
  -v "$(pwd)/work/member3/hdbet_weights:/root/.cache/torch/hub/checkpoints" \
  mri-hdbet:latest \
  run_tool \
  --input /input/sub-002_T1w.nii \
  --output-dir /output \
  --work-dir /work \
  --subject-id sub-002 \
  --threads 1 \
  --device cpu
