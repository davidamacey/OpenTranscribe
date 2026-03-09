"""Add suggested_name column to speaker_cluster for title-based name extraction.

Revision ID: v320_add_cluster_suggested_name
Revises: v310_add_speaker_constraints
Create Date: 2026-03-08
"""

from alembic import op

revision = "v320_add_cluster_suggested_name"
down_revision = "v310_add_speaker_constraints"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'speaker_cluster' AND column_name = 'suggested_name'
            ) THEN
                ALTER TABLE speaker_cluster ADD COLUMN suggested_name VARCHAR(255);
            END IF;
        END $$;
    """)


def downgrade():
    op.execute("ALTER TABLE speaker_cluster DROP COLUMN IF EXISTS suggested_name")
