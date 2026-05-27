#!/usr/bin/env python3
import argparse, sys, subprocess, os

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--work-dir', required=True)
    parser.add_argument('--subject-id', required=True)
    parser.add_argument('--threads', default='1')
    parser.add_argument('--device', default='cpu')
    args, _ = parser.parse_known_args()

    if not os.path.exists(args.input):
        sys.exit(1)

    os.makedirs(os.path.join(args.output_dir, 'logs'), exist_ok=True)
    os.makedirs(args.work_dir, exist_ok=True)

    out_file = os.path.join(args.work_dir, "01_reoriented.nii.gz")
    log_file = os.path.join(args.output_dir, 'logs', 'mri_convert.log')

    cmd = ["mri_convert", args.input, out_file]

    try:
        with open(log_file, 'w') as f:
            subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=True)
    except subprocess.CalledProcessError:
        sys.exit(2)

    if not os.path.exists(out_file):
        sys.exit(3)

    print("mri_convert thành công!")
    sys.exit(0)

if __name__ == "__main__":
    main()
