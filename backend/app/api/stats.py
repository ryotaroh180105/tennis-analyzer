"""ミス分類スタッツAPI（04-miss-taxonomy.md / 01 §Phase1）。"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.matches import _get_match_or_404
from app.api.schemas import StatsResponse
from app.core.db import get_db
from app.models.match import EventStream
from app.models.user import User
from app.services.stats import aggregate_stats

router = APIRouter(prefix="/api/matches", tags=["stats"])


@router.get("/{match_id}/stats", response_model=StatsResponse)
def get_stats(
    match_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> StatsResponse:
    match = _get_match_or_404(db, user, match_id)
    stream = (
        db.query(EventStream)
        .filter(EventStream.match_id == match.id)
        .order_by(desc(EventStream.version))
        .first()
    )
    if stream is None:
        return StatsResponse(total_points=0, unclassified_points=0, stat_counts={}, labels=[], highlights=[])

    return StatsResponse(**aggregate_stats(stream.payload))
