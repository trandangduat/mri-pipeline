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

    if not os.path.exists(args.input): sys.exit(1)

    os.makedirs(os.path.join(args.output_dir, 'logs'), exist_ok=True)
    os.makedirs(args.work_dir, exist_ok=True)

    out_file = os.path.join(args.work_dir, "05_ants_n3_bias_corrected.nii.gz")
    log_file = os.path.join(args.output_dir, 'logs', 'ants_n3_bias.log')

    # Gọi công cụ N3 chuẩn của hệ sinh thái ANTs
    cmd = ["N3BiasFieldCorrection", "-d", "3", "-i", args.input, "-o", out_file]

    try:
        with open(log_file, 'w') as f:
            subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=True)
    except Exception:
        sys.exit(2)

    if not os.path.exists(out_file): sys.exit(3)

    print("ANTs N3 Bias Correction thành công!")
    sys.exit(0)

if __name__ == "__main__":
    main()
