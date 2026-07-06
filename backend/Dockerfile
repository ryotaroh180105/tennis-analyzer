FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# backendとcv-worker両方のパッケージを入れる（precheck/editはCPU queueで
# 動くが、コート検出等cvpipelineの古典的CVコードに依存するため。10 §リポジトリ構成）
COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/app /app/backend/app
COPY cv-worker/pyproject.toml /app/cv-worker/pyproject.toml
COPY cv-worker/cvpipeline /app/cv-worker/cvpipeline

RUN pip install --no-cache-dir -e /app/backend -e /app/cv-worker

ENV PYTHONPATH=/app/backend:/app/cv-worker
ENV CONFIG_DIR=/app/config

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
