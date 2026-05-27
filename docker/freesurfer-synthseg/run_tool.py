#!/usr/bin/env python3
import argparse, sys, subprocess, os

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--work-dir', required=True)
    parser.add_argument('--subject-id', required=True)
    parser.add_argument('--threads', default='8')
    parser.add_argument('--device', default='cpu')
    args, _ = parser.parse_known_args()

    if not os.path.exists(args.input): sys.exit(1)

    os.makedirs(os.path.join(args.output_dir, 'logs'), exist_ok=True)
    os.makedirs(os.path.join(args.output_dir, 'stats'), exist_ok=True)
    os.makedirs(args.work_dir, exist_ok=True)

    out_seg = os.path.join(args.work_dir, "03_freesurfer_synthseg_segmentation.nii.gz")
    out_vol_csv = os.path.join(args.work_dir, "03_freesurfer_synthseg_volumes.csv")
    log_file = os.path.join(args.output_dir, 'logs', 'synthseg_freesurfer.log')

    cmd = ["mri_synthseg", "--i", args.input, "--o", out_seg, "--vol", out_vol_csv, "--threads", args.threads, "--crop", "160"]
    if args.device.lower() != 'cpu': cmd.append("--nocpu")

    # 1. Chạy mri_synthseg
    try:
        with open(log_file, 'w') as f:
            subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=True)
    except:
        sys.exit(2)

    if not os.path.exists(out_seg) or not os.path.exists(out_vol_csv): sys.exit(3)

    # 2. Chạy chuẩn hóa TSV
    out_sub = os.path.join(args.output_dir, 'stats', 'subcortical_volume.tsv')
    out_cort = os.path.join(args.output_dir, 'stats', 'cortical_volume.tsv')
    
    try:
        subprocess.run(["python3", "/app/normalize_volumes.py", out_vol_csv, out_sub, out_cort], check=True)
    except:
        sys.exit(2)

    print("mri_synthseg thành công!")
    sys.exit(0)

if __name__ == "__main__":
    main()
