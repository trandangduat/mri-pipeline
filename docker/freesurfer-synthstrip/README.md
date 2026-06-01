# mri_synthstrip Docker Tool (`mri-synthstrip:latest`)

## Mo ta
Skull-stripping (boc tach hop so) bang mo hinh Deep Learning tich hop cua FreeSurfer 7.4.1. Sinh ra anh nao da boc so va file mask nhi phan.

## Build
```bash
docker build -t mri-synthstrip:latest .
```

## Test command
```bash
docker run --rm \
  -v ./data:/input \
  -v ./outputs_test/member1/sub-002:/output \
  -v ./work/member1/sub-002:/work \
  -v ./license:/license \
  mri-synthstrip:latest \
  run_tool \
  --input /input/sub-002_T1w.nii \
  --output-dir /output \
  --work-dir /work \
  --subject-id sub-002 \
  --threads 8 \
  --device cpu
```

## Output
```
outputs_test/member1/<subject>/
├── logs/
│   └── synthstrip.log
work/member1/<subject>/
├── 02_synthstrip_brain.nii.gz
└── 02_synthstrip_brain_mask.nii.gz
```

## GPU
```bash
docker run --rm --gpus all \
  -v ./data:/input \
  -v ./outputs_test/member1/sub-002:/output \
  -v ./work/member1/sub-002:/work \
  -v ./license:/license \
  mri-synthstrip:latest \
  run_tool \
  --input /input/sub-002_T1w.nii \
  --output-dir /output \
  --work-dir /work \
  --subject-id sub-002 \
  --threads 8 \
  --device gpu
```

## Exit code
- `0`: Thanh cong
- `1`: Input khong ton tai
- `2`: mri_synthstrip that bai
- `3`: Thieu output brain hoac mask file
