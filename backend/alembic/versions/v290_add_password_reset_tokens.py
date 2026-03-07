"""v0.29.0 - Add password_reset_token table for self-service password recovery

Revision ID: v290_add_password_reset_tokens
Revises: v280_add_upload_sessions
Create Date: 2026-03-06

Adds the password_reset_token table to support forgot-password flows.
Tokens are stored as SHA-256 hashes with expiration and one-time use.
"""

from alembic import op

revision = "v290_add_password_reset_tokens"
down_revision = "v280_add_upload_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_token (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ip_address VARCHAR(45)
        );
        CREATE INDEX IF NOT EXISTS ix_password_reset_token_token_hash
            ON password_reset_token(token_hash);
        CREATE INDEX IF NOT EXISTS ix_password_reset_token_user_id
            ON password_reset_token(user_id);
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS password_reset_token")
