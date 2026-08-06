# CAT12 SPM Handoff

Date: 2026-08-06

## Branches

- Base branch: `fix-fastsurfer-pipeline`
- CAT12 development branch: `integrate-cat12-volume`
- Merged/pushed branch for continuation: `feature/cat12-spm-presets`

## What Is Implemented

- Added GUI presets:
  - `CAT12 + Volume`
  - `CAT12 + Volume + Cortical Thickness`
- CAT12 is modeled as a monolithic SPM/CAT segmentation step plus a stats extraction step.
- CAT12 presets skip separate repo stages that CAT performs internally:
  - `reorientation`
  - `brain_extraction`
  - `template_registration`
  - `bias_correction`
  - `white_matter_segmentation`
  - `surface_reconstruction`
  - `surface_registration`
- Added CAT12 XML parsing in `normalize_volumes.py`:
  - `report/cat_*.xml` for TIV/global tissue volumes.
  - `label/catROI_*.xml` for ROI volume values.
  - CAT ROI thickness values into `cat12_cortical_thickness.tsv` when available.
- Remote job handling now canonicalizes preset-selected tools from `pipeline_mode`, preventing stale GUI selections from accidentally running FastSurfer/FreeSurfer reorientation before CAT12.

## Important Files

- `pipeline/presets.py`: CAT12 preset definitions and skipped stages.
- `pipeline/registry.py`: CAT12 Docker tool definitions and command builders.
- `normalize_volumes.py`: CAT12 report/ROI XML parsers.
- `ui/main.py`: CAT12 stage skipping in GUI.
- `ui/gui_pipeline.py`: run request uses preset tools for non-Custom modes.
- `remote/remote_runner.py`: remote CLI args use preset tools for non-Custom modes.
- `pipeline/job_worker.py`: remote worker canonicalizes `selected_tools` from `pipeline_mode`.
- `tests/test_cat12_volume_preset.py`: CAT12 registry/preset command tests.
- `tests/test_cat12_volume_normalization.py`: CAT12 XML parser tests.

## Current Runtime Findings

- `jhuguetn/cat12:r2665-2`
  - Volume-only works.
  - Surface/cortical-thickness fails in CAT binary `CAT_FixTopology` with segmentation fault.
  - This reproduced on both the original server and a new Azure server.
- `vnmd/cat12_26.0.rc3:latest`
  - The stock image fails early because `cat_sanlm.mexa64` requires `GLIBC_2.34`, but the container has GLIBC 2.31.
- A patched local image was being tested on the new Azure server:
  - Image tag: `local/cat12_26_glibc:latest`
  - Built by copying `/opt/cat12` and `/opt/mcr` from `vnmd/cat12_26.0.rc3:latest` into an Ubuntu 22.04 base image with GLIBC 2.35.
  - This is a server-local experimental image, not pushed to a registry.
- The matching Dockerfile is now in the repo at `docker/cat12_26_glibc/Dockerfile` for local build/publish as `duattran05/cat12_26_glibc:latest`.
- The patched local image completed CAT12 cortical thickness successfully on `catcd1@10.8.0.1`.
  - Previous `cat_sanlm.mexa64` `GLIBC_2.34` failure is resolved by the Ubuntu 22.04 base.
  - Previous `CAT_FixTopology` segmentation fault did not reproduce in this image.
  - CAT12 reported average thickness `2.2115 +/- 0.4703 mm` and wrote cortical thickness files for both hemispheres.
  - Raw FreeSurfer curv thickness values were validated as finite, positive, and plausible: LH mean `2.256294 mm`, RH mean `2.166684 mm`, combined LH+RH mean `2.212437 mm` and std `0.472864 mm`.
  - Combined LH+RH raw values match CAT12's reported average thickness closely: mean delta `0.000937 mm`, std delta `0.002564 mm`.
  - Thickness vertex/face counts match the corresponding `central`, `pial`, `white`, `sphere`, and `sphere.reg` GIFTI surfaces for LH, RH, and cerebellum.
- A later CAT12 full run failed on a `.mgz` input because the old command copied `001.mgz` to `/work/input.nii` without conversion, causing SPM/CAT `read_hdr` to reject the file. The CAT12 GLIBC image now includes `python3-nibabel`, and the pipeline command converts `.mgz`/`.mgh` inputs to NIfTI before launching CAT.

## New Azure Server Test State

Server details and credentials were provided out of band. Do not commit passwords or private keys.

Latest successful workspace on `catcd1@10.8.0.1`:

```bash
/home/catcd1/duat-jobs/run-cat12-glibc
```

