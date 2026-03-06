"""Add CHECK constraints and missing indexes for groups/sharing tables.

Revision ID: v211_add_sharing_constraints_and_indexes
Revises: v210_add_groups_and_sharing
Create Date: 2026-03-02
"""

from alembic import op

revision = "v211_add_sharing_constraints_and_indexes"
down_revision = "v210_add_groups_and_sharing"
branch_labels = None
depends_on = None


def upgrade():
    """Add CHECK constraints on enum-like columns and missing FK indexes."""

    # CHECK constraint on user_group_member.role
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '_user_group_member_role_check'
            ) THEN
                ALTER TABLE user_group_member
                    ADD CONSTRAINT _user_group_member_role_check
                    CHECK (role IN ('owner', 'admin', 'member'));
            END IF;
        END $$;
    """
    )

    # CHECK constraint on collection_share.target_type
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '_collection_share_target_type_check'
            ) THEN
                ALTER TABLE collection_share
                    ADD CONSTRAINT _collection_share_target_type_check
                    CHECK (target_type IN ('user', 'group'));
            END IF;
        END $$;
    """
    )

    # Migrate any legacy "owner" permission values before adding CHECK constraint
    op.execute(
        """
        UPDATE collection_share SET permission = 'editor' WHERE permission = 'owner';
    """
    )

    # CHECK constraint on collection_share.permission
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '_collection_share_permission_check'
            ) THEN
                ALTER TABLE collection_share
                    ADD CONSTRAINT _collection_share_permission_check
                    CHECK (permission IN ('viewer', 'editor'));
            END IF;
        END $$;
    """
    )

    # Index on user_group.owner_id for FK cascade lookups
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_group_owner_id
            ON user_group(owner_id);
    """
    )

    # Index on user_group_member.user_id for "find all groups a user belongs to"
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_group_member_user_id
            ON user_group_member(user_id);
    """
    )

    # Index on user_group_member.group_id for membership lookups and joins
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_group_member_group_id
            ON user_group_member(group_id);
    """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_user_group_member_group_id")
    op.execute("DROP INDEX IF EXISTS ix_user_group_member_user_id")
    op.execute("DROP INDEX IF EXISTS ix_user_group_owner_id")
    op.execute(
        "ALTER TABLE collection_share DROP CONSTRAINT IF EXISTS _collection_share_permission_check"
    )
    op.execute(
        "ALTER TABLE collection_share DROP CONSTRAINT IF EXISTS _collection_share_target_type_check"
    )
    op.execute(
        "ALTER TABLE user_group_member DROP CONSTRAINT IF EXISTS _user_group_member_role_check"
    )
