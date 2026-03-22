"""Fix transcript_segment unique index for large text segments.

The original btree index on (media_file_id, start_time, end_time, text)
fails when text exceeds btree's 2704 byte limit (~900 chars). This happens
with long continuous speech segments (e.g., 7+ minute monologues).

Replace with a functional index using md5(text) which is always 32 bytes.

Revision ID: v353_fix_segment_unique_index
Revises: v352_add_requested_whisper_model
Create Date: 2026-03-22
"""

from alembic import op

revision = "v353_fix_segment_unique_index"
down_revision = "v352_add_requested_whisper_model"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DO $$
        BEGIN
            -- Drop as constraint if it exists (created via UniqueConstraint)
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_transcript_segment_content'
            ) THEN
                ALTER TABLE transcript_segment
                    DROP CONSTRAINT uq_transcript_segment_content;
            END IF;

            -- Drop as plain index if it exists (may have been manually fixed)
            DROP INDEX IF EXISTS uq_transcript_segment_content;

            -- Create functional index with md5 hash of text (always 32 bytes)
            CREATE UNIQUE INDEX uq_transcript_segment_content
                ON transcript_segment (media_file_id, start_time, end_time, md5(text));
        END $$;
    """)


def downgrade():
    op.execute("""
        DROP INDEX IF EXISTS uq_transcript_segment_content;
        ALTER TABLE transcript_segment
            ADD CONSTRAINT uq_transcript_segment_content
            UNIQUE (media_file_id, start_time, end_time, text);
    """)
