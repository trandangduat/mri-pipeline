# SPM/CAT12 Integration Research

Research date: 2026-07-30

Question: How should SPM/CAT12 be integrated into this MRI pipeline, considering official SPM/CAT12 behavior, standalone/runtime options, outputs, the repo's nine-stage architecture, Docker packaging, stats/vector adapters, and licensing/runtime caveats?

## Short Answer

SPM is the general MATLAB-based Statistical Parametric Mapping neuroimaging package from UCL/FIL. CAT/CAT12 is a computational anatomy toolbox that runs inside SPM and extends SPM segmentation for structural morphometry: VBM, DBM, SBM, and ROI/RBM analyses. CAT is therefore the relevant integration target for this pipeline's structural volume and cortical-thickness outputs; SPM is the host/runtime layer and provides file I/O, batch execution, segmentation foundations, and statistics infrastructure.

The lowest-friction implementation is a CAT standalone Docker image using the official CAT standalone bundle plus MATLAB Runtime R2023b/v232, exposed as a new tool family in `pipeline/registry.py`. Start with a CAT volume-only preset that runs CAT segmentation with surface extraction disabled and adapts `catROI*.xml` plus TIV/global-volume outputs into the repo's existing `subcortical_volume.tsv` and `cortical_volume.tsv`/new CAT-specific TSVs. Then add a CAT full preset with surface/thickness enabled and parse CAT surface/ROI thickness outputs into CAT-provenance vector columns rather than reusing FreeSurfer feature semantics.

## Primary Sources Inspected

| Source | Used for |
|---|---|
| Official SPM home page, `https://www.fil.ion.ucl.ac.uk/spm/` | Definition of SPM and modalities. |
| Official SPM12 page, `https://www.fil.ion.ucl.ac.uk/spm/software/spm12/` | MATLAB/core-toolbox requirements, NIfTI/GIfTI formats, standalone availability. |
| Official SPM standalone docs, `https://www.fil.ion.ucl.ac.uk/spm/docs/installation/standalone/` | MATLAB Runtime behavior, batch invocation, contributed-toolbox limitation. |
| Official SPM container docs, `https://www.fil.ion.ucl.ac.uk/spm/docs/installation/containers/` | Official standalone-based SPM Docker packaging. |
| Official SPM GitHub README, `https://raw.githubusercontent.com/spm/spm/main/README.md` | GPL license and SPM software summary. |
| Official CAT site, `https://neuro-jena.github.io/cat/` | CAT definition, SPM toolbox status, morphometry scope, standalone/runtime note. |
| Official CAT manual, `https://neuro-jena.github.io/cat12-help/` | CAT processing, quick-start outputs, volume/surface/ROI behavior. |
| Official ENIGMA CAT12 page, `https://neuro-jena.github.io/enigma-cat12/#standalone` | Standalone shell examples and output filenames/folders. |
| Official CAT GitHub README, `https://raw.githubusercontent.com/ChristianGaser/cat12/26.0.rc4/README.md` | CAT requirements, installation under `spm/toolbox`, GPL, standalone links. |
| Official CAT defaults source, `https://raw.githubusercontent.com/ChristianGaser/cat12/26.0.rc4/cat_defaults.m` | Default output knobs for surface, ROI, tissue maps, warps, atlases. |
| Repo architecture and code: `AGENTS.md`, `pipeline/registry.py`, `pipeline/config.py`, `pipeline/stats.py`, `pipeline/export.py`, `pipeline/executor.py` | Current nine-stage, Docker, export, and stats/vector seams. |

## SPM vs CAT12

SPM stands for Statistical Parametric Mapping. The official SPM site defines both the statistical methodology and a free/open-source software package for analysis of brain imaging data sequences, including fMRI, PET, SPECT, EEG, and MEG. SPM12 is a MATLAB suite that requires core MATLAB only, uses NIfTI-1 for image data, uses GIfTI for surface-based data, and ships precompiled MEX binaries for major platforms. Sources: SPM home page; SPM12 page; SPM GitHub README.

CAT is a Computational Anatomy Toolbox for SPM. The official CAT site describes CAT as an extension to SPM that provides computational anatomy methods including voxel-based morphometry, surface-based morphometry, deformation-based morphometry, and region-/label-based morphometry. The CAT README says it is designed to work with SPM12 or newer, installs by copying the CAT folder into `spm/toolbox`, and requires MATLAB R2007a or newer with no additional toolboxes. Sources: CAT site; CAT GitHub README.

