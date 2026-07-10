import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ScorePointWinner(str, enum.Enum):
    self = "self"
    opponent = "opponent"


class ScoreEvent(Base):
    """ポイントごとの勝敗タップの追加専用ログ（10 §半自動スコア入力）。

    自動スコア判定は行わず、ユーザーがワンタップで入力した結果のみを記録する
    （SwingVisionの自動スコアリング精度問題を回避しつつ正解データを蓄積する設計、01）。
    """

    __tablename__ = "score_events"
    __table_args__ = (UniqueConstraint("match_id", "sequence", name="uq_score_event_sequence"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    sequence: Mapped[int] = mapped_column(Integer)
    winner: Mapped[ScorePointWinner] = mapped_column(SAEnum(ScorePointWinner, name="score_point_winner"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
