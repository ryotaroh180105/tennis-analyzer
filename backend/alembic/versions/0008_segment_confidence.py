"""segments.confidence for low-confidence ribbon visualization (13 B-2)

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-12

"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("segments", sa.Column("confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("segments", "confidence")
