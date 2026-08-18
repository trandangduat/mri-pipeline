# Plan: Integrate MNI Volume Atlases into Stats Vector Output

## Goal

Allow users to select multiple atlases for each stats vector type (subcortical volume, cortical volume, cortical thickness). When multiple atlases are selected, the output must contain a separate vector for each atlas.

**Naming convention:**

```
{vector_type}                         → default atlas (first in list)
{vector_type}_{atlas_short_name}      → non-default atlases
```

**Example:**

User selects:
- `subcortical_volume`: [freesurfer_aseg, harvard_oxford_subcortical]
- `cortical_volume`: [freesurfer_aparc, harvard_oxford_cortical]
- `cortical_thickness`: [aparc, schaefer2018_100_7]

Output vectors:
```
subcortical_volume                      → freesurfer_aseg (default)
subcortical_volume_harvard_oxford_sub   → harvard_oxford_subcortical
cortical_volume                         → freesurfer_aparc (default)
cortical_volume_harvard_oxford_cort     → harvard_oxford_cortical
cortical_thickness                      → aparc (default)
cortical_thickness_schaefer2018         → schaefer2018_100_7
```

## Current State

### What exists today

1. **Three stats vector types**: `subcortical_volume`, `cortical_volume`, `cortical_thickness`
2. **Default atlases per preset** (hardcoded in `pipeline/presets.py`):
   - FreeSurfer: `freesurfer_aseg`, `freesurfer_aparc`, `aparc`
   - CAT12: `cat12_neuromorphometrics`, `cat12_schaefer2018_200parcels_17networks`, `aparc`
   - FastSurfer: `fastsurfer_dkt`, `fastsurfer_dkt`, `aparc`
3. **Vector column names** are hardcoded in `VECTOR_SPECS` (stats.py):
   - `freesurfer_aseg` → column `freesurfer_aseg_subcortical_volume`
   - `harvard_oxford_subcortical` → column `harvard_oxford_subcortical_volume`
   - `aparc` → column `aparc_cortical_thickness`
4. **Feature lists** exist in `info/` directory (one file per atlas)
5. **LUT files** exist in `MNI_ATLASES/` directory (created during testing)

### What does NOT exist yet

1. No dynamic column naming based on vector type + atlas
2. No MNI atlas projection tool for FreeSurfer 8 (only `mni_sclimbic` is implemented)
3. No integration of external MNI atlases (Harvard-Oxford, Brainnetome, etc.) into the pipeline
4. No atlas short name mapping for the desired naming convention

### Proven workflow (tested manually)

The following workflow was tested and confirmed working for FreeSurfer 8:

```bash
# Step 1: Register MNI template to subject (once per subject, ~60s)
mri_synthmorph register -m affine \
    -t mni152_to_subject.affine.lta \
    $FREESURFER_HOME/average/mni305.cor.stripped.mgz \
    subject/mri/norm.mgz

# Step 2: Warp atlas to subject space (per atlas, ~5s)
mri_vol2vol --mov atlas.nii.gz \
    --targ subject/mri/norm.mgz \
    --o atlas.mgz \
    --lta mni152_to_subject.affine.lta \
    --nearest

# Step 3: Extract volumes (per atlas, ~2s)
mri_segstats --seg atlas.mgz --sum atlas.stats --ctab atlas_LUT.txt
```

**Tested atlases:**

| Atlas | Regions | NIfTI File | LUT File |
|-------|---------|------------|----------|
| SCLimbic | 13 | `sclimbic.t1.nii.gz` | `sclimbic_LUT.txt` |
| Harvard-Oxford Sub | 21 | `HarvardOxford-sub-maxprob-thr25-1mm.nii.gz` | `harvard_oxford_sub_LUT.txt` |
| Harvard-Oxford Cort | 48 | `HarvardOxford-cort-maxprob-thr25-1mm.nii.gz` | `harvard_oxford_cort_LUT.txt` |
| Brainnetome 246 | 246 | `BN_Atlas_246_1mm.nii.gz` | `BN_Atlas_246_LUT.txt` |
| Pauli 2017 | 15 | `pauli_2017_labels.nii.gz` | `pauli_2017_LUT.txt` |
| Juelich | 62 | `juelich_maxprob-thr0-1mm.nii.gz` | `juelich_LUT.txt` |
| AAL3 | 167 | `aal.nii.gz` | `aal_LUT.txt` |
| Schaefer 2018 (100p, 7n) | 100 | `schaefer2018_100_7.nii.gz` | `schaefer2018_100_7_LUT.txt` |

