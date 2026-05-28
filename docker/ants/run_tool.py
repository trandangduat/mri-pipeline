import argparse
import sys
import os
import traceback
from pathlib import Path
import ants

def main():
    # 1. Khai báo các tham số đầu vào chuẩn Contract
    parser = argparse.ArgumentParser(description="ANTs N4 Bias Field Correction wrapper")
    parser.add_argument("--input", required=True, help="Đường dẫn file ảnh đầu vào")
    parser.add_argument("--output-dir", required=True, help="Thư mục xuất kết quả")
    parser.add_argument("--work-dir", required=True, help="Thư mục làm việc trung gian")
    parser.add_argument("--subject-id", required=True, help="Subject ID")
    parser.add_argument("--threads", type=int, default=1, help="Số luồng CPU")
    parser.add_argument("--device", default="cpu", help="Thiết bị chạy (cpu hoặc gpu)")

    args = parser.parse_args()

    # 2. Tạo cấu trúc thư mục đầu ra chuẩn hóa
    output_dir = Path(args.output_dir)
    work_dir = Path(args.work_dir)
    log_dir = output_dir / "logs"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file_path = log_dir / "ants_n4.log"
    out_file = work_dir / "05_standardized.nii.gz"

    # 3. Mở file log để ghi nhận tiến trình
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(f"=== BẮT ĐẦU TIẾN TRÌNH ANTs N4 CHO SUBJECT: {args.subject_id} ===\n")
        log_file.write(f"Input: {args.input}\n")
        log_file.write(f"Output mong đợi: {out_file}\n\n")

        # Kiểm tra Exit Code 1: Lỗi input
        if not os.path.exists(args.input):
            log_file.write(f"❌ LỖI CODE 1: Không tìm thấy file input tại {args.input}\n")
            print("Lỗi: Không tìm thấy file input.")
            sys.exit(1)

        try:
            log_file.write("Đang đọc ảnh bằng ANTs...\n")
            # Tải ảnh vào bộ nhớ ANTs
            img = ants.image_read(args.input)

            log_file.write("Đang chạy thuật toán N4 Bias Field Correction (Cân bằng độ sáng từ trường)...\n")
            # Chạy thuật toán N4 (Core C++ của ANTs)
            n4_img = ants.n4_bias_field_correction(img)

            log_file.write("Đang lưu file kết quả chuẩn hóa...\n")
            # Ghi file kết quả ra ổ đĩa
            ants.image_write(n4_img, str(out_file))

            # Kiểm tra Exit Code 3: Thiếu output bắt buộc
            if not out_file.exists():
                log_file.write("❌ LỖI CODE 3: Tool chạy không báo lỗi nhưng không sinh ra file kết quả.\n")
                print("Lỗi: Chạy xong nhưng thiếu output bắt buộc.")
                sys.exit(3)

            log_file.write("\n✅ HOÀN TẤT THÀNH CÔNG! File đã được chuẩn hóa ánh sáng.\n")
            print("Xử lý ANTs N4 thành công!")
            sys.exit(0) # Exit Code 0: Thành công

        except Exception as e:
            # Exit Code 2: Lỗi trong quá trình chạy tool
            log_file.write(f"\n❌ LỖI CODE 2: Gặp sự cố khi chạy ANTs: {str(e)}\n")
            log_file.write(traceback.format_exc())
            print(f"Lỗi khi chạy ANTs: {str(e)}")
            sys.exit(2)

if __name__ == "__main__":
    main()