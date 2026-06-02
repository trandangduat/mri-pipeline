#!/bin/bash
# member1_push.sh - Thành viên 1 (Baor): FreeSurfer Stack
set -e

DOCKER_USER="${1:?Usage: ./member1_push.sh <dockerhub_username>}"

echo "=== Member 1 (Baor): FreeSurfer Stack ==="
echo "Pushing to: ${DOCKER_USER}/"
echo ""

images=(
  mri-freesurfer-base
  mri-mri-convert
  mri-synthstrip
  mri-synthseg-freesurfer
)

for img in "${images[@]}"; do
  echo ">>> ${img}..."
  docker tag "${img}:latest" "${DOCKER_USER}/${img}:latest"
  docker push "${DOCKER_USER}/${img}:latest"
  echo "    ✅ Done"
done

echo ""
echo "=== Member 1 hoàn tất! ==="
echo "Images: ${DOCKER_USER}/mri-freesurfer-base, mri-mri-convert, mri-synthstrip, mri-synthseg-freesurfer"
