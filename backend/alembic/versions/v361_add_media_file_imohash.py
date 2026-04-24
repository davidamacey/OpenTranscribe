"""Add imohash column to media_file for server-side fingerprinting.

Phase 2 PR #2 of the timing audit plan. Complements the existing
``file_hash`` (client-computed SHA-256) with a constant-time fingerprint
computed on the backend from three ranged MinIO reads. Used for:

- Server-side duplicate detection when client hash is missing
- Artifact cache key (preprocessed WAV, waveform, thumbnail)
- Reprocess short-circuit for re-ingested files

Not security-critical — imohash samples the file, it is not
collision-resistant against adversaries. Security-sensitive dedup still
uses ``file_hash``.

Revision ID: v361_add_media_file_imohash
Revises: v360_add_file_pipeline_timing
Create Date: 2026-04-24
"""

from alembic import op

revision = "v361_add_media_file_imohash"
down_revision = "v360_add_file_pipeline_timing"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'media_file' AND column_name = 'imohash'
            ) THEN
                ALTER TABLE media_file ADD COLUMN imohash VARCHAR(64);
            END IF;
        END $$;
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_media_file_imohash ON media_file(imohash)")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_media_file_imohash")
    op.execute("ALTER TABLE media_file DROP COLUMN IF EXISTS imohash")
