# Hướng dẫn phân phối & triển khai MRI Pipeline

## Tổng quan kiến trúc

```
┌─────────────────────────────────────────────────────┐
│                    Máy người dùng                    │
│                                                      │
│  ┌──────────┐    ┌──────────────┐    ┌───────────┐  │
│  │ Streamlit│───▶│pipeline_runner│───▶│  Docker   │  │
│  │   GUI    │    │     .py      │    │ Containers│  │
│  └──────────┘    └──────────────┘    └───────────┘  │
│       │                                    │         │
│       ▼                                    ▼         │
│  http://localhost:8501              MRI outputs      │
└─────────────────────────────────────────────────────┘
```

Mỗi tool là 1 Docker image. Pipeline runner gọi từng image theo thứ tự.
GUI (Streamlit) chạy trên browser, hiển thị real-time progress.

---

## Bước 1: Đẩy Docker images lên Docker Hub

### 1.1 Đăng ký Docker Hub

1. Tạo tài khoản tại https://hub.docker.com (miễn phí)
2. Login trên terminal:

```bash
docker login
# Nhập username và password
```

### 1.2 Tag và push images

Giả sử username Docker Hub là `yourusername`:

```bash
# Danh sách images cần push
IMAGES=(
  "mri-freesurfer-base"
  "mri-mri-convert"
  "mri-synthstrip"
  "mri-synthseg-freesurfer"
  "mri-nibabel-utils"
  "mri-hdbet"
  "mri-ants"
  "mri-synthseg-standalone"
  "mri-fastsurfervinn"
)

for img in "${IMAGES[@]}"; do
  echo "=== Tagging and pushing $img ==="
  docker tag "${img}:latest" "yourusername/${img}:latest"
  docker push "yourusername/${img}:latest"
done
```

Hoặc dùng script tự động (xem mục 1.3).

### 1.3 Script tự động push

```bash
#!/bin/bash
# push_images.sh
set -e

DOCKER_USER="${1:?Usage: ./push_images.sh <dockerhub_username>}"

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

for img in "${images[@]}"; do
  if docker image inspect "${img}:latest" > /dev/null 2>&1; then
    echo ">>> Pushing ${img}..."
    docker tag "${img}:latest" "${DOCKER_USER}/${img}:latest"
    docker push "${DOCKER_USER}/${img}:latest"
    echo "    Done."
  else
    echo ">>> Skipping ${img} (not built locally)"
  fi
done

echo ""
echo "All images pushed to ${DOCKER_USER}/"
```

---

## Bước 2: Cập nhật code để pull từ Docker Hub

Sau khi push, cần sửa `pipeline_runner.py` để dùng image từ Docker Hub thay vì build local:

### 2.1 Thêm registry prefix vào TOOL_DEFS

```python
# Trong pipeline_runner.py, đổi image name:
DOCKER_REGISTRY = "yourusername"  # hoặc bỏ trống nếu dùng local

TOOL_DEFS = {
    "mri_convert": {
        "image": f"{DOCKER_REGISTRY}/mri-mri-convert:latest" if DOCKER_REGISTRY else "mri-mri-convert:latest",
        ...
    },
    ...
}
```

### 2.2 Thêm logic: pull nếu không có local

```python
def ensure_image(tool_key, ...):
    image = tool["image"]
    if not image_exists(image):
        # Thử pull trước
        if _try_pull(image):
            return True, "", 0.0
        # Nếu không pull được thì build
        ...
```

---

## Bước 3: Đóng gói GitHub Repository

### 3.1 Cấu trúc repo sạch

```
pipeline-containerize/
├── app.py                    # Streamlit GUI
├── pipeline_runner.py        # Pipeline orchestrator
├── requirements.txt          # Python dependencies
├── README.md                 # Documentation
├── DEPLOYMENT.md             # Hướng dẫn triển khai (file này)
├── .gitignore
├── docker/
│   ├── freesurfer-base/
│   ├── freesurfer-mri-convert/
│   ├── freesurfer-synthstrip/
│   ├── freesurfer-synthseg/
│   ├── nibabel-utils/
│   ├── hdbet/
│   ├── ants/
│   ├── synthseg-standalone/
│   └── fastsurfervinn/
├── data/
│   ├── sub-003_small.nii.gz  # Small test file (8KB)
│   └── .gitkeep
├── license/
│   └── .gitkeep
└── models/
    └── .gitkeep
```

### 3.2 Tạo requirements.txt

```txt
streamlit>=1.30.0
```

### 3.3 Push lên GitHub

```bash
# Tạo repo trên GitHub (trống, không README)
# Sau đó:

git init
git add .
git commit -m "Initial commit: MRI pipeline with Docker + Streamlit GUI"
git remote add origin https://github.com/yourusername/pipeline-containerize.git
git push -u origin main
```

---

## Bước 4: Máy khác cài đặt và sử dụng

### 4.1 Yêu cầu hệ thống

