"""アドバイス配信API（07-advice-delivery.md §① 即時フィードバック）。"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.matches import _get_match_or_404
from app.api.schemas import ImmediateFeedbackResponse
from app.core.db import get_db
from app.core.errors import not_found
from app.models.advice import AdviceDelivery, AdviceDeliveryKind
from app.models.user import User

router = APIRouter(prefix="/api/matches", tags=["advice"])


@router.get("/{match_id}/feedback", response_model=ImmediateFeedbackResponse)
def get_immediate_feedback(
    match_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ImmediateFeedbackResponse:
    """解析完了直後の即時フィードバック（run_immediate_feedbackタスクが非同期で生成）。

    未生成（生成中・失敗）の場合は404。フロントエンドはポーリングで待つ想定。
    """
    match = _get_match_or_404(db, user, match_id)
    delivery = (
        db.query(AdviceDelivery)
        .filter(
            AdviceDelivery.match_id == match.id,
            AdviceDelivery.kind == AdviceDeliveryKind.immediate,
        )
        .order_by(desc(AdviceDelivery.created_at))
        .first()
    )
    if delivery is None:
        raise not_found("feedback")

    return ImmediateFeedbackResponse(
        summary=delivery.content.get("summary", ""),
        tendencies=delivery.content.get("tendencies", []),
        drill_suggestions=delivery.content.get("drill_suggestions", []),
        created_at=delivery.created_at,
    )