All atlas files are stored in `C:\Users\ADMIN\Desktop\MRI\MNI_ATLASES\`.

## Design Decisions

### D1: Use FreeSurfer 8 for MNI atlas projection

**Decision:** Use `mri_synthmorph register` + `mri_vol2vol` + `mri_segstats` (FreeSurfer 8 tools) for MNI atlas projection.

**Rationale:**
- FreeSurfer 8 Docker image (`mkdayyyy/mri-fs8-all:latest`) is already available
- `mri_synthmorph` produces fast, accurate affine registration
- `mri_vol2vol --nearest` correctly handles discrete label maps
- `mri_segstats` extracts volumes with proper LUT support
- The registration transform is reusable across all MNI atlases (same MNI152 space)

**Alternatives considered:**
- ANTs registration: More complex, not needed for affine-only registration
- CAT12 internal registration: Only works with CAT12's built-in atlases
- FastSurfer: No MNI152 registration capability

### D2: Dynamic column naming

**Decision:** Generate column names dynamically based on vector type and atlas selection.

**Format:**
```
{vector_type}                    → default atlas (first in list)
{vector_type}_{atlas_short_name} → non-default atlases
```

**Atlas short name mapping:**

| Atlas Key | Short Name |
|-----------|------------|
| `freesurfer_aseg` | *(default, no suffix)* |
| `freesurfer_aparc` | *(default, no suffix)* |
| `aparc` | *(default, no suffix)* |
| `harvard_oxford_subcortical` | `harvard_oxford_sub` |
| `harvard_oxford_cortical` | `harvard_oxford_cort` |
| `brainnetome246` | `brainnetome246` |
| `pauli_2017` | `pauli_2017` |
| `juelich` | `juelich` |
| `aal` | `aal` |
| `schaefer2018_100_7` | `schaefer2018` |
| `sclimbic` | `sclimbic` |
| `cat12_neuromorphometrics` | *(default for CAT12, no suffix)* |
| `cat12_schaefer2018_200parcels_17networks` | *(default for CAT12, no suffix)* |
| `fastsurfer_dkt` | *(default for FastSurfer, no suffix)* |

### D3: Registration transform reuse

**Decision:** Compute the MNI→Subject affine transform once per subject, then reuse for all MNI atlases.

**Storage:** `<subject>/stats/atlas_mapping/mni152_to_subject.affine.lta`

**Cache key:** Subject's `norm.mgz` file path (the transform is valid as long as the subject data does not change).

### D4: Preserve backward compatibility

**Decision:** Default atlas selections produce identical output to current implementation.

**Requirements:**
- Default presets use the same atlases as today
- Column names for default atlases remain unchanged
- Feature lists remain unchanged
- Output file structure remains unchanged
- No new Docker images or tools required for default configuration

### D5: Atlas assets location

**Decision:** Atlas NIfTI files and LUT files are stored in a configurable directory, defaulting to `assets/atlases/mni/`.

**Structure:**
```
assets/atlases/mni/
├── sclimbic.t1.nii.gz
├── sclimbic_LUT.txt
├── HarvardOxford-sub-maxprob-thr25-1mm.nii.gz
├── harvard_oxford_sub_LUT.txt
├── HarvardOxford-cort-maxprob-thr25-1mm.nii.gz
├── harvard_oxford_cort_LUT.txt
├── BN_Atlas_246_1mm.nii.gz
├── BN_Atlas_246_LUT.txt
├── pauli_2017_labels.nii.gz
├── pauli_2017_LUT.txt
├── juelich_maxprob-thr0-1mm.nii.gz
├── juelich_LUT.txt
├── aal.nii.gz
├── aal_LUT.txt
├── schaefer2018_100_7.nii.gz
├── schaefer2018_100_7_LUT.txt
└── atlas_sources.csv
```

### D6: Scope limitation

**Decision:** This plan covers FreeSurfer 8 presets only. CAT12 and FastSurfer are out of scope for this iteration.

**Rationale:**
- CAT12 uses its own built-in atlases (different mechanism)
- FastSurfer has no MNI152 registration capability
- FreeSurfer 8 has the most flexible atlas support

## Implementation Plan

### Step 1: Add atlas short name mapping

**File:** `pipeline/config.py`

Add a dictionary mapping atlas keys to their short names for column naming:

```python
ATLAS_SHORT_NAMES: dict[str, str] = {
    "freesurfer_aseg": "",
    "freesurfer_aparc": "",
    "aparc": "",
    "harvard_oxford_subcortical": "harvard_oxford_sub",
    "harvard_oxford_cortical": "harvard_oxford_cort",
    "brainnetome246": "brainnetome246",
    "pauli_2017": "pauli_2017",
    "juelich": "juelich",
    "aal": "aal",
    "schaefer2018_100_7": "schaefer2018",
    "sclimbic": "sclimbic",
    "cat12_neuromorphometrics": "",
    "cat12_schaefer2018_200parcels_17networks": "",
    "fastsurfer_dkt": "",
}
```

Add MNI atlas definitions to `EXTERNAL_MNI_*` tuples:

```python
EXTERNAL_MNI_SUBCORTICAL_VOLUME_ATLASES: tuple[str, ...] = (
    "mni_sclimbic",
    "harvard_oxford_subcortical",
    "brainnetome246",      # has subcortical regions
    "pauli_2017",
    "aal",                 # has subcortical regions
)

