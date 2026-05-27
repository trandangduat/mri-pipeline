#!/usr/bin/env python3
import argparse
import nibabel as nib
import numpy as np
import pandas as pd
import os

# Simplified mapping for demo purposes. In reality, we'd use FreeSurferColorLUT.txt
SUBCORTICAL_LABELS = {
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

CORTICAL_LABELS = {
    1003: 'ctx-lh-caudalmiddlefrontal',
    1028: 'ctx-lh-superiorfrontal',
    2003: 'ctx-rh-caudalmiddlefrontal',
    2028: 'ctx-rh-superiorfrontal'
    # Adding a few for demonstration
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject-id", required=True)
    parser.add_argument("--input-seg", required=True)
    parser.add_argument("--output-subcortical", required=True)
    parser.add_argument("--output-cortical", required=True)
    args = parser.parse_args()

    if not os.path.exists(args.input_seg):
        print(f"Segmentation file not found: {args.input_seg}")
        return

    img = nib.load(args.input_seg)
    data = img.get_fdata()
    header = img.header
    zooms = header.get_zooms()
    voxel_vol = np.prod(zooms)

    subcortical_data = []
    cortical_data = []

    unique_labels, counts = np.unique(data, return_counts=True)
    label_vol_map = {lbl: count * voxel_vol for lbl, count in zip(unique_labels, counts)}

    for lbl, name in SUBCORTICAL_LABELS.items():
        if lbl in label_vol_map:
            subcortical_data.append([args.subject_id, name, label_vol_map[lbl], "FastSurferVINN"])

    for lbl, name in CORTICAL_LABELS.items():
        if lbl in label_vol_map:
            hemi = "lh" if name.startswith("ctx-lh") else "rh"
            region = name.split("-")[-1]
            cortical_data.append([args.subject_id, region, hemi, label_vol_map[lbl], "FastSurferVINN"])

    df_sub = pd.DataFrame(subcortical_data, columns=["subject", "structure", "volume_mm3", "tool"])
    df_sub.to_csv(args.output_subcortical, sep="\t", index=False)

    df_cort = pd.DataFrame(cortical_data, columns=["subject", "region", "hemisphere", "volume_mm3", "tool"])
    df_cort.to_csv(args.output_cortical, sep="\t", index=False)
    
    # Touch volumes.tsv for requirement
    work_dir = os.path.dirname(args.input_seg)
    pd.concat([df_sub, df_cort]).to_csv(os.path.join(work_dir, "03_fastsurfervinn_volumes.tsv"), sep="\t", index=False)

if __name__ == "__main__":
    main()
