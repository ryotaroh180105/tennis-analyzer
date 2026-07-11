"""サーブ骨格解析API（Phase 3。01 §Phase3 / 06-pro-reference-data.md）。"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import (
    ServeAnalysisResponse,
    ServeSessionCreateRequest,
    ServeSessionResponse,
)
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import conflict, not_found, rate_limited
from app.jobs.enqueue import enqueue_serve_analyze
from app.models.serve import ServeAnalysis, ServeSession
from app.models.upload import Upload, UploadStatus
from app.models.user import User

router = APIRouter(prefix="/api/serve-sessions", tags=["serve"])


def _get_session_or_404(db: Session, user: User, serve_session_id: uuid.UUID) -> ServeSession:
    session = db.get(ServeSession, serve_session_id)
    if session is None or session.user_id != user.id:
        raise not_found("serve_session")
    return session


def _serialize(session: ServeSession) -> ServeSessionResponse:
    return ServeSessionResponse(
        id=session.id,
        title=session.title,
        status=session.status.value,
        failure_reason=session.failure_reason,
        duration_s=session.duration_s,
        created_at=session.created_at,
    )


@router.post("", response_model=ServeSessionResponse)
def create_serve_session(
    body: ServeSessionCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ServeSessionResponse:
    settings = get_settings()

    # matchesと同じ10本/日の乱用対策を流用（10 §共通事項）
    since = datetime.now(timezone.utc) - timedelta(days=1)
    recent_count = (
        db.query(ServeSession)
        .filter(ServeSession.user_id == user.id, ServeSession.created_at >= since)
        .count()
    )
    if recent_count >= settings.upload_daily_limit:
        raise rate_limited("daily upload limit reached")

    upload = db.get(Upload, body.upload_id)
    if upload is None or upload.user_id != user.id:
        raise not_found("upload")
    if upload.status != UploadStatus.completed or upload.used_by_match:
        raise conflict("upload is not completed or already used")

    session = ServeSession(
        user_id=user.id,
        upload_id=upload.id,
        title=body.title,
        original_r2_key=upload.r2_key,
    )
    db.add(session)
    upload.used_by_match = True
    db.commit()
    db.refresh(session)

    enqueue_serve_analyze(str(session.id))

    return _serialize(session)


@router.get("", response_model=list[ServeSessionResponse])
def list_serve_sessions(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ServeSessionResponse]:
    sessions = (
        db.query(ServeSession)
        .filter(ServeSession.user_id == user.id)
        .order_by(desc(ServeSession.created_at))
        .all()
    )
    return [_serialize(s) for s in sessions]


@router.get("/{serve_session_id}", response_model=ServeSessionResponse)
def get_serve_session(
    serve_session_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ServeSessionResponse:
    return _serialize(_get_session_or_404(db, user, serve_session_id))


@router.get("/{serve_session_id}/analysis", response_model=ServeAnalysisResponse)
def get_serve_analysis(
    serve_session_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ServeAnalysisResponse:
    session = _get_session_or_404(db, user, serve_session_id)
    analysis = (
        db.query(ServeAnalysis).filter(ServeAnalysis.serve_session_id == session.id).one_or_none()
    )
    if analysis is None:
        raise not_found("serve_analysis")

    payload = analysis.payload
    return ServeAnalysisResponse(
        phases=payload["phases"],
        metrics=payload["metrics"],
        feedback_metrics=payload["feedback_metrics"],
        confidence=payload["confidence"],
        citation_status=payload["citation_status"],
        created_at=analysis.created_at,
    )