EXTERNAL_MNI_CORTICAL_VOLUME_ATLASES: tuple[str, ...] = (
    "harvard_oxford_cortical",
    "brainnetome246",      # has cortical regions
    "juelich",
    "aal",                 # has cortical regions
    "schaefer2018_100_7",
)
```

### Step 2: Add VECTOR_SPECS for new atlases

**File:** `pipeline/stats.py`

Add entries to `VECTOR_SPECS` for each new atlas:

```python
"harvard_oxford_subcortical": {
    "column": "harvard_oxford_subcortical_volume",  # will be overridden by dynamic naming
    "features": "harvard_oxford_subcortical_subcortical_volume_feats.txt",
    "value": "volume_mm3",
    "requires_projection": True,
    "template_space": "mni152",
    "atlas_nifti": "HarvardOxford-sub-maxprob-thr25-1mm.nii.gz",
    "atlas_lut": "harvard_oxford_sub_LUT.txt",
    "stats_basename": "harvard_oxford_sub.stats",
},

"harvard_oxford_cortical": {
    "column": "harvard_oxford_cortical_volume",
    "features": "harvard_oxford_cortical_cortical_volume_feats.txt",
    "value": "volume_mm3",
    "requires_projection": True,
    "template_space": "mni152",
    "atlas_nifti": "HarvardOxford-cort-maxprob-thr25-1mm.nii.gz",
    "atlas_lut": "harvard_oxford_cort_LUT.txt",
    "stats_basename": "harvard_oxford_cort.stats",
},
# ... similar for other atlases
```

### Step 3: Implement dynamic column naming

**File:** `pipeline/stats.py`

Add a function to generate column names:

```python
def _atlas_column_name(vector_type: str, atlas: str, is_default: bool) -> str:
    if is_default:
        return vector_type
    short_name = ATLAS_SHORT_NAMES.get(atlas, atlas)
    return f"{vector_type}_{short_name}"
