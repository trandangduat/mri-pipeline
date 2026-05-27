#!/usr/bin/env python3
import argparse, sys, subprocess, os

def main():
    parser = argparse.ArgumentParser(description="Wrapper cho mri_synthstrip")
    parser.add_argument('--input', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--work-dir', required=True)
    parser.add_argument('--subject-id', required=True)
    parser.add_argument('--threads', default='8')
    parser.add_argument('--device', default='cpu')
    args = parser.parse_args()

    # 1. Kiểm tra Input (Exit Code 1)
    if not os.path.exists(args.input):
        print(f"Error: Input không tồn tại: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Tạo thư mục đích
    log_dir = os.path.join(args.output_dir, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(args.work_dir, exist_ok=True)

    # Khai báo file output
    out_brain = os.path.join(args.work_dir, "02_synthstrip_brain.nii.gz")
    out_mask = os.path.join(args.work_dir, "02_synthstrip_brain_mask.nii.gz")
    log_file = os.path.join(log_dir, 'synthstrip.log')

    # Lệnh chạy mri_synthstrip
    cmd = [
        "mri_synthstrip",
        "-i", args.input,
        "-o", out_brain,
        "-m", out_mask
    ]
    if args.device.lower() != 'cpu':
        cmd.append("-g") # Chạy GPU nếu được yêu cầu

    # 2. Chạy tool (Exit Code 2)
    try:
        with open(log_file, 'w') as f:
            subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, check=True)
    except subprocess.CalledProcessError:
        print("Error: mri_synthstrip chạy thất bại.", file=sys.stderr)
        sys.exit(2)

    # 3. Kiểm tra Output bắt buộc (Exit Code 3)
    if not os.path.exists(out_brain) or not os.path.exists(out_mask):
        print("Error: Thiếu output file bắt buộc sau khi chạy.", file=sys.stderr)
        sys.exit(3)

    # Thành công (Exit Code 0)
    print("mri_synthstrip chạy thành công!")
    sys.exit(0)

if __name__ == "__main__":
    main()
