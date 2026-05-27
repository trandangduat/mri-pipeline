FROM mri-freesurfer-base:latest
COPY run_tool.py /app/run_tool.py
COPY normalize_volumes.py /app/normalize_volumes.py
RUN chmod +x /app/run_tool.py /app/normalize_volumes.py
ENTRYPOINT ["python3", "/app/run_tool.py"]
