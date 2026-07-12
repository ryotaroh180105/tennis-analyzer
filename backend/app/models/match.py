import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class MatchStatus(str, enum.Enum):
    queued = "queued"
    prechecking = "prechecking"
    ingesting = "ingesting"
    analyzing = "analyzing"
    editing = "editing"
    done = "done"
    failed = "failed"


# stage → matches.status の対応（10 §matches.status コメント）
STAGE_TO_STATUS = {
    "precheck": MatchStatus.prechecking,
    "ingest": MatchStatus.ingesting,
    "analyze": MatchStatus.analyzing,
    "edit": MatchStatus.editing,
}


class SelfSide(str, enum.Enum):
    """コートサイドでの自分/相手識別（01 §Phase1: ユーザーが初回指定）。

    court-spec.v1.yaml の baseline_near/baseline_far と対応させる
    （near=カメラに近い側、far=奥側）。CVのショット帰属（stage5）はこの値を参照する。
    """

    near = "near"
    far = "far"


class VideoAssetKind(str, enum.Enum):
    original = "original"
    normalized = "normalized"
    edited = "edited"
    hls = "hls"
    thumbnail = "thumbnail"
    highlight = "highlight"
    highlight_hls = "highlight_hls"


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    upload_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("uploads.id", ondelete="RESTRICT"), unique=True
    )
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[MatchStatus] = mapped_column(
        SAEnum(MatchStatus, name="match_status"), default=MatchStatus.queued
    )
    # {code, message} — code: input_invalid | analyze_error | edit_error | retry_exhausted
    # court_not_detected は使わない（縮退モードで続行するため）
    failure_reason: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    preflight_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    self_side: Mapped[SelfSide | None] = mapped_column(
        SAEnum(SelfSide, name="self_side"), nullable=True
    )
    # stage1-3（コート検出・選手・ボール追跡、重い部分）の出力をgzip JSONでR2に保存した
    # キー。analyzeジョブのリトライ・再開時にこれが設定済みなら、動画再ダウンロードと
    # stage1-3の再実行をスキップしてstage4-5のみ再実行する（不変原則3、13 C-1）。
    stage_results_r2_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video_assets: Mapped[list["VideoAsset"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )
    event_streams: Mapped[list["EventStream"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )


class VideoAsset(Base):
    __tablename__ = "video_assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    kind: Mapped[VideoAssetKind] = mapped_column(SAEnum(VideoAssetKind, name="video_asset_kind"))
    # 現行版 = kindごとの最大generation。旧世代は新世代の生成成功後に削除（10）
    generation: Mapped[int] = mapped_column(Integer, default=0)
    r2_key: Mapped[str] = mapped_column(String(500))
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    match: Mapped["Match"] = relationship(back_populates="video_assets")


class EventStream(Base):
    """CV出力のイミュータブルなスナップショット。作成後は更新しない（02, 10）。"""

    __tablename__ = "event_streams"
    __table_args__ = (UniqueConstraint("match_id", "version", name="uq_event_stream_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    match: Mapped["Match"] = relationship(back_populates="event_streams")
