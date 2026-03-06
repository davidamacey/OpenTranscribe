"""Add avatar_path column to speaker_profile table.

Revision ID: v270_add_profile_avatar
Revises: v260_add_cluster_quality_metrics
Create Date: 2026-03-05

Adds:
- speaker_profile.avatar_path (VARCHAR 512) — MinIO object path for profile avatar
"""

from alembic import op

revision = "v270_add_profile_avatar"
down_revision = "v260_add_cluster_quality_metrics"
branch_labels = None
depends_on = None


def upgrade():
    """Add avatar_path column to speaker_profile."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'speaker_profile' AND column_name = 'avatar_path'
            ) THEN
                ALTER TABLE speaker_profile ADD COLUMN avatar_path VARCHAR(512);
            END IF;
        END $$;
        """
    )


def downgrade():
    """Remove avatar_path column."""
    op.execute("ALTER TABLE speaker_profile DROP COLUMN IF EXISTS avatar_path")
