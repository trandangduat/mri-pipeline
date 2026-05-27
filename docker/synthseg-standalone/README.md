# SynthSeg Standalone Docker Image

This directory contains the Dockerfile and wrapper scripts to run the standalone version of SynthSeg from its GitHub repository.

## Pre-requisites for Build

SynthSeg requires model weights to run. To prevent the container from downloading them every time, you should copy the weights into the `models` directory before building the Docker image.

**Tải model weights:**
Nếu bạn chưa có models, bạn có thể tải chúng (file `SynthSeg_models.zip`) trực tiếp từ link OneDrive của tác giả tại đây:
[Download SynthSeg_models.zip (MIT OneDrive)](https://mitprod-my.sharepoint.com/personal/bbillot_mit_edu/_layouts/15/onedrive.aspx?id=%2Fpersonal%2Fbbillot%5Fmit%5Fedu%2FDocuments%2FSynthSeg%5Fmodels%2Ezip&parent=%2Fpersonal%2Fbbillot%5Fmit%5Fedu%2FDocuments&ga=1)

Sau khi tải về, giải nén và copy vào thư mục `models`:

```bash
mkdir -p models
# Nếu bạn đã có sẵn ở local:
cp ../../models/synthseg/* models/
# Hoặc copy từ thư mục bạn vừa giải nén:
# cp /đường/dẫn/đến/folder/giải/nén/* models/

# Tiến hành build
docker build -t mri-synthseg-standalone:latest .
```

## Run

```bash
docker run --rm \
  -v ./data:/input \
  -v ./outputs_test/member2:/output \
  -v ./work/member2:/work \
  mri-synthseg-standalone:latest \
  --input /input/sub-001_T1w.nii.gz \
  --output-dir /output/sub-001 \
  --work-dir /work/sub-001 \
  --subject-id sub-001 \
  --threads 8 \
  --device cpu
```

## Outputs

- `work/03_synthseg_standalone_segmentation.nii.gz`
- `work/03_synthseg_standalone_volumes.tsv`
- `stats/subcortical_volume.tsv`
- `stats/cortical_volume.tsv`
