# ANTs N4 Bias Field Correction (`mri-ants:latest`)

## Mo ta
Chuan hoa cuong do sang anh MRI bang thuat toan N4 Bias Field Correction cua ANTs. Khac phuc hieu ung bong mo, vung sang toi khong dong deu do tu truong may quet.

## Build
```bash
docker build -t mri-ants:latest .
```

## Test command
```bash
docker run --rm \
  -v ./data:/input \
  -v ./outputs_test/member3/sub-002:/output \
  -v ./work/member3/sub-002:/work \
  mri-ants:latest \
  run_tool \
  --input /input/sub-002_T1w.nii \
  --output-dir /output \
  --work-dir /work \
  --subject-id sub-002 \
  --threads 4 \
  --device cpu
```

## Output
```
outputs_test/member3/<subject>/
├── logs/
│   └── ants_n4.log
work/member3/<subject>/
└── 05_standardized.nii.gz
```

## Exit code
- `0`: Thanh cong
- `1`: Input khong ton tai
- `2`: Loi khi chay ANTs
- `3`: Chay xong nhung thieu output