CAT is therefore an SPM toolbox, not a separate replacement for SPM. For this pipeline, CAT should be modeled as a tool family that owns structural morphometry outputs while depending on either SPM+MATLAB or the compiled CAT standalone runtime.

## Standalone and Runtime Options

SPM has an official standalone distribution compiled with MATLAB Compiler. Official SPM docs say it does not require a MATLAB license, but it does require MATLAB Runtime matching the version used to compile SPM. It can run GUI modes, `batch`, or `batch <file.mat|file.m>`. The same docs state that contributed SPM toolboxes are not present in standalone SPM and cannot be added without recompilation. Sources: SPM standalone docs.

SPM also has official container documentation. The official SPM Dockerfile uses Standalone SPM, and images are hosted in the GitHub container registry. This is useful evidence that a standalone-runtime container pattern is acceptable for SPM, but it is not sufficient for CAT unless CAT is compiled into that standalone image. Source: SPM container docs.

CAT provides its own standalone version. The CAT site and README say the standalone version needs no MATLAB license and uses MATLAB Runtime R2023b/v232; the CAT site notes limitations such as no parallelization and no interactive help in the GUI version, and that standalone is primarily intended for headless Unix use. The ENIGMA CAT12 page provides shell examples using `cat_standalone.sh -m <runtime> -b <batch.m> <inputs>`. Sources: CAT site; CAT README; ENIGMA CAT12 page.

Recommended runtime choice for this repo: use CAT standalone in Docker first. It avoids requiring the user's MATLAB license inside a container and avoids the SPM-standalone contributed-toolbox recompilation problem.

## Outputs Supporting Volume and Cortical Thickness

CAT supports volume morphometry through VBM/RBM. The CAT site says VBM estimates the local amount or volume of tissue compartments and RBM estimates regional tissue volumes, optionally cortical thickness, for volume and surface atlas maps. The manual quick start says CAT segmentation writes VBM segmentations in the `mri` folder, with `mwp1` for gray matter and `mwp2` for white matter, and uses XML files in the `report` folder for TIV. The ENIGMA page provides `cat_standalone_get_TIV.m`, which can save TIV and optionally global GM, WM, CSF, and WMH volumes. Sources: CAT site; CAT manual; ENIGMA CAT12 page.

CAT supports cortical thickness through the surface pipeline. The CAT site says CAT estimates cortical thickness and central surfaces using projection-based thickness. The manual quick start says enabling surface and thickness estimation writes surface data in `surf`, named `?h.thickness.*`; resampling/smoothing produces outputs like `s12.mesh.resampled_32k.thickness.*`. The manual also says ROI-based thickness extraction is included in the segmentation pipeline since CAT12.7, and the ENIGMA page says `cat_standalone_get_ROI_values.m` saves mean surface values such as cortical thickness and mean volumes from `label/catROI*.xml`. Sources: CAT site; CAT manual; ENIGMA CAT12 page.

CAT defaults confirm that surface/thickness and ROI XML outputs are first-class controls: `cat.output.surface = 1` by default, `cat.output.ROI = 1`, modulated GM/WM outputs are enabled, native labels are enabled, forward deformation fields are enabled, and volume/surface atlas definitions are present. Source: CAT `cat_defaults.m`.

## Mapping to the Repo's Nine Stages

The repo stage order is fixed in `pipeline/registry.py`: `reorientation`, `brain_extraction`, `segmentation`, `template_registration`, `bias_correction`, `white_matter_segmentation`, `surface_reconstruction`, `surface_registration`, and `stats_extraction`. Tool definitions live in `TOOL_DEFS`, Docker execution is delegated through `ExecutionRequest`/`LocalDockerExecutor`, and `runner.py` builds a `ToolContext` for `command_builder` functions. Sources: `AGENTS.md`; `pipeline/registry.py`; `pipeline/runner.py`; `pipeline/executor.py`.

