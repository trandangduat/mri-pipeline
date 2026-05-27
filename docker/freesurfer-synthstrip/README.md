# mri_synthstrip Docker Tool (`mri-synthstrip:latest`)

## Mô tả
Công cụ thực hiện Skull-stripping (bóc tách hộp sọ) bằng mô hình Deep Learning tích hợp của FreeSurfer. Sinh ra ảnh não đã bóc sọ và file mask.

## Command Chuẩn (Test)
```bash
docker run --rm \
  -v ./data:/input \
  -v ./outputs_test/member1/sub-001:/output \
  -v ./work/member1/sub-001:/work \
  -v ./license:/license \
  mri-synthstrip:latest \
  --input /input/sub-001.mgz \
  --output-dir /output \
  --work-dir /work \
  --subject-id sub-001 \
  --threads 8 \
  --device cpu
