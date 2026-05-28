import argparse
import sys
import os
from pathlib import Path
import nibabel as nib

def main():
    # 1. Định nghĩa các tham số đầu vào theo đúng Contract (giao kèo) của nhóm
    parser = argparse.ArgumentParser(description="NiBabel Preprocessing Utilities wrapper")
    parser.add_index = False
    parser.add_argument("--input", required=True, help="Đường dẫn tới file ảnh MRI (.nii.gz) đầu vào")
    parser.add_argument("--output-dir", required=True, help="Thư mục xuất kết quả đầu ra")
    parser.add_argument("--work-dir", required=True, help="Thư mục làm việc trung gian")
    parser.add_argument("--subject-id", required=True, help="ID của đối tượng (Subject ID)")
    parser.add_argument("--threads", type=int, default=1, help="Số luồng CPU sử dụng (NiBabel chạy đơn luồng nên để phòng hờ)")
    parser.add_argument("--device", default="cpu", help="Thiết bị chạy (cpu hoặc gpu)")

    args = parser.parse_args()

    # 2. Tạo cấu trúc thư mục đầu ra chuẩn hóa (work và logs)
    output_dir = Path(args.output_dir)
    work_dir = Path(args.work_dir)
    log_dir = output_dir / "logs"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Đường dẫn file log và file kết quả đầu ra
    log_file_path = log_dir / "nibabel_utils.log"
    output_file_path = work_dir / "01_nibabel_reoriented.nii.gz"

    # 3. Mở file log để ghi lại toàn bộ quá trình chạy
    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(f"=== BẮT ĐẦU TIẾN TRÌNH NIBABEL UTILS CHO SUBJECT: {args.subject_id} ===\n")
        log_file.write(f"Input file: {args.input}\n")
        log_file.write(f"Output file chuẩn: {output_file_path}\n\n")

        # Kiểm tra xem file input ngoài đời thật có tồn tại trong Docker không
        if not os.path.exists(args.input):
            log_file.write(f"❌ LỖI CODE 1: Không tìm thấy file input tại: {args.input}\n")
            print("Lỗi: Không tìm thấy file input.")
            sys.exit(1) # Trả về Exit Code 1 (Lỗi cấu hình/đầu vào) theo đúng giao kèo

        try:

            log_file.write("Đang tải file ảnh MRI bằng NiBabel...\n")

            # Đọc ảnh ảnh MRI

            img = nib.load(args.input)

           

            log_file.write(f"Hướng ảnh gốc ban đầu (Orientation): {''.join(nib.aff2axcodes(img.affine))}\n")

            log_file.write("Đang tiến hành chuẩn hóa hướng ảnh về chuẩn RAS (Right-Anterior-Superior)...\n")

           

            # Thực hiện xoay ảnh về chuẩn RAS

            img_ras = nib.as_closest_canonical(img)

           

            log_file.write(f"Hướng ảnh sau khi xử lý: {''.join(nib.aff2axcodes(img_ras.affine))}\n")

            log_file.write("Đang lưu file ảnh mới ra thư mục work...\n")

           

            # Lưu lại file mới vào thư mục work theo đúng quy chuẩn tên nhóm giao

            nib.save(img_ras, str(output_file_path))

           

            log_file.write("\n✅ HOÀN TÀT THÀNH CÔNG! File đã được lưu sạch sẽ.\n")

            print("Xử lý NiBabel thành công!")

            sys.exit(0) # Trả về Exit Code 0 (Thành công mượt mà)

        except Exception as e:
            log_file.write(f"❌ LỖI CODE 2: Gặp sự cố nghiêm trọng khi chạy tool: {str(e)}\n")
            print(f"Lỗi khi chạy tool: {str(e)}")
            sys.exit(2) # Trả về Exit Code 2 (Lỗi trong lúc chạy tool)

if __name__ == "__main__":
    main()