#!/usr/bin/env python3
import argparse
import pandas as pd
import os
import shutil

# SynthSeg standalone usually gives a single CSV with volumes.
# The format might differ but we need subcortical_volume.tsv and cortical_volume.tsv

SUBCORTICAL_LABELS_SYNTHSEG = {
    10: 'Left-Thalamus',
    11: 'Left-Caudate',
    12: 'Left-Putamen',
    13: 'Left-Pallidum',
    17: 'Left-Hippocampus',
    18: 'Left-Amygdala',
    49: 'Right-Thalamus',
    50: 'Right-Caudate',
    51: 'Right-Putamen',
    52: 'Right-Pallidum',
    53: 'Right-Hippocampus',
    54: 'Right-Amygdala'
}

CORTICAL_LABELS_SYNTHSEG = {
    1001: ('bankssts', 'lh'),
    1002: ('caudalanteriorcingulate', 'lh'),
    1003: ('caudalmiddlefrontal', 'lh'),
    1005: ('cuneus', 'lh'),
    1006: ('entorhinal', 'lh'),
    1007: ('fusiform', 'lh'),
    1008: ('inferiorparietal', 'lh'),
    1009: ('inferiortemporal', 'lh'),
    1010: ('isthmuscingulate', 'lh'),
    1011: ('lateraloccipital', 'lh'),
    1012: ('lateralorbitofrontal', 'lh'),
    1013: ('lingual', 'lh'),
    1014: ('medialorbitofrontal', 'lh'),
    1015: ('middletemporal', 'lh'),
    1016: ('parahippocampal', 'lh'),
    1017: ('paracentral', 'lh'),
    1018: ('parsopercularis', 'lh'),
    1019: ('parsorbitalis', 'lh'),
    1020: ('parstriangularis', 'lh'),
    1021: ('pericalcarine', 'lh'),
    1022: ('postcentral', 'lh'),
    1023: ('posteriorcingulate', 'lh'),
    1024: ('precentral', 'lh'),
    1025: ('precuneus', 'lh'),
    1026: ('rostralanteriorcingulate', 'lh'),
    1027: ('rostralmiddlefrontal', 'lh'),
    1028: ('superiorfrontal', 'lh'),
    1029: ('superiorparietal', 'lh'),
    1030: ('superiortemporal', 'lh'),
    1031: ('supramarginal', 'lh'),
    1034: ('transversetemporal', 'lh'),
    1035: ('insula', 'lh'),
    2001: ('bankssts', 'rh'),
    2002: ('caudalanteriorcingulate', 'rh'),
    2003: ('caudalmiddlefrontal', 'rh'),
    2005: ('cuneus', 'rh'),
    2006: ('entorhinal', 'rh'),
    2007: ('fusiform', 'rh'),
    2008: ('inferiorparietal', 'rh'),
    2009: ('inferiortemporal', 'rh'),
    2010: ('isthmuscingulate', 'rh'),
    2011: ('lateraloccipital', 'rh'),
    2012: ('lateralorbitofrontal', 'rh'),
    2013: ('lingual', 'rh'),
    2014: ('medialorbitofrontal', 'rh'),
    2015: ('middletemporal', 'rh'),
    2016: ('parahippocampal', 'rh'),
    2017: ('paracentral', 'rh'),
    2018: ('parsopercularis', 'rh'),
    2019: ('parsorbitalis', 'rh'),
    2020: ('parstriangularis', 'rh'),
    2021: ('pericalcarine', 'rh'),
    2022: ('postcentral', 'rh'),
    2023: ('posteriorcingulate', 'rh'),
    2024: ('precentral', 'rh'),
    2025: ('precuneus', 'rh'),
    2026: ('rostralanteriorcingulate', 'rh'),
    2027: ('rostralmiddlefrontal', 'rh'),
    2028: ('superiorfrontal', 'rh'),
    2029: ('superiorparietal', 'rh'),
    2030: ('superiortemporal', 'rh'),
    2031: ('supramarginal', 'rh'),
    2034: ('transversetemporal', 'rh'),
    2035: ('insula', 'rh'),
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject-id", required=True)
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--input-seg", required=True)
    parser.add_argument("--output-subcortical", required=True)
    parser.add_argument("--output-cortical", required=True)
    args = parser.parse_args()

    subcortical_data = []
    cortical_data = []

    if os.path.exists(args.input_csv):
        # The CSV has structure names in rows or columns depending on SynthSeg version.
        # We will parse it and dump into our format. For simplicity and robustness, we just generate mock based on it.
        # But let's write a simple parser.
        try:
            df = pd.read_csv(args.input_csv)
            # Usually column names are structures, and there is one row of volumes.
            # E.g. df.columns = ['subject', 'Left-Thalamus', ...]
            # For simplicity, we fallback to computing from segmentation if CSV parsing fails.
        except:
            pass

    # Better to compute directly from segmentation like before to guarantee the same logic
    import nibabel as nib
    import numpy as np

    if not os.path.exists(args.input_seg):
        print(f"Segmentation file not found: {args.input_seg}")
        return

    img = nib.load(args.input_seg)
    data = img.get_fdata()
    header = img.header
    zooms = header.get_zooms()
    voxel_vol = np.prod(zooms)

    unique_labels, counts = np.unique(data, return_counts=True)
    label_vol_map = {lbl: count * voxel_vol for lbl, count in zip(unique_labels, counts)}

    for lbl, name in SUBCORTICAL_LABELS_SYNTHSEG.items():
        if lbl in label_vol_map:
            subcortical_data.append([args.subject_id, name, label_vol_map[lbl], "SynthSegStandalone"])

    for lbl, (region, hemi) in CORTICAL_LABELS_SYNTHSEG.items():
        if lbl in label_vol_map:
            cortical_data.append([args.subject_id, region, hemi, label_vol_map[lbl], "SynthSegStandalone"])

    df_sub = pd.DataFrame(subcortical_data, columns=["subject", "structure", "volume_mm3", "tool"])
    df_sub.to_csv(args.output_subcortical, sep="\t", index=False)

    df_cort = pd.DataFrame(cortical_data, columns=["subject", "region", "hemisphere", "volume_mm3", "tool"])
    df_cort.to_csv(args.output_cortical, sep="\t", index=False)

    work_dir = os.path.dirname(args.input_seg)
    out_tsv = os.path.join(work_dir, "03_synthseg_standalone_volumes.tsv")
    # Convert original CSV to TSV for the requirement if needed
    if os.path.exists(args.input_csv):
        pd.read_csv(args.input_csv).to_csv(out_tsv, sep="\t", index=False)
    else:
        pd.concat([df_sub, df_cort]).to_csv(out_tsv, sep="\t", index=False)

if __name__ == "__main__":
    main()
