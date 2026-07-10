"""self/opponent court side identification (Phase 1)

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-11

"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matches",
        sa.Column("self_side", sa.Enum("near", "far", name="self_side"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("matches", "self_side")
    op.execute("DROP TYPE IF EXISTS self_side")
