"""v0.9.1 - Add suggestion_source column to speaker table

Revision ID: v091_add_speaker_suggestion_source
Revises: v090_add_error_category
Create Date: 2026-02-09

Add suggestion_source column to distinguish between different types of speaker
name suggestions: "llm_analysis" (from transcript context), "voice_match"
(from voice embedding similarity), and "profile_match" (from speaker profiles).
This fixes the broken speaker identification feature where LLM suggestions
were being incorrectly skipped due to ambiguity.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "v091_add_speaker_suggestion_source"
down_revision = "v090_add_error_category"
branch_labels = None
depends_on = None


def upgrade():
    """Add suggestion_source column to speaker table."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'speaker' AND column_name = 'suggestion_source'
            ) THEN
                ALTER TABLE speaker ADD COLUMN suggestion_source VARCHAR(50);
                COMMENT ON COLUMN speaker.suggestion_source IS
                    'Source of suggestion: llm_analysis, voice_match, or profile_match';
            END IF;
        END $$;
        """
    )


def downgrade():
    """Remove suggestion_source column from speaker table."""
    op.execute("ALTER TABLE speaker DROP COLUMN IF EXISTS suggestion_source")
