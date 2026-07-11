"""serve_sessions/serve_analyses -> form_sessions/form_analyses + shot_type (Phase 3拡張: 12-form-analysis.md)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-11

"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("serve_sessions", "form_sessions")
    op.rename_table("serve_analyses", "form_analyses")

    op.execute("ALTER TYPE serve_session_status RENAME TO form_session_status")
    op.execute("ALTER INDEX serve_sessions_pkey RENAME TO form_sessions_pkey")
    op.execute("ALTER INDEX serve_sessions_upload_id_key RENAME TO form_sessions_upload_id_key")
    op.execute("ALTER TABLE form_sessions RENAME CONSTRAINT serve_sessions_upload_id_fkey TO form_sessions_upload_id_fkey")
    op.execute("ALTER TABLE form_sessions RENAME CONSTRAINT serve_sessions_user_id_fkey TO form_sessions_user_id_fkey")

    op.execute("ALTER INDEX serve_analyses_pkey RENAME TO form_analyses_pkey")
    op.execute("ALTER INDEX serve_analyses_serve_session_id_key RENAME TO form_analyses_form_session_id_key")
    op.execute(
        "ALTER TABLE form_analyses RENAME CONSTRAINT serve_analyses_serve_session_id_fkey TO form_analyses_form_session_id_fkey"
    )
    op.alter_column("form_analyses", "serve_session_id", new_column_name="form_session_id")

    form_shot_type = sa.Enum("serve", "forehand", "backhand", "smash", "volley", name="form_shot_type")
    form_shot_type.create(op.get_bind(), checkfirst=True)
    backhand_style = sa.Enum("one_handed", "two_handed", "auto", name="backhand_style")
    backhand_style.create(op.get_bind(), checkfirst=True)

    # 既存データ（Phase 3aのサーブ専用データ）は shot_type='serve' として移行する
    op.add_column(
        "form_sessions",
        sa.Column("shot_type", form_shot_type, nullable=False, server_default="serve"),
    )
    op.alter_column("form_sessions", "shot_type", server_default=None)
    op.add_column("form_sessions", sa.Column("backhand_style", backhand_style, nullable=True))
    op.add_column("form_sessions", sa.Column("landmarks_r2_key", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("form_sessions", "landmarks_r2_key")
    op.drop_column("form_sessions", "backhand_style")
    op.drop_column("form_sessions", "shot_type")
    op.execute("DROP TYPE IF EXISTS backhand_style")
    op.execute("DROP TYPE IF EXISTS form_shot_type")

    op.execute(
        "ALTER TABLE form_analyses RENAME CONSTRAINT form_analyses_form_session_id_fkey TO serve_analyses_serve_session_id_fkey"
    )
    op.execute("ALTER INDEX form_analyses_form_session_id_key RENAME TO serve_analyses_serve_session_id_key")
    op.execute("ALTER INDEX form_analyses_pkey RENAME TO serve_analyses_pkey")
    op.alter_column("form_analyses", "form_session_id", new_column_name="serve_session_id")

    op.execute("ALTER TABLE form_sessions RENAME CONSTRAINT form_sessions_user_id_fkey TO serve_sessions_user_id_fkey")
    op.execute("ALTER TABLE form_sessions RENAME CONSTRAINT form_sessions_upload_id_fkey TO serve_sessions_upload_id_fkey")
    op.execute("ALTER INDEX form_sessions_upload_id_key RENAME TO serve_sessions_upload_id_key")
    op.execute("ALTER INDEX form_sessions_pkey RENAME TO serve_sessions_pkey")
    op.execute("ALTER TYPE form_session_status RENAME TO serve_session_status")

    op.rename_table("form_analyses", "serve_analyses")
    op.rename_table("form_sessions", "serve_sessions")
