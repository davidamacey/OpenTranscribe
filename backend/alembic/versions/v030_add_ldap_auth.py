"""v0.3.0 - Add LDAP authentication columns

Revision ID: v030_add_ldap_auth
Revises: v020_add_system_settings
Create Date: 2025-01-12

Adds columns for LDAP/Active Directory authentication support:
- auth_type: Distinguishes between local and LDAP users
- ldap_uid: Stores sAMAccountName from Active Directory

New columns:
    - auth_type VARCHAR(10) DEFAULT 'local' NOT NULL
    - ldap_uid VARCHAR(255) UNIQUE NULL

Indexes:
    - idx_user_ldap_uid ON "user" (ldap_uid)
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "v030_add_ldap_auth"
down_revision = "v020_add_system_settings"
branch_labels = None
depends_on = None


def upgrade():
    """Add LDAP authentication columns to user table."""
    conn = op.get_bind()

    result = conn.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
            "WHERE table_name='user' AND column_name='auth_type')"
        )
    )
    auth_type_exists = result.scalar()

    if not auth_type_exists:
        op.add_column(
            "user", sa.Column("auth_type", sa.String(10), nullable=False, server_default="local")
        )

    result = conn.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
            "WHERE table_name='user' AND column_name='ldap_uid')"
        )
    )
    ldap_uid_exists = result.scalar()

    if not ldap_uid_exists:
        op.add_column("user", sa.Column("ldap_uid", sa.String(255), nullable=True))

    result = conn.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM pg_indexes "
            "WHERE tablename='user' AND indexname='idx_user_ldap_uid')"
        )
    )
    index_exists = result.scalar()

    if not index_exists:
        op.create_index("idx_user_ldap_uid", "user", ["ldap_uid"])

    result = conn.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name='user' AND constraint_name='uq_user_ldap_uid')"
        )
    )
    constraint_exists = result.scalar()

    if not constraint_exists and not ldap_uid_exists:
        op.create_unique_constraint("uq_user_ldap_uid", "user", ["ldap_uid"])


def downgrade():
    """Remove LDAP authentication columns from user table."""
    conn = op.get_bind()

    result = conn.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name='user' AND constraint_name='uq_user_ldap_uid')"
        )
    )
    constraint_exists = result.scalar()

    if constraint_exists:
        op.drop_constraint("uq_user_ldap_uid", "user", type_="unique")

    result = conn.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM pg_indexes "
            "WHERE tablename='user' AND indexname='idx_user_ldap_uid')"
        )
    )
    index_exists = result.scalar()

    if index_exists:
        op.drop_index("idx_user_ldap_uid", table_name="user")

    result = conn.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
            "WHERE table_name='user' AND column_name='ldap_uid')"
        )
    )
    ldap_uid_exists = result.scalar()

    if ldap_uid_exists:
        op.drop_column("user", "ldap_uid")

    result = conn.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
            "WHERE table_name='user' AND column_name='auth_type')"
        )
    )
    auth_type_exists = result.scalar()

    if auth_type_exists:
        op.drop_column("user", "auth_type")
