FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    libgl1 \
    libglib2.0-0 \
    libgles2 \
    libegl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# backendのapp（Celeryタスク定義・DBモデル）とcvpipelineの両方が必要
COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/app /app/backend/app
COPY cv-worker/pyproject.toml /app/cv-worker/pyproject.toml
COPY cv-worker/cvpipeline /app/cv-worker/cvpipeline

RUN pip install --no-cache-dir -e /app/backend -e /app/cv-worker

# MediaPipe Pose Landmarker（Apache-2.0、事前学習済み）。stage6_pose.py（Phase3サーブ骨格解析）用。
# URLはGoogleの公開モデルストレージ（https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker）。
RUN mkdir -p /app/models && curl -sSL -o /app/models/pose_landmarker.task \
    https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task

ENV PYTHONPATH=/app/backend:/app/cv-worker
ENV CONFIG_DIR=/app/config
ENV ENCODER=libx264
ENV POSE_MODEL_PATH=/app/models/pose_landmarker.task

WORKDIR /app/backend

CMD ["celery", "-A", "app.jobs.celery_app", "worker", "-Q", "gpu", "--loglevel=info", "--concurrency=1"]
