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

## New Azure Server Test State

Server details and credentials were provided out of band. Do not commit passwords or private keys.

Workspace on server:

```bash
/home/mriuser/cat12-surface-test
```

Useful server files:

```bash
/home/mriuser/cat12-surface-test/input/input.nii.gz
/home/mriuser/cat12-surface-test/Dockerfile.cat12_26_glibc
/home/mriuser/cat12-surface-test/build_and_run_cat12_fixed.sh
/home/mriuser/cat12-surface-test/scripts/run_cat12_surface_test.sh
/home/mriuser/cat12-surface-test/scripts/test_cat12_docker_image.sh
```

Tmux session used for patched image test:

```bash
tmux attach -t cat12_surface_glibc
```

Logs:

```bash
tail -f /home/mriuser/cat12-surface-test/output/cat12_26_glibc_build.log
tail -f /home/mriuser/cat12-surface-test/output/cat12_surface_glibc.log
```

The build of `local/cat12_26_glibc:latest` completed successfully. The first test attempt failed because the test script tried to `docker pull local/cat12_26_glibc:latest`; the script was patched on the server to skip pulling if the image already exists locally. The test was restarted in `cat12_surface_glibc`.

At the end of the previous session, SSH to the server began timing out, so final status of the patched-image run was not confirmed.

## Commands To Check Patched CAT12 Surface Test

```bash
ssh mriuser@104.214.184.21
tmux ls
tmux attach -t cat12_surface_glibc
```

Or non-interactive checks:

```bash
tail -120 /home/mriuser/cat12-surface-test/output/cat12_surface_glibc.log
find /home/mriuser/cat12-surface-test/output/cat12_surface_glibc_output -maxdepth 5 -type f \
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

## Known Risks / Next Steps

- CAT12 full cortical thickness is not proven until `local/cat12_26_glibc:latest` completes successfully.
- If the patched image works, update `CAT12_SURFACE_IMAGE` in `pipeline/registry.py` to a real pushed image tag rather than `vnmd/cat12_26.0.rc3:latest`.
- If the patched image fails, inspect whether failure is still `CAT_FixTopology`, a missing shared library, or input-specific CAT preprocessing.
- CAT12 volume path should remain on `jhuguetn/cat12:r2665-2` unless another image is proven more stable for volume-only.
