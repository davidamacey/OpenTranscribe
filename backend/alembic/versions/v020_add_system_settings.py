"""v0.2.0 - Add system_settings table

Revision ID: v020_add_system_settings
Revises: v010_baseline
Create Date: 2025-12-08

Adds the system_settings table for global configuration management.
This enables runtime-adjustable settings for transcription processing,
including retry limits and garbage word cleanup thresholds.

New table: system_settings
    - id: Primary key
    - key: Unique setting identifier (e.g., 'transcription.max_retries')
    - value: Setting value as text
    - description: Human-readable description
    - updated_at: Timestamp of last update

Default settings seeded:
    - transcription.max_retries: 3
    - transcription.retry_limit_enabled: true
    - transcription.garbage_cleanup_enabled: true
    - transcription.max_word_length: 50
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "v020_add_system_settings"
down_revision = "v010_baseline"
branch_labels = None
depends_on = None


def upgrade():
    """Add system_settings table and seed default values."""
    # Check if table already exists (defensive - handles edge cases)
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_name='system_settings')"
        )
    )
    table_exists = result.scalar()

    if not table_exists:
        # Create system_settings table
        op.create_table(
            "system_settings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(100), nullable=False),
            sa.Column("value", sa.Text(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("key"),
        )

        # Create index for fast key lookups
        op.create_index("idx_system_settings_key", "system_settings", ["key"])

    # Seed default system settings (idempotent - safe to run multiple times)
    op.execute(
        """
        INSERT INTO system_settings (key, value, description) VALUES
            ('transcription.max_retries', '3',
             'Maximum number of retry attempts for failed transcriptions (0 = unlimited)'),
            ('transcription.retry_limit_enabled', 'true',
             'Whether to enforce retry limits on transcription processing'),
            ('transcription.garbage_cleanup_enabled', 'true',
             'Whether to clean up garbage words (very long words with no spaces) during transcription'),
            ('transcription.max_word_length', '50',
             'Maximum word length threshold for garbage detection (words longer than this with no spaces are replaced)')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade():
    """Remove system_settings table."""
    # Check if table exists before dropping (defensive)
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_name='system_settings')"
        )
    )
    if result.scalar():
        op.drop_index("idx_system_settings_key", table_name="system_settings")
        op.drop_table("system_settings")
