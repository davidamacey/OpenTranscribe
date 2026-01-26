"""v0.4.0 - Add FedRAMP compliance tables and columns

Revision ID: v040_add_fedramp_compliance
Revises: v031_add_keycloak_pki_auth
Create Date: 2026-01-26

Adds tables and columns for FedRAMP compliance requirements:
- Password history tracking for password reuse prevention
- Multi-factor authentication (MFA/TOTP) support
- Refresh token management with revocation capability
- Enhanced user account lifecycle management

New tables:
    - password_history: Track previous password hashes for reuse prevention
    - user_mfa: Store TOTP secrets and backup codes for 2FA
    - refresh_token: Manage refresh tokens with revocation support

New columns on "user" table:
    - password_hash_version: Track hashing algorithm version (default: 'bcrypt')
    - password_changed_at: Timestamp of last password change
    - must_change_password: Flag to force password change on next login
    - last_login_at: Timestamp of last successful login
    - account_expires_at: Account expiration date for compliance
    - banner_acknowledged_at: DOD/FedRAMP banner acknowledgment timestamp
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision = "v040_add_fedramp_compliance"
down_revision = "v031_add_keycloak_pki_auth"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    """Check if a table exists in the database."""
    result = conn.execute(
        sa.text("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name=:table)"),
        {"table": table_name},
    )
    return result.scalar()


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


# =============================================================================
# Upgrade helper functions
# =============================================================================


def _create_password_history_table(conn) -> None:
    """Create the password_history table and its indexes.

    This table tracks previous password hashes to enforce password reuse
    prevention policies required for FedRAMP compliance.
    """
    if _table_exists(conn, "password_history"):
        return

    op.create_table(
        "password_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "uuid",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_password_history_uuid"),
    )

    # Index for UUID lookups
    op.create_index(
        "idx_password_history_uuid",
        "password_history",
        ["uuid"],
    )

    # Index for efficient password history lookups by user
    op.create_index(
        "idx_password_history_user_id",
        "password_history",
        ["user_id"],
    )

    # Index for efficient cleanup of old password history entries
    op.create_index(
        "idx_password_history_created_at",
        "password_history",
        ["created_at"],
    )


def _create_user_mfa_table(conn) -> None:
    """Create the user_mfa table and its index.

    This table stores TOTP secrets and backup codes for multi-factor
    authentication (MFA/2FA) support required for FedRAMP compliance.
    """
    if _table_exists(conn, "user_mfa"):
        return

    op.create_table(
        "user_mfa",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("totp_secret", sa.String(255), nullable=True),
        sa.Column(
            "totp_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("backup_codes", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_user_mfa_user_id"),
    )

    # Index for fast MFA lookups by user_id
    op.create_index(
        "idx_user_mfa_user_id",
        "user_mfa",
        ["user_id"],
    )


def _create_refresh_token_table(conn) -> None:
    """Create the refresh_token table and its indexes.

    This table manages refresh tokens with revocation support for
    secure session management required for FedRAMP compliance.
    """
    if _table_exists(conn, "refresh_token"):
        return

    op.create_table(
        "refresh_token",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_token_hash"),
    )

    # Index for fast token lookups by hash
    op.create_index(
        "idx_refresh_token_hash",
        "refresh_token",
        ["token_hash"],
    )

    # Index for efficient user token queries
    op.create_index(
        "idx_refresh_token_user_id",
        "refresh_token",
        ["user_id"],
    )

    # Index for efficient cleanup of expired tokens
    op.create_index(
        "idx_refresh_token_expires_at",
        "refresh_token",
        ["expires_at"],
    )

    # Partial index for active (non-revoked) tokens
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_refresh_token_active
        ON refresh_token(user_id, expires_at)
        WHERE revoked_at IS NULL
        """
    )


