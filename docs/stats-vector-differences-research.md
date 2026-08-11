# Stats Vector Differences Research

Research date: 2026-07-29

Question: Why do stats vectors differ between `batch_20260729_132743_fs7_full`, `batch_20260729_013341_fastsurfer_full`, `batch_20260725_220504_fs8_full`, and `batch_20260726_154327_fs8_volume`, when comparing only features that both sides have numeric values?

## Short Answer

Most observed differences have plausible, non-catastrophic explanations: FreeSurfer 8 changed the reconstruction stream relative to FreeSurfer 7, FastSurfer uses a different segmentation/surface pipeline and DKT-derived aparc mapping, and the FS8 volume-only run uses SynthSeg-style volumetric labels rather than surface-derived `aparc.stats` morphometry. The concerning part is not that the numbers differ; it is mixing these sources under the same vector names without source/provenance tags.

The safest interpretation is:

| Comparison | Interpretation |
|---|---|
| FS7 full vs FS8 full cortical volume/thickness | Reasonably comparable; differences are expected from version/pipeline changes. |
| FS7/FS8 full vs FastSurfer full | Partly comparable, but atlas/schema differences matter, especially missing aparc regions. |
| Any full pipeline vs FS8 volume-only cortical volume | Not directly comparable as the same metric; surface `aparc.stats` and volumetric SynthSeg labels measure different things. |
| FS8 full vs FS8 volume-only SynthSeg subcortical outputs | Highly comparable; in this batch their common `synthseg.vol.csv` values are identical. |

## Findings

FreeSurfer 8 is expected to differ from FreeSurfer 7. The FreeSurfer release notes state that FreeSurfer 8 `recon-all` output differs from version 7, and the FS8 stream incorporates newer tools such as SynthSeg, SynthStrip, and SynthMorph. Since `lh.aparc.stats` and `rh.aparc.stats` are generated from the reconstructed surfaces, small changes in skull stripping, segmentation, white/pial surface placement, and registration can change both `GrayVol` and `ThickAvg`. Sources: FreeSurfer release notes `https://surfer.nmr.mgh.harvard.edu/fswiki/ReleaseNotes`; `recon-all` docs `https://surfer.nmr.mgh.harvard.edu/fswiki/recon-all`; `mris_anatomical_stats` docs `https://surfer.nmr.mgh.harvard.edu/fswiki/mris_anatomical_stats`.

Surface cortical volume is not the same as a voxel count. FreeSurfer's morphometry documentation describes cortical volume as a measure derived from the white and pial surfaces, and `mris_anatomical_stats` reports parcellation statistics from surface anatomy. Therefore, cortical `GrayVol` from `lh/rh.aparc.stats` should not be treated as the same measurement as a SynthSeg volumetric cortical label. This explains why FS8 volume-only cortical volumes can have high relative differences versus FS7/FS8 full even when the run is successful. Sources: FreeSurfer morphometry stats `https://surfer.nmr.mgh.harvard.edu/fswiki/MorphometryStats`; `mris_anatomical_stats` docs `https://surfer.nmr.mgh.harvard.edu/fswiki/mris_anatomical_stats`; SynthSeg docs `https://surfer.nmr.mgh.harvard.edu/fswiki/SynthSeg`.

FastSurfer's missing `bankssts`, `frontalpole`, and `temporalpole` entries are plausibly an atlas/schema issue rather than failed anatomy. FastSurfer's documented outputs center on `aparc.DKTatlas+aseg`, and the DKT-style atlas merges or omits some classic Desikan-Killiany aparc labels. In the local batch this appears as 62 cortical volume/thickness regions instead of 68, with the missing classic aparc regions `bankssts`, `frontalpole`, and `temporalpole` in both hemispheres. These should be encoded as unavailable for that source, not as zeros. Sources: FastSurfer introduction `https://deep-mi.org/FastSurfer/stable/overview/intro.html`; FastSurfer output files `https://deep-mi.org/FastSurfer/stable/overview/OUTPUT_FILES.html`; FastSurfer LUT `https://raw.githubusercontent.com/Deep-MI/FastSurfer/stable/FastSurferCNN/config/FastSurfer_ColorLUT.tsv`; FreeSurfer LUT documentation `https://surfer.nmr.mgh.harvard.edu/fswiki/FsTutorial/AnatomicalROI/FreeSurferColorLUT`.

