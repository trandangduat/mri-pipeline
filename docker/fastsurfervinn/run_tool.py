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
    mri_dir = os.path.join(args.output_dir, "mri")
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(stats_dir, exist_ok=True)
    os.makedirs(mri_dir, exist_ok=True)

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
        cmd += ["--device", "cpu"]
    else:
        cmd += ["--device", "cuda"]

    env = os.environ.copy()
    env["FS_LICENSE"] = "/license/license.txt"

    with open(log_file, "w") as f:
        print(f"Running command: {' '.join(cmd)}")
        f.write(f"Running command: {' '.join(cmd)}\n")
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env)

    if result.returncode != 0:
        print(f"FastSurfer failed with return code {result.returncode}")
        sys.exit(2)

    # FastSurfer outputs at: <work_dir>/<subject_id>/
    subject_sd = os.path.join(args.work_dir, args.subject_id)

    # Copy segmentation (.mgz) to mri/
    seg_mgz = os.path.join(subject_sd, "mri", "aparc.DKTatlas+aseg.deep.mgz")
    if os.path.exists(seg_mgz):
        shutil.copy(seg_mgz, os.path.join(mri_dir, "aparc.DKTatlas+aseg.deep.mgz"))
        # Also convert to .nii.gz
        out_nii = os.path.join(mri_dir, "03_fastsurfervinn_segmentation.nii.gz")
        conv = subprocess.run(["mri_convert", seg_mgz, out_nii], env=env,
                              capture_output=True, text=True)
        if conv.returncode != 0:
            print(f"mri_convert warning: {conv.stderr}")
    else:
        print(f"Missing segmentation output: {seg_mgz}")
        sys.exit(3)

    # Copy original stats files to stats/
    src_stats = os.path.join(subject_sd, "stats")
    if os.path.isdir(src_stats):
        for fname in os.listdir(src_stats):
            src = os.path.join(src_stats, fname)
            if os.path.isfile(src):
                shutil.copy(src, os.path.join(stats_dir, fname))
                print(f"Copied stats: {fname}")
        norm = subprocess.run([
            "python3",
            "/app/normalize_volumes.py",
            "--subject-id", args.subject_id,
            "--stats-dir", stats_dir,
            "--output-subcortical", os.path.join(stats_dir, "subcortical_volume.tsv"),
            "--output-cortical", os.path.join(stats_dir, "cortical_volume.tsv"),
        ], capture_output=True, text=True)
        if norm.returncode != 0:
            print(f"normalize_volumes warning: {norm.stderr or norm.stdout}")
    else:
        print(f"No stats directory found at {src_stats}")

    print("FastSurferVINN completed successfully.")
    sys.exit(0)

if __name__ == "__main__":
    main()
