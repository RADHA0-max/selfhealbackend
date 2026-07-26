FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir flask prometheus_client psutil gunicorn

COPY app.py .

EXPOSE 8080

# CRITICAL: -w 1 is required for this demo. 
# Our chaos/rate-limit state is stored in Python memory (not Redis).
# If we had multiple workers, state would be split across processes.
# We still get concurrency via --threads 4.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "app:app"]