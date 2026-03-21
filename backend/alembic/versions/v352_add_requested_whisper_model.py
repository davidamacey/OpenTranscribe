"""Add requested_whisper_model column to media_file table.

Tracks the Whisper model the user requested at upload/reprocess time.
When it differs from the actual whisper_model column (written at task
completion), a model fallback occurred.

Revision ID: v352_add_requested_whisper_model
Revises: v351_add_ai_summary_settings
Create Date: 2026-03-20
"""

from alembic import op

revision = "v352_add_requested_whisper_model"
down_revision = "v351_add_ai_summary_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'media_file'
                  AND column_name = 'requested_whisper_model'
            ) THEN
                ALTER TABLE media_file
                ADD COLUMN requested_whisper_model VARCHAR;

                COMMENT ON COLUMN media_file.requested_whisper_model IS
                    'Whisper model requested by the user at upload/reprocess time. '
                    'May differ from whisper_model if a fallback occurred.';
            END IF;
        END $$;
    """)


def downgrade():
    op.execute("ALTER TABLE media_file DROP COLUMN IF EXISTS requested_whisper_model")
