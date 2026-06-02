FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

RUN git clone https://github.com/MIC-DKFZ/HD-BET.git && \
    cd HD-BET && \
    pip install --no-cache-dir -e . --no-deps && \
    pip install --no-cache-dir \
        scikit-image \
        nnunetv2>=2.5.1 \
        SimpleITK \
        connected-components-3d \
        acvl-utils \
        batchgenerators \
        batchgeneratorsv2 \
        dynamic-network-architectures \
        timm \
        einops \
        yacs \
        graphviz \
        pandas \
        seaborn \
        matplotlib \
        huggingface_hub

COPY run_tool.py /app/run_tool.py

ENTRYPOINT ["python", "/app/run_tool.py"]
