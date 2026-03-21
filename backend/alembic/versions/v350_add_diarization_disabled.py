"""Add diarization_disabled flag to media_file.

Revision ID: v350_add_diarization_disabled
Revises: v340_add_user_media_sources
Create Date: 2026-03-20
"""

from alembic import op

revision = "v350_add_diarization_disabled"
down_revision = "v340_add_user_media_sources"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'media_file'
                  AND column_name = 'diarization_disabled'
            ) THEN
                ALTER TABLE media_file
                    ADD COLUMN diarization_disabled BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
        END $$;
    """)


def downgrade():
    op.execute("ALTER TABLE media_file DROP COLUMN IF EXISTS diarization_disabled")
