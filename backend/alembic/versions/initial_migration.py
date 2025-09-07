"""initial migration

Revision ID: 001
Revises:
Create Date: 2025-05-04 19:55:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create user table
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, default=False),
        sa.Column("role", sa.String(), nullable=False, default="user"),
        sa.Column("created_at", sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )

    # Create speaker table
    op.create_table(
        "speaker",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create media_file table
    op.create_table(
        "media_file",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("file_type", sa.String(), nullable=False),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("upload_time", sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column(
            "last_updated",
            sa.DateTime(),
            nullable=False,
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create transcript_segment table
    op.create_table(
        "transcript_segment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("media_file_id", sa.Integer(), nullable=False),
        sa.Column("speaker_id", sa.Integer(), nullable=True),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["media_file_id"], ["media_file.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["speaker_id"],
            ["speaker.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create tag table
    op.create_table(
        "tag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Create file_tag junction table
    op.create_table(
        "file_tag",
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.ForeignKeyConstraint(["file_id"], ["media_file.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("file_id", "tag_id"),
    )

    # Create comment table
    op.create_table(
        "comment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["file_id"], ["media_file.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create task table
    op.create_table(
        "task",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=True),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["media_file.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create analytics table
    op.create_table(
        "analytics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("talk_time", sa.JSON(), nullable=True),
        sa.Column("interruptions", sa.JSON(), nullable=True),
        sa.Column("turn_taking", sa.JSON(), nullable=True),
        sa.Column("questions", sa.JSON(), nullable=True),
        sa.Column("keywords", sa.JSON(), nullable=True),
        sa.Column("sentiment", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["file_id"], ["media_file.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("ix_user_email", "user", ["email"], unique=True)
    op.create_index("ix_media_file_user_id", "media_file", ["user_id"], unique=False)
    op.create_index(
        "ix_transcript_segment_media_file_id",
        "transcript_segment",
        ["media_file_id"],
        unique=False,
    )
    op.create_index(
        "ix_transcript_segment_speaker_id",
        "transcript_segment",
        ["speaker_id"],
        unique=False,
    )
    op.create_index("ix_comment_file_id", "comment", ["file_id"], unique=False)
    op.create_index("ix_task_user_id", "task", ["user_id"], unique=False)
    op.create_index("ix_task_file_id", "task", ["file_id"], unique=False)
    op.create_index("ix_analytics_file_id", "analytics", ["file_id"], unique=True)


def downgrade():
    op.drop_index("ix_analytics_file_id", table_name="analytics")
    op.drop_index("ix_task_file_id", table_name="task")
    op.drop_index("ix_task_user_id", table_name="task")
    op.drop_index("ix_comment_file_id", table_name="comment")
    op.drop_index("ix_transcript_segment_speaker_id", table_name="transcript_segment")
    op.drop_index(
        "ix_transcript_segment_media_file_id", table_name="transcript_segment"
    )
    op.drop_index("ix_media_file_user_id", table_name="media_file")
    op.drop_index("ix_user_email", table_name="user")

    op.drop_table("analytics")
    op.drop_table("task")
    op.drop_table("comment")
    op.drop_table("file_tag")
    op.drop_table("tag")
    op.drop_table("transcript_segment")
    op.drop_table("media_file")
    op.drop_table("speaker")
    op.drop_table("user")