The very large CSF difference between classic FS7/FastSurfer `aseg.stats` and FS8/SynthSeg is likely a label-definition difference, not simply a numeric error. In these batches, FS7/FastSurfer `CSF` is around 1.4k-1.6k mm3, while FS8/SynthSeg-style `CSF` is around 451k-463k mm3. FreeSurfer 8 uses SynthSeg in the modern stream, and SynthSeg includes CSF for intracranial volume estimation. FreeSurfer source comments also distinguish broader extracerebral CSF behavior in SAMSEG/SynthSeg-style segmentations from classic aseg labels. This feature should be version/source-qualified before longitudinal or cross-pipeline comparison. Sources: FreeSurfer release notes `https://surfer.nmr.mgh.harvard.edu/fswiki/ReleaseNotes`; SynthSeg docs `https://surfer.nmr.mgh.harvard.edu/fswiki/SynthSeg`; FreeSurfer source `utils/cma.cpp` `https://raw.githubusercontent.com/freesurfer/freesurfer/dev/utils/cma.cpp`.

Zero/nonzero differences can be reporting-schema artifacts. FreeSurfer `mri_segstats` can report only non-empty structures or include empty structures depending on options such as `--empty`. FastSurfer's `segstats.py` has similar behavior. A downstream vector builder that aligns to a fixed feature list can accidentally conflate absent labels, empty labels, and true zero measurements. Sources: FreeSurfer `mri_segstats` docs `https://surfer.nmr.mgh.harvard.edu/fswiki/mri_segstats`; FastSurfer `segstats.py` docs `https://deep-mi.org/FastSurfer/stable/scripts/segstats.html`.

Aggregate measures need provenance. In the local FastSurfer stats, `VentricleChoroidVol` differs between `aseg.stats` and `brainvol.stats`: `64728.339281` versus `16725.024617`. That does not necessarily mean either file is corrupt; aggregate measures can be imported, recomputed, or defined over different constituent labels. The vector pipeline should not silently merge same-named aggregate measures from different files unless source precedence is explicit. Sources: FastSurfer `segstats.py` docs `https://deep-mi.org/FastSurfer/stable/scripts/segstats.html`; FreeSurfer `mri_segstats` source `https://raw.githubusercontent.com/freesurfer/freesurfer/dev/mri_segstats/mri_segstats.cpp`; FreeSurfer label/measure source `https://raw.githubusercontent.com/freesurfer/freesurfer/dev/utils/cma.cpp`.

FreeSurfer 8 has a known stats reporting caveat around segmented intracranial volume in some 8.0 outputs. The release notes mention a `csvprint` Python 2 issue that can cause `SegmentedIntraCranialVolume` to be reported as `0.00` in `aseg.stats`, with a patch available. Any zero or missing FS8 intracranial aggregate should be treated as a reporting issue candidate before biological interpretation. Source: FreeSurfer release notes `https://surfer.nmr.mgh.harvard.edu/fswiki/ReleaseNotes`.

## Interpretation For The Current Batches

The low relative differences for FS7 vs FS8 full cortical stats are reassuring. Median relative difference was about `3.59%` for cortical volume and `2.40%` for thickness, which is consistent with two related but not identical FreeSurfer versions.

The FastSurfer full run is not failing just because it has fewer aparc features. Its missing regions match the expected DKT/classic-aparc schema mismatch. The vector builder should mark these as missing for FastSurfer, not zero.

The FS8 volume-only cortical volume vector should be labeled as volumetric/SynthSeg-derived. It should not be used as a drop-in replacement for surface `aparc.stats` cortical `GrayVol` in the same model without normalization or source indicators.

The FS8 full and FS8 volume-only subcortical SynthSeg outputs are internally consistent. Their shared `synthseg.vol.csv` features are identical in this subject, so the differences seen against `aseg.stats` are primarily source-definition differences rather than random run instability.

## Practical Recommendations

Store feature provenance with each vector key: source file, tool family, atlas, and metric type. For example, distinguish `surface_aparc_grayvol:lh:insula` from `synthseg_volume:lh:insula`.

Use pairwise comparisons only within compatible metric families. Good comparisons include FS7 `lh.aparc.stats` vs FS8 `lh.aparc.stats`, or FS8 full `synthseg.vol.csv` vs FS8 volume `synthseg.vol.csv`. Risky comparisons include FS8 volume `cortical_volume.tsv` vs FreeSurfer surface `aparc.stats` `GrayVol`.

Treat zero/nonzero relative differences as a special QA class. A `200%` relative diff often means absent-vs-present or zero-vs-nonzero, not necessarily a proportional anatomical discrepancy.

For aggregate measures such as `BrainSegVol`, `CortexVol`, `VentricleChoroidVol`, and `eTIV`, compare only when the source file and definition are the same or explicitly documented.
