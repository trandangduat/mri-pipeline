#!/bin/bash
# member3_push.sh - Thành viên 3 (khang): NiBabel + HD-BET + ANTs
set -e

DOCKER_USER="${1:?Usage: ./member3_push.sh <dockerhub_username>}"

echo "=== Member 3 (khang): Non-FreeSurfer Tools ==="
echo "Pushing to: ${DOCKER_USER}/"
echo ""

images=(
  mri-nibabel-utils
  mri-hdbet
  mri-ants
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
echo "=== Member 3 hoàn tất! ==="
echo "Images: ${DOCKER_USER}/mri-nibabel-utils, mri-hdbet, mri-ants"
