# mri_synthseg Docker Tool (`mri-synthseg-freesurfer:latest`)

## Mô tả
Công cụ phân vùng não (Segmentation) và trích xuất thể tích. Sử dụng mạng 3D U-Net. Image này bao gồm một script `normalize_volumes.py` để tự động parse file CSV gốc thành 2 file TSV riêng biệt.

## Command Chuẩn (Test)
```bash
docker run --rm \
  -v ./data:/input \
  -v ./outputs_test/member1/sub-001:/output \
  -v ./work/member1/sub-001:/work \
  -v ./license:/license \
  mri-synthseg-freesurfer:latest \
  --input /input/sub-001.mgz \
  --output-dir /output \
  --work-dir /work \
  --subject-id sub-001 \
  --threads 4 \
  --device cpu
