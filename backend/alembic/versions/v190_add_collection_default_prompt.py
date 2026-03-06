"""v0.19.0 - Add default_summary_prompt_id to collection table

Revision ID: v190_add_collection_default_prompt
Revises: v180_add_speaker_attributes
Create Date: 2026-02-26

Allows collections to have a default AI summarization prompt.
When a file in the collection is auto-summarized, it will use
the collection's default prompt instead of the user's active prompt.

ON DELETE SET NULL ensures graceful fallback if the prompt is deleted.

GitHub issue: #146
"""

from alembic import op

revision = "v190_add_collection_default_prompt"
down_revision = "v180_add_speaker_attributes"
branch_labels = None
depends_on = None


def upgrade():
    """Add default_summary_prompt_id FK column to collection table."""
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'collection'
                AND column_name = 'default_summary_prompt_id'
            ) THEN
                ALTER TABLE collection
                ADD COLUMN default_summary_prompt_id INTEGER
                REFERENCES summary_prompt(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )

    # Add index for faster joins
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = 'idx_collection_default_prompt_id'
            ) THEN
                CREATE INDEX idx_collection_default_prompt_id
                ON collection(default_summary_prompt_id);
            END IF;
        END $$;
        """
    )


def downgrade():
    """Remove default_summary_prompt_id column from collection table."""
    op.execute("DROP INDEX IF EXISTS idx_collection_default_prompt_id")
    op.execute("ALTER TABLE collection DROP COLUMN IF EXISTS default_summary_prompt_id")
