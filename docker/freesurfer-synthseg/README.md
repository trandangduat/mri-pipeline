# mri_synthseg Docker Tool (`mri-synthseg-freesurfer:latest`)

## Mo ta
Phan vung nao (Segmentation) va trich xuat the tich bang 3D U-Net tich hop cua FreeSurfer 7.4.1. Bao gom script `normalize_volumes.py` de tu dong chuyen CSV goc thanh 2 file TSV dung format.

## Build
```bash
docker build -t mri-synthseg-freesurfer:latest .
```

## Test command
```bash
docker run --rm \
  -v ./data:/input \
  -v ./outputs_test/member1/sub-002:/output \
  -v ./work/member1/sub-002:/work \
  -v ./license:/license \
  mri-synthseg-freesurfer:latest \
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
outputs_test/member1/<subject>/
├── logs/
│   └── synthseg_freesurfer.log
├── stats/
│   ├── subcortical_volume.tsv
│   └── cortical_volume.tsv
work/member1/<subject>/
├── 03_freesurfer_synthseg_segmentation.nii.gz
└── 03_freesurfer_synthseg_volumes.csv
```

## Format TSV
subcortical_volume.tsv:
```tsv
subject	structure	volume_mm3	tool
sub-002	left hippocampus	3426.325	FreeSurferSynthSeg
sub-002	right hippocampus	3558.713	FreeSurferSynthSeg
```

cortical_volume.tsv:
```tsv
subject	region	hemisphere	volume_mm3	tool
sub-002	cerebral cortex	lh	210206.95	FreeSurferSynthSeg
sub-002	cerebral cortex	rh	212808.816	FreeSurferSynthSeg
```

## Exit code
- `0`: Thanh cong
- `1`: Input khong ton tai
- `2`: mri_synthseg hoac normalize_volumes that bai
- `3`: Thieu segmentation hoac volumes CSV
