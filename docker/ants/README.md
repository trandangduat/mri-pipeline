# ⚡ ANTs N4 Bias Field Correction Wrapper

Công cụ chuẩn hóa cường độ sáng và khử nhiễu từ trường không đồng đều sử dụng lõi thuật toán C++ tối ưu của hệ sinh thái ANTs (thông qua package `antspyx`).

## 🛠️ Chức năng chính
- Sửa lỗi hiệu ứng bóng mờ, vùng sáng tối không đồng đều (Bias Field) sinh ra do sự sai lệch của từ trường máy quét MRI.
- Chuẩn hóa lại dải tương phản (Contrast) của các pixel ảnh.
- Khôi phục rõ nét ranh giới giải phẫu giữa chất trắng (White Matter) và chất xám (Gray Matter), làm tiền đề cho các bước Segmentation (Thành viên 1 & 2) chạy chính xác nhất.

## 🚀 Hướng dẫn chạy kiểm tra (Test Command)
Chạy lệnh sau:

```bash
docker run --rm \
  -v ./work:/work \
  -v ./outputs_test:/outputs \
  mri-ants:latest \
  --input /work/02_hdbet_brain.nii.gz \
  --output-dir /outputs \
  --work-dir /work \
  --subject-id sub-0010 \
  --device cpu