# MRI Processing Pipeline

Docker-based MRI preprocessing pipeline with Streamlit GUI.

## Output Structure

```
outputs/
  <subject_id>/
    mri/          — NIfTI/MGZ volume files
    stats/        — TSV/CSV statistics
    logs/         — tool logs + execution timing
```

Default `subject_id` = input filename without extension (e.g., `sub-002_T1w.nii` -> `sub-002_T1w`).

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Images are pulled automatically from Docker Hub on first run.

## Pipeline Stages

| Stage | Tools |
|-------|-------|
| Reorientation | mri_convert, nibabel |
| Brain Extraction | synthstrip, hdbet |
| Segmentation | synthseg_freesurfer, synthseg_standalone, fastsurfervinn |
| Bias Correction | ants_n4 |

## Python API

```python
from pipeline_runner import PipelineConfig, run_pipeline

config = PipelineConfig(
    input_file="data/sub-002_T1w.nii",
    output_dir="outputs",
    subject_id="sub-002",
    license_dir="license",
    device="cpu",
    threads=4,
)

results = run_pipeline(config)
```

## Requirements

- Docker 20.10+
- Python 3.9+
- 8GB+ RAM (16GB recommended)

## Project Structure

```
├── app.py                # Streamlit GUI
├── pipeline_runner.py    # Pipeline orchestrator
├── requirements.txt
├── DEPLOYMENT.md         # Deployment guide
├── setup.sh              # Auto-install script
├── docker/               # Dockerfiles for 9 tools
├── data/                 # Test MRI data
├── license/              # FreeSurfer license
└── models/               # Model weights (gitignored)
```
