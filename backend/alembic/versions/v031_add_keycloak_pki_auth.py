"""v0.3.1 - Add Keycloak and PKI authentication columns

Revision ID: v031_add_keycloak_pki_auth
Revises: v030_add_ldap_auth
Create Date: 2025-01-26

Adds columns for Keycloak OIDC and PKI/X.509 certificate authentication support:
- keycloak_id: Stores Keycloak user subject ID
- pki_subject_dn: Stores X.509 certificate Distinguished Name
- Expands auth_type to support 'keycloak' and 'pki' values

New columns:
    - keycloak_id VARCHAR(255) UNIQUE NULL
    - pki_subject_dn VARCHAR(512) UNIQUE NULL

Indexes:
    - idx_user_keycloak_id ON "user" (keycloak_id)
    - idx_user_pki_subject_dn ON "user" (pki_subject_dn)
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "v031_add_keycloak_pki_auth"
down_revision = "v030_add_ldap_auth"
branch_labels = None
depends_on = None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    result = conn.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
            "WHERE table_name=:table AND column_name=:column)"
        ),
        {"table": table_name, "column": column_name},
    )
    return result.scalar()


def _index_exists(conn, table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table."""
    result = conn.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM pg_indexes WHERE tablename=:table AND indexname=:index)"
        ),
        {"table": table_name, "index": index_name},
    )
    return result.scalar()


def _constraint_exists(conn, table_name: str, constraint_name: str) -> bool:
    """Check if a constraint exists on a table."""
    result = conn.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_name=:table AND constraint_name=:constraint)"
        ),
        {"table": table_name, "constraint": constraint_name},
    )
    return result.scalar()


def upgrade():
    """Add Keycloak and PKI authentication columns to user table."""
    conn = op.get_bind()

    # Add keycloak_id column if it doesn't exist
    if not _column_exists(conn, "user", "keycloak_id"):
        op.add_column("user", sa.Column("keycloak_id", sa.String(255), nullable=True))

    # Add pki_subject_dn column if it doesn't exist
    if not _column_exists(conn, "user", "pki_subject_dn"):
        op.add_column("user", sa.Column("pki_subject_dn", sa.String(512), nullable=True))

    # Create indexes if they don't exist
    if not _index_exists(conn, "user", "idx_user_keycloak_id"):
        op.create_index("idx_user_keycloak_id", "user", ["keycloak_id"])

    if not _index_exists(conn, "user", "idx_user_pki_subject_dn"):
        op.create_index("idx_user_pki_subject_dn", "user", ["pki_subject_dn"])

    # Create unique constraints if they don't exist
    if not _constraint_exists(conn, "user", "uq_user_keycloak_id"):
        op.create_unique_constraint("uq_user_keycloak_id", "user", ["keycloak_id"])

    if not _constraint_exists(conn, "user", "uq_user_pki_subject_dn"):
        op.create_unique_constraint("uq_user_pki_subject_dn", "user", ["pki_subject_dn"])

    # Expand auth_type column size to accommodate longer auth types
    # PostgreSQL VARCHAR(10) -> VARCHAR(20)
    op.alter_column(
        "user",
        "auth_type",
        existing_type=sa.String(10),
        type_=sa.String(20),
        existing_nullable=False,
    )


def downgrade():
    """Remove Keycloak and PKI authentication columns from user table."""
    conn = op.get_bind()

    # Drop unique constraints
    if _constraint_exists(conn, "user", "uq_user_pki_subject_dn"):
        op.drop_constraint("uq_user_pki_subject_dn", "user", type_="unique")

    if _constraint_exists(conn, "user", "uq_user_keycloak_id"):
        op.drop_constraint("uq_user_keycloak_id", "user", type_="unique")

    # Drop indexes
    if _index_exists(conn, "user", "idx_user_pki_subject_dn"):
        op.drop_index("idx_user_pki_subject_dn", table_name="user")

    if _index_exists(conn, "user", "idx_user_keycloak_id"):
        op.drop_index("idx_user_keycloak_id", table_name="user")

    # Drop columns
    if _column_exists(conn, "user", "pki_subject_dn"):
        op.drop_column("user", "pki_subject_dn")

    if _column_exists(conn, "user", "keycloak_id"):
        op.drop_column("user", "keycloak_id")

    # Restore auth_type column size
    op.alter_column(
        "user",
        "auth_type",
        existing_type=sa.String(20),
        type_=sa.String(10),
        existing_nullable=False,
    )
