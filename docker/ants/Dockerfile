# 1. Sử dụng image Python thu nhỏ
FROM python:3.9-slim

# 2. Cài đặt thư viện hệ thống cần thiết cho ANTs (chạy song song)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 3. Thiết lập thư mục làm việc
WORKDIR /app

# 4. Cài đặt antspyx (chứa core ANTs)
RUN pip install --no-cache-dir antspyx

# 5. Copy file script điều khiển
COPY run_tool.py /app/run_tool.py

# 6. Mặc định chạy script bằng Python
ENTRYPOINT ["python", "/app/run_tool.py"]