"""Schema reconciliation migration.

Reconciles all discrepancies between init_db.sql (fresh installs) and the
migration chain (upgraded databases). This migration is fully idempotent and
safe to run against any database state.

Revision ID: v200_schema_reconciliation
Revises: v190_add_collection_default_prompt
Create Date: 2026-02-28
"""

from alembic import op

revision = "v200_schema_reconciliation"
down_revision = "v190_add_collection_default_prompt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Reconcile schema discrepancies across all database states."""

    # =========================================================================
    # CRITICAL: PKI column name reconciliation
    # init_db.sql uses pki_cert_valid_from/until, ORM uses pki_not_before/after
    # =========================================================================
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='user' AND column_name='pki_cert_valid_from')
            AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='user' AND column_name='pki_not_before')
            THEN
                ALTER TABLE "user" RENAME COLUMN pki_cert_valid_from TO pki_not_before;
            END IF;
        END $$;
    """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns
                       WHERE table_name='user' AND column_name='pki_cert_valid_until')
            AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='user' AND column_name='pki_not_after')
            THEN
                ALTER TABLE "user" RENAME COLUMN pki_cert_valid_until TO pki_not_after;
            END IF;
        END $$;
    """
    )

    # Drop orphan column pki_cert_fingerprint (only exists in init_db.sql)
    op.execute("""ALTER TABLE "user" DROP COLUMN IF EXISTS pki_cert_fingerprint""")

    # =========================================================================
    # CRITICAL: Add missing refresh_token.jti column
    # Exists in ORM and init_db.sql but no migration creates it
    # =========================================================================
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='refresh_token' AND column_name='jti')
            THEN
                ALTER TABLE refresh_token ADD COLUMN jti VARCHAR(36);
                UPDATE refresh_token SET jti = gen_random_uuid()::text WHERE jti IS NULL;
                ALTER TABLE refresh_token ALTER COLUMN jti SET NOT NULL;
            END IF;
        END $$;
    """
    )

    # =========================================================================
    # HIGH: Add missing refresh_token columns (user_agent, ip_address)
    # =========================================================================
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='refresh_token' AND column_name='user_agent')
            THEN
                ALTER TABLE refresh_token ADD COLUMN user_agent VARCHAR(512) NULL;
            END IF;
        END $$;
    """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='refresh_token' AND column_name='ip_address')
            THEN
                ALTER TABLE refresh_token ADD COLUMN ip_address VARCHAR(45) NULL;
            END IF;
        END $$;
    """
    )

    # Ensure token_hash is VARCHAR(128) for SHA-512 support (safe no-op if already 128)
    op.execute(
        """
        ALTER TABLE refresh_token ALTER COLUMN token_hash TYPE VARCHAR(128);
    """
    )

    # =========================================================================
    # HIGH: Add missing user_mfa columns (uuid, last_verified_at)
    # =========================================================================
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='user_mfa' AND column_name='uuid')
            THEN
                ALTER TABLE user_mfa ADD COLUMN uuid UUID UNIQUE NOT NULL DEFAULT gen_random_uuid();
            END IF;
        END $$;
    """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='user_mfa' AND column_name='last_verified_at')
            THEN
                ALTER TABLE user_mfa ADD COLUMN last_verified_at TIMESTAMP WITH TIME ZONE NULL;
            END IF;
        END $$;
    """
    )

    # =========================================================================
    # HIGH: Fix user_mfa.totp_secret nullability and backup_codes defaults
    # Migration v040 creates totp_secret as nullable, but ORM says NOT NULL
    # =========================================================================
    op.execute(
        """
        UPDATE user_mfa SET totp_secret = '' WHERE totp_secret IS NULL;
    """
    )
    op.execute(
        """
        ALTER TABLE user_mfa ALTER COLUMN totp_secret SET NOT NULL;
    """
    )
    op.execute(
        """
        UPDATE user_mfa SET backup_codes = '[]'::jsonb WHERE backup_codes IS NULL;
    """
    )
    op.execute(
        """
        ALTER TABLE user_mfa ALTER COLUMN backup_codes SET NOT NULL;
    """
    )
    op.execute(
        """
        ALTER TABLE user_mfa ALTER COLUMN backup_codes SET DEFAULT '[]'::jsonb;
    """
    )

    # =========================================================================
    # MEDIUM: Fix user.role and user.full_name constraints
    # =========================================================================
    # Ensure role is NOT NULL with default
    op.execute(
        """
        UPDATE "user" SET role = 'user' WHERE role IS NULL;
    """
    )
    op.execute(
        """
        ALTER TABLE "user" ALTER COLUMN role SET NOT NULL;
    """
    )
    op.execute(
        """
        ALTER TABLE "user" ALTER COLUMN role SET DEFAULT 'user';
    """
    )

    # Allow NULL for full_name (external auth users may not have one)
    op.execute(
        """
        ALTER TABLE "user" ALTER COLUMN full_name DROP NOT NULL;
    """
    )

    # =========================================================================
    # MEDIUM: Add CHECK constraints
    # =========================================================================
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_role_check') THEN
                ALTER TABLE "user" ADD CONSTRAINT users_role_check
                    CHECK (role IN ('user', 'admin', 'super_admin'));
            END IF;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """
    )
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_auth_type_check') THEN
                ALTER TABLE "user" ADD CONSTRAINT users_auth_type_check
                    CHECK (auth_type IN ('local', 'ldap', 'keycloak', 'pki'));
            END IF;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """
    )

    # =========================================================================
    # MEDIUM: Add missing indexes
    # =========================================================================
    # User compliance indexes (created by v040 for migrated DBs, missing from init_db.sql)
    op.execute(
        """CREATE INDEX IF NOT EXISTS idx_user_password_changed_at ON "user"(password_changed_at)"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS idx_user_account_expires_at ON "user"(account_expires_at)"""
    )
    op.execute("""CREATE INDEX IF NOT EXISTS idx_user_last_login_at ON "user"(last_login_at)""")
    op.execute(
        """CREATE INDEX IF NOT EXISTS idx_user_must_change_password ON "user"(must_change_password)"""
    )

    # Refresh token indexes
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'idx_refresh_token_active') THEN
                CREATE INDEX idx_refresh_token_active ON refresh_token(user_id, expires_at) WHERE revoked_at IS NULL;
            END IF;
        END $$;
    """
    )
    op.execute("""CREATE INDEX IF NOT EXISTS idx_refresh_token_jti ON refresh_token(jti)""")
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_refresh_token_jti') THEN
                ALTER TABLE refresh_token ADD CONSTRAINT uq_refresh_token_jti UNIQUE (jti);
            END IF;
        EXCEPTION WHEN duplicate_table THEN NULL;
                  WHEN duplicate_object THEN NULL;
        END $$;
    """
    )
    op.execute("""CREATE INDEX IF NOT EXISTS idx_refresh_token_hash ON refresh_token(token_hash)""")

    # user_mfa indexes
    op.execute("""CREATE INDEX IF NOT EXISTS idx_user_mfa_uuid ON user_mfa(uuid)""")


