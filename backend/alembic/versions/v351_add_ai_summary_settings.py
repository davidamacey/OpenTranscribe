"""Add AI summary enabled system setting.

Revision ID: v351_add_ai_summary_settings
Revises: v350_add_diarization_disabled
Create Date: 2026-03-20

Seeds the system-wide default (true = enabled, matches current behavior).
No schema changes needed — both user_setting and system_settings are
key-value stores, and the new 'disabled' summary_status is just a
string stored in an existing VARCHAR column.
"""

from alembic import op

revision = "v351_add_ai_summary_settings"
down_revision = "v350_add_diarization_disabled"
branch_labels = None
depends_on = None


def upgrade():
    """Seed the system-wide AI summary enabled setting."""
    op.execute("""
        INSERT INTO system_settings (key, value, description)
        VALUES (
            'ai.summary_enabled',
            'true',
            'Global toggle for AI summary generation. '
            'Set to false to disable for all users.'
        )
        ON CONFLICT (key) DO NOTHING;
    """)


def downgrade():
    """Remove the AI summary enabled system setting."""
    op.execute("DELETE FROM system_settings WHERE key = 'ai.summary_enabled'")
