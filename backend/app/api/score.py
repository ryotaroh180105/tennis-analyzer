"""スコア半自動入力API（10 §API契約 / 01 §Phase1）。

自動スコア判定は行わない。ユーザーがポイントごとにワンタップで勝敗を入力し、
サーバーは追加専用ログ（score_events）から標準的なテニスのスコアリングルールで
現在のスコアを合成して返す。
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.matches import _get_match_or_404
from app.api.schemas import ScorePointRequest, ScoreResponse
from app.core.db import get_db
from app.core.errors import conflict, validation_error
from app.models.score import ScoreEvent, ScorePointWinner
from app.models.user import User
from app.services.scoring import compute_score

router = APIRouter(prefix="/api/matches", tags=["score"])


def _serialize(events: list[ScoreEvent]) -> ScoreResponse:
    winners = [e.winner.value for e in events]
    return ScoreResponse(**compute_score(winners))


@router.get("/{match_id}/score", response_model=ScoreResponse)
def get_score(
    match_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ScoreResponse:
    match = _get_match_or_404(db, user, match_id)
    events = (
        db.query(ScoreEvent)
        .filter(ScoreEvent.match_id == match.id)
        .order_by(ScoreEvent.sequence)
        .all()
    )
    return _serialize(events)


@router.post("/{match_id}/score/points", response_model=ScoreResponse)
def add_point(
    match_id: uuid.UUID,
    body: ScorePointRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScoreResponse:
    match = _get_match_or_404(db, user, match_id)
    if body.winner not in ("self", "opponent"):
        raise validation_error("winner must be 'self' or 'opponent'")

    events = (
        db.query(ScoreEvent)
        .filter(ScoreEvent.match_id == match.id)
        .order_by(ScoreEvent.sequence)
        .all()
    )
    current = compute_score([e.winner.value for e in events])
    if current["match_winner"] is not None:
        raise conflict("match already finished")

    next_seq = (events[-1].sequence + 1) if events else 1
    event = ScoreEvent(match_id=match.id, sequence=next_seq, winner=ScorePointWinner(body.winner))
    db.add(event)
    db.commit()

    events.append(event)
    return _serialize(events)


@router.delete("/{match_id}/score/points/last", response_model=ScoreResponse)
def undo_last_point(
    match_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ScoreResponse:
    match = _get_match_or_404(db, user, match_id)
    last = (
        db.query(ScoreEvent)
        .filter(ScoreEvent.match_id == match.id)
        .order_by(desc(ScoreEvent.sequence))
        .first()
    )
    if last is None:
        raise conflict("no points to undo")

    db.delete(last)
    db.commit()

    events = (
        db.query(ScoreEvent)
        .filter(ScoreEvent.match_id == match.id)
        .order_by(ScoreEvent.sequence)
        .all()
    )
    return _serialize(events)
