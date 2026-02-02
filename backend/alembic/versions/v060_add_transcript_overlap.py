"""v0.6.0 - Add transcript overlap support for PyAnnote v4

Revision ID: v060_add_transcript_overlap
Revises: v050_add_search_settings
Create Date: 2026-02-02

Adds support for overlapping speech detection and separation (Issue #59).
PyAnnote v4 provides exclusive_speaker_diarization output which identifies
when multiple speakers talk simultaneously.

Schema changes:
    - transcript_segment.is_overlap: Boolean flag for segments from overlapped speech
    - transcript_segment.overlap_group_id: UUID to group segments from same overlap
    - transcript_segment.overlap_confidence: Confidence score for overlap detection

This enables the frontend to display overlapping segments with special indicators
and allows users to see all speakers who spoke at the same time.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "v060_add_transcript_overlap"
down_revision = "v050_add_search_settings"
branch_labels = None
depends_on = None


def upgrade():
    """Add overlap columns to transcript_segment table."""
    # Add is_overlap column with default value (idempotent check)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'transcript_segment' AND column_name = 'is_overlap'
            ) THEN
                ALTER TABLE transcript_segment
                ADD COLUMN is_overlap BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
        END $$;
        """
    )

    # Add overlap_group_id column
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'transcript_segment' AND column_name = 'overlap_group_id'
            ) THEN
                ALTER TABLE transcript_segment
                ADD COLUMN overlap_group_id UUID NULL;
            END IF;
        END $$;
        """
    )

    # Add overlap_confidence column
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'transcript_segment' AND column_name = 'overlap_confidence'
            ) THEN
                ALTER TABLE transcript_segment
                ADD COLUMN overlap_confidence FLOAT NULL;
            END IF;
        END $$;
        """
    )

    # Add index on overlap_group_id for efficient grouping (partial index)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'idx_transcript_segment_overlap_group'
            ) THEN
                CREATE INDEX idx_transcript_segment_overlap_group
                ON transcript_segment(overlap_group_id)
                WHERE overlap_group_id IS NOT NULL;
            END IF;
        END $$;
        """
    )


def downgrade():
    """Remove overlap columns from transcript_segment table."""
    op.execute("DROP INDEX IF EXISTS idx_transcript_segment_overlap_group")
    op.drop_column("transcript_segment", "overlap_confidence")
    op.drop_column("transcript_segment", "overlap_group_id")
    op.drop_column("transcript_segment", "is_overlap")
