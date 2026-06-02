import argparse
import sys
import subprocess
from pathlib import Path

def main():
    # 1. Khai báo các tham số đầu vào chuẩn Contract của nhóm
    parser = argparse.ArgumentParser(description="HD-BET Brain Extraction wrapper")
    parser.add_argument("--input", required=True, help="Đường dẫn file ảnh MRI đầu vào")
    parser.add_argument("--output-dir", required=True, help="Thư mục xuất kết quả")
    parser.add_argument("--work-dir", required=True, help="Thư mục làm việc trung gian")
    parser.add_argument("--subject-id", required=True, help="Subject ID")
    parser.add_argument("--threads", type=int, default=1, help="Số luồng CPU")
    parser.add_argument("--device", default="cpu", help="Thiết bị chạy (cpu hoặc gpu)")

    args, _ = parser.parse_known_args()

    # 2. Tạo cấu trúc thư mục đầu ra chuẩn hóa
    output_dir = Path(args.output_dir)
    work_dir = Path(args.work_dir)
    log_dir = output_dir / "logs"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file_path = log_dir / "hdbet.log"
    
    # Định nghĩa tên file đầu ra trong thư mục work theo chuẩn của Thành viên 3
    out_brain_file = work_dir / "02_hdbet_brain.nii.gz"
    out_mask_file = work_dir / "02_hdbet_brain_mask.nii.gz"

    # 3. Mở file log để ghi nhận tiến trình
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(f"=== BẮT ĐẦU TIẾN TRÌNH HD-BET CHO SUBJECT: {args.subject_id} ===\n")
        log_file.write(f"Input: {args.input}\n\n")
        log_file.flush()

        # Dịch tham số --device sang định dạng lệnh của HD-BET
        # HD-BET nhận diện: -device 0, 1... cho GPU hoặc -device cpu
        hdbet_device = "cpu" if args.device.lower() == "cpu" else "0"

        # Khởi tạo lệnh chạy HD-BET hệ thống
        # -i: input, -o: output, -device: thiết bị, -b 0: không lưu file weights tạm lung tung
        # Khởi tạo lệnh chạy HD-BET hệ thống
        cmd = [
            "hd-bet",
            "-i", args.input,
            "-o", str(out_brain_file),
            "-device", hdbet_device,
            "--save_bet_mask"
        ]

        log_file.write(f"Chạy lệnh hệ thống: {' '.join(cmd)}\n\n")
        log_file.flush()

        try:
            # Gọi HD-BET chạy và bắn trực tiếp toàn bộ log của tool vào file hdbet.log
            result = subprocess.run(cmd, stdout=log_file, stderr=log_file, text=True, check=True)
            
            # Đổi tên file mask do HD-BET tự sinh ra đuôi mặc định (_mask.nii.gz) về đúng tên quy chuẩn nhóm
            hdbet_auto_mask = work_dir / "02_hdbet_brain_mask.nii.gz"
            # Nếu HD-BET sinh ra file dạng 02_hdbet_brain_mask.nii.gz thì chuẩn, nếu có hậu tố lạ thì rename lại
            
            log_file.write("\n✅ HOÀN TẤT THÀNH CÔNG! Đã bóc tách sọ não xong.\n")
            print("Xử lý HD-BET thành công!")
            sys.exit(0)

        except subprocess.CalledProcessError as e:
            log_file.write(f"\n❌ LỖI KHI CHẠY HD-BET (Exit code {e.returncode})\n")
            print(f"Lỗi khi chạy HD-BET hệ thống.")
            sys.exit(2)
        except Exception as e:
            log_file.write(f"\n❌ LỖI HỆ THỐNG: {str(e)}\n")
            print(f"Lỗi hệ thống: {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    main()