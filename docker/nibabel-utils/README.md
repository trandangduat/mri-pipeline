# NiBabel Preprocessing Utility (`mri-nibabel-utils:latest`)

## Mo ta
Tien xu ly anh MRI bang NiBabel: doc anh thoi, chuan hoa huong ve RAS (Right-Anterior-Superior), luu ra file `.nii.gz`.

## Build
```bash
docker build -t mri-nibabel-utils:latest .
```

## Test command
```bash
docker run --rm \
  -v ./data:/input \
  -v ./outputs_test/member3/sub-002:/output \
  -v ./work/member3/sub-002:/work \
  mri-nibabel-utils:latest \
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
outputs_test/member3/<subject>/
├── logs/
│   └── nibabel_utils.log
work/member3/<subject>/
└── 01_nibabel_reoriented.nii.gz
```

## Exit code
- `0`: Thanh cong
- `1`: Input khong ton tai
- `2`: Loi khi xu ly anh
