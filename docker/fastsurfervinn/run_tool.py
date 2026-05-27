#!/usr/bin/env python3
import argparse
import subprocess
import os
import sys
import shutil

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input T1w NIfTI file")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--work-dir", required=True, help="Working directory")
    parser.add_argument("--subject-id", required=True, help="Subject ID")
    parser.add_argument("--threads", type=int, default=1, help="Number of threads")
    parser.add_argument("--device", default="cpu", help="Device (cpu or cuda)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.work_dir, exist_ok=True)
    
    log_dir = os.path.join(args.output_dir, "logs")
    stats_dir = os.path.join(args.output_dir, "stats")
    work_dir = os.path.join(args.output_dir, "work")
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(stats_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "fastsurfervinn.log")

    cmd = [
        "/fastsurfer/run_fastsurfer.sh",
        "--fs_license", "/license/license.txt",
        "--t1", args.input,
        "--sd", args.work_dir,
        "--sid", args.subject_id,
        "--threads", str(args.threads),
        "--seg_only",
        "--no_cereb",
        "--no_hypothal",
        "--no_cc",
        "--allow_root"
    ]

    if args.device == "cpu":
        cmd.append("--device")
        cmd.append("cpu")
    else:
        cmd.append("--device")
        cmd.append("cuda") # assuming cuda if not cpu

    env = os.environ.copy()
    env["FS_LICENSE"] = "/license/license.txt"

    with open(log_file, "w") as f:
        print(f"Running command: {' '.join(cmd)}")
        f.write(f"Running command: {' '.join(cmd)}\n")
        
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)
    
    if result.returncode != 0:
        print(f"FastSurfer failed with return code {result.returncode}")
        sys.exit(2)
        
    # Copy results to output dir
    subject_sd = os.path.join(args.work_dir, args.subject_id)
    seg_file = os.path.join(subject_sd, "mri", "aparc.DKTatlas+aseg.deep.mgz")
    seg_stats_file = os.path.join(subject_sd, "stats", "aseg.stats") # This might not exist if vol_segstats doesn't work this way
    
    out_seg = os.path.join(work_dir, "03_fastsurfervinn_segmentation.nii.gz")
    
    # We might need to convert mgz to nii.gz
    # Use mri_convert if available, or just copy
    if os.path.exists(seg_file):
        # Let's try to convert with mri_convert (which is in FastSurfer)
        conv_cmd = ["mri_convert", seg_file, out_seg]
        subprocess.run(conv_cmd, env=env)
        if not os.path.exists(out_seg):
             shutil.copy(seg_file, os.path.join(work_dir, "03_fastsurfervinn_segmentation.mgz"))
    else:
        print("Missing expected segmentation output!")
        sys.exit(3)
        
    # Call normalize_volumes.py
    norm_cmd = [
        sys.executable, "/app/normalize_volumes.py",
        "--subject-id", args.subject_id,
        "--input-seg", out_seg if os.path.exists(out_seg) else os.path.join(work_dir, "03_fastsurfervinn_segmentation.mgz"),
        "--output-subcortical", os.path.join(stats_dir, "subcortical_volume.tsv"),
        "--output-cortical", os.path.join(stats_dir, "cortical_volume.tsv")
    ]
    subprocess.run(norm_cmd)

    print("FastSurferVINN completed successfully.")
    sys.exit(0)

if __name__ == "__main__":
    main()