- **OS:** Linux (Ubuntu 20.04+), macOS, hoặc Windows với WSL2
- **Docker:** Version 20.10+ (cài đặt: https://docs.docker.com/engine/install/)
- **Python:** 3.9+ (chỉ cần cho GUI)
- **RAM:** Tối thiểu 8GB (16GB khuyến nghị)
- **Disk:** Tối thiểu 15GB trống

### 4.2 Cài đặt nhanh (pull images từ Docker Hub)

```bash
# 1. Clone repo
git clone https://github.com/yourusername/pipeline-containerize.git
cd pipeline-containerize

# 2. Cài Python dependencies
pip install -r requirements.txt

# 3. Pull Docker images (không cần build)
docker pull yourusername/mri-freesurfer-base:latest
docker pull yourusername/mri-mri-convert:latest
docker pull yourusername/mri-synthstrip:latest
docker pull yourusername/mri-synthseg-freesurfer:latest
docker pull yourusername/mri-nibabel-utils:latest
docker pull yourusername/mri-hdbet:latest
docker pull yourusername/mri-ants:latest

# 4. Copy FreeSurfer license (nếu dùng FreeSurfer tools)
cp /path/to/license.txt license/license.txt

# 5. Chạy GUI
streamlit run app.py
```

### 4.3 Cài đặt tự động (script)

```bash
#!/bin/bash
# setup.sh - Cài đặt tự động
set -e

echo "=== MRI Pipeline Setup ==="

# Kiểm tra Docker
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker chưa được cài. Xem: https://docs.docker.com/engine/install/"
    exit 1
fi

# Kiểm tra Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 chưa được cài."
    exit 1
fi

# Cài dependencies
echo ">>> Cài Python dependencies..."
pip install -r requirements.txt

# Pull images
echo ">>> Pull Docker images..."
DOCKER_USER="yourusername"
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
  echo "    Pulling ${img}..."
  docker pull "${DOCKER_USER}/${img}:latest"
done

echo ""
echo "=== Cài đặt hoàn tất! ==="
echo "Chạy: streamlit run app.py"
```

### 4.4 Sử dụng không cần GUI (Python API)

```python
from pipeline_runner import PipelineConfig, run_pipeline

config = PipelineConfig(
    input_file="data/sub-002_T1w.nii",
    output_dir="output",
    work_dir="work",
    subject_id="sub-002",
    license_dir="license",
    device="cpu",
    threads=4,
    selected_tools={
        "reorientation": "mri_convert",
        "brain_extraction": "synthstrip",
        "segmentation": "synthseg_freesurfer",
        "bias_correction": "ants_n4",
    },
)

results = run_pipeline(config)
for r in results:
    print(f"{r.stage}: {'OK' if r.success else 'FAIL'} "
          f"(build: {r.build_duration_sec:.0f}s, run: {r.duration_sec:.0f}s)")
```

---

## Bước 5: CI/CD (tùy chọn)

### 5.1 GitHub Actions - Auto build và push images

```yaml
# .github/workflows/docker-build.yml
name: Build and Push Docker Images

on:
  push:
    branches: [main]
    paths:
      - 'docker/**'

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        image:
          - freesurfer-base
          - freesurfer-mri-convert
          - freesurfer-synthstrip
          - freesurfer-synthseg
          - nibabel-utils
          - hdbet
          - ants

    steps:
      - uses: actions/checkout@v4

      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: docker/${{ matrix.image }}
          push: true
          tags: ${{ secrets.DOCKERHUB_USERNAME }}/mri-${{ matrix.image }}:latest
```

### 5.2 GitHub Secrets cần thiết

Vào GitHub repo → Settings → Secrets and variables → Actions:

| Secret | Giá trị |
|--------|---------|
| `DOCKERHUB_USERNAME` | Username Docker Hub |
| `DOCKERHUB_TOKEN` | Access Token (tạo tại Docker Hub → Account Settings → Security) |

---

## Bước 6: Triển nâng cao (tùy chọn)

### 6.1 Docker Compose

```yaml
# docker-compose.yml
version: "3.8"

services:
  gui:
    build: .
    ports:
      - "8501:8501"
    volumes:
      - ./data:/app/data
      - ./output:/app/output
      - ./work:/app/work
      - ./license:/app/license
```

### 6.2 Đóng gói thành single Docker image (GUI + all tools)

```dockerfile
# Dockerfile.gui
FROM python:3.10-slim

RUN pip install streamlit

COPY app.py pipeline_runner.py /app/
COPY requirements.txt /app/
RUN pip install -r /app/requirements.txt

# Pull tất cả tool images khi build (hoặc mount Docker socket)
# Lưu ý: cách này rất nặng (~15GB+)

WORKDIR /app
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.headless=true"]
```

### 6.3 Kubernetes deployment (cho bệnh viện / phòng khám lớn)

Xem thêm: `k8s/` directory (chưa tạo).

---

## Kích thước tham khảo

| Component | Kích thước |
|-----------|-----------|
| freesurfer-base | ~5 GB |
| mri-convert | ~5 GB (share layers với base) |
| synthstrip | ~5 GB (share layers) |
| synthseg-freesurfer | ~5 GB (share layers) |
| nibabel-utils | ~200 MB |
| hdbet | ~3 GB |
| ants | ~1.5 GB |
| synthseg-standalone | ~8 GB |
| fastsurfervinn | ~10 GB |
| **Tổng (nếu share layers)** | **~15-20 GB** |
| Code + test data | ~50 MB |

---

## Troubleshooting

| Vấn đề | Giải pháp |
|--------|-----------|
| `docker: command not found` | Cài Docker: https://docs.docker.com/engine/install/ |
| `permission denied` | `sudo usermod -aG docker $USER` rồi logout/login |
| `error getting credentials` | Xóa `credsStore` trong `~/.docker/config.json` |
| `no space left on device` | `docker system prune -a` để xóa images/containers cũ |
| FreeSurfer license error | Copy license.txt vào `license/` directory |
| HD-BET timeout | Chạy CPU mất ~15 phút/lần, lần đầu download 109MB weights |
| Streamlit không mở | Thử `streamlit run app.py --server.port 8502` |
