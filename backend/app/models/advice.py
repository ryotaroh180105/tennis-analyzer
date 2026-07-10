"""アドバイス配信履歴（07-advice-delivery.md §配信の3層設計）。

配信済みアドバイスを1テーブルに集約する：
- kind=immediate（①解析完了直後）は本タスクで発行。
- kind=weekly_digest（②週次）・kind=trigger（③トリガー型、trigger_idでcooldown判定）は
  週次ダイジェスト配信タスクが発行する。
metrics_snapshot は発行時点の compute_match_metrics() 出力で、
advice_engine.AdviceEvalContext.improved_since_last_advice() が前回配信時との比較に使う。
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AdviceDeliveryKind(str, enum.Enum):
    immediate = "immediate"
    weekly_digest = "weekly_digest"
    trigger = "trigger"


class AdviceDelivery(Base):
    __tablename__ = "advice_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # weekly_digestは特定試合に紐付かないためnullable
    match_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("matches.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[AdviceDeliveryKind] = mapped_column(SAEnum(AdviceDeliveryKind, name="advice_delivery_kind"))
    # kind=triggerのみ設定（advice-rules.v1.yamlのtrigger id。cooldown_days判定に使う）
    trigger_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content: Mapped[dict] = mapped_column(JSONB)
    metrics_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
