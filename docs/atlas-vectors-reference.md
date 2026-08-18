# Atlas & Stats Vector Reference (defaults)

Three things explained with diagrams: the default feature lists, the FreeSurfer atlases they
come from, and what SynthSeg actually outputs.

---

## 1. Default feats lists

Each stats vector type has a default atlas, and each atlas has a **feats file** that defines
the vector's feature names and order:

| stats vector type | default atlas | feats file (in `info/`) | features |
|---|---|---|---|
| `subcortical_volume` | `freesurfer_aseg` | `freesurfer_aseg_subcortical_volume_feats.txt` | 64 |
| `cortical_volume` | `freesurfer_aparc` | `freesurfer_aparc_cortical_volume_feats.txt` | 68 |
| `cortical_thickness` | `aparc` | `aparc_cortical_thickness_feats.txt` | 68 |

The vector is built 1:1 from the feats file — every feature gets one value from the stats
output; anything missing is filled with `NA`:

```mermaid
flowchart LR
    subgraph feats["feats file (info/)"]
        F1["1. Left-Lateral-Ventricle"]
        F2["2. Left-Thalamus"]
        F3["3. ..."]
        F64["64. EstimatedTotalIntracranialVol"]
    end

    subgraph stats["stats output (name → volume)"]
        S1["Left-Lateral-Ventricle: 19694.6"]
        S2["Left-Thalamus: 5586.9"]
        S3["..."]
        SMISS["(not present)"]
    end

    subgraph vector["vector (values, same order)"]
        V1["19694.6"]
        V2["5586.9"]
        V3["..."]
        VNA["NA"]
    end

    F1 --> S1
    F2 --> S2
    F3 --> S3
    F64 --> SMISS
    S1 --> V1
    S2 --> V2
    S3 --> V3
    SMISS -.-> VNA

    FEATS[[only these names matter]] -.-> F1
    MISS[[missing in stats → NA]] -.-> SMISS
```

- `freesurfer_aseg_subcortical_volume_feats.txt` (64) — mirrors FreeSurfer `aseg.stats`:
  the standard subcortical structures + summary measures (`BrainSegVol`, `eTIV`,
  `CortexVol`, ...).
- `freesurfer_aparc_cortical_volume_feats.txt` (68) — 34 `lh_*` + 34 `rh_*` Desikan–Killiany
  region names, from FreeSurfer `lh.aparc.stats` / `rh.aparc.stats`.

---

## 2. Default FreeSurfer atlases

FreeSurfer's own stats files carry atlas names directly:

```mermaid
flowchart TB
    RECON["recon-all output (FreeSurfer 8)"]

    RECON --> ASEG[["stats/aseg.stats — aseg<br/>Automatic Subcortical Segmentation<br/>~40 structures: white matter, lateral ventricle,<br/>caudate, putamen, hippocampus, amygdala, ..."]]
    RECON --> APARC[["stats/lh.aparc.stats + stats/rh.aparc.stats — aparc<br/>Desikan–Killiany, 34 regions per hemisphere<br/>e.g. bankssts, precentral, fusiform, insula, ..."]]
    RECON --> VARIANTS[["variants: aparc.a2009s (Destrieux),<br/>aparc.DKTatlas, aseg subfields, ..."]]

    FEAT1["freesurfer_aseg_subcortical_volume_feats.txt"] -. from .-> ASEG
    FEAT2["freesurfer_aparc_cortical_volume_feats.txt"] -. from .-> APARC
```

| atlas name | what it is | regions | stats file |
|---|---|---|---|
| `aseg` | Automatic Subcortical Segmentation | ~40 bilateral structures | `aseg.stats` |
| `aparc` | Desikan–Killiany cortical atlas | 34 per hemisphere | `lh.aparc.stats`, `rh.aparc.stats` |
| `aparc.a2009s` | Destrieux cortical atlas | 74 per hemisphere | `lh.aparc.a2009s.stats`, ... |

Mapping to the default feats:

```mermaid
flowchart LR
    ASEG["aseg.stats"] --> F1["freesurfer_aseg_subcortical_volume_feats.txt"]
    LH["lh.aparc.stats"] --> F2["freesurfer_aparc_cortical_volume_feats.txt"]
    RH["rh.aparc.stats"] --> F2

    F1 --> V1["subcortical_volume vector"]
    F2 --> V2["cortical_volume vector"]
```

---

## 3. SynthSeg output

The FS8 **volume** pipeline runs `synthseg 2.0 --parc` — no surface reconstruction.

```mermaid
flowchart TB
    INPUT["input T1 volume"]
    SYNTHSEG["SynthSeg 2.0 --parc"]
    SUBC["32 subcortical structures<br/>(subset of FreeSurfer's ~40 aseg labels)"]
    CORT["62 cortical parcels / hemisphere<br/>(extended Desikan–Killiany, volume-based)"]
    CSV["synthseg.vol.csv<br/>(subject + one column per structure)"]

    INPUT --> SYNTHSEG
    SYNTHSEG --> SUBC
    SYNTHSEG --> CORT
    SUBC --> CSV
    CORT --> CSV
```

SynthSeg's names look like:

```
subcortical:  Left-Thalamus, Left-Caudate, ...            (aseg-style)
cortical:     ctx-lh-bankssts, ctx-lh-precentral, ...     (DK-style, ctx-lh/rh- prefix)
```

How SynthSeg output fills the **default** feats lists (via `normalize_volumes.py`):

```mermaid
flowchart LR
    subgraph synthseg["synthseg.vol.csv"]
        T1["Left-Thalamus · 5586.9"]
        B1["ctx-lh-bankssts · 2461.0"]
        X1["ctx-lh-xxx (extra parcels)"]
        E1["eTIV / BrainSegVol (FS-only)"]
    end

    subgraph feats2["default feats files"]
        FA["Left-Thalamus<br/>(aseg feats)"]
        FB["lh_bankssts<br/>(aparc feats)"]
        FX["lh_xxx<br/>(not in the 68 names)"]
        FE["eTIV<br/>(aseg feats)"]
    end

    subgraph result["result"]
        RA["5586.9 ✓"]
        RB["2461.0 ✓"]
        RX["dropped ✗"]
        RE["NA ✗"]
    end

    T1 --> FA --> RA
    B1 --> FB --> RB
    X1 --> FX --> RX
    E1 --> FE --> RE
```

Rules of thumb:

- **Cortical:** only the 34 classic DK regions per hemisphere overlap between SynthSeg
  (62/hemi) and the aparc feats (34/hemi); SynthSeg's extra 28 parcels per hemisphere are
  ignored.
- **Subcortical:** the 32 SynthSeg structures map onto the aseg names; FreeSurfer-only
  summary measures (`eTIV`, `BrainSegVol`, ...) don't exist in SynthSeg output → `NA`
  (that's the recurring "29/64 missing" warning).
- **Volumes differ by definition:** SynthSeg counts voxels per parcel; FreeSurfer surface
  aparc computes pial−white geometric volume (Σ vertex area × thickness). Same names,
  different numbers.