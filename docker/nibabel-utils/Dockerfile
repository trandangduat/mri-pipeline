# 1. Sử dụng một image Linux hệ thu nhỏ đã cài sẵn Python 3.9
FROM python:3.9-slim

# 2. Thiết lập thư mục làm việc mặc định bên trong lòng Docker
WORKDIR /app

# 3. Cài đặt các thư viện Python cần thiết để xử lý ảnh MRI (NiBabel và Numpy)
RUN pip install --no-cache-dir \
    nibabel \
    numpy

# 4. Copy file script điều khiển từ máy bạn vào bên trong Docker
COPY run_tool.py /app/run_tool.py

# 5. Mặc định khi Docker khởi động, nó sẽ chạy file script này bằng Python
ENTRYPOINT ["python", "/app/run_tool.py"]