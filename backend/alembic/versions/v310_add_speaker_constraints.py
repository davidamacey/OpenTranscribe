"""Add speaker constraint tables for cannot-link and profile blacklist.

Revision ID: v310_add_speaker_constraints
Revises: v300_add_gender_confirmed
Create Date: 2026-03-08
"""

from alembic import op

revision = "v310_add_speaker_constraints"
down_revision = "v300_add_gender_confirmed"
branch_labels = None
depends_on = None


def upgrade():
    # speaker_cannot_link table
    op.execute("""
        CREATE TABLE IF NOT EXISTS speaker_cannot_link (
            id SERIAL PRIMARY KEY,
            speaker_id INTEGER NOT NULL REFERENCES speaker(id) ON DELETE CASCADE,
            cannot_link_speaker_id INTEGER NOT NULL REFERENCES speaker(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            reason VARCHAR(255),
            UNIQUE(speaker_id, cannot_link_speaker_id)
        );
    """)

    # speaker_profile_blacklist table
    op.execute("""
        CREATE TABLE IF NOT EXISTS speaker_profile_blacklist (
            id SERIAL PRIMARY KEY,
            speaker_id INTEGER NOT NULL REFERENCES speaker(id) ON DELETE CASCADE,
            profile_id INTEGER NOT NULL REFERENCES speaker_profile(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            reason VARCHAR(255),
            UNIQUE(speaker_id, profile_id)
        );
    """)

    # Add indexes for common query patterns
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_speaker_cannot_link_speaker
        ON speaker_cannot_link(speaker_id);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_speaker_cannot_link_target
        ON speaker_cannot_link(cannot_link_speaker_id);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_speaker_profile_blacklist_speaker
        ON speaker_profile_blacklist(speaker_id);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_speaker_profile_blacklist_profile
        ON speaker_profile_blacklist(profile_id);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS speaker_profile_blacklist")
    op.execute("DROP TABLE IF EXISTS speaker_cannot_link")
