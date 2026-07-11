"""フォーム解析セッション（Phase 3拡張。12-form-analysis.md）。

試合（Match）とは別エンティティ：練習動画は編集・ハイライト・スコアを必要としない
単発の解析対象のため、Matchの4段ジョブパイプラインは流用しない。
serve_sessions/serve_analyses（Phase 3a）をショット全種対応に一般化したもの。
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class FormSessionStatus(str, enum.Enum):
    queued = "queued"
    analyzing = "analyzing"
    done = "done"
    failed = "failed"


class FormShotType(str, enum.Enum):
    """練習セッションの申告ショット種別（config/shot-mechanics.v1.yamlのshots.*キーと対応）。

    taxonomy.v1.yamlのshot_type軸（試合中のCV自動分類。volley_smashは統合値）とは
    別物（12-form-analysis.md §DB/API）。
    """

    serve = "serve"
    forehand = "forehand"
    backhand = "backhand"
    smash = "smash"
    volley = "volley"


class BackhandStyle(str, enum.Enum):
    one_handed = "one_handed"
    two_handed = "two_handed"
    auto = "auto"


class FormSession(Base):
    __tablename__ = "form_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    upload_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("uploads.id", ondelete="RESTRICT"), unique=True
    )
    title: Mapped[str] = mapped_column(String(200))
    shot_type: Mapped[FormShotType] = mapped_column(SAEnum(FormShotType, name="form_shot_type"))
    # backhandのみ意味を持つ。他ショットはnullable（12 §ハンドネス・スタイルの扱い）
    backhand_style: Mapped[BackhandStyle | None] = mapped_column(
        SAEnum(BackhandStyle, name="backhand_style"), nullable=True
    )
    status: Mapped[FormSessionStatus] = mapped_column(
        SAEnum(FormSessionStatus, name="form_session_status"), default=FormSessionStatus.queued
    )
    original_r2_key: Mapped[str] = mapped_column(String(500))
    # 抽出済みランドマーク系列のgzip JSON（S3中間出力。指標定義変更時の再計算に使う。不変原則3）
    landmarks_r2_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    # {code, message}. code: input_invalid | analyze_error
    failure_reason: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FormAnalysis(Base):
    """解析結果のイミュータブルなスナップショット（EventStreamと同じ思想。02, 10）。"""

    __tablename__ = "form_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    form_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("form_sessions.id", ondelete="CASCADE"), unique=True
    )
    # pose.orchestrator.analyze_landmarks() の出力（swings/metrics/feedback_metrics/
    # confidence/citation_status/insufficient_data。landmark_seriesは含まない）
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
