# mri_convert Docker Tool (`mri-mri-convert:latest`)

## Mo ta
Dung de reorient hoac chuyen dinh dang anh MRI. Ho tro doc truc tiep `.mgz`, `.nii`, `.nii.gz`.

## Build
```bash
docker build -t mri-mri-convert:latest .
```

## Test command
```bash
docker run --rm \
  -v ./data:/input \
  -v ./outputs_test/member1/sub-002:/output \
  -v ./work/member1/sub-002:/work \
  -v ./license:/license \
  mri-mri-convert:latest \
  run_tool \
  --input /input/sub-002_T1w.nii \
  --output-dir /output \
  --work-dir /work \
  --subject-id sub-002 \
  --threads 1 \
  --device cpu
```

## Output
```
outputs_test/member1/<subject>/
├── logs/
│   └── mri_convert.log
work/member1/<subject>/
└── 01_reoriented.nii.gz
```

## Exit code
- `0`: Thanh cong
- `1`: Input khong ton tai
- `2`: mri_convert that bai
- `3`: Thieu output file