Useful server files from the successful run:

```bash
/home/catcd1/duat-jobs/run-cat12-glibc/Dockerfile.cat12_26_glibc
/home/catcd1/duat-jobs/run-cat12-glibc/run_cat12_glibc_surface.sh
/home/catcd1/duat-jobs/run-cat12-glibc/logs/surface_20260806_112907.log
/home/catcd1/duat-jobs/run-cat12-glibc/output/surface_20260806_112907/SUCCESS_THICKNESS.txt
```

Tmux session used for patched image test:

```bash
tmux attach -t cat12_glibc_surface
```

Final successful outputs included:

```bash
/home/catcd1/duat-jobs/run-cat12-glibc/output/surface_20260806_112907/label/catROI_input.xml
/home/catcd1/duat-jobs/run-cat12-glibc/output/surface_20260806_112907/report/cat_input.xml
/home/catcd1/duat-jobs/run-cat12-glibc/output/surface_20260806_112907/surf/lh.thickness.input
/home/catcd1/duat-jobs/run-cat12-glibc/output/surface_20260806_112907/surf/rh.thickness.input
/home/catcd1/duat-jobs/run-cat12-glibc/output/surface_20260806_112907/surf/lh.central.input.gii
/home/catcd1/duat-jobs/run-cat12-glibc/output/surface_20260806_112907/surf/rh.central.input.gii
```

The build and full surface/thickness run of `local/cat12_26_glibc:latest` completed successfully. The first test attempt failed because the test script tried to `docker pull local/cat12_26_glibc:latest`; the server run script was patched to skip pulling for the local image.

## Commands To Check Patched CAT12 Surface Test

```bash
ssh -i /tmp/opencode/duat_ssh_key -p 19622 catcd1@10.8.0.1
tmux ls
tmux attach -t cat12_glibc_surface
```

Or non-interactive checks:

```bash
tail -120 /home/catcd1/duat-jobs/run-cat12-glibc/logs/surface_20260806_112907.log
find /home/catcd1/duat-jobs/run-cat12-glibc/output/surface_20260806_112907 -maxdepth 5 -type f \
  \( -name "*thickness*" -o -name "*.gii" -o -name "catROI_*.xml" -o -name "cat_*.xml" \) | sort
```

Successful CAT12 thickness output should include files such as:

```text
*thickness*
lh.central.input.gii
rh.central.input.gii
catROI_*.xml
```

## Verification Run Locally

On the merge branch, run:

```bash
python3 -m compileall pipeline/ remote/ ui/ normalize_volumes.py tests/test_cat12_volume_preset.py tests/test_cat12_volume_normalization.py tests/test_gui_pipeline_mode_sync.py tests/test_job_worker.py tests/test_remote_runner.py
```

`pytest` was not available in the local WSL environment during development.

## Build And Publish Fixed CAT12 Image

Build the proven GLIBC-rebased CAT12 image locally:

```bash
docker build -t duattran05/cat12_26_glibc:latest docker/cat12_26_glibc
```

Smoke-test the image before pushing:

```bash
docker run --rm --entrypoint sh duattran05/cat12_26_glibc:latest -lc 'ldd --version | head -n 1; python3 -c "import nibabel"; test -x /opt/cat12/standalone/cat_standalone.sh; test -d /opt/mcr/R2023b'
```

Publish to Docker Hub:

```bash
docker login
docker push duattran05/cat12_26_glibc:latest
```

The image was pushed successfully to Docker Hub:

```text
duattran05/cat12_26_glibc:latest
digest: sha256:a7be6fa0f1613ad5876eb813553019ec9add19aac5a5c0fe72a826f91a4a54f3
linux/amd64 manifest: sha256:2e3d81a280a8c0922b2a2065019c447d8e75a19ea0689e67c1df032e8d667921
```

`CAT12_IMAGE` and `CAT12_SURFACE_IMAGE` in `pipeline/registry.py` now point to `duattran05/cat12_26_glibc:latest` so both CAT12 presets can use the same GLIBC-fixed image and `.mgz`/`.mgh` conversion path.

## Known Risks / Next Steps

- CAT12 full cortical thickness is proven with server-local `local/cat12_26_glibc:latest` and the pushed `duattran05/cat12_26_glibc:latest` image built from `docker/cat12_26_glibc/Dockerfile`.
- Keep monitoring future CAT12 inputs for image-specific or input-specific surface failures, because only one subject has been fully validated so far.
- CAT12 volume path should remain on `jhuguetn/cat12:r2665-2` unless another image is proven more stable for volume-only.