| Repo stage | CAT/SPM mapping | Integration note |
|---|---|---|
| `reorientation` | SPM/CAT expects well-oriented T1 NIfTI input; SPM can import/convert DICOM/NIfTI. | Initially reuse existing reorientation or call CAT on the original/conformed input. Do not make CAT DICOM import the first implementation unless needed. |
| `brain_extraction` | CAT preprocessing includes skull-stripping inside its segmentation flow. | CAT does not naturally expose a FreeSurfer-like independent brain-extraction stage; model as no-op/hidden or a CAT preflight stage unless writing a derived brain mask is required. |
| `segmentation` | CAT `estwrite` performs initial SPM segmentation, refined CAT segmentation, tissue maps, labels, VBM outputs, ROI XML, and optional surface. | This is the main CAT run. It may cover several repo stages in one command, similar to tool families that maintain subject workspace state. |
| `template_registration` | CAT performs spatial normalization using DARTEL/Geodesic Shooting templates and writes deformation fields when configured. | Verify deformation output paths and expose the forward deformation field as the stage output. |
| `bias_correction` | CAT writes bias/noise/global-intensity corrected T1 outputs when configured. | Map to corrected T1 in CAT `mri` output, but avoid forcing a separate rerun. |
| `white_matter_segmentation` | CAT writes GM/WM/CSF tissue maps and labels. | Use WM tissue maps/labels as stage outputs if the pipeline needs this checkpoint. |
| `surface_reconstruction` | CAT optional surface-based processing estimates central surfaces and `?h.thickness.*`. | Enable when cortical thickness is requested; disable for volume-only mode using the documented standalone override. |
| `surface_registration` | CAT registers individual surfaces to FreeSurfer `FsAverage` and can resample/smooth thickness to 32k template space. | Prefer a separate post-step for resample/smooth if vectors should use template-space thickness. |
| `stats_extraction` | CAT ROI/TIV scripts export TIV, global tissue volumes, ROI volumes, and mean surface values. | Add CAT-specific parsers/adapters that convert XML/CSV outputs into long TSVs with explicit CAT provenance. |

Because CAT segmentation is monolithic, the cleanest mapping is not nine separate CAT Docker commands at first. Use a CAT tool family where the first CAT command populates the subject's CAT derivatives, later repo stages validate/copy expected outputs, and stats extraction runs lightweight CAT standalone helper batches or Python XML parsers.

### Dependency-Driven Stage Correction

The repo should not force a CAT12 preset to execute every semantic stage. CAT segmentation already includes skull stripping, bias correction, tissue segmentation, spatial normalization, ROI output, and optional surface/thickness estimation. Therefore the CAT preset should be driven by the requested stats vectors, not by a one-to-one translation of the nine stage labels.

For `CAT12 + Volume`, the minimum useful work is input preparation, one CAT segmentation run with ROI output enabled and surface output disabled, then stats extraction/parsing. Separate `brain_extraction`, `template_registration`, `bias_correction`, `white_matter_segmentation`, `surface_reconstruction`, and `surface_registration` stages should be blank/skipped unless the UI needs cheap output validation checkpoints. They are internal CAT operations, not separate required Docker jobs for the volume vector.

For `CAT12 + Volume + Cortical Thickness`, the minimum useful work is input preparation, one CAT segmentation run with surface/thickness and ROI output enabled, then stats extraction/parsing. Separate surface stages are not required to generate ROI cortical-thickness vectors if CAT's segmentation pipeline already writes the needed surface/ROI thickness outputs. They can be represented as skipped or cheap validators, but should not rerun CAT surface processing.

This is similar in spirit to the existing FastSurfer volume/thickness design where not every named pipeline stage is independently required. A robust implementation should encode this in `PRESET_CONFIGS` rather than relying on UI-only hiding, so CLI and saved presets do not accidentally run unnecessary stages.

## Docker Packaging Implications

Package CAT as a dedicated Docker image, not as an extension of the current FreeSurfer images. The image should contain the CAT standalone release, MATLAB Runtime R2023b/v232, a small wrapper script, and any batch files needed for volume-only and full/surface processing. CAT standalone's limitation around no internal parallelization means the repo should control concurrency at the subject/job level and avoid assuming CAT's `nproc` behaves like MATLAB-standard CAT. Sources: CAT site; ENIGMA CAT12 page.

Do not rely on official standalone SPM Docker plus a mounted CAT folder. Official SPM standalone docs say contributed SPM toolboxes cannot be added without recompilation, so that route is fragile unless the image is rebuilt specifically with CAT. Source: SPM standalone docs.

### Can CAT12 Be Installed Into `ghcr.io/spm/spm-docker`?

