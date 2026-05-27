FROM deepmi/fastsurfer:latest

USER root
RUN apt-get update && apt-get install -y python3-pip && rm -rf /var/lib/apt/lists/*
RUN pip3 install pandas nibabel --no-cache-dir

COPY run_tool.py /app/run_tool.py
COPY normalize_volumes.py /app/normalize_volumes.py

RUN chmod +x /app/run_tool.py /app/normalize_volumes.py

ENTRYPOINT ["python3", "/app/run_tool.py"]
