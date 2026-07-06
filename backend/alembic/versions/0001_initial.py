"""initial schema (Phase 0)

Revision ID: 0001
Revises:
Create Date: 2026-07-06

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("locale", sa.String(10), nullable=False, server_default="ja"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "auth_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_user_id", sa.String(200), nullable=False),
        sa.Column("line_friend", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_auth_provider_identity"),
    )

    op.create_table(
        "uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("r2_key", sa.String(500), nullable=False),
        sa.Column("r2_upload_id", sa.String(500), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column(
            "status",
            sa.Enum("in_progress", "completed", "aborted", "expired", name="upload_status"),
            nullable=False,
            server_default="in_progress",
        ),
        sa.Column("total_size", sa.BigInteger(), nullable=False),
        sa.Column("used_by_match", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("uploads.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued", "prechecking", "ingesting", "analyzing", "editing", "done", "failed",
                name="match_status",
            ),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("failure_reason", postgresql.JSONB(), nullable=True),
        sa.Column("preflight_report", postgresql.JSONB(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "video_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("original", "normalized", "edited", "hls", "thumbnail", name="video_asset_kind"),
            nullable=False,
        ),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("r2_key", sa.String(500), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_video_assets_match_kind", "video_assets", ["match_id", "kind", "generation"])

    op.create_table(
        "event_streams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("match_id", "version", name="uq_event_stream_version"),
    )

    op.create_table(
        "analysis_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.Enum("precheck", "ingest", "analyze", "edit", name="job_stage"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "succeeded", "failed", name="job_status"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(2000), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("match_id", "stage", "attempt", name="uq_job_attempt"),
    )

    op.create_table(
        "segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("op", sa.Enum("add", "remove", "adjust", name="segment_op"), nullable=False),
        sa.Column("base_segment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("segments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("start_s", sa.Float(), nullable=True),
        sa.Column("end_s", sa.Float(), nullable=True),
        sa.Column("source", sa.Enum("auto", "user", name="segment_source"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_segments_match_revision", "segments", ["match_id", "revision"])

    op.create_table(
        "share_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("share_links")
    op.drop_index("ix_segments_match_revision", table_name="segments")
    op.drop_table("segments")
    op.drop_table("analysis_jobs")
    op.drop_table("event_streams")
    op.drop_index("ix_video_assets_match_kind", table_name="video_assets")
    op.drop_table("video_assets")
    op.drop_table("matches")
    op.drop_table("uploads")
    op.drop_table("auth_providers")
    op.drop_table("users")
    for enum_name in (
        "upload_status", "match_status", "video_asset_kind", "job_stage",
        "job_status", "segment_op", "segment_source",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
