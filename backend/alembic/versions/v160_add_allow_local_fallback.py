"""v0.16.0 - Add allow_local_fallback column for super admin hybrid auth

Revision ID: v160_add_allow_local_fallback
Revises: v150_add_file_retention_settings
Create Date: 2026-02-21

Adds allow_local_fallback BOOLEAN column to user table.
When True, the user can authenticate via username+password even if
auth_type is not 'local' (e.g., PKI or Keycloak users).

This enables super admin emergency access when external auth
providers (PKI, Keycloak) are unavailable.

DEFAULT FALSE means zero behavior change for all existing users.

GitHub issue: #127
"""

from alembic import op

revision = "v160_add_allow_local_fallback"
down_revision = "v150_add_file_retention_settings"
branch_labels = None
depends_on = None


def upgrade():
    """Add allow_local_fallback column to user table."""
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'user' AND column_name = 'allow_local_fallback'
            ) THEN
                ALTER TABLE "user" ADD COLUMN allow_local_fallback BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
        END $$;
        """
    )


def downgrade():
    """Remove allow_local_fallback column from user table."""
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS allow_local_fallback')
