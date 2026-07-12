"""フォーム解析API（Phase 3拡張。12-form-analysis.md）。"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import (
    FormAnalysisResponse,
    FormSessionCreateRequest,
    FormSessionResponse,
)
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import conflict, not_found, rate_limited, validation_error
from app.jobs.enqueue import enqueue_form_analyze
from app.models.form import BackhandStyle, FormAnalysis, FormSession, FormShotType
from app.models.upload import Upload, UploadStatus
from app.models.user import User

router = APIRouter(prefix="/api/form-sessions", tags=["form"])


def _get_session_or_404(db: Session, user: User, form_session_id: uuid.UUID) -> FormSession:
    session = db.get(FormSession, form_session_id)
    if session is None or session.user_id != user.id:
        raise not_found("form_session")
    return session


def _serialize(session: FormSession) -> FormSessionResponse:
    return FormSessionResponse(
        id=session.id,
        title=session.title,
        shot_type=session.shot_type.value,
        backhand_style=session.backhand_style.value if session.backhand_style else None,
        status=session.status.value,
        failure_reason=session.failure_reason,
        duration_s=session.duration_s,
        created_at=session.created_at,
    )


@router.post("", response_model=FormSessionResponse)
def create_form_session(
    body: FormSessionCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FormSessionResponse:
    settings = get_settings()

    if body.shot_type not in [s.value for s in FormShotType]:
        raise validation_error(f"shot_type must be one of {[s.value for s in FormShotType]}")
    if body.backhand_style is not None and body.backhand_style not in [s.value for s in BackhandStyle]:
        raise validation_error(f"backhand_style must be one of {[s.value for s in BackhandStyle]}")

    # matchesと同じ10本/日の乱用対策を流用（10 §共通事項）
    since = datetime.now(timezone.utc) - timedelta(days=1)
    recent_count = (
        db.query(FormSession)
        .filter(FormSession.user_id == user.id, FormSession.created_at >= since)
        .count()
    )
    if recent_count >= settings.upload_daily_limit:
        raise rate_limited("daily upload limit reached")

    upload = db.get(Upload, body.upload_id)
    if upload is None or upload.user_id != user.id:
        raise not_found("upload")
    if upload.status != UploadStatus.completed or upload.used_by_match:
        raise conflict("upload is not completed or already used")

    session = FormSession(
        user_id=user.id,
        upload_id=upload.id,
        title=body.title,
        shot_type=FormShotType(body.shot_type),
        backhand_style=BackhandStyle(body.backhand_style) if body.backhand_style else None,
        original_r2_key=upload.r2_key,
    )
    db.add(session)
    upload.used_by_match = True
    db.commit()
    db.refresh(session)

    enqueue_form_analyze(str(session.id))

    return _serialize(session)


@router.get("", response_model=list[FormSessionResponse])
def list_form_sessions(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[FormSessionResponse]:
    sessions = (
        db.query(FormSession)
        .filter(FormSession.user_id == user.id)
        .order_by(desc(FormSession.created_at))
        .all()
    )
    return [_serialize(s) for s in sessions]


@router.get("/{form_session_id}", response_model=FormSessionResponse)
def get_form_session(
    form_session_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> FormSessionResponse:
    return _serialize(_get_session_or_404(db, user, form_session_id))


@router.get("/{form_session_id}/analysis", response_model=FormAnalysisResponse)
def get_form_analysis(
    form_session_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> FormAnalysisResponse:
    session = _get_session_or_404(db, user, form_session_id)
    analysis = (
        db.query(FormAnalysis).filter(FormAnalysis.form_session_id == session.id).one_or_none()
    )
    if analysis is None:
        raise not_found("form_analysis")

    payload = analysis.payload
    return FormAnalysisResponse(
        shot_type=payload["shot_type"],
        dominant_side=payload["dominant_side"],
        swing_count=payload["swing_count"],
        insufficient_data=payload["insufficient_data"],
        swings=payload["swings"],
        metrics=payload["metrics"],
        feedback_metrics=payload["feedback_metrics"],
        confidence=payload["confidence"],
        citation_status=payload["citation_status"],
        created_at=analysis.created_at,
    )
