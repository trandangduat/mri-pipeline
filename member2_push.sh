#!/bin/bash
# member2_push.sh - Thành viên 2 (duaajt): SynthSeg Standalone + FastSurferVINN
set -e

DOCKER_USER="${1:?Usage: ./member2_push.sh <dockerhub_username>}"

echo "=== Member 2 (duaajt): Standalone Segmentation ==="
echo "Pushing to: ${DOCKER_USER}/"
echo ""

images=(
  mri-synthseg-standalone
  mri-fastsurfervinn
)

for img in "${images[@]}"; do
  if docker image inspect "${img}:latest" > /dev/null 2>&1; then
    echo ">>> ${img}..."
    docker tag "${img}:latest" "${DOCKER_USER}/${img}:latest"
    docker push "${DOCKER_USER}/${img}:latest"
    echo "    ✅ Done"
  else
    echo ">>> ${img}: chưa build, bỏ qua"
  fi
done

echo ""
echo "=== Member 2 hoàn tất! ==="
echo "Images: ${DOCKER_USER}/mri-synthseg-standalone, mri-fastsurfervinn"
