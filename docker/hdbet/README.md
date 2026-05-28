# 🧠 HD-BET Brain Extraction Wrapper

Công cụ bóc tách sọ não tự động (Brain Extraction/Skull Stripping) sử dụng sức mạnh mạng thần kinh nhân tạo tiên tiến của công cụ HD-BET (giả lập kiến trúc nnU-Net).

## 🛠️ Chức năng chính
- Tự động nhận diện và phân tách vùng nhu mô não (Brain Tissue) khỏi cấu trúc sọ ngoại vi.
- Cắt gọt sạch sẽ xương sọ, cơ sọ mặt, mô mỡ quanh mắt và các tế bào mô mềm không liên quan.
- Xuất ra file ảnh não sạch và file mặt nạ nhị phân (Binary Mask) ôm khít vỏ não.

## 🚀 Hướng dẫn chạy kiểm tra (Test Command)
Chạy lệnh sau:

```bash
docker run --rm \
  -v ./work:/work \
  -v ./outputs_test:/outputs \
  mri-hdbet:latest \
  --input /work/01_nibabel_reoriented.nii.gz \
  --output-dir /outputs \
  --work-dir /work \
  --subject-id sub-0010 \
  --device cpu