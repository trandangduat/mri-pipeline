FROM mri-freesurfer-base:latest

COPY run_tool.py /app/run_tool.py
RUN chmod +x /app/run_tool.py

ENTRYPOINT ["python3", "/app/run_tool.py"]
