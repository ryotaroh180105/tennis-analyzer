"""score events (Phase 1: semi-automatic score input)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-10

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "score_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("winner", sa.Enum("self", "opponent", name="score_point_winner"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("match_id", "sequence", name="uq_score_event_sequence"),
    )


def downgrade() -> None:
    op.drop_table("score_events")
    op.execute("DROP TYPE IF EXISTS score_point_winner")
