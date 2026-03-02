"""Add user groups and collection sharing tables.

Creates tables for user groups, group membership, and collection sharing
to support collaborative access to collections.

Revision ID: v210_add_groups_and_sharing
Revises: v200_schema_reconciliation
Create Date: 2026-03-01
"""

from alembic import op

revision = "v210_add_groups_and_sharing"
down_revision = "v200_schema_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create user_group, user_group_member, and collection_share tables."""

    # =========================================================================
    # 1. Create user_group table
    # =========================================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_group (
            id SERIAL PRIMARY KEY,
            uuid UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            owner_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Indexes for user_group
    op.execute("""CREATE INDEX IF NOT EXISTS ix_user_group_id ON user_group(id)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_user_group_uuid ON user_group(uuid)""")
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint
                           WHERE conname = '_user_group_owner_name_uc') THEN
                ALTER TABLE user_group
                    ADD CONSTRAINT _user_group_owner_name_uc UNIQUE (owner_id, name);
            END IF;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # =========================================================================
    # 2. Create user_group_member table
    # =========================================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_group_member (
            id SERIAL PRIMARY KEY,
            uuid UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
            group_id INTEGER NOT NULL REFERENCES user_group(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL DEFAULT 'member',
            joined_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Indexes for user_group_member
    op.execute("""CREATE INDEX IF NOT EXISTS ix_user_group_member_id ON user_group_member(id)""")
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_user_group_member_uuid ON user_group_member(uuid)"""
    )
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint
                           WHERE conname = '_group_member_uc') THEN
                ALTER TABLE user_group_member
                    ADD CONSTRAINT _group_member_uc UNIQUE (group_id, user_id);
            END IF;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # =========================================================================
    # 3. Create collection_share table
    # =========================================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS collection_share (
            id SERIAL PRIMARY KEY,
            uuid UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
            collection_id INTEGER NOT NULL REFERENCES collection(id) ON DELETE CASCADE,
            shared_by_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            target_type VARCHAR(20) NOT NULL,
            target_user_id INTEGER REFERENCES "user"(id) ON DELETE CASCADE,
            target_group_id INTEGER REFERENCES user_group(id) ON DELETE CASCADE,
            permission VARCHAR(20) NOT NULL DEFAULT 'viewer',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    # Indexes for collection_share
    op.execute("""CREATE INDEX IF NOT EXISTS ix_collection_share_id ON collection_share(id)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_collection_share_uuid ON collection_share(uuid)""")
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_collection_share_collection_id """
        """ON collection_share(collection_id)"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_collection_share_shared_by_id """
        """ON collection_share(shared_by_id)"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_collection_share_target_user_id """
        """ON collection_share(target_user_id)"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_collection_share_target_group_id """
        """ON collection_share(target_group_id)"""
    )

    # Check constraint: exactly one target must be set
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint
                           WHERE conname = '_collection_share_target_check') THEN
                ALTER TABLE collection_share ADD CONSTRAINT _collection_share_target_check
                    CHECK (
                        (target_user_id IS NOT NULL AND target_group_id IS NULL) OR
                        (target_user_id IS NULL AND target_group_id IS NOT NULL)
                    );
            END IF;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # Partial unique indexes: one share per (collection, target_user) and (collection, target_group)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS _collection_share_user_uc
            ON collection_share(collection_id, target_user_id)
            WHERE target_user_id IS NOT NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS _collection_share_group_uc
            ON collection_share(collection_id, target_group_id)
            WHERE target_group_id IS NOT NULL;
    """)


def downgrade() -> None:
    """Drop collection sharing and user group tables in reverse order."""
    op.execute("""DROP TABLE IF EXISTS collection_share CASCADE""")
    op.execute("""DROP TABLE IF EXISTS user_group_member CASCADE""")
    op.execute("""DROP TABLE IF EXISTS user_group CASCADE""")
