from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "tennis_analyzer",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Tokyo",
    enable_utc=True,
    # ポイズンピル対策の前提（10 §冪等性）：ワーカー喪失時にタスクを受け直す。
    # ただしCeleryのretryカウンタは増えないため、実際の打ち切りは
    # analysis_jobs.attempt をDBで管理して行う（jobs/orchestration.py）。
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # ジョブ最長時間(60分)×2。デフォルト1hのままにしない（10）。
    broker_transport_options={"visibility_timeout": 7200},
    task_routes={
        "app.jobs.tasks.run_precheck": {"queue": "cpu"},
        "app.jobs.tasks.run_edit": {"queue": "cpu"},
        "app.jobs.tasks.run_ingest": {"queue": "gpu"},
        "app.jobs.tasks.run_analyze": {"queue": "gpu"},
    },
)
