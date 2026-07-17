FROM nvidia/cuda:11.1.1-runtime-ubuntu20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    wget bzip2 git libgl1-mesa-glx && \
    rm -rf /var/lib/apt/lists/*

RUN wget https://repo.anaconda.com/miniconda/Miniconda3-py38_4.9.2-Linux-x86_64.sh -O /tmp/miniconda.sh && \
    bash /tmp/miniconda.sh -b -p /opt/conda && \
    rm /tmp/miniconda.sh

ENV PATH="/opt/conda/bin:$PATH"

RUN conda install -y pytorch=1.9.0 torchvision torchaudio cudatoolkit=11.1 -c pytorch -c nvidia && \
    conda install -y -c fvcore -c iopath -c conda-forge fvcore iopath && \
    conda install -y -c bottler nvidiacub && \
    conda install -y -c pytorch3d pytorch3d=0.5.0 && \
    conda clean -ya

RUN pip install hydra-core --upgrade && \
    pip install trimesh nibabel tensorboard pandas

WORKDIR /app
RUN git clone https://github.com/lebrat/CorticalFlow.git .

# Entry point is bash, we'll run commands via command_builder
ENTRYPOINT []
