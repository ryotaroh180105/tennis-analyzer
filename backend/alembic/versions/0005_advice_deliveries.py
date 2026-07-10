"""advice_deliveries table (Phase 1: 07-advice-delivery.md)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-10

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "advice_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=True),
        sa.Column(
            "kind",
            sa.Enum("immediate", "weekly_digest", "trigger", name="advice_delivery_kind"),
            nullable=False,
        ),
        sa.Column("trigger_id", sa.String(100), nullable=True),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("metrics_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_advice_deliveries_user_created", "advice_deliveries", ["user_id", "created_at"])
    op.create_index("ix_advice_deliveries_match", "advice_deliveries", ["match_id"])


def downgrade() -> None:
    op.drop_index("ix_advice_deliveries_match", table_name="advice_deliveries")
    op.drop_index("ix_advice_deliveries_user_created", table_name="advice_deliveries")
    op.drop_table("advice_deliveries")
    op.execute("DROP TYPE IF EXISTS advice_delivery_kind")
