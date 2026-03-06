"""v1.1.0 - Add missing FK indexes for comment and transcript_segment

Revision ID: v110_add_missing_fk_indexes
Revises: v100_optimize_query_performance
Create Date: 2026-02-09

Adds indexes on frequently-queried foreign key columns that PostgreSQL
does not create automatically:

1. comment(media_file_id) - comment retrieval per file
2. comment(user_id) - comment permission checks
3. transcript_segment(media_file_id, start_time) - ordered segment retrieval
   (replaces individual media_file_id index for this common access pattern)
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "v110_add_missing_fk_indexes"
down_revision = "v100_optimize_query_performance"
branch_labels = None
depends_on = None


def upgrade():
    """Add missing FK indexes."""
    # 1. Comment media_file_id: every comment retrieval filters by file
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'idx_comment_media_file_id'
            ) THEN
                CREATE INDEX idx_comment_media_file_id
                ON comment(media_file_id);
            END IF;
        END $$;
        """
    )

    # 2. Comment user_id: permission checks filter by user
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'idx_comment_user_id'
            ) THEN
                CREATE INDEX idx_comment_user_id
                ON comment(user_id);
            END IF;
        END $$;
        """
    )

    # 3. Transcript segment compound index: (media_file_id, start_time)
    # Covers the most common access pattern: fetch segments for a file
    # ordered by start_time. The existing single-column index on
    # media_file_id still works for COUNT-only queries.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'idx_transcript_segment_media_start'
            ) THEN
                CREATE INDEX idx_transcript_segment_media_start
                ON transcript_segment(media_file_id, start_time);
            END IF;
        END $$;
        """
    )


def downgrade():
    """Remove indexes. Safe — no data loss."""
    op.execute("DROP INDEX IF EXISTS idx_comment_media_file_id;")
    op.execute("DROP INDEX IF EXISTS idx_comment_user_id;")
    op.execute("DROP INDEX IF EXISTS idx_transcript_segment_media_start;")