```

Modify `StatsGenerator.generate()` to use dynamic naming:

```python
def generate(self, config, ...):
    # ...
    for stat_type, atlas_list in config.atlases.items():
        for i, atlas in enumerate(atlas_list):
            is_default = (i == 0)
            column = _atlas_column_name(stat_type, atlas, is_default)
            # ... rest of vector generation
```

### Step 4: Create MNI atlas projection tool

**File:** `pipeline/registry.py`

Add a new command builder for MNI atlas projection:

```python
def _mni_atlas_projection(ctx: ToolContext) -> str:
    """Project MNI atlases to subject space and extract volumes."""
    atlases = ctx.enabled_stats.get("selected_atlases", [])
    mni_atlases = [a for a in atlases if _is_mni_atlas(a)]
    
    if not mni_atlases:
        return "true"  # no-op
    
    script = []
    script.append("set -e")
    script.append("mkdir -p /output/stats/atlas_mapping")
    
    # Register MNI to subject (once)
    script.append("""
        MNI_TEMPLATE="$FREESURFER_HOME/average/mni305.cor.stripped.mgz"
        if [ ! -s /output/stats/atlas_mapping/mni152_to_subject.affine.lta ]; then
            mri_synthmorph register -m affine \
                -t /output/stats/atlas_mapping/mni152_to_subject.affine.lta \
                "$MNI_TEMPLATE" /input/{subject}/mri/norm.mgz
        fi
    """)
    
    # Warp and extract for each atlas
    for atlas in mni_atlases:
        spec = VECTOR_SPECS[atlas]
        nifti = spec["atlas_nifti"]
        lut = spec["atlas_lut"]
        stats_name = spec["stats_basename"]
        
        script.append(f"""
            mri_vol2vol --mov /atlases/{nifti} \
                --targ /input/{subject}/mri/norm.mgz \
                --o /output/stats/atlas_mapping/{atlas}.mgz \
                --lta /output/stats/atlas_mapping/mni152_to_subject.affine.lta \
                --nearest
            mri_segstats --seg /output/stats/atlas_mapping/{atlas}.mgz \
                --sum /output/stats/{stats_name} \
                --ctab /atlases/{lut}
        """)
    
    return "; ".join(script)
```

Register the tool:

```python
"mni_atlas_projection": {
    "display_name": "MNI Atlas Projection",
    "image": "mkdayyyy/mri-fs8-all:latest",
    "stage": "stats_extraction",
    "needs_license": True,
    "command_builder": _mni_atlas_projection,
    "output_files": [],
    "output_globs": [
        "stats/atlas_mapping/*.lta",
        "stats/atlas_mapping/*.mgz",
        "stats/*.stats",
    ],
},
```

### Step 5: Add reader for MNI atlas stats

**File:** `pipeline/stats.py`

Add a function to read MNI atlas stats files:

```python
def _read_mni_atlas_values(stats_dir: Path, atlas: str) -> dict[str, str]:
    """Read volumes from MNI atlas stats file."""
    spec = VECTOR_SPECS[atlas]
    stats_path = stats_dir / spec["stats_basename"]
    
    values = {}
    if stats_path.exists():
        headers, rows = _parse_freesurfer_stats_table(stats_path)
        for row in rows:
            name = row.get("StructName", "")
            volume = row.get("Volume_mm3") or row.get("NVoxels", "")
            if name and name != "Unknown":
                _put_value(values, name, volume)
    
    return values
```

Update `_values_for_vector()` to dispatch to the new reader:

```python
def _values_for_vector(stats_dir, stat, atlas):
    # ... existing code ...
    
    # MNI atlases
    if atlas in EXTERNAL_MNI_ATLASES:
        return _read_mni_atlas_values(stats_dir, atlas)
    
    # ... rest of existing code ...