def _add_user_fedramp_columns(conn) -> None:
    """Add FedRAMP compliance columns to the user table.

    Adds columns for password tracking, account lifecycle management,
    and compliance banner acknowledgment.
    """
    # password_hash_version - Track hashing algorithm version
    if not _column_exists(conn, "user", "password_hash_version"):
        op.add_column(
            "user",
            sa.Column(
                "password_hash_version",
                sa.String(20),
                nullable=False,
                server_default="bcrypt",
            ),
        )

    # password_changed_at - Track when password was last changed
    if not _column_exists(conn, "user", "password_changed_at"):
        op.add_column(
            "user",
            sa.Column(
                "password_changed_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    # must_change_password - Force password change on next login
    if not _column_exists(conn, "user", "must_change_password"):
        op.add_column(
            "user",
            sa.Column(
                "must_change_password",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
        )

    # last_login_at - Track last successful login
    if not _column_exists(conn, "user", "last_login_at"):
        op.add_column(
            "user",
            sa.Column(
                "last_login_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    # account_expires_at - Account expiration for compliance
    if not _column_exists(conn, "user", "account_expires_at"):
        op.add_column(
            "user",
            sa.Column(
                "account_expires_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    # banner_acknowledged_at - DOD/FedRAMP banner acknowledgment
    if not _column_exists(conn, "user", "banner_acknowledged_at"):
        op.add_column(
            "user",
            sa.Column(
                "banner_acknowledged_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def _create_user_compliance_indexes(conn) -> None:
    """Create indexes on user compliance columns.

    These indexes optimize queries for password expiration, account
    expiration, inactive account detection, and password change enforcement.
    """
    # Index for password expiration queries
    if not _index_exists(conn, "user", "idx_user_password_changed_at"):
        op.create_index(
            "idx_user_password_changed_at",
            "user",
            ["password_changed_at"],
        )

    # Index for account expiration queries
    if not _index_exists(conn, "user", "idx_user_account_expires_at"):
        op.create_index(
            "idx_user_account_expires_at",
            "user",
            ["account_expires_at"],
        )

    # Index for last login queries (inactive account detection)
    if not _index_exists(conn, "user", "idx_user_last_login_at"):
        op.create_index(
            "idx_user_last_login_at",
            "user",
            ["last_login_at"],
        )

    # Index for users requiring password change
    if not _index_exists(conn, "user", "idx_user_must_change_password"):
        op.create_index(
            "idx_user_must_change_password",
            "user",
            ["must_change_password"],
        )


# =============================================================================
# Downgrade helper functions
# =============================================================================


def _drop_user_compliance_indexes(conn) -> None:
    """Drop indexes on user compliance columns."""
    if _index_exists(conn, "user", "idx_user_must_change_password"):
        op.drop_index("idx_user_must_change_password", table_name="user")

    if _index_exists(conn, "user", "idx_user_last_login_at"):
        op.drop_index("idx_user_last_login_at", table_name="user")

    if _index_exists(conn, "user", "idx_user_account_expires_at"):
        op.drop_index("idx_user_account_expires_at", table_name="user")

    if _index_exists(conn, "user", "idx_user_password_changed_at"):
        op.drop_index("idx_user_password_changed_at", table_name="user")


def _drop_user_fedramp_columns(conn) -> None:
    """Drop FedRAMP compliance columns from the user table."""
    if _column_exists(conn, "user", "banner_acknowledged_at"):
        op.drop_column("user", "banner_acknowledged_at")

    if _column_exists(conn, "user", "account_expires_at"):
        op.drop_column("user", "account_expires_at")

    if _column_exists(conn, "user", "last_login_at"):
        op.drop_column("user", "last_login_at")

    if _column_exists(conn, "user", "must_change_password"):
        op.drop_column("user", "must_change_password")

    if _column_exists(conn, "user", "password_changed_at"):
        op.drop_column("user", "password_changed_at")

    if _column_exists(conn, "user", "password_hash_version"):
        op.drop_column("user", "password_hash_version")


def _drop_refresh_token_table(conn) -> None:
    """Drop the refresh_token table and its indexes."""
    if not _table_exists(conn, "refresh_token"):
        return

    # Drop partial index first
    op.execute("DROP INDEX IF EXISTS idx_refresh_token_active")

    if _index_exists(conn, "refresh_token", "idx_refresh_token_expires_at"):
        op.drop_index("idx_refresh_token_expires_at", table_name="refresh_token")

    if _index_exists(conn, "refresh_token", "idx_refresh_token_user_id"):
        op.drop_index("idx_refresh_token_user_id", table_name="refresh_token")

    if _index_exists(conn, "refresh_token", "idx_refresh_token_hash"):
        op.drop_index("idx_refresh_token_hash", table_name="refresh_token")

    op.drop_table("refresh_token")


def _drop_user_mfa_table(conn) -> None:
    """Drop the user_mfa table and its index."""
    if not _table_exists(conn, "user_mfa"):
        return

    if _index_exists(conn, "user_mfa", "idx_user_mfa_user_id"):
        op.drop_index("idx_user_mfa_user_id", table_name="user_mfa")

    op.drop_table("user_mfa")


def _drop_password_history_table(conn) -> None:
    """Drop the password_history table and its indexes."""
    if not _table_exists(conn, "password_history"):
        return

    if _index_exists(conn, "password_history", "idx_password_history_created_at"):
        op.drop_index("idx_password_history_created_at", table_name="password_history")

    if _index_exists(conn, "password_history", "idx_password_history_user_id"):
        op.drop_index("idx_password_history_user_id", table_name="password_history")

    if _index_exists(conn, "password_history", "idx_password_history_uuid"):
        op.drop_index("idx_password_history_uuid", table_name="password_history")

    op.drop_table("password_history")


# =============================================================================
# Main migration functions
# =============================================================================


def upgrade():
    """Add FedRAMP compliance tables and columns."""
    conn = op.get_bind()

    _create_password_history_table(conn)
    _create_user_mfa_table(conn)
    _create_refresh_token_table(conn)
    _add_user_fedramp_columns(conn)
    _create_user_compliance_indexes(conn)


def downgrade():
    """Remove FedRAMP compliance tables and columns."""
    conn = op.get_bind()

    _drop_user_compliance_indexes(conn)
    _drop_user_fedramp_columns(conn)
    _drop_refresh_token_table(conn)
    _drop_user_mfa_table(conn)
    _drop_password_history_table(conn)
