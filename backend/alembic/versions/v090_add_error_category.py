"""v0.9.0 - Add error_category column to media_file table

Revision ID: v090_add_error_category
Revises: v080_add_auth_config
Create Date: 2026-02-08

Add error_category column to track classified error types for smart retry
decisions and analytics. Enables filtering files by error type (permanent,
retriable, OOM, network, etc.).
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "v090_add_error_category"
down_revision = "v080_add_auth_config"
branch_labels = None
depends_on = None


def upgrade():
    """Add error_category column and index to media_file table."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'media_file' AND column_name = 'error_category'
            ) THEN
                ALTER TABLE media_file ADD COLUMN error_category VARCHAR(50);
                CREATE INDEX IF NOT EXISTS idx_media_file_error_category
                    ON media_file(error_category) WHERE error_category IS NOT NULL;
            END IF;
        END $$;
        """
    )


def downgrade():
    """Remove error_category column from media_file table."""
    op.execute("DROP INDEX IF EXISTS idx_media_file_error_category")
    op.execute("ALTER TABLE media_file DROP COLUMN IF EXISTS error_category")
