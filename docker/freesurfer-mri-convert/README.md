# mri_convert Docker Tool (`mri-mri-convert:latest`)

## Mô tả
Công cụ dùng để reorient hoặc chuyển đổi định dạng ảnh MRI (hỗ trợ đọc thẳng `.mgz` hoặc `.nii.gz`).

## Command Chuẩn (Test)
```bash
docker run --rm \
  -v ./data:/input \
  -v ./outputs_test/member1/sub-001:/output \
  -v ./work/member1/sub-001:/work \
  -v ./license:/license \
  mri-mri-convert:latest \
  --input /input/sub-001.mgz \
  --output-dir /output \
  --work-dir /work \
  --subject-id sub-001 \
  --threads 1 \
  --device cpu


