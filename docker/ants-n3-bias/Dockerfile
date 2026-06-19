FROM antsx/ants:latest

LABEL maintainer="Baor"
LABEL description="ANTs N3 Bias Field Correction Tool"

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3 \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /input /output /work /app
WORKDIR /app

COPY run_tool.py /app/run_tool.py
RUN chmod +x /app/run_tool.py

ENTRYPOINT ["python3", "/app/run_tool.py"]
