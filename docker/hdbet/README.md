# HD-BET Brain Extraction (`mri-hdbet:latest`)

## Mo ta
Boc tach hop so (skull-stripping) bang mo hinh Deep Learning HD-BET. Sinh ra anh nao da boc so va file mask.

**Luu y**: HD-BET can tai model weights (109MB) tu zenodo.org lan dau chay. Can mount volume de giu weights tran bi tai lai.

## Build
```bash
docker build -t mri-hdbet:latest .
```

## Test command
```bash
mkdir -p work/member3/hdbet_weights

docker run --rm \
  -v ./data:/input \
  -v ./outputs_test/member3/sub-002:/output \
  -v ./work/member3/sub-002:/work \
  -v ./work/member3/hdbet_weights:/root/.cache/torch/hub/checkpoints \
  mri-hdbet:latest \
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
│   └── hdbet.log
work/member3/<subject>/
├── 02_hdbet_brain.nii.gz
└── 02_hdbet_brain_mask.nii.gz
```

## GPU
```bash
docker run --rm --gpus all \
  -v ./data:/input \
  -v ./outputs_test/member3/sub-002:/output \
  -v ./work/member3/sub-002:/work \
  -v ./work/member3/hdbet_weights:/root/.cache/torch/hub/checkpoints \
  mri-hdbet:latest \
  run_tool \
  --input /input/sub-002_T1w.nii \
  --output-dir /output \
  --work-dir /work \
  --subject-id sub-002 \
  --threads 1 \
  --device gpu
```

## Exit code
- `0`: Thanh cong
- `1`: Loi input hoac config
- `2`: Loi khi chay HD-BET

## Thoi gian
- CPU: khoang 2 phut voi `--disable_tta`, tuy kich thuoc anh va CPU
- GPU: vai giay den 1-2 phut, tuy GPU va kich thuoc anh

Tham khao upstream HD-BET: https://github.com/MIC-DKFZ/HD-BET
