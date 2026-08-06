# CAT12 26 GLIBC Image

This image rebases `vnmd/cat12_26.0.rc3:latest` onto Ubuntu 22.04 so CAT12 runs with GLIBC 2.35.

The server-local image built from this Dockerfile completed CAT12 cortical thickness successfully with `output.surface = 2` and produced valid LH/RH thickness files.

The image includes `python3-nibabel` so the pipeline can convert FreeSurfer `.mgz`/`.mgh` inputs to NIfTI before launching CAT/SPM.

## Build

```bash
docker build -t duattran05/cat12_26_glibc:latest docker/cat12_26_glibc
```

## Smoke Test

```bash
docker run --rm --entrypoint sh duattran05/cat12_26_glibc:latest -lc 'ldd --version | head -n 1; python3 -c "import nibabel"; test -x /opt/cat12/standalone/cat_standalone.sh; test -d /opt/mcr/R2023b'
```

## Push

```bash
docker login
docker push duattran05/cat12_26_glibc:latest
```

## Pipeline Switch

After the image is pushed and pull-tested, update `CAT12_SURFACE_IMAGE` in `pipeline/registry.py` from `vnmd/cat12_26.0.rc3:latest` to `duattran05/cat12_26_glibc:latest`.
