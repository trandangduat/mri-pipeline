# 1. Sử dụng image PyTorch chính thức làm nền (đã tối ưu sẵn cho cả CPU và GPU)
FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime

# 2. Cài đặt các thư viện hệ thống cần thiết cho xử lý ảnh và git để tải source code
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 3. Thiết lập thư mục làm việc mặc định trong container
WORKDIR /app

# 4. Clone mã nguồn HD-BET chính thức từ GitHub và tiến hành cài đặt
RUN git clone https://github.com/MIC-DKFZ/HD-BET.git && \
    cd HD-BET && \
    pip install -e .

# 5. Copy file script điều khiển của bạn vào trong Docker
COPY run_tool.py /app/run_tool.py

# 6. Đặt lệnh chạy mặc định
ENTRYPOINT ["python", "/app/run_tool.py"]