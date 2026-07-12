import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SegmentOp(str, enum.Enum):
    add = "add"
    remove = "remove"
    adjust = "adjust"


class SegmentSource(str, enum.Enum):
    auto = "auto"
    user = "user"


class Segment(Base):
    """区間の追加専用ログ。有効区間はrevision昇順に全opを適用した結果（10）。

    真実源はこのテーブル。event_streamsは更新しない。
    op別必須フィールド: add={start_s,end_s} / remove={base_segment_id} /
    adjust={base_segment_id,start_s,end_s}
    """

    __tablename__ = "segments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    op: Mapped[SegmentOp] = mapped_column(SAEnum(SegmentOp, name="segment_op"))
    base_segment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("segments.id", ondelete="SET NULL"), nullable=True
    )
    start_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[SegmentSource] = mapped_column(SAEnum(SegmentSource, name="segment_source"))
    # CV自動検出(op=add, source=auto)の信頼度（stage4_segments.py参照）。
    # ユーザー編集(source=user)はNoneのまま（「低信頼」はCV検出固有のシグナルであり、
    # ユーザーが直接指定した区間には適用されない。11 §低信頼可視化、13 B-2）。
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