The local image available on this workstation is `ghcr.io/spm/spm-docker:docker-matlab-latest`, not `ghcr.io/spm/spm-docker:latest`. Inspecting it showed entrypoint `spm`, `SPM_TAG=25.01.02`, MATLAB Runtime R2024b libraries in `LD_LIBRARY_PATH`, `/opt/spm` as the SPM installation, and no CAT toolbox in `/opt/spm/toolbox`. Running `spm eval "disp(spm('Ver')); disp(exist('CAT','file')); disp(exist('cat_defaults','file'));"` returned SPM25 standalone and `0` for CAT/CAT defaults.

The official `spm-docker` README and Dockerfile confirm that the `docker-matlab-latest` image is built from SPM Standalone plus MATLAB Runtime, not from a full MATLAB interpreter. Official SPM standalone documentation explicitly says contributed SPM toolboxes are not present and cannot be added without a whole recompilation. Therefore copying a CAT/CAT12 folder into `/opt/spm/toolbox` in this image is expected to succeed only as a filesystem operation; it should not make CAT executable through the compiled SPM standalone runtime.

There are three viable alternatives:

1. Build a separate CAT standalone image using the official CAT standalone bundle and the matching MATLAB Runtime R2023b/v232. This is the recommended route for this repo.
2. Build an image with full MATLAB, SPM source, and CAT installed under `spm/toolbox/CAT`; this requires a MATLAB license at runtime and is less suitable for redistribution.
3. Recompile SPM standalone with CAT included using MATLAB Compiler; this requires MATLAB plus MATLAB Compiler and is more complex than using the official CAT standalone distribution.

Using `ghcr.io/spm/spm-docker:docker-matlab-latest` as a base image is possible only if the derived image installs CAT standalone and the matching R2023b runtime alongside SPM's existing R2024b runtime, or if SPM is recompiled with CAT. It is not a drop-in CAT12 base image.

### Existing CAT12 Docker Images

Docker Hub already has CAT12 images, so a custom build is not the first option.

`jhuguetn/cat12` is the clearest ready-to-use candidate. Docker Hub describes it as a CAT12 standalone image with no MATLAB license required, and its source repository is `jhuguetn/cat12-docker`. The Dockerfile installs MATLAB Runtime R2023b/v232, downloads the official CAT standalone Linux ZIP, installs it under `/opt/spm`, and sets the entrypoint to `/opt/spm/standalone/cat_standalone.sh`. The current useful tag is `r2665-2`, also aliased by `latest`, with digest `sha256:97a5e7c01bd546f44313575628b7d6152e99fa4f58ed1e0e106824e109c3ce06` and compressed size about 5.8 GB according to Docker Hub tag metadata. Example invocation from the image README is `docker run -v /data:/data jhuguetn/cat12 -b /opt/spm/standalone/cat_standalone_segment.m /data/img.nii`.

`vnmd/cat12_26.0.rc3` and `vnmd/cat12_12.9` appear to be Neurodesk/neurocontainers builds. The Neurodesk `recipes/cat12/build.yaml` builds CAT12 standalone from the official CAT release, installs MATLAB Runtime R2023b under `/opt/mcr/R2023b`, installs CAT under `/opt/cat12`, and deploys `run_spm25.sh`, `spm25`, `cat_standalone.sh`, and `cat_parallelize.sh`. The recipe's full test suite verifies `/opt/cat12/standalone/cat_standalone_segment.m`, `cat_standalone_segment_enigma.m`, `cat_standalone_get_TIV.m`, `cat_standalone_get_ROI_values.m`, and related helpers. Docker Hub tag metadata lists `vnmd/cat12_26.0.rc3:latest` at about 6.2 GB and `vnmd/cat12_12.9:latest` at about 3.0 GB. These are good candidates, but they should be pull-tested because Docker Hub does not provide as much usage documentation as `jhuguetn/cat12`.

`bids/cat12:unstable` also exists, with compressed size about 2.9 GB, but Docker Hub exposes little description/source metadata. It should not be selected as the default without pull-testing and locating its source/build recipe.

Recommended external-image order for this repo:

1. Try `jhuguetn/cat12:r2665-2` first because it has public source, a direct CAT standalone entrypoint, clear invocation examples, and recent maintenance.
2. If image size/startup or version policy is a problem, test `vnmd/cat12_26.0.rc3:latest` or `vnmd/cat12_12.9:latest` from Neurodesk.
3. Only build a local image if none of the above can run the exact CAT batch and output layout needed by the pipeline.

