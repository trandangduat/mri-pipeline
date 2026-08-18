# MNI Atlas Assets

External MNI atlas NIfTI and LUT files used by the FreeSurfer 8 MNI atlas projection stage.

Files are mounted into the Docker container at `/atlases` when an external MNI atlas is selected. To use a different asset directory, set `MRI_PIPELINE_MNI_ATLAS_DIR` before running the pipeline.

Sources are documented in `atlas_sources.csv`.

- `HarvardOxford-subl-maxprob-thr0-1mm.nii.gz` / `harvard_oxford_sub_LUT.txt` (lateralized, 22 regions; Brain-Stem split into left/right halves)
- `HarvardOxford-cortl-maxprob-thr0-1mm.nii.gz` / `harvard_oxford_cort_LUT.txt` (lateralized, 96 regions)
- `BN_Atlas_246_1mm.nii.gz` / `BN_Atlas_246_LUT.txt`
- `pauli_2017_labels.nii.gz` / `pauli_2017_LUT.txt`
- `juelich_maxprob-thr0-1mm.nii.gz` / `juelich_LUT.txt`
- `aal.nii.gz` / `aal_LUT.txt`
- `schaefer2018_100_7.nii.gz` / `schaefer2018_100_7_LUT.txt`
- `sclimbic.t1.nii.gz` / `sclimbic_LUT.txt` (backup; `mni_sclimbic` uses the copy bundled with the FreeSurfer 8 image)