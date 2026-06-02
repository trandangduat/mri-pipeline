#!/bin/bash
# setup.sh - Cài đặt tự động MRI Pipeline
set -e

echo "==================================="
echo "  MRI Pipeline - Setup Script"
echo "==================================="
echo ""

# --- Kiểm tra Docker ---
if ! command -v docker &> /dev/null; then
    echo "❌ Docker chưa được cài."
    echo "   Cài đặt: https://docs.docker.com/engine/install/"
    exit 1
fi
echo "✅ Docker: $(docker --version | head -1)"

# --- Kiểm tra Python ---
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 chưa được cài."
    exit 1
fi
echo "✅ Python: $(python3 --version)"

# --- Cài dependencies ---
echo ""
echo ">>> Cài Python dependencies..."
pip install -r requirements.txt --quiet

# --- Pull Docker images ---
echo ""
echo ">>> Pull Docker images từ Docker Hub..."

# Đổi DOCKER_USER thành username Docker Hub của bạn
DOCKER_USER="${1:-mriproject}"

images=(
  mri-freesurfer-base
  mri-mri-convert
  mri-synthstrip
  mri-synthseg-freesurfer
  mri-nibabel-utils
  mri-hdbet
  mri-ants
)

for img in "${images[@]}"; do
    echo "    Pulling ${DOCKER_USER}/${img}:latest ..."
    if docker pull "${DOCKER_USER}/${img}:latest" 2>/dev/null; then
        docker tag "${DOCKER_USER}/${img}:latest" "${img}:latest"
        echo "    ✅ ${img}"
    else
        echo "    ⚠️  ${img} - pull thất bại, sẽ build local khi cần"
    fi
done

# --- Kiểm tra license ---
echo ""
if [ -f "license/license.txt" ]; then
    echo "✅ FreeSurfer license found"
else
    echo "⚠️  FreeSurfer license chưa có."
    echo "   Copy license.txt vào thư mục license/"
    echo "   (Cần cho mri-convert, synthstrip, synthseg)"
fi

echo ""
echo "==================================="
echo "  Setup hoàn tất!"
echo "==================================="
echo ""
echo "Chạy GUI:"
echo "  streamlit run app.py"
echo ""
echo "Chạy từ Python:"
echo "  python -c \"from pipeline_runner import PipelineConfig, run_pipeline; ...\""
