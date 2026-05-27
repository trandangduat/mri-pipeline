#!/usr/bin/env python3
import argparse
import subprocess
import os
import sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input T1w NIfTI file")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--work-dir", required=True, help="Working directory")
    parser.add_argument("--subject-id", required=True, help="Subject ID")
    parser.add_argument("--threads", type=int, default=1, help="Number of threads")
    parser.add_argument("--device", default="cpu", help="Device (cpu or cuda)")
    parser.add_argument("--crop", type=int, default=192, help="Crop size for 3D patches (default 192)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.work_dir, exist_ok=True)
    
    log_dir = os.path.join(args.output_dir, "logs")
    stats_dir = os.path.join(args.output_dir, "stats")
    work_dir = os.path.join(args.output_dir, "work")
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(stats_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "synthseg_standalone.log")

    out_seg = os.path.join(work_dir, "03_synthseg_standalone_segmentation.nii.gz")
    out_vol_csv = os.path.join(work_dir, "03_synthseg_standalone_volumes.csv")

    cmd = [
        "python3", "/app/SynthSeg/scripts/commands/SynthSeg_predict.py",
        "--i", args.input,
        "--o", out_seg,
        "--vol", out_vol_csv,
        "--crop", str(args.crop),
        "--parc"
    ]

    if args.device == "cpu":
        cmd.extend(["--cpu"])

    # Number of threads for SynthSeg can be controlled via tf/keras environment vars, usually --threads flag isn't in predict.py directly unless added later
    os.environ["OMP_NUM_THREADS"] = str(args.threads)
    os.environ["TF_NUM_INTEROP_THREADS"] = str(args.threads)
    os.environ["TF_NUM_INTRAOP_THREADS"] = str(args.threads)

    with open(log_file, "w") as f:
        print(f"Running command: {' '.join(cmd)}")
        f.write(f"Running command: {' '.join(cmd)}\n")
        
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    
    if result.returncode != 0:
        print(f"SynthSeg failed with return code {result.returncode}")
        sys.exit(2)
        
    if not os.path.exists(out_seg):
        print("Missing expected segmentation output!")
        sys.exit(3)
        
    # Call normalize_volumes.py
    norm_cmd = [
        sys.executable, "/app/normalize_volumes.py",
        "--subject-id", args.subject_id,
        "--input-csv", out_vol_csv,
        "--input-seg", out_seg,
        "--output-subcortical", os.path.join(stats_dir, "subcortical_volume.tsv"),
        "--output-cortical", os.path.join(stats_dir, "cortical_volume.tsv")
    ]
    subprocess.run(norm_cmd)

    print("SynthSeg standalone completed successfully.")
    sys.exit(0)

if __name__ == "__main__":
    main()
