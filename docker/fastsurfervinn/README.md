# FastSurferVINN Docker Image

This directory contains the Dockerfile and wrapper scripts to run FastSurferVINN.

## Build

```bash
docker build -t mri-fastsurfervinn:latest .
```

## Run

```bash
docker run --rm \
  -v ./data:/input \
  -v ./outputs_test/member2:/output \
  -v ./work/member2:/work \
  -v ./license:/license \
  mri-fastsurfervinn:latest \
  --input /input/sub-001_T1w.nii.gz \
  --output-dir /output/sub-001 \
  --work-dir /work/sub-001 \
  --subject-id sub-001 \
  --threads 8 \
  --device cpu
```

## Outputs

- `work/03_fastsurfervinn_segmentation.nii.gz` or `.mgz`
- `stats/subcortical_volume.tsv`
- `stats/cortical_volume.tsv`
