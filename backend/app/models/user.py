import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str] = mapped_column(String(120))
    # NULL可：devユーザー・メール取得前状態（10 §DBスキーマ）
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # i18nの配線。既定'ja'（10 §users.locale、設計方針7）
    locale: Mapped[str] = mapped_column(String(10), default="ja", server_default="ja")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    auth_providers: Mapped[list["AuthProvider"]] = relationship(back_populates="user")


class AuthProvider(Base):
    """LINEをusersに直接持たせない — 海外展開時のチャネル差し替えをスキーマ変更なしにする（10）。"""

    __tablename__ = "auth_providers"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id", name="uq_auth_provider_identity"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(20))  # line | email_magic | dev
    provider_user_id: Mapped[str] = mapped_column(String(200))
    # 友だち判定はfollow/unfollow webhookで更新（10: profile APIプローブはしない）
    line_friend: Mapped[bool | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="auth_providers")