def downgrade() -> None:
    """Reverse the schema reconciliation.

    Note: Column renames and drops are not reversed as they represent
    corrections to the canonical schema.
    """
    # Drop added indexes
    op.execute("""DROP INDEX IF EXISTS idx_user_mfa_uuid""")
    op.execute("""DROP INDEX IF EXISTS idx_refresh_token_hash""")
    op.execute("""DROP INDEX IF EXISTS idx_refresh_token_jti""")
    op.execute("""DROP INDEX IF EXISTS idx_refresh_token_active""")
    op.execute("""DROP INDEX IF EXISTS idx_user_must_change_password""")
    op.execute("""DROP INDEX IF EXISTS idx_user_last_login_at""")
    op.execute("""DROP INDEX IF EXISTS idx_user_account_expires_at""")
    op.execute("""DROP INDEX IF EXISTS idx_user_password_changed_at""")

    # Drop added constraints
    op.execute("""ALTER TABLE "user" DROP CONSTRAINT IF EXISTS users_auth_type_check""")
    op.execute("""ALTER TABLE "user" DROP CONSTRAINT IF EXISTS users_role_check""")
    op.execute("""ALTER TABLE refresh_token DROP CONSTRAINT IF EXISTS uq_refresh_token_jti""")

    # Note: We don't reverse column additions or renames in downgrade
    # as those represent corrections to match the ORM definitions.
