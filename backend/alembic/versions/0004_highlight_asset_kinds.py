"""highlight video asset kinds (Phase 1)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-11

"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE video_asset_kind ADD VALUE IF NOT EXISTS 'highlight'")
    op.execute("ALTER TYPE video_asset_kind ADD VALUE IF NOT EXISTS 'highlight_hls'")


def downgrade() -> None:
    # PostgreSQLはenum値の削除を直接サポートしない（ダウングレードは型再作成が必要なため省略）。
    pass
