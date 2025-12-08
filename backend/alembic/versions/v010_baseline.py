"""v0.1.0 baseline - Full schema at release

Revision ID: v010_baseline
Revises:
Create Date: 2025-12-08

This migration represents the complete database schema at v0.1.0 release.
It is a baseline migration that creates all tables for fresh installations
or stamps existing databases that were created via init_db.sql.

For existing v0.1.0 databases:
    alembic stamp v010_baseline

For fresh installations:
    alembic upgrade head
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "v010_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create all tables for v0.1.0 schema."""
    # Enable UUID extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # Users table
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("role", sa.String(50), server_default="user"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_user_uuid", "user", ["uuid"])

    # Media files table
    op.create_table(
        "media_file",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column(
            "upload_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("is_public", sa.Boolean(), server_default="false"),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("summary_data", postgresql.JSONB(), nullable=True),
        sa.Column("summary_opensearch_id", sa.String(255), nullable=True),
        sa.Column("summary_status", sa.String(50), server_default="pending"),
        sa.Column("summary_schema_version", sa.Integer(), server_default="1"),
        sa.Column("translated_text", sa.Text(), nullable=True),
        sa.Column("file_hash", sa.String(255), nullable=True),
        sa.Column("thumbnail_path", sa.String(500), nullable=True),
        sa.Column("metadata_raw", postgresql.JSONB(), nullable=True),
        sa.Column("metadata_important", postgresql.JSONB(), nullable=True),
        sa.Column("waveform_data", postgresql.JSONB(), nullable=True),
        sa.Column("media_format", sa.String(50), nullable=True),
        sa.Column("codec", sa.String(50), nullable=True),
        sa.Column("frame_rate", sa.Float(), nullable=True),
        sa.Column("frame_count", sa.Integer(), nullable=True),
        sa.Column("resolution_width", sa.Integer(), nullable=True),
        sa.Column("resolution_height", sa.Integer(), nullable=True),
        sa.Column("aspect_ratio", sa.String(20), nullable=True),
        sa.Column("audio_channels", sa.Integer(), nullable=True),
        sa.Column("audio_sample_rate", sa.Integer(), nullable=True),
        sa.Column("audio_bit_depth", sa.Integer(), nullable=True),
        sa.Column("creation_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_modified_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("device_make", sa.String(100), nullable=True),
        sa.Column("device_model", sa.String(100), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(2048), nullable=True),
        sa.Column("active_task_id", sa.String(255), nullable=True),
        sa.Column("task_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_last_update", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_requested", sa.Boolean(), server_default="false"),
        sa.Column("retry_count", sa.Integer(), server_default="0"),
        sa.Column("max_retries", sa.Integer(), server_default="3"),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("force_delete_eligible", sa.Boolean(), server_default="false"),
        sa.Column("recovery_attempts", sa.Integer(), server_default="0"),
        sa.Column("last_recovery_attempt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_media_file_user_id", "media_file", ["user_id"])
    op.create_index("idx_media_file_status", "media_file", ["status"])
    op.create_index("idx_media_file_upload_time", "media_file", ["upload_time"])
    op.create_index("idx_media_file_hash", "media_file", ["file_hash"])
    op.create_index("idx_media_file_active_task_id", "media_file", ["active_task_id"])
    op.create_index("idx_media_file_task_last_update", "media_file", ["task_last_update"])
    op.create_index(
        "idx_media_file_force_delete_eligible", "media_file", ["force_delete_eligible"]
    )
    op.create_index("idx_media_file_retry_count", "media_file", ["retry_count"])
    op.create_index("idx_media_file_uuid", "media_file", ["uuid"])

    # Tag table
    op.create_table(
        "tag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_tag_uuid", "tag", ["uuid"])

    # FileTag join table
    op.create_table(
        "file_tag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("media_file_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["media_file_id"], ["media_file.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("media_file_id", "tag_id"),
        sa.UniqueConstraint("uuid"),
    )

    # Speaker profile table (global speaker identities)
    op.create_table(
        "speaker_profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("embedding_count", sa.Integer(), server_default="0"),
        sa.Column("last_embedding_update", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_speaker_profile_uuid", "speaker_profile", ["uuid"])
    op.create_index("idx_speaker_profile_user_id", "speaker_profile", ["user_id"])

    # Speaker table (speaker instances within specific media files)
    op.create_table(
        "speaker",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("media_file_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("suggested_name", sa.String(255), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("computed_status", sa.String(50), nullable=True),
        sa.Column("status_text", sa.String(500), nullable=True),
        sa.Column("status_color", sa.String(50), nullable=True),
        sa.Column("resolved_display_name", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["media_file_id"], ["media_file.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["speaker_profile.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "media_file_id", "name"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_speaker_uuid", "speaker", ["uuid"])
    op.create_index("idx_speaker_user_id", "speaker", ["user_id"])
    op.create_index("idx_speaker_media_file_id", "speaker", ["media_file_id"])
    op.create_index("idx_speaker_profile_id", "speaker", ["profile_id"])
    op.create_index("idx_speaker_verified", "speaker", ["verified"])

    # Speaker collection table
    op.create_table(
        "speaker_collection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_speaker_collection_uuid", "speaker_collection", ["uuid"])
    op.create_index("idx_speaker_collection_user_id", "speaker_collection", ["user_id"])

    # Speaker collection members join table
    op.create_table(
        "speaker_collection_member",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("speaker_profile_id", sa.Integer(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["speaker_collection.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["speaker_profile_id"], ["speaker_profile.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "speaker_profile_id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index(
        "idx_speaker_collection_member_collection_id",
        "speaker_collection_member",
        ["collection_id"],
    )
    op.create_index(
        "idx_speaker_collection_member_profile_id",
        "speaker_collection_member",
        ["speaker_profile_id"],
    )

    # Transcript segments table
    op.create_table(
        "transcript_segment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("media_file_id", sa.Integer(), nullable=False),
        sa.Column("speaker_id", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["media_file_id"], ["media_file.id"]),
        sa.ForeignKeyConstraint(["speaker_id"], ["speaker.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index(
        "idx_transcript_segment_media_file_id", "transcript_segment", ["media_file_id"]
    )
    op.create_index(
        "idx_transcript_segment_speaker_id", "transcript_segment", ["speaker_id"]
    )

    # Comments table
    op.create_table(
        "comment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("media_file_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["media_file_id"], ["media_file.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_comment_uuid", "comment", ["uuid"])

    # Tasks table
    op.create_table(
        "task",
        sa.Column("id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("media_file_id", sa.Integer(), nullable=True),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("progress", sa.Float(), server_default="0.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["media_file_id"], ["media_file.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_task_user_id", "task", ["user_id"])
    op.create_index("idx_task_status", "task", ["status"])
    op.create_index("idx_task_media_file_id", "task", ["media_file_id"])

    # Analytics table
    op.create_table(
        "analytics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("media_file_id", sa.Integer(), nullable=True),
        sa.Column("overall_analytics", postgresql.JSONB(), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("version", sa.String(50), nullable=True),
        sa.ForeignKeyConstraint(["media_file_id"], ["media_file.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("media_file_id"),
        sa.UniqueConstraint("uuid"),
    )

    # Collection table
    op.create_table(
        "collection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_collection_uuid", "collection", ["uuid"])
    op.create_index("idx_collection_user_id", "collection", ["user_id"])

    # Collection members join table
    op.create_table(
        "collection_member",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("media_file_id", sa.Integer(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["collection_id"], ["collection.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["media_file_id"], ["media_file.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "media_file_id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index(
        "idx_collection_member_collection_id", "collection_member", ["collection_id"]
    )
    op.create_index(
        "idx_collection_member_media_file_id", "collection_member", ["media_file_id"]
    )

    # Speaker match table
    op.create_table(
        "speaker_match",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("speaker1_id", sa.Integer(), nullable=False),
        sa.Column("speaker2_id", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["speaker1_id"], ["speaker.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["speaker2_id"], ["speaker.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("speaker1_id", "speaker2_id"),
        sa.UniqueConstraint("uuid"),
        sa.CheckConstraint("speaker1_id < speaker2_id"),
    )
    op.create_index("idx_speaker_match_speaker1", "speaker_match", ["speaker1_id"])
    op.create_index("idx_speaker_match_speaker2", "speaker_match", ["speaker2_id"])
    op.create_index("idx_speaker_match_confidence", "speaker_match", ["confidence"])

    # Topic suggestion table
    op.create_table(
        "topic_suggestion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("media_file_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "suggested_tags",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=True,
        ),
        sa.Column(
            "suggested_collections",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=True,
        ),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("user_decisions", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["media_file_id"], ["media_file.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("media_file_id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index(
        "idx_topic_suggestion_user_status", "topic_suggestion", ["user_id", "status"]
    )
    op.create_index(
        "idx_topic_suggestion_media_file", "topic_suggestion", ["media_file_id"]
    )

    # Summary prompt table
    op.create_table(
        "summary_prompt",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column(
            "is_system_default", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("content_type", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_summary_prompt_user_id", "summary_prompt", ["user_id"])
    op.create_index(
        "idx_summary_prompt_is_system_default", "summary_prompt", ["is_system_default"]
    )
    op.create_index("idx_summary_prompt_content_type", "summary_prompt", ["content_type"])
    op.create_index("idx_summary_prompt_uuid", "summary_prompt", ["uuid"])

    # Partial unique index for system prompts
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS unique_system_default_per_content_type
        ON summary_prompt(content_type)
        WHERE is_system_default = TRUE
        """
    )

    # User setting table
    op.create_table(
        "user_setting",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("setting_key", sa.String(100), nullable=False),
        sa.Column("setting_value", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "setting_key"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_user_setting_user_id", "user_setting", ["user_id"])
    op.create_index("idx_user_setting_key", "user_setting", ["setting_key"])

    # User LLM settings table
    op.create_table(
        "user_llm_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=False, server_default="8192"),
        sa.Column("temperature", sa.String(10), nullable=False, server_default="0.3"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_tested", sa.DateTime(timezone=True), nullable=True),
        sa.Column("test_status", sa.String(20), nullable=True),
        sa.Column("test_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name"),
        sa.UniqueConstraint("uuid"),
    )
    op.create_index("idx_user_llm_settings_user_id", "user_llm_settings", ["user_id"])
    op.create_index("idx_user_llm_settings_provider", "user_llm_settings", ["provider"])
    op.create_index("idx_user_llm_settings_active", "user_llm_settings", ["is_active"])
    op.create_index("idx_user_llm_settings_uuid", "user_llm_settings", ["uuid"])


def downgrade():
    """Drop all tables in reverse order of creation."""
    # Drop tables with foreign key dependencies first
    op.drop_table("user_llm_settings")
    op.drop_table("user_setting")
    op.execute("DROP INDEX IF EXISTS unique_system_default_per_content_type")
    op.drop_table("summary_prompt")
    op.drop_table("topic_suggestion")
    op.drop_table("speaker_match")
    op.drop_table("collection_member")
    op.drop_table("collection")
    op.drop_table("analytics")
    op.drop_table("task")
    op.drop_table("comment")
    op.drop_table("transcript_segment")
    op.drop_table("speaker_collection_member")
    op.drop_table("speaker_collection")
    op.drop_table("speaker")
    op.drop_table("speaker_profile")
    op.drop_table("file_tag")
    op.drop_table("tag")
    op.drop_table("media_file")
    op.drop_table("user")
