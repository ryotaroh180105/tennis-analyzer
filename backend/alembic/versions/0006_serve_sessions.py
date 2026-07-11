"""serve_sessions / serve_analyses tables (Phase 3: 01-mvp-scope.md, 06-pro-reference-data.md)

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-11

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "serve_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("uploads.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column(
            "status",
            sa.Enum("queued", "analyzing", "done", "failed", name="serve_session_status"),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("original_r2_key", sa.String(500), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("failure_reason", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "serve_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "serve_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("serve_sessions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("serve_analyses")
    op.drop_table("serve_sessions")
    op.execute("DROP TYPE IF EXISTS serve_session_status")
