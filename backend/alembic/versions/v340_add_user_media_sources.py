"""Add per-user media sources table with sharing support.

Revision ID: v340_add_user_media_sources
Revises: v330_add_shared_configs_and_prompts
Create Date: 2026-03-14
"""

from alembic import op

revision = "v340_add_user_media_sources"
down_revision = "v330_add_shared_configs_and_prompts"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_media_source (
            id SERIAL PRIMARY KEY,
            uuid UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
            user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            hostname VARCHAR(255) NOT NULL,
            provider_type VARCHAR(50) NOT NULL DEFAULT 'mediacms',
            username TEXT,
            password TEXT,
            verify_ssl BOOLEAN NOT NULL DEFAULT TRUE,
            label VARCHAR(200),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            is_shared BOOLEAN NOT NULL DEFAULT FALSE,
            shared_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            CONSTRAINT _user_media_source_host_unique UNIQUE (user_id, hostname)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_user_media_source_uuid
            ON user_media_source(uuid)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_user_media_source_user
            ON user_media_source(user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_user_media_source_shared
            ON user_media_source(is_shared) WHERE is_shared = TRUE
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_user_media_source_shared")
    op.execute("DROP INDEX IF EXISTS ix_user_media_source_user")
    op.execute("DROP INDEX IF EXISTS ix_user_media_source_uuid")
    op.execute("DROP TABLE IF EXISTS user_media_source")