```

### Step 6: Create feature lists for new atlases

**Files:** `info/` directory

Create feature list files for each new atlas. These files define the ordered list of region names for each atlas vector.

Example for Harvard-Oxford subcortical:

```
# info/harvard_oxford_subcortical_subcortical_volume_feats.txt
Left-Cerebral-White-Matter
Left-Cerebral-Cortex
Left-Lateral-Ventricle
Left-Thalamus
Left-Caudate
Left-Putamen
Left-Pallidum
Brain-Stem
Left-Hippocampus
Left-Amygdala
Left-Accumbens
Right-Cerebral-White-Matter
Right-Cerebral-Cortex
Right-Lateral-Ventricle
Right-Thalamus
Right-Caudate
Right-Putamen
Right-Pallidum
Right-Hippocampus
Right-Amygdala
Right-Accumbens
```

Similar files for:
- `info/harvard_oxford_cortical_cortical_volume_feats.txt`
- `info/brainnetome246_cortical_volume_feats.txt`
- `info/pauli_2017_subcortical_volume_feats.txt`
- `info/juelich_cortical_volume_feats.txt`
- `info/aal_cortical_volume_feats.txt`
- `info/schaefer2018_100_7_cortical_volume_feats.txt`

### Step 7: Update presets to include new atlases

**File:** `pipeline/presets.py`

Add new preset options that include MNI atlases:

```python
"FreeSurfer 8 + Volume + MNI Atlases": {
    "tools": FREESURFER_8_TOOLS,
    "stats": VOLUME_STATS,
    "default_atlases": {
        "subcortical_volume": [
            "freesurfer_aseg",
            "harvard_oxford_subcortical",
            "sclimbic",
            "pauli_2017",
        ],
        "cortical_volume": [
            "freesurfer_aparc",
            "harvard_oxford_cortical",
            "brainnetome246",
            "aal",
            "schaefer2018_100_7",
        ],
    },
},
```

### Step 8: Update runner to mount atlas files

**File:** `pipeline/runner.py`

Mount the atlas directory into the Docker container:

```python
def _build_docker_command(self, config, ...):
    # ... existing code ...
    
    # Mount MNI atlases if any are selected
    mni_atlases = [a for a in selected_atlases if _is_mni_atlas(a)]
    if mni_atlases:
        atlas_dir = self._resolve_atlas_dir(config)
        volumes.append(f"-v {atlas_dir}:/atlases:ro")
    
    # ... rest of existing code ...
```

### Step 9: Update metadata for frontend

**File:** `app_backend/metadata.py`

Add atlas metadata for the frontend:

```python
def get_atlas_metadata():
    return {
        "mni_atlases": {
            "harvard_oxford_subcortical": {
                "label": "Harvard-Oxford Subcortical",
                "type": "subcortical_volume",
                "regions": 21,
                "source": "FSL",
            },
            "harvard_oxford_cortical": {
                "label": "Harvard-Oxford Cortical",
                "type": "cortical_volume",
                "regions": 48,
                "source": "FSL",
            },
            # ... similar for other atlases
        },
    }
