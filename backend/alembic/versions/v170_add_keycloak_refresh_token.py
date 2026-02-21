"""v0.17.0 - Add keycloak_refresh_token column for federated logout

Revision ID: v170_add_keycloak_refresh_token
Revises: v160_add_allow_local_fallback
Create Date: 2026-02-21

Stores the encrypted Keycloak refresh token on the user record so that
the backend can call Keycloak's logout endpoint when the user logs out
of OpenTranscribe, ensuring full federated session termination.

Without this, logging out of OpenTranscribe leaves the Keycloak session
active — meaning other apps in the same realm still see the user as
authenticated.

The token is encrypted at rest using the same Fernet/AES encryption
used for TOTP secrets (MFAService.encrypt_totp_secret).

GitHub issue: #125 (Gap 2: Federated Keycloak Logout)
"""

from alembic import op

revision = "v170_add_keycloak_refresh_token"
down_revision = "v160_add_allow_local_fallback"
branch_labels = None
depends_on = None


def upgrade():
    """Add keycloak_refresh_token column to user table."""
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'user' AND column_name = 'keycloak_refresh_token'
            ) THEN
                ALTER TABLE "user" ADD COLUMN keycloak_refresh_token TEXT;
            END IF;
        END $$;
        """
    )


def downgrade():
    """Remove keycloak_refresh_token column from user table."""
    op.execute('ALTER TABLE "user" DROP COLUMN IF EXISTS keycloak_refresh_token')
