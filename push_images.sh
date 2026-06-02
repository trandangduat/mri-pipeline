#!/bin/bash
# push_images.sh - Đẩy tất cả Docker images lên Docker Hub
set -e

DOCKER_USER="${1:?Usage: ./push_images.sh <dockerhub_username>}"

echo "==================================="
echo "  Push MRI images to ${DOCKER_USER}"
echo "==================================="
echo ""

# Login (nếu chưa)
if ! docker info 2>/dev/null | grep -q "Username"; then
    echo ">>> Đăng nhập Docker Hub..."
    docker login
fi

images=(
  mri-freesurfer-base
  mri-mri-convert
  mri-synthstrip
  mri-synthseg-freesurfer
  mri-nibabel-utils
  mri-hdbet
  mri-ants
  mri-synthseg-standalone
  mri-fastsurfervinn
)

pushed=0
skipped=0

for img in "${images[@]}"; do
    if docker image inspect "${img}:latest" > /dev/null 2>&1; then
        echo ">>> ${img}: tag + push..."
        docker tag "${img}:latest" "${DOCKER_USER}/${img}:latest"
        docker push "${DOCKER_USER}/${img}:latest"
        echo "    ✅ Done"
        ((pushed++))
    else
        echo ">>> ${img}: chưa build local, bỏ qua"
        ((skipped++))
    fi
done

echo ""
echo "==================================="
echo "  Hoàn tất!"
echo "  Pushed: ${pushed}  |  Skipped: ${skipped}"
echo "==================================="
echo ""
echo "Images đã có tại: https://hub.docker.com/u/${DOCKER_USER}"
echo ""
echo "Machines khác pull bằng:"
echo "  docker pull ${DOCKER_USER}/mri-<tool>:latest"
