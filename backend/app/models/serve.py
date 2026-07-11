"""サーブ骨格解析（Phase 3。01 §Phase3 / 06-pro-reference-data.md）。

試合（Match）とは別エンティティ：サーブ練習動画は編集・ハイライト・スコアを
必要としない単発の解析対象のため、Matchの4段ジョブパイプラインは流用しない。
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ServeSessionStatus(str, enum.Enum):
    queued = "queued"
    analyzing = "analyzing"
    done = "done"
    failed = "failed"


class ServeSession(Base):
    __tablename__ = "serve_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    upload_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("uploads.id", ondelete="RESTRICT"), unique=True
    )
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[ServeSessionStatus] = mapped_column(
        SAEnum(ServeSessionStatus, name="serve_session_status"), default=ServeSessionStatus.queued
    )
    original_r2_key: Mapped[str] = mapped_column(String(500))
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    # {code, message}. code: input_invalid | analyze_error
    failure_reason: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ServeAnalysis(Base):
    """解析結果のイミュータブルなスナップショット（EventStreamと同じ思想。02, 10）。"""

    __tablename__ = "serve_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    serve_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("serve_sessions.id", ondelete="CASCADE"), unique=True
    )
    # stage6_pose.analyze_serve() の出力（phases/metrics/feedback_metrics/confidence/citation_status）
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
