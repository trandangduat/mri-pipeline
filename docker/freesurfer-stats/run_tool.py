#!/usr/bin/env python3
import argparse
import subprocess
import os
import sys
import shutil

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input segmentation file (.mgz or .nii.gz)")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--work-dir", required=True, help="Working directory")
    parser.add_argument("--subject-id", required=True, help="Subject ID")
    parser.add_argument("--threads", type=int, default=1, help="Number of threads")
    parser.add_argument("--device", default="cpu", help="Device (cpu or cuda)")
    parser.add_argument("--seg-type", default="aparc+aseg", help="Segmentation type: aparc+aseg, aseg, aparc.DKTatlas+aseg.deep")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.work_dir, exist_ok=True)

    log_dir = os.path.join(args.output_dir, "logs")
    stats_dir = os.path.join(args.output_dir, "stats")
    mri_dir = os.path.join(args.output_dir, "mri")
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(stats_dir, exist_ok=True)
    os.makedirs(mri_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "freesurfer_stats.log")

    env = os.environ.copy()
    env["SUBJECTS_DIR"] = args.work_dir
    env["FS_LICENSE"] = "/license/license.txt"

    with open(log_file, "w") as f:
        f.write(f"Extracting FreeSurfer stats for {args.subject_id}\n")
        f.write(f"Input: {args.input}\n")
        f.write(f"Seg type: {args.seg_type}\n\n")

    # Find or create subject directory structure
    subject_sd = os.path.join(args.work_dir, args.subject_id)
    subject_mri = os.path.join(subject_sd, "mri")
    os.makedirs(subject_mri, exist_ok=True)

    # Determine output segmentation name based on seg-type
    seg_name = "aparc+aseg.mgz"
    if "DKTatlas" in args.seg_type or "deep" in args.seg_type:
        seg_name = "aparc.DKTatlas+aseg.deep.mgz"
    elif args.seg_type == "aseg":
        seg_name = "aseg.mgz"

    dest_seg = os.path.join(subject_mri, seg_name)

    # Convert input to .mgz if it's .nii.gz
    input_file = args.input
    if args.input.endswith(".nii.gz") or args.input.endswith(".nii"):
        mgz_path = args.input.replace(".nii.gz", ".mgz").replace(".nii", ".mgz")
        with open(log_file, "a") as f:
            f.write(f"Converting {args.input} -> {mgz_path}\n")
        result = subprocess.run(["mri_convert", args.input, mgz_path], env=env, capture_output=True, text=True)
        if result.returncode != 0:
            with open(log_file, "a") as f:
                f.write(f"mri_convert failed: {result.stderr}\n")
            sys.exit(2)
        input_file = mgz_path

    # Copy input segmentation to subject mri dir with standard name
    if input_file != dest_seg:
        shutil.copy2(input_file, dest_seg)
        with open(log_file, "a") as f:
            f.write(f"Copied {input_file} -> {dest_seg}\n")

    # Also copy to output mri/ for pipeline consistency
    out_seg = os.path.join(mri_dir, seg_name)
    if input_file != out_seg:
        shutil.copy2(input_file, out_seg)

    # Copy existing stats from subject directory if they exist (from fastsurfervinn)
    src_stats_dir = os.path.join(subject_sd, "stats")
    if os.path.isdir(src_stats_dir):
        for fname in os.listdir(src_stats_dir):
            src = os.path.join(src_stats_dir, fname)
            if os.path.isfile(src):
                dst = os.path.join(stats_dir, fname)
                shutil.copy2(src, dst)
                with open(log_file, "a") as f:
                    f.write(f"Copied existing stats: {fname}\n")

    # Run asegstats2table for subcortical volumes
    aseg_stats = os.path.join(stats_dir, "aseg.stats")
    if not os.path.exists(aseg_stats):
        cmd = ["asegstats2table", "--subjects", args.subject_id, "--tablefile", aseg_stats, "--seg", seg_name.replace(".mgz", "")]
        with open(log_file, "a") as f:
            f.write(f"Running: {' '.join(cmd)}\n")
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)

    # Run aparcstats2table for cortical parcellation (both hemispheres)
    for hemi in ["lh", "rh"]:
        aparc_stats = os.path.join(stats_dir, f"{hemi}.aparc.stats")
        if not os.path.exists(aparc_stats):
            cmd = ["aparcstats2table", "--subjects", args.subject_id, "--hemi", hemi, "--tablefile", aparc_stats, "--seg", seg_name.replace(".mgz", "")]
            with open(log_file, "a") as f:
                f.write(f"Running: {' '.join(cmd)}\n")
                result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)

    # Run aparcstats2table for DKT atlas if using DKT segmentation
    if "DKTatlas" in args.seg_type:
        for hemi in ["lh", "rh"]:
            aparc_dkt_stats = os.path.join(stats_dir, f"{hemi}.aparc.DKTatlas.stats")
            if not os.path.exists(aparc_dkt_stats):
                cmd = ["aparcstats2table", "--subjects", args.subject_id, "--hemi", hemi, "--tablefile", aparc_dkt_stats, "--parc", "aparc.DKTatlas"]
                with open(log_file, "a") as f:
                    f.write(f"Running: {' '.join(cmd)}\n")
                    result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)

    # Convert aseg.stats to TSV
    if os.path.exists(aseg_stats):
        out_tsv = os.path.join(stats_dir, "subcortical_volume.tsv")
        with open(aseg_stats, "r") as f_in, open(out_tsv, "w") as f_out:
            for line in f_in:
                if not line.startswith("#"):
                    f_out.write(line.replace(",", "\t"))
        with open(log_file, "a") as f:
            f.write(f"Created {out_tsv}\n")

    # Convert cortical stats to TSV
    for hemi in ["lh", "rh"]:
        for parc in ["aparc", "aparc.DKTatlas"]:
            in_file = os.path.join(stats_dir, f"{hemi}.{parc}.stats")
            if os.path.exists(in_file):
                out_tsv = os.path.join(stats_dir, f"{hemi}_{parc}_volume.tsv")
                with open(in_file, "r") as f_in, open(out_tsv, "w") as f_out:
                    for line in f_in:
                        if not line.startswith("#"):
                            f_out.write(line.replace(",", "\t"))
                with open(log_file, "a") as f:
                    f.write(f"Created {out_tsv}\n")

    # Also run mri_segstats for volume summary from segmentation directly
    seg_stats_tsv = os.path.join(stats_dir, "segmentation_volumes.tsv")
    norm_mgz = os.path.join(args.work_dir, args.subject_id, "mri", "norm.mgz")
    if os.path.exists(norm_mgz):
        cmd = ["mri_segstats", "--seg", dest_seg, "--sum", seg_stats_tsv, "--pv", norm_mgz]
        with open(log_file, "a") as f:
            f.write(f"Running: {' '.join(cmd)}\n")
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)

    with open(log_file, "a") as f:
        f.write("\nFreeSurfer stats extraction completed.\n")

    print("FreeSurfer stats extraction completed.")
    sys.exit(0)

if __name__ == "__main__":
    main()