# CAT12 native volume contracts

These corrections apply to newly generated CAT12 outputs.
They do not change scheduler policies or historical results.

## Native identity and tissue selection

`info/cat12_roi_mapping.txt` records native atlas IDs, ROI IDs, labels, abbreviations, hemisphere, category, fields, and feature names.
Its header records SHA-256 hashes of the supplied CAT12 atlas dictionaries.
These files contain atlas metadata, not patient measurements.

Match source XML IDs and labels before selecting tissue arrays.
Duplicate abbreviations, including JulichBrain3 lCM, require the native ROI ID.
A conflicting ID and label produces an explicit error.

For dictionaries with Vgm/Vwm/Vcsf flags, use every designated tissue field.
Cross-check the mapping against `cat12_tissue_flags.txt`.
Undefined tissue selections and unavailable required arrays remain NA.

Other cortical volume contracts use the native Vgm measurement.
Thalamus and thalamic-nuclei dictionaries use their native Vgm measurement.
SUIT exports lobule parenchyma as Vgm+Vwm, excluding CSF.
These contracts are explicit metadata, not region-name guesses.

CAT12 defines separate tissue measurements in its
[native ROI implementation](https://github.com/ChristianGaser/cat12/blob/main/cat_main_roi.m).
Its [atlas defaults](https://github.com/ChristianGaser/cat12/blob/main/cat_defaults.m) identify the exported tissue channels.

Convert native volume mL to mm3 once, after field selection.
Thickness remains in millimeters.
Atlas TSVs append roi_id and retain native labels.
The reader never borrows a same-name value from another atlas or a mixed general TSV.

## Anatomical subsets

The metadata lists the exact native category of every supported row.
Schaefer variants use their corresponding 17-network cortical parcels.
AAL3 cortical IDs are 1–40, 43–44, 47–74, 83–94, and 151–156.
Mori cortical IDs are 1–48.
LPBA40 uses its cortical dictionary rows below ID 160.

Anatomy3 excludes its nuclei, basal-forebrain, amygdala, and hippocampal subdivisions from the cortical vector.
Its entorhinal cortex remains cortical.
JulichBrain3 cortical entries use native cortical areas.
Its fourteen GapMap entries remain unclassified and are excluded from cortical features.
They do not become invented anatomical regions.

Hammers subcortical IDs are 1–4, 17–19, 34–49, 74, and 75.
Its remaining seventy regions use a separate cortical feature list.
Native flags still determine the contributing tissue fields in both categories.

## Feature contracts

Some old lists described different atlases or incomplete network summaries.
Their corrected counts and names intentionally change new CSV columns.

| Atlas/statistic | Previous slots | Corrected slots |
|---|---:|---:|
| Schaefer 100 / 17, cortical | 8 | 100 |
| Schaefer 200 / 17, cortical | 8 | 200 |
| Schaefer 400 / 17, cortical | 8 | 400 |
| Schaefer 600 / 17, cortical | 8 | 600 |
| AAL3 cortical | 62 | 88 |
| Anatomy3 cortical | 90 | 154 |
| JulichBrain3 cortical | 106 | 270 |
| Mori cortical | 50 | 48 |
| COBRA subcortical | 14 | 52 |
| Hammers subcortical | 23 | 25 |
| Hammers cortical | Shared subcortical list | Separate 70 |
| SUIT subcortical | 34 | 28 |
| Thalamic nuclei | 28 | 24 |
| Thalamus | 2 | 14 |
| LPBA40 cortical | 48 | Unchanged 48 |
| IBSR subcortical | 16 | Unchanged 16 |
| Neuromorphometrics subcortical | 33 | Unchanged 33 |

LPBA40 and IBSR retain valid existing feature contracts through exact aliases.
On the supplied native samples, LPBA40 has forty numeric slots and eight unavailable slots.
IBSR has fourteen numeric slots and two unavailable whole-cerebellum slots.
No arbitrary aggregation substitutes for unavailable source definitions.
Neuromorphometrics retains thirty numeric slots and three genuine NA slots.

Static lists follow the corresponding native dictionary order where contracts needed replacement.
Their entries do not depend on which measurements a patient produces.
`stats_vectors_manifest.json` records the feature file for each generated column.

CAT12 batch reports align stored per-subject values by feature name.
An older vector's index cannot silently label a value with a new region name.
Both summary and wide CSVs use the aligned feature order.
Existing per-subject files are not rewritten by report export.

## Runtime resources

Packaging, Docker mounts, and SSH staging include both CAT12 dictionaries.
Selected-atlas SSH upload sends these dictionaries separately from atlas feature assets.
Changed metadata invalidate the shared-code signature.
Feature lists are uploaded without file-size shortcuts.

CAT12 volume normalization rejects missing, unreadable, empty, or malformed dictionaries.
FreeSurfer and FastSurfer do not acquire a mandatory CAT12 dependency.

## Validation

Focused tests cover native IDs, duplicate abbreviations, hemispheres, tissue selection, missing arrays, and old-vector alignment.
They also cover resource delivery and cross-atlas isolation.

Independent checks used the supplied I7054 and I329386 XML and native dictionaries.
Each sample checked 2,621 classified native rows, including undefined entries.
Every checked measurement, requested vector value, and batch CSV value matched.
Fourteen JulichBrain3 GapMap rows were excluded explicitly.
Neuromorphometrics retained all thirty numeric reference feature matches.

The actual SSH uploader staged code and resources into a clean local directory.
A separate Python process normalized each native sample there.
Its four TSV outputs matched the local outputs byte for byte.

The final focused suite passed 330 tests.
Another 67 scheduler/RAM/retry contract cases passed.
No MRI inference, historical cohort, real server deployment, or desktop executable build was run.
