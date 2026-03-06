"""v0.8.0 - Add authentication configuration tables

Revision ID: v080_add_auth_config
Revises: v070_pki_security
Create Date: 2026-02-05

Add tables for super admin authentication configuration UI:
    - auth_config: Stores authentication settings (LDAP, Keycloak, PKI, etc.)
    - auth_config_audit: Audit log for configuration changes
    - user_certificate_preferences: User preferences for PKI certificate display

These tables support the super admin UI for managing authentication settings
via the web interface instead of environment variables.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "v080_add_auth_config"
down_revision = "v070_pki_security"
branch_labels = None
depends_on = None


def upgrade():
    """Add authentication configuration tables."""
    # Create auth_config table
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_config (
            id SERIAL PRIMARY KEY,
            uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
            config_key VARCHAR(100) UNIQUE NOT NULL,
            config_value TEXT NULL,
            is_sensitive BOOLEAN DEFAULT FALSE,
            category VARCHAR(50) NOT NULL,
            data_type VARCHAR(20) DEFAULT 'string',
            description TEXT NULL,
            requires_restart BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER REFERENCES "user"(id),
            updated_by INTEGER REFERENCES "user"(id)
        );
        """
    )

    # Create indexes for auth_config
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_auth_config_category ON auth_config(category);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_auth_config_key ON auth_config(config_key);
        """
    )

    # Create auth_config_audit table
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_config_audit (
            id SERIAL PRIMARY KEY,
            uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
            config_key VARCHAR(100) NOT NULL,
            old_value TEXT NULL,
            new_value TEXT NULL,
            changed_by INTEGER NOT NULL REFERENCES "user"(id),
            change_type VARCHAR(20) NOT NULL,
            ip_address VARCHAR(45) NULL,
            user_agent VARCHAR(512) NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # Create indexes for auth_config_audit
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_auth_config_audit_key ON auth_config_audit(config_key);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_auth_config_audit_created ON auth_config_audit(created_at);
        """
    )

    # Create user_certificate_preferences table
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_certificate_preferences (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            show_cert_badge BOOLEAN DEFAULT TRUE,
            show_cert_in_profile BOOLEAN DEFAULT TRUE,
            show_expiration_warnings BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id)
        );
        """
    )


def downgrade():
    """Remove authentication configuration tables."""
    op.execute("DROP TABLE IF EXISTS user_certificate_preferences")
    op.execute("DROP TABLE IF EXISTS auth_config_audit")
    op.execute("DROP TABLE IF EXISTS auth_config")