```

### Step 10: Write tests

**Files:** `tests/` directory

Create tests for:

1. **Atlas short name mapping** (`test_config.py`):
   - Verify all atlas keys have short name entries
   - Verify short names are unique within each vector type

2. **Dynamic column naming** (`test_stats.py`):
   - Verify default atlas gets `{vector_type}` column name
   - Verify non-default atlas gets `{vector_type}_{short_name}` column name
   - Verify multiple atlases produce multiple columns

3. **MNI atlas projection** (`test_volume_atlas.py`):
   - Mock `mri_synthmorph`, `mri_vol2vol`, `mri_segstats`
   - Verify registration is called once per subject
   - Verify warping and extraction is called per atlas
   - Verify LUT file is passed to `mri_segstats`

4. **Stats reading** (`test_stats.py`):
   - Verify `_read_mni_atlas_values` parses stats files correctly
   - Verify region names match feature list
   - Verify volumes are numeric

5. **Integration** (`test_integration.py`):
   - Verify full pipeline with multiple atlases
   - Verify output CSV has correct column names
   - Verify feature lists are generated for each atlas

## Files to Change

### New files

| File | Purpose |
|------|---------|
| `assets/atlases/mni/*.nii.gz` | Atlas NIfTI files |
| `assets/atlases/mni/*_LUT.txt` | Atlas label lookup tables |
| `assets/atlases/mni/atlas_sources.csv` | Atlas metadata and sources |
| `info/harvard_oxford_subcortical_subcortical_volume_feats.txt` | Feature list |
| `info/harvard_oxford_cortical_cortical_volume_feats.txt` | Feature list |
| `info/brainnetome246_cortical_volume_feats.txt` | Feature list |
| `info/pauli_2017_subcortical_volume_feats.txt` | Feature list |
| `info/juelich_cortical_volume_feats.txt` | Feature list |
| `info/aal_cortical_volume_feats.txt` | Feature list |
| `info/schaefer2018_100_7_cortical_volume_feats.txt` | Feature list |
| `tests/test_volume_atlas.py` | Tests for MNI atlas integration |

### Modified files

| File | Changes |
|------|---------|
| `pipeline/config.py` | Add `ATLAS_SHORT_NAMES`, update `EXTERNAL_MNI_*` tuples |
| `pipeline/stats.py` | Add `VECTOR_SPECS` entries, add `_read_mni_atlas_values()`, add `_atlas_column_name()`, update `StatsGenerator.generate()` |
| `pipeline/registry.py` | Add `_mni_atlas_projection()` command builder, register tool |
| `pipeline/runner.py` | Mount atlas directory when MNI atlases selected |
| `pipeline/presets.py` | Add new preset options with MNI atlases |
| `app_backend/metadata.py` | Add MNI atlas metadata |
| `app_backend/run_request.py` | Handle MNI atlas selection |

### Files NOT to change

| File | Reason |
|------|--------|
| `pipeline/executor.py` | No new capabilities needed |
| `pipeline/state.py` | Resume logic unchanged |
| `remote/remote_runner.py` | Out of scope (FS8 only) |
| `tauri-app/` | Frontend changes deferred |

## Verification

### Unit tests

```bash
pytest -q tests/test_config.py tests/test_stats.py tests/test_volume_atlas.py
```

### Integration tests

```bash
pytest -q tests/test_integration.py
```

### Manual verification

1. Run pipeline with default atlas selection → output identical to current
2. Run pipeline with additional MNI atlases → output contains new vectors
3. Verify column names follow `{vector_type}_{short_name}` convention
4. Verify feature lists match region names in stats files
5. Verify registration transform is reused across atlases

### Final check

```bash
python3 -m compileall pipeline/ app_backend/
pytest -q
```

## Implementation Order

1. **Step 1-2**: Atlas definitions and VECTOR_SPECS (no behavior change)
2. **Step 3**: Dynamic column naming (no behavior change for single atlas)
3. **Step 4-5**: MNI atlas projection and reading (new capability)
4. **Step 6**: Feature lists (required for vector generation)
5. **Step 7-8**: Presets and runner integration (wire everything together)
6. **Step 9**: Metadata for frontend (optional for this iteration)
7. **Step 10**: Tests (throughout implementation)

## Definition of Done

1. User can select multiple atlases per stats vector type
2. Default atlas produces identical output to current implementation
3. Non-default atlases produce new vectors with correct naming convention
4. Registration transform is computed once and reused
5. All tests pass
6. No regression in existing functionality

---

# Part 2: Fix Surface Atlas Integration (Cortical Thickness)

## Problem

The pipeline defines 25 surface atlases for cortical thickness but only 3 are fully working:

| Status | Count | Atlases |
|--------|-------|---------|
| Working | 3 | `aparc`, `kong` (200/17), `schaefer2018` (200/7) |
| Missing .annot | 22 | All other Kong and Schaefer variants |
| Missing feature file | 22 | All other Kong and Schaefer variants |

## Root Cause

Two parallel gaps:

1. **`.annot` files** must exist in `$FREESURFER_HOME/subjects/fsaverage/label/` (inside Docker image)
2. **`*_feats.txt` files** must exist in `info/` directory

## Available Assets

### Schaefer 2018 (all 20 variants)

| Asset | Location | Status |
|-------|----------|--------|
| `.gcs` files | `gcs_Schaefer2018/gcs/` | ✓ 40 files (lh+rh for all 20 variants) |
| `.annot` files | Not found | ✗ Must be generated from `.gcs` |
| Feature files | `info/` | ✗ Only `schaefer200_7network_feats.txt` exists |

### Kong 2022

| Asset | Location | Status |
|-------|----------|--------|
| `.annot` (200/17) | `frsf_output_9patients/frsf_output/atlas/kong17/` | ✓ lh + rh |
| Feature file (200/17) | `frsf_output_9patients/frsf_output/atlas/` | ✓ 202 features |
| `.annot` (100, 300, 400) | Not found | ✗ Must be obtained or generated |
| Feature files (100, 300, 400) | Not found | ✗ Must be created |

### Yale Brain Atlas

| Asset | Location | Status |
|-------|----------|--------|
| `.annot` files | `frsf_output_9patients/frsf_output/atlas/yale/` | ✓ Multiple versions |
| Feature file | `frsf_output_9patients/frsf_output/atlas/` | ✓ 150 features |

## Solution

### Approach A: Generate .annot from .gcs (for Schaefer)

Use `mris_ca_label` to create `.annot` files from `.gcs` files:

```bash
mris_ca_label -l label/lh.cortex.label \
    -aseg mri/aseg.presurf.mgz \
    -seed 1234 "$SUBJ" lh \
    surf/lh.sphere.reg \
    lh.Schaefer2018_100Parcels_7Networks.gcs \
    label/lh.schaefer2018_100parcels_7networks.annot
```

This must be done:
1. For fsaverage (once, during Docker image build)
2. Or for each subject (during stats extraction)

### Approach B: Use mri_surf2surf (for Kong/Yale)

If `.annot` files exist in fsaverage, use `mri_surf2surf` to resample:

```bash
mri_surf2surf --srcsubject fsaverage \
    --trgsubject "$SUBJ" \
    --hemi lh \
    --sval-annot fsaverage/label/lh.200Parcels_Kong2022_17Networks.annot \
    --tval label/lh.200Parcels_Kong2022_17Networks.annot
```

## Implementation Steps

### Step 11: Copy available assets to pipeline

Copy the following files to the pipeline:

| Source | Destination |
|--------|-------------|
| `frsf_output/atlas/kong17/*.annot` | `assets/atlases/surface/kong/` |
| `frsf_output/atlas/yale/*.annot` | `assets/atlases/surface/yale/` |
| `frsf_output/atlas/200Parcels_Kong2022_17Networks_feats.txt` | `info/` |
| `frsf_output/atlas/YBA_696parcels_feats.txt` | `info/` |
| `gcs_Schaefer2018/gcs/*.gcs` | `assets/atlases/surface/schaefer/` |

### Step 12: Generate Schaefer .annot files

Create a script or Docker build step that:

1. Mounts the `.gcs` files into the Docker container
2. Runs `mris_ca_label` for each Schaefer variant on fsaverage
3. Saves the resulting `.annot` files

This can be done:
- During Docker image build (preferred)
- Or at runtime (slower, but no image rebuild needed)

### Step 13: Create missing feature files

Generate feature files for all Schaefer variants. The feature names follow the pattern:

```
LH_Background+FreeSurfer_Defined_Medial_Wall
RH_Background+FreeSurfer_Defined_Medial_Wall
LH_Vis_1
RH_Vis_1
LH_Vis_2
RH_Vis_2
...
```

The number of features per variant:
- 100 parcels: 102 features (50 per hemisphere + 2 background)
- 200 parcels: 202 features (100 per hemisphere + 2 background)
- 300 parcels: 302 features
- ... up to ...
- 1000 parcels: 1002 features

For 7-network variants: `{network}_{region}` (e.g., `LH_Vis_1`)
For 17-network variants: `{network}_{region}` (e.g., `LH_17networks_LH_DefaultC_IPL`)

### Step 14: Update pipeline to use .gcs files

Modify `pipeline/registry.py` to use `mris_ca_label` when `.gcs` files are available:

```python
def _generate_annot_from_gcs(ctx: ToolContext, atlas_stem: str) -> str:
    """Generate .annot files from .gcs files if they don't exist."""
    return f"""
        for hemi in lh rh; do
            GCS="/atlases/surface/schaefer/${{hemi}}.{atlas_stem}.gcs"
            ANNOT="$SUBJECTS_DIR/$SUBJ/label/${{hemi}}.{atlas_stem}.annot"
            if [ -s "$GCS" ] && [ ! -s "$ANNOT" ]; then
                mris_ca_label -l label/${{hemi}}.cortex.label \
                    -aseg mri/aseg.presurf.mgz \
                    -seed 1234 "$SUBJ" ${{hemi}} \
                    surf/${{hemi}}.sphere.reg \
                    "$GCS" \
                    "$ANNOT"
            fi
        done
    """
```

### Step 15: Update runner to mount surface atlas files

Mount the surface atlas directory into the Docker container:

```python
# In pipeline/runner.py
if any(a in SURFACE_ATLASES for a in selected_atlases):
    volumes.append(f"-v {surface_atlas_dir}:/atlases/surface:ro")
```

### Step 16: Hide broken atlases from frontend

Update `app_backend/metadata.py` to filter out atlases that don't have all required assets:

```python
def get_available_atlases():
    """Return only atlases with all required assets."""
    available = {}
    for atlas, spec in VECTOR_SPECS.items():
        if _has_all_assets(atlas, spec):
            available[atlas] = spec
    return available
```

## Files to Change (Part 2)

### New files

| File | Purpose |
|------|---------|
| `assets/atlases/surface/kong/*.annot` | Kong 2022 annotation files |
| `assets/atlases/surface/yale/*.annot` | Yale annotation files |
| `assets/atlases/surface/schaefer/*.gcs` | Schaefer 2018 atlas files |
| `info/100Parcels_Kong2022_17Networks_feats.txt` | Kong 100p feature list |
| `info/300Parcels_Kong2022_17Networks_feats.txt` | Kong 300p feature list |
| `info/400Parcels_Kong2022_17Networks_feats.txt` | Kong 400p feature list |
| `info/schaefer100_7network_feats.txt` | Schaefer 100/7 feature list |
| `info/schaefer100_17network_feats.txt` | Schaefer 100/17 feature list |
| ... (19 total Schaefer feature files) | ... |

### Modified files

| File | Changes |
|------|---------|
| `pipeline/registry.py` | Add `.gcs` → `.annot` generation, mount surface atlases |
| `pipeline/runner.py` | Mount surface atlas directory |
| `app_backend/metadata.py` | Filter unavailable atlases |
| Docker image | Install `.gcs` and `.annot` files into fsaverage |

## Implementation Order (Updated)

1. **Steps 1-2**: Atlas definitions and VECTOR_SPECS (no behavior change)
2. **Step 3**: Dynamic column naming (no behavior change for single atlas)
3. **Steps 4-5**: MNI atlas projection and reading (new capability)
4. **Step 6**: Feature lists for MNI atlases (required for vector generation)
5. **Step 11**: Copy available surface assets (.annot, .gcs, feature files)
6. **Step 12-13**: Generate Schaefer .annot files, create missing feature files
7. **Step 14-15**: Update pipeline for surface atlas integration
8. **Steps 7-8**: Presets and runner integration (wire everything together)
9. **Step 16**: Hide broken atlases from frontend
10. **Steps 9-10**: Metadata and tests
