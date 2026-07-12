"""matches.stage_results_r2_key for stage-level analyze resumption (13 C-1)

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-12

"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("stage_results_r2_key", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "stage_results_r2_key")
