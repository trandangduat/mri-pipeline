# FreeSurfer Base Image (`mri-freesurfer-base`)

## Mo ta
Base image nen tang cho toan bo cac cong cu thuoc he sinh thai FreeSurfer. Duoc build tu `freesurfer/freesurfer:7.4.1` (CentOS), da cau san Python 3 va cac bien moi truong can thiet.

FreeSurfer 7.4.1 da bao gom: `mri_convert`, `mri_synthstrip`, `mri_synthseg`.

## Cau hinh
- `FREESURFER_HOME`: `/usr/local/freesurfer`
- `FS_LICENSE`: `/license/license.txt`
- Base OS: CentOS (da patch vault.centos.org vi CentOS 8 da EOL)
- Python 3.6 duoc cai them

## Build
```bash
docker build -t mri-freesurfer-base:latest .
```

## Cac image con ke thua
- `mri-mri-convert:latest`
- `mri-synthstrip:latest`
- `mri-synthseg-freesurfer:latest`

## Volume mount chuan
```bash
-v ./data:/input
-v ./outputs_test/member1/<subject>:/output
-v ./work/member1/<subject>:/work
-v ./license:/license
```
