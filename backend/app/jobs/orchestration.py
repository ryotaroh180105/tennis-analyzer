"""ジョブ実行の冪等性・ポイズンピル対策（10 §冪等性・リトライ）。

全ジョブは match_id + 入力アセット世代で決まり、再実行しても行を重複させない。
タスク実行の冒頭で毎回 analysis_jobs.attempt をDBでインクリメントするのが唯一のゲート
——ブローカー再配送（ワーカー喪失）・アプリ側の明示的backoff再投入のどちらでも
同じ経路を通るため、同じ動画がGPU課金を永久に焼き続けることがない。
"""

from datetime import datetime, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.job import AnalysisJob, JobStage, JobStatus


def start_attempt(db: Session, match_id, stage: JobStage) -> AnalysisJob | None:
    settings = get_settings()
    existing = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.match_id == match_id, AnalysisJob.stage == stage)
        .order_by(desc(AnalysisJob.attempt))
        .first()
    )
    next_attempt = (existing.attempt + 1) if existing else 1
    if next_attempt > settings.job_max_attempts:
        return None

    job = AnalysisJob(
        match_id=match_id,
        stage=stage,
        status=JobStatus.running,
        attempt=next_attempt,
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def finish_success(db: Session, job: AnalysisJob, metrics: dict) -> None:
    job.status = JobStatus.succeeded
    job.progress = 100
    job.metrics = metrics
    job.finished_at = datetime.now(timezone.utc)
    db.commit()


def finish_failure(db: Session, job: AnalysisJob, error_message: str) -> None:
    job.status = JobStatus.failed
    job.error = error_message[:2000]
    job.finished_at = datetime.now(timezone.utc)
    db.commit()


def build_metrics(wall_seconds: float, gpu_seconds: float, breakdown: dict) -> dict:
    settings = get_settings()
    cost = round((gpu_seconds / 3600.0) * settings.gpu_unit_price_amount, 4)
    return {
        "wall_seconds": round(wall_seconds, 2),
        "gpu_seconds": round(gpu_seconds, 2),
        "breakdown": breakdown,
        "unit_price": {
            "amount": settings.gpu_unit_price_amount,
            "currency": settings.gpu_unit_price_currency,
            "per": "hour",
        },
        "cost_estimate": {"amount": cost, "currency": settings.gpu_unit_price_currency},
    }


class PermanentJobError(Exception):
    """恒久失敗（入力不正等）。リトライしても無意味なため即failedにする。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
