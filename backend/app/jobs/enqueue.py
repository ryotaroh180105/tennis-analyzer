"""API層から呼ぶジョブ投入インターフェース。タスク実体は app.jobs.tasks（Celeryワーカー側）。"""

from app.jobs.celery_app import celery_app


def enqueue_precheck(match_id: str) -> None:
    celery_app.send_task("app.jobs.tasks.run_precheck", args=[match_id])


def enqueue_recut(match_id: str) -> None:
    celery_app.send_task("app.jobs.tasks.run_edit", args=[match_id])


def enqueue_highlight(match_id: str) -> None:
    celery_app.send_task("app.jobs.tasks.run_highlight", args=[match_id])