The image can follow the repo's existing registry pattern: add command builders in `pipeline/registry.py`, define output globs, set a long timeout comparable to FreeSurfer reconstruction stages, and mark it as `needs_license: False` if using CAT standalone. The repo's executor already supports bind mounts, env vars, timeouts, memory limits, and command overrides. Sources: `pipeline/registry.py`; `pipeline/executor.py`; `pipeline/runner.py`.

## Stats and Vector Adapter Implications

The current vector code is FreeSurfer/FastSurfer-shaped. `StatsVectorConfig` defines `cortical_thickness`, `cortical_volume`, and `subcortical_volume`; `StatsGenerator` reads FreeSurfer `.stats` files, existing `subcortical_volume.tsv`/`cortical_volume.tsv`, and atlas-specific `*_cortical_thickness.tsv` files into vectors aligned to fixed `info/*_feats.txt` files. Sources: `pipeline/config.py`; `pipeline/stats.py`.

CAT outputs should not be silently mapped to FreeSurfer feature names unless an atlas/schema equivalence is proven. CAT ROI volume outputs are atlas/tissue-measure outputs, often in CAT template/ROI space, while FreeSurfer `aparc.stats` cortical `GrayVol` and `ThickAvg` are surface-parcellation metrics. Add CAT-specific provenance fields/column names such as `cat_neuromorphometrics_volume`, `cat_tiv`, `cat_global_gm_volume`, and `cat_desikan_thickness` rather than reusing `aparc_cortical_thickness` blindly.

Implementation implication: add a CAT stats adapter that reads CAT `report/cat_*.xml` and `label/catROI*.xml` or CSVs produced by `cat_standalone_get_TIV.m` and `cat_standalone_get_ROI_values.m`, then writes normalized long TSVs. Suggested TSV columns are `subject`, `tool`, `cat_version`, `atlas`, `space`, `measure`, `tissue`, `region`, `hemisphere`, `value`, and `unit`. `StatsGenerator` can then add CAT-specific vector specs only when the feature list and atlas are known.

## Licensing and Runtime Caveats

SPM is GPL software according to the official SPM README. CAT is free but copyrighted and distributed under GPL v2 or later according to the CAT site and README. The MATLAB Runtime does not require a MATLAB license for compiled applications, according to the CAT site/README and SPM standalone docs. Sources: SPM README; CAT site; CAT README; SPM standalone docs.

Runtime caveats are operationally important: MATLAB Runtime version must match the compiled standalone build; CAT standalone currently points to R2023b/v232; runtime installation is large; first execution can unpack CTF files and needs writable cache space; GUI behavior is not the target for this headless pipeline; standalone CAT has limitations around parallelization and interactive help. Sources: SPM standalone docs; CAT site; ENIGMA CAT12 page.

For Docker distribution, confirm whether bundling MATLAB Runtime in the image is acceptable for the intended deployment and citation/license policy. If uncertain, build the Dockerfile to download/install runtime at build time from MathWorks/CAT-provided links, record exact versions, and keep the image private until redistribution terms are reviewed.

## Recommended Implementation Path

1. Add a `docker/cat12-standalone` image with CAT standalone Linux plus MATLAB Runtime R2023b/v232 and minimal wrapper scripts.
2. Add CAT tool definitions in `pipeline/registry.py` behind a new preset, starting with one monolithic CAT segmentation command that writes into the subject workspace and uses `cat_standalone_segment_enigma.m` with surface disabled for volume-only mode.
3. Add output-glob validation for CAT `mri`, `report`, `label`, and optional `surf` outputs; keep repo stages lightweight validators after the initial CAT run rather than re-running CAT per stage.
4. Add a CAT stats adapter that converts TIV/global-volume/ROI XML or CAT helper CSV outputs to long TSVs with CAT provenance.
5. Add CAT-specific vector specs and feature files only after selecting exact CAT atlas outputs to support; do not merge CAT features into existing FreeSurfer vectors without provenance.
6. Add full/surface mode after volume-only works: enable CAT surface output, optionally resample/smooth thickness, parse mean thickness ROI outputs, and expose cortical-thickness vectors under CAT-specific columns.
7. Add unit tests for the CAT stats parser using small fixture XML/CSV files, plus registry tests for expected output globs and command construction.

## Conclusion

CAT12 is the right SPM-based structural morphometry integration point. It can provide both volume outputs and cortical-thickness outputs, but it should enter this repo as a CAT standalone Docker tool family with explicit CAT stats/vector provenance. Treat SPM as the required host/runtime ecosystem, not as the primary stats-output adapter.
