from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

_WEEKDAY_MAP = {"SUN": "sun", "MON": "mon", "TUE": "tue", "WED": "wed", "THU": "thu", "FRI": "fri", "SAT": "sat"}


def _weekly_digest_crontab() -> crontab:
    # advice-rules.v1.yaml の settings.weekly_digest.default_schedule
    # （例: "SUN 20:00 Asia/Tokyo"）が唯一の真実源（CLAUDE.md 不変原則2）。
    # タイムゾーン欄はcelery_app.conf.timezoneと一致させる運用とし、ここではパースしない。
    from app.services.advice_engine import load_advice_rules

    spec = load_advice_rules()["settings"]["weekly_digest"]["default_schedule"]
    day_str, time_str, _tz = spec.split()
    hour, minute = time_str.split(":")
    return crontab(hour=int(hour), minute=int(minute), day_of_week=_WEEKDAY_MAP[day_str])


celery_app = Celery(
    "tennis_analyzer",
    broker=settings.redis_url,
    backend=settings.redis_url,
    # ワーカー起動時（celery -A app.jobs.celery_app worker）にタスク定義を読み込ませる。
    # これが無いと @celery_app.task のデコレータが実行されずタスク未登録エラーになる。
    include=["app.jobs.tasks"],
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
        "app.jobs.tasks.run_highlight": {"queue": "cpu"},
        "app.jobs.tasks.run_immediate_feedback": {"queue": "cpu"},
        "app.jobs.tasks.run_weekly_digest": {"queue": "cpu"},
        "app.jobs.tasks.run_weekly_digest_for_user": {"queue": "cpu"},
        "app.jobs.tasks.run_ingest": {"queue": "gpu"},
        "app.jobs.tasks.run_analyze": {"queue": "gpu"},
        "app.jobs.tasks.run_serve_analyze": {"queue": "gpu"},
    },
    beat_schedule={
        "weekly-advice-digest": {
            "task": "app.jobs.tasks.run_weekly_digest",
            "schedule": _weekly_digest_crontab(),
        },
    },
)
