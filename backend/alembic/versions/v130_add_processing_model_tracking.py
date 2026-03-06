"""Add processing model tracking columns to media_file.

Revision ID: v130_add_processing_model_tracking
Revises: v120_add_remaining_fk_indexes
Create Date: 2026-02-10
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "v130_add_processing_model_tracking"
down_revision = "v120_add_remaining_fk_indexes"
branch_labels = None
depends_on = None


def upgrade():
    """Add whisper_model, diarization_model, and embedding_mode columns."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'media_file' AND column_name = 'whisper_model'
            ) THEN
                ALTER TABLE media_file ADD COLUMN whisper_model VARCHAR;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'media_file' AND column_name = 'diarization_model'
            ) THEN
                ALTER TABLE media_file ADD COLUMN diarization_model VARCHAR;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'media_file' AND column_name = 'embedding_mode'
            ) THEN
                ALTER TABLE media_file ADD COLUMN embedding_mode VARCHAR;
            END IF;
        END $$;
    """
    )


def downgrade():
    """Remove processing model tracking columns."""
    op.execute("ALTER TABLE media_file DROP COLUMN IF EXISTS whisper_model")
    op.execute("ALTER TABLE media_file DROP COLUMN IF EXISTS diarization_model")
    op.execute("ALTER TABLE media_file DROP COLUMN IF EXISTS embedding_mode")
