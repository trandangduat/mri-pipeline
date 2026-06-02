# Phân công push Docker images lên Docker Hub

## Quy trình chung

1. **Mỗi thành viên** tạo tài khoản Docker Hub tại https://hub.docker.com
2. **Login** trên terminal: `docker login`
3. **Chạy script** tương ứng với phần của mình
4. **Báo lại username** Docker Hub cho người code để cập nhật image names

---

## Thành viên 1 — Baor (FreeSurfer Stack)

```bash
# Đăng nhập Docker Hub
docker login

# Chạy script push (thay YOUR_USERNAME)
./member1_push.sh YOUR_USERNAME
```

| Image | Kích thước | Ghi chú |
|-------|-----------|---------|
| `mri-freesurfer-base` | ~9 GB | Base image, push đầu tiên |
| `mri-mri-convert` | ~9 GB | Share layers với base → push nhanh |
| `mri-synthstrip` | ~9 GB | Share layers với base → push nhanh |
| `mri-synthseg-freesurfer` | ~9 GB | Share layers với base → push nhanh |

**Thời gian ước tính:** 30-60 phút (base push đầu, còn lại share layers nên nhanh)

---

## Thành viên 2 — duaajt (Standalone Segmentation)

```bash
docker login
./member2_push.sh YOUR_USERNAME
```

| Image | Kích thước | Ghi chú |
|-------|-----------|---------|
| `mri-synthseg-standalone` | ~8 GB | CUDA + TensorFlow |
| `mri-fastsurfervinn` | ~10 GB | FastSurfer + dependencies |

**Thời gian ước tính:** 30-45 phút

---

## Thành viên 3 — khang (Non-FreeSurfer Tools)

```bash
docker login
./member3_push.sh YOUR_USERNAME
```

| Image | Kích thước | Ghi chú |
|-------|-----------|---------|
| `mri-nibabel-utils` | ~200 MB | Nhỏ nhất, push nhanh |
| `mri-hdbet` | ~3 GB | PyTorch CPU + HD-BET |
| `mri-ants` | ~1.5 GB | ANTsPy |

**Thời gian ước tính:** 10-15 phút

---

## Sau khi tất cả push xong

Mỗi thành viên **báo username Docker Hub** cho người code.

Ví dụ:
- Member 1 username: `baor`
- Member 2 username: `duaajt`  
- Member 3 username: `khang`

Người code sẽ sửa `pipeline_runner.py`:

```python
TOOL_DEFS = {
    "mri_convert":     {"image": "baor/mri-mri-convert:latest", ...},
    "nibabel":         {"image": "khang/mri-nibabel-utils:latest", ...},
    "synthstrip":      {"image": "baor/mri-synthstrip:latest", ...},
    "hdbet":           {"image": "khang/mri-hdbet:latest", ...},
    "synthseg_freesurfer": {"image": "baor/mri-synthseg-freesurfer:latest", ...},
    "synthseg_standalone": {"image": "duaajt/mri-synthseg-standalone:latest", ...},
    "fastsurfervinn":  {"image": "duaajt/mri-fastsurfervinn:latest", ...},
    "ants_n4":         {"image": "khang/mri-ants:latest", ...},
}
```

Hoặc nếu muốn dùng chung 1 account (khuyến nghị):
- Tạo Docker Hub **organization** (miễn phí)
- Tất cả push vào organization đó
- Ví dụ: `mriproject/mri-freesurfer-base:latest`
