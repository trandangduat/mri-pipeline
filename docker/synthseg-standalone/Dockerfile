FROM nvidia/cuda:11.8.0-devel-ubuntu22.04 AS builder

FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

COPY --from=builder /usr/local/cuda-11.8/bin/ptxas /usr/local/cuda-11.8/bin/ptxas
COPY --from=builder /usr/local/cuda-11.8/nvvm/libdevice/libdevice.10.bc /usr/local/cuda-11.8/nvvm/libdevice/libdevice.10.bc
COPY --from=builder /usr/local/cuda-11.8/lib64/libcudart.so.11.0 /usr/local/cuda-11.8/lib64/libcudart.so.11.0

RUN apt-get update && apt-get install -y \
    git python3.10 python3-pip libcudnn8 libcudnn8-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1

RUN git clone --depth 1 https://github.com/BBillot/SynthSeg.git /app/SynthSeg \
    && rm -rf /app/SynthSeg/.git

WORKDIR /app

RUN pip install --no-cache-dir tensorflow==2.14.1 numpy==1.23.5 scipy nibabel pandas scikit-image

COPY models/ /app/SynthSeg/models/

COPY run_tool.py /app/run_tool.py
COPY normalize_volumes.py /app/normalize_volumes.py

RUN chmod +x /app/run_tool.py /app/normalize_volumes.py

ENTRYPOINT ["python3", "/app/run_tool.py"]
