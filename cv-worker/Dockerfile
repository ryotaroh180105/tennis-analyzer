FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# backendのapp（Celeryタスク定義・DBモデル）とcvpipelineの両方が必要
COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/app /app/backend/app
COPY cv-worker/pyproject.toml /app/cv-worker/pyproject.toml
COPY cv-worker/cvpipeline /app/cv-worker/cvpipeline

RUN pip install --no-cache-dir -e /app/backend -e /app/cv-worker

ENV PYTHONPATH=/app/backend:/app/cv-worker
ENV CONFIG_DIR=/app/config
ENV ENCODER=libx264

WORKDIR /app/backend

CMD ["celery", "-A", "app.jobs.celery_app", "worker", "-Q", "gpu", "--loglevel=info", "--concurrency=1"]
