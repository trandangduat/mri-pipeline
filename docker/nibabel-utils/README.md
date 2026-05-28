# 📁 NiBabel Preprocessing Utility

Bộ công cụ xử lý tiền bối (Preprocessing Utilities) sử dụng thư viện NiBabel để chuẩn hóa dữ liệu ảnh MRI thô từ các định dạng cổ điển.

## 🛠️ Chức năng chính
- Đọc định dạng ảnh ảnh MRI cổ điển Analyze 7.5 (`.hdr/.img`).
- Chuẩn hóa cấu trúc dữ liệu sang định dạng NIfTI hiện đại (`.nii.gz`).
- Gán lại ma trận định vị không gian để ép ảnh về hướng chuẩn **RAS** (Right-Anterior-Superior), đảm bảo hiển thị đúng cấu trúc giải phẫu.

## 🚀 Hướng dẫn chạy kiểm tra (Test Command)
Chạy trực tiếp lệnh sau tại thư mục gốc của dự án:

```bash
docker run --rm \
  -v ./data:/data \
  -v ./work:/work \
  -v ./outputs_test:/outputs \
  mri-nibabel:latest \
  --input /data/OASIS_0010/sub-0010_T1w.hdr \
  --output-dir /outputs \
  --work-dir /work \
  --subject-id sub-0010