"""Add unique constraint to transcript_segment to prevent duplicates

Revision ID: v071_add_transcript_segment_unique_constraint
Revises: v130_add_processing_model_tracking
Create Date: 2026-02-11
"""

from alembic import op

revision = "v071_add_transcript_segment_unique_constraint"
down_revision = "v130_add_processing_model_tracking"


def upgrade():
    """Add unique constraint to prevent duplicate transcript segments."""
    # Use idempotent SQL to add constraint only if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            -- Check if constraint exists
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_transcript_segment_content'
            ) THEN
                -- Create unique constraint on (media_file_id, start_time, end_time, text)
                -- This prevents the same segment from being inserted twice
                ALTER TABLE transcript_segment
                ADD CONSTRAINT uq_transcript_segment_content
                UNIQUE (media_file_id, start_time, end_time, text);

                RAISE NOTICE 'Added unique constraint uq_transcript_segment_content';
            ELSE
                RAISE NOTICE 'Constraint uq_transcript_segment_content already exists, skipping';
            END IF;
        END $$;
    """)


def downgrade():
    """Remove unique constraint."""
    op.execute("""
        ALTER TABLE transcript_segment
        DROP CONSTRAINT IF EXISTS uq_transcript_segment_content;
    """)
