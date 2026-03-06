"""Add words JSONB column to transcript_segment for word-level timestamps.

Revision ID: v140_add_word_timestamps
Revises: v073_convert_filestatus_enum_to_varchar
Create Date: 2026-02-16
"""

from alembic import op

revision = "v140_add_word_timestamps"
down_revision = "v073_convert_filestatus_enum_to_varchar"


def upgrade():
    """Add words JSONB column for word-level timestamps from faster-whisper."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'transcript_segment' AND column_name = 'words'
            ) THEN
                ALTER TABLE transcript_segment ADD COLUMN words JSONB NULL;
            END IF;
        END $$;
    """
    )


def downgrade():
    """Remove words column."""
    op.execute("ALTER TABLE transcript_segment DROP COLUMN IF EXISTS words")
